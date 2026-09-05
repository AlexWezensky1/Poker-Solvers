"""Win / tie / equity calculation for Noah's Ark.

Runouts are enumerated exactly whenever that is cheap enough (everything from
the flop onward, typically) and sampled with Monte Carlo otherwise.
"""

import random
from dataclasses import dataclass, field
from itertools import combinations
from math import comb, sqrt
from time import perf_counter

from .cards import FULL_DECK, cards_str, check_no_duplicates
from .evaluator import BUCKET_NAMES, CARD_KEY, bucket, describe, score_accumulator

MAX_PLAYERS = 8

#: Two community cards on each of the three streets.
STREETS = (2, 2, 2)
BOARD_SIZE = sum(STREETS)
DEFAULT_TRIALS = 100_000

#: Enumerate exactly while runouts x players stays under this many evaluations.
DEFAULT_EXACT_BUDGET = 1_500_000

#: How much of a time budget full enumeration may spend before it is given up
#: on. What is left goes to sampling. A part-walked enumeration is no answer at
#: all -- runouts come out in order, so the half that was reached is not a fair
#: sample of the whole -- so the work is thrown away rather than reported.
EXACT_WALK_SHARE = 0.6


def _until(draws, deadline, check=2048):
    """Yield runouts until the clock passes ``deadline``, then stop.

    The clock is read every ``check`` runouts, often enough to land close to
    the budget and rarely enough not to show up in the timing.
    """
    if deadline is None:
        yield from draws
        return
    for i, draw in enumerate(draws):
        if not i & (check - 1) and i and perf_counter() >= deadline:
            return
        yield draw


#: Six community cards make C(48,6) runouts before the first street -- twelve
#: million, over half a minute of walking. Asking for the walk outright still
#: has to come back, so past this many evaluations it samples instead and the
#: report says which it did.
EXACT_CEILING = 5_000_000


@dataclass
class HandEquity:
    index: int
    cards: tuple
    wins: int
    ties: int
    equity: float
    trials: int
    #: Half-width of the 95% interval on `equity_pct`, in points. Zero when the
    #: runouts were enumerated: there is nothing left to be uncertain about.
    margin: float = 0.0
    best_hand: str = ""
    #: How many runouts finished in each of BUCKET_NAMES, best first.
    made: tuple = ()

    @property
    def label(self):
        return cards_str(self.cards)

    @property
    def made_pct(self):
        """How often the hand ends up in each category, best first.

        Counted over every runout, so it says what the hand becomes rather than
        what it beats -- a royal flush and a busted draw are both in here. The
        row always sums to 100%: every runout finishes as something.
        """
        if not self.trials:
            return [(name, 0.0) for name in BUCKET_NAMES]
        return [(name, 100.0 * made / self.trials)
                for name, made in zip(BUCKET_NAMES, self.made)]

    @property
    def win_pct(self):
        return 100.0 * self.wins / self.trials if self.trials else 0.0

    @property
    def tie_pct(self):
        return 100.0 * self.ties / self.trials if self.trials else 0.0

    @property
    def equity_pct(self):
        return 100.0 * self.equity / self.trials if self.trials else 0.0


@dataclass
class EquityReport:
    hands: list = field(default_factory=list)
    board: tuple = ()
    mode: str = "exact"
    trials: int = 0

    @property
    def exact(self):
        return self.mode == "exact"


def _validate(hands, board, dead):
    if len(hands) < 2:
        raise ValueError("need at least 2 hands to compare")
    if len(hands) > MAX_PLAYERS:
        raise ValueError("at most %d hands are supported" % MAX_PLAYERS)
    for i, hand in enumerate(hands):
        if len(hand) != 2:
            raise ValueError("hand %d has %d cards, expected 2" % (i + 1, len(hand)))
    if len(board) > BOARD_SIZE:
        raise ValueError("the board holds at most %d cards, got %d"
                         % (BOARD_SIZE, len(board)))
    groups = [("hand %d" % (i + 1), h) for i, h in enumerate(hands)]
    check_no_duplicates(groups + [("the board", board),
                                  ("the folded hands", dead)])


def _tally(hands, board, draws):
    """Score every runout in ``draws`` and accumulate wins, ties and equity."""
    n = len(hands)
    seats = range(n)
    hole_accs = [CARD_KEY[a] + CARD_KEY[b] for a, b in hands]
    board_acc = sum(CARD_KEY[c] for c in board)

    wins = [0] * n
    ties = [0] * n
    equity = [0.0] * n
    equity2 = [0.0] * n   # sum of squared shares, for the standard error
    made = [[0] * len(BUCKET_NAMES) for _ in seats]
    trials = 0
    last_scores = None

    for draw in draws:
        acc = board_acc
        for card in draw:
            acc += CARD_KEY[card]
        runout = board + tuple(draw)

        best = -1
        winners = []
        scores = []
        for i in seats:
            value = score_accumulator(hole_accs[i] + acc, hands[i], runout)
            scores.append(value)
            made[i][bucket(value)] += 1
            if value > best:
                best = value
                winners = [i]
            elif value == best:
                winners.append(i)

        trials += 1
        last_scores = scores
        if len(winners) == 1:
            seat = winners[0]
            wins[seat] += 1
            equity[seat] += 1.0
            equity2[seat] += 1.0
        else:
            share = 1.0 / len(winners)
            for seat in winners:
                ties[seat] += 1
                equity[seat] += share
                equity2[seat] += share * share

    return wins, ties, equity, made, trials, last_scores, equity2


def equity(hands, board=(), dead=(), trials=DEFAULT_TRIALS, seed=None,
           mode="auto", exact_budget=DEFAULT_EXACT_BUDGET, seconds=None):
    """Compute equity for two or more Hold'em hands.

    ``hands`` is a sequence of two-card sequences and ``board`` holds 0-5
    community cards, all as card ints from :mod:`noahsark.cards`.

    ``dead`` holds cards that are out of the deck without belonging to anyone
    still in the pot -- a folded hand's. They are not scored and take no share,
    but nothing unknown can be dealt them either, which is the point of naming
    them.

    ``mode`` is ``"auto"`` (enumerate when affordable, otherwise sample),
    ``"exact"`` to force full enumeration, or ``"monte-carlo"`` to force
    sampling.
   
``seconds`` caps how long the answer may take. Enumeration gets the first
    part of it and is given up on if it will not finish, leaving the rest to
    sampling, so the wait is bounded either way and ``trials`` becomes a
    ceiling rather than a target.
    """
    hands = [tuple(h) for h in hands]
    board = tuple(board)
    dead = tuple(dead)
    _validate(hands, board, dead)

    gone = set(board) | set(dead)
    for hand in hands:
        gone.update(hand)
    deck = [c for c in FULL_DECK if c not in gone]
    needed = BOARD_SIZE - len(board)

    runouts = comb(len(deck), needed)
    work = runouts * len(hands)
    if mode == "auto":
        mode = "exact" if work <= exact_budget else "monte-carlo"
    elif mode == "exact" and work > EXACT_CEILING:
        # Too wide to walk while somebody waits; say so by answering as
        # monte-carlo rather than taking the minute it would need.
        mode = "monte-carlo"
    if mode not in ("exact", "monte-carlo"):
        raise ValueError("unknown mode %r" % mode)

    budget_ends = perf_counter() + seconds if seconds else None
    pots2 = None

    if mode == "exact":
        # Enumeration gets part of the budget only, so giving up on it still
        # leaves clock enough to sample an answer instead of returning none.
        walk_ends = perf_counter() + seconds * EXACT_WALK_SHARE if seconds else None
        wins, ties, pots, made, total, last_scores, pots2 = _tally(
            hands, board, _until(combinations(deck, needed), walk_ends))
        if total < runouts:
            mode = "monte-carlo"   # cut short, so none of that counts

    if mode == "monte-carlo":
        if trials < 1:
            raise ValueError("trials must be at least 1")
        rng = random.Random(seed)
        sample = rng.sample
        left = budget_ends - perf_counter() if budget_ends else None
        if left is not None and left <= 0:
            left = 0.01    # enumeration overran; still answer with something
        deadline = perf_counter() + left if left is not None else None
        wins, ties, pots, made, total, last_scores, pots2 = _tally(
            hands, board,
            _until((sample(deck, needed) for _ in range(trials)), deadline))
        if not total:
            raise ValueError("no runouts were dealt; the time budget was too short")

    # A sampled share is a mean, so it carries the usual spread: 1.96 standard
    # errors either side, in points of equity. An enumerated one carries none.
    margins = [0.0] * len(hands)
    if mode == "monte-carlo" and total > 1:
        for i in range(len(hands)):
            mean = pots[i] / total
            spread = max(pots2[i] / total - mean * mean, 0.0)
            margins[i] = 196.0 * sqrt(spread / total)

    report = EquityReport(board=board, mode=mode, trials=total)
    for i, hand in enumerate(hands):
        report.hands.append(HandEquity(
            index=i,
            cards=hand,
            wins=wins[i],
            ties=ties[i],
            equity=pots[i],
            trials=total,
            margin=margins[i],
            made=tuple(made[i]),
            # Only meaningful when the board is already complete, where the one
            # runout is the real one.
            best_hand=describe(last_scores[i]) if len(board) == BOARD_SIZE else "",
        ))
    return report


#: A Hold'em board is five community cards. This variant's board is a different
#: length, so the comparison against Hold'em stops there.
HOLDEM_BOARD = 5


def holdem_made(hands, board=(), dead=(), trials=DEFAULT_TRIALS, seed=None,
                mode="auto", exact_budget=DEFAULT_EXACT_BUDGET,
                seconds=None):
    """How often each hand ends in each category under ordinary Hold'em rules.

    Same hole cards and the same board so far, but the board stops at five
    community cards -- which is the board this deal would have had if it were
    Hold'em. Returns one list of fractions per hand, in :data:`BUCKET_NAMES`
    order, so it reads directly against the variant's own numbers.

    Cards past the fifth are simply not dealt here rather than being held out
    of the deck. It makes no difference either way: a board with five or more
    cards leaves nothing to enumerate, and a board with fewer has no cards
    past the fifth to argue about.
    """
    hands = [tuple(h) for h in hands]
    board = tuple(board)[:HOLDEM_BOARD]

    gone = set(board) | set(dead)
    for hand in hands:
        gone.update(hand)
    deck = [c for c in FULL_DECK if c not in gone]
    needed = HOLDEM_BOARD - len(board)
    if needed < 0 or needed > len(deck):
        return [[0.0] * len(BUCKET_NAMES) for _ in hands]

    work = comb(len(deck), needed) * max(len(hands), 1)
    if mode == "auto":
        mode = "exact" if work <= exact_budget else "monte-carlo"
    elif mode == "exact" and work > EXACT_CEILING:
        mode = "monte-carlo"

    deadline = perf_counter() + seconds if seconds else None
    if mode == "exact":
        draws = _until(combinations(deck, needed), deadline)
    else:
        rng = random.Random(seed)
        draws = _until((rng.sample(deck, needed) for _ in range(max(int(trials), 1))),
                       deadline)

    seats = range(len(hands))
    hole_accs = [CARD_KEY[a] + CARD_KEY[b] for a, b in hands]
    board_acc = sum(CARD_KEY[c] for c in board)
    made = [[0] * len(BUCKET_NAMES) for _ in seats]
    total = 0

    for draw in draws:
        acc = board_acc
        for card in draw:
            acc += CARD_KEY[card]
        runout = board + tuple(draw)
        for i in seats:
            value = score_accumulator(hole_accs[i] + acc, hands[i], runout)
            made[i][bucket(value)] += 1
        total += 1

    if not total:
        return [[0.0] * len(BUCKET_NAMES) for _ in hands]
    return [[count / total for count in row] for row in made]
