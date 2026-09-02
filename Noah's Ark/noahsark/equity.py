"""Win / tie / equity calculation for Noah's Ark.

Runouts are enumerated exactly whenever that is cheap enough (everything from
the flop onward, typically) and sampled with Monte Carlo otherwise.
"""

import random
from dataclasses import dataclass, field
from itertools import combinations
from math import comb

from .cards import FULL_DECK, cards_str, check_no_duplicates
from .evaluator import BUCKET_NAMES, CARD_KEY, bucket, describe, score_accumulator

MAX_PLAYERS = 8

#: Two community cards on each of the three streets.
STREETS = (2, 2, 2)
BOARD_SIZE = sum(STREETS)
DEFAULT_TRIALS = 100_000

#: Enumerate exactly while runouts x players stays under this many evaluations.
DEFAULT_EXACT_BUDGET = 1_500_000

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


def _validate(hands, board):
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
    check_no_duplicates(groups + [("the board", board)])


def _tally(hands, board, draws):
    """Score every runout in ``draws`` and accumulate wins, ties and equity."""
    n = len(hands)
    seats = range(n)
    hole_accs = [CARD_KEY[a] + CARD_KEY[b] for a, b in hands]
    board_acc = sum(CARD_KEY[c] for c in board)

    wins = [0] * n
    ties = [0] * n
    equity = [0.0] * n
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
        else:
            share = 1.0 / len(winners)
            for seat in winners:
                ties[seat] += 1
                equity[seat] += share

    return wins, ties, equity, made, trials, last_scores


def equity(hands, board=(), trials=DEFAULT_TRIALS, seed=None,
           mode="auto", exact_budget=DEFAULT_EXACT_BUDGET):
    """Compute equity for two or more Hold'em hands.

    ``hands`` is a sequence of two-card sequences and ``board`` holds 0-5
    community cards, all as card ints from :mod:`noahsark.cards`.

    ``mode`` is ``"auto"`` (enumerate when affordable, otherwise sample),
    ``"exact"`` to force full enumeration, or ``"monte-carlo"`` to force
    sampling.
    """
    hands = [tuple(h) for h in hands]
    board = tuple(board)
    _validate(hands, board)

    dead = set(board)
    for hand in hands:
        dead.update(hand)
    deck = [c for c in FULL_DECK if c not in dead]
    needed = BOARD_SIZE - len(board)

    runouts = comb(len(deck), needed)
    work = runouts * len(hands)
    if mode == "auto":
        mode = "exact" if work <= exact_budget else "monte-carlo"
    elif mode == "exact" and work > EXACT_CEILING:
        # Too wide to walk while somebody waits; say so by answering as
        # monte-carlo rather than taking the minute it would need.
        mode = "monte-carlo"
    if mode == "exact":
        draws = combinations(deck, needed)
    elif mode == "monte-carlo":
        if trials < 1:
            raise ValueError("trials must be at least 1")
        rng = random.Random(seed)
        sample = rng.sample
        draws = (sample(deck, needed) for _ in range(trials))
    else:
        raise ValueError("unknown mode %r" % mode)

    wins, ties, pots, made, total, last_scores = _tally(hands, board, draws)

    report = EquityReport(board=board, mode=mode, trials=total)
    for i, hand in enumerate(hands):
        report.hands.append(HandEquity(
            index=i,
            cards=hand,
            wins=wins[i],
            ties=ties[i],
            equity=pots[i],
            trials=total,
            made=tuple(made[i]),
            # Only meaningful when the board is already complete, where the one
            # runout is the real one.
            best_hand=describe(last_scores[i]) if len(board) == BOARD_SIZE else "",
        ))
    return report
