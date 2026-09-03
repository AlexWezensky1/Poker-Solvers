"""Win / tie / equity calculation for Red River Hold'em.

Red River is Hold'em until the river, and then the river does not stop. The
dealer turns a card; if it is red another follows it, and another, until a black
one lands. So the board is five cards, or six, or seven, and the only thing
known in advance is that it ends in a club or a spade.

That is what makes this one different to solve. Every other board in this repo
has a length fixed before the first card is dealt, so a runout is a combination
and the whole set of them can be counted with :func:`math.comb`. Here a runout
is a *sequence*, and how long it runs depends on what it turned up -- so the
runouts have different probabilities as well as different lengths, and they are
counted by walking rather than by formula.

Walking all of them is rarely affordable. Each red card that lands opens the
whole deck again, so the number of runouts grows like a factorial while their
probability only halves: past a couple of cards there are millions of runouts
carrying a percent of the answer between them. :data:`EXACT_CEILING` is where
the walk gives up and samples instead, and the report says which it did.
"""

import random
from dataclasses import dataclass, field
from itertools import combinations
from math import comb

from .cards import FULL_DECK, cards_str, check_no_duplicates, is_red
from .evaluator import BUCKET_NAMES, CARD_KEY, bucket, describe, score_accumulator

MAX_PLAYERS = 8
DEFAULT_TRIALS = 100_000

#: Flop, turn, and then the river for as long as it keeps coming up red.
FLOP_AND_TURN = 4
MIN_BOARD = 5

#: The longest board the game can actually produce. Every red card has to be
#: dealt on the river, which means none may be spent anywhere else -- the flop,
#: the turn and every hole card black -- and then a black one to end it:
#: 3 + 1 + 26 + 1. There are always blacks left to finish on, with two players
#: or eight, so this is a real ceiling rather than a rail.
MAX_BOARD = 31

#: Walk every runout while there are fewer than this many of them.
DEFAULT_EXACT_BUDGET = 1_500_000

#: Asking for the walk outright still has to come back. The river is what makes
#: this bite: a board four cards down has millions of ways to finish.
EXACT_CEILING = 2_000_000


@dataclass
class HandEquity:
    index: int
    cards: tuple
    #: Shares of one whole pot, not counts -- runouts here are weighted by how
    #: likely they are, so a plain tally would misread the short ones.
    wins: float
    ties: float
    equity: float
    trials: float
    best_hand: str = ""
    made: tuple = ()

    @property
    def label(self):
        return cards_str(self.cards)

    @property
    def win_pct(self):
        return 100.0 * self.wins

    @property
    def tie_pct(self):
        return 100.0 * self.ties

    @property
    def equity_pct(self):
        return 100.0 * self.equity

    @property
    def made_pct(self):
        """How often the hand ends in each category, best first, summing to 100."""
        if not self.made:
            return [(name, 0.0) for name in BUCKET_NAMES]
        return [(name, 100.0 * made) for name, made in zip(BUCKET_NAMES, self.made)]


@dataclass
class EquityReport:
    hands: list = field(default_factory=list)
    board: tuple = ()
    mode: str = "exact"
    trials: float = 0

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
    if len(board) > MAX_BOARD:
        raise ValueError("the board holds at most %d cards, got %d"
                         % (MAX_BOARD, len(board)))
    # A black river card ends the hand, so one can only ever be the last card
    # on the board. Anything dealt after it could not have been dealt at all.
    for i in range(FLOP_AND_TURN, len(board) - 1):
        if not is_red(board[i]):
            raise ValueError(
                "%s is black, so the board ends there -- nothing follows it"
                % cards_str([board[i]]))
    groups = [("hand %d" % (i + 1), h) for i, h in enumerate(hands)]
    check_no_duplicates(groups + [("the board", board),
                                  ("the folded hands", dead)])


def is_complete(board):
    """Is the board finished? Five cards at least, ending on a black one."""
    return len(board) >= MIN_BOARD and not is_red(board[-1])


def _finishes(board, deck):
    """Every way the board can finish, as ``(cards to come, probability)``.

    The flop and turn are taken as a combination, since their order changes
    nothing. The river is walked one card at a time, because whether another
    follows depends on the one before it.
    """
    missing = max(0, FLOP_AND_TURN - len(board))

    def river(drawn, pool, weight):
        settled = tuple(board) + drawn
        if is_complete(settled):
            yield drawn, weight
            return
        if len(settled) >= MAX_BOARD or not pool:
            # Out of room. Vanishingly rare, and the weight goes with it, so
            # the shares still divide by the weight actually walked.
            return
        share = weight / len(pool)
        for i, card in enumerate(pool):
            yield from river(drawn + (card,), pool[:i] + pool[i + 1:], share)

    if missing:
        opening = comb(len(deck), missing)
        for combo in combinations(deck, missing):
            rest = [c for c in deck if c not in combo]
            yield from river(tuple(combo), rest, 1.0 / opening)
    else:
        yield from river((), list(deck), 1.0)


def _count_finishes(board, deck, cap):
    """Roughly how many runouts there are, stopping once it passes ``cap``.

    Counted rather than walked. Walking a million runouts to discover there are
    too many to walk costs as much as the answer would have, and the shape is
    simple enough to multiply out: the flop and turn are a combination, and each
    red card that lands opens what is left of the deck again.
    """
    missing = max(0, FLOP_AND_TURN - len(board))
    total = comb(len(deck), missing)
    left = len(deck) - missing
    reds = sum(1 for card in deck if is_red(card))
    blacks = left - reds

    # One black card ends it; every red before that multiplies the ways in.
    ways, running = total, 0.0
    for depth in range(min(reds, 40) + 1):
        running += ways * max(blacks, 0)
        if running > cap:
            return running
        ways *= max(reds - depth, 0)
        if not ways:
            break
    return running


def _sample(board, deck, rng):
    """Deal one runout: finish the flop and turn, then river until it is black."""
    pool = list(deck)
    rng.shuffle(pool)
    drawn = []
    while True:
        settled = tuple(board) + tuple(drawn)
        if is_complete(settled) or len(settled) >= MAX_BOARD or not pool:
            return tuple(drawn)
        drawn.append(pool.pop())


def _tally(hands, board, runouts):
    """Score every runout, each weighted by how likely it is."""
    n = len(hands)
    seats = range(n)
    hole_accs = [CARD_KEY[a] + CARD_KEY[b] for a, b in hands]
    board_acc = sum(CARD_KEY[c] for c in board)

    wins = [0.0] * n
    ties = [0.0] * n
    equity = [0.0] * n
    made = [[0.0] * len(BUCKET_NAMES) for _ in seats]
    weighed = 0.0
    walked = 0
    last_scores = None

    for draw, weight in runouts:
        acc = board_acc
        for card in draw:
            acc += CARD_KEY[card]
        runout = tuple(board) + tuple(draw)

        best = -1
        winners = []
        scores = []
        for i in seats:
            value = score_accumulator(hole_accs[i] + acc, hands[i], runout)
            scores.append(value)
            made[i][bucket(value)] += weight
            if value > best:
                best = value
                winners = [i]
            elif value == best:
                winners.append(i)

        weighed += weight
        walked += 1
        last_scores = scores
        if len(winners) == 1:
            wins[winners[0]] += weight
            equity[winners[0]] += weight
        else:
            share = weight / len(winners)
            for seat in winners:
                ties[seat] += weight
                equity[seat] += share

    # Runouts that ran out of room take their weight with them, so everything
    # is divided by the weight actually walked rather than by one.
    if weighed:
        for seat in seats:
            wins[seat] /= weighed
            ties[seat] /= weighed
            equity[seat] /= weighed
            made[seat] = [m / weighed for m in made[seat]]
    return wins, ties, equity, made, walked, last_scores


def equity(hands, board=(), dead=(), trials=DEFAULT_TRIALS, seed=None,
           mode="auto", exact_budget=DEFAULT_EXACT_BUDGET):
    """Compute equity for two or more Red River hands.

    ``hands`` is a sequence of two-card sequences and ``board`` holds the
    community cards dealt so far, as card ints from :mod:`redriver.cards`.

    ``dead`` holds cards that are out of the deck without belonging to anyone
    still in the pot -- a folded hand's. They are not scored and take no share,
    but nothing unknown can be dealt them either, which is the point of naming
    them.

    ``mode`` is ``"auto"`` (walk when affordable, otherwise sample), ``"exact"``
    to ask for the walk, or ``"monte-carlo"`` to force sampling. The walk is not
    always on offer -- see :data:`EXACT_CEILING` -- and the report says which
    was used.
    """
    hands = [tuple(h) for h in hands]
    board = tuple(board)
    dead = tuple(dead)
    _validate(hands, board, dead)

    gone = set(board) | set(dead)
    for hand in hands:
        gone.update(hand)
    deck = [c for c in FULL_DECK if c not in gone]

    if is_complete(board):
        walkable, runouts = True, 1
    else:
        cap = max(1, (exact_budget if mode != "exact" else EXACT_CEILING)
                  // max(len(hands), 1))
        runouts = _count_finishes(board, deck, cap)
        walkable = runouts <= cap

    if mode == "auto":
        mode = "exact" if walkable else "monte-carlo"
    elif mode == "exact" and not walkable:
        # The river has no length of its own, so a board still waiting on one
        # can have millions of ways to finish. Say so by answering as
        # monte-carlo rather than sitting there counting them.
        mode = "monte-carlo"

    if mode == "exact":
        draws = _finishes(board, deck)
    elif mode == "monte-carlo":
        if trials < 1:
            raise ValueError("trials must be at least 1")
        rng = random.Random(seed)
        draws = ((_sample(board, deck, rng), 1.0) for _ in range(trials))
    else:
        raise ValueError("unknown mode %r" % mode)

    wins, ties, pots, made, walked, last_scores = _tally(hands, board, draws)

    report = EquityReport(board=board, mode=mode, trials=walked)
    for i, hand in enumerate(hands):
        report.hands.append(HandEquity(
            index=i,
            cards=hand,
            wins=wins[i],
            ties=ties[i],
            equity=pots[i],
            trials=walked,
            made=tuple(made[i]),
            # Only meaningful once the board has actually finished, where the
            # one runout walked is the real one.
            best_hand=describe(last_scores[i]) if is_complete(board) else "",
        ))
    return report


#: A Hold'em board is five community cards. This variant's board is a different
#: length, so the comparison against Hold'em stops there.
HOLDEM_BOARD = 5


def holdem_made(hands, board=(), dead=(), trials=DEFAULT_TRIALS, seed=None,
                mode="auto", exact_budget=DEFAULT_EXACT_BUDGET):
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

    if mode == "exact":
        draws = combinations(deck, needed)
    else:
        rng = random.Random(seed)
        draws = (rng.sample(deck, needed) for _ in range(max(int(trials), 1)))

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
