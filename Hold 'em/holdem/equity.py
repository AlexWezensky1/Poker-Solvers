"""Win / tie / equity calculation for Texas Hold'em.

Runouts are enumerated exactly whenever that is cheap enough (everything from
the flop onward, typically) and sampled with Monte Carlo otherwise.
"""

import random
from dataclasses import dataclass, field
from itertools import combinations
from math import comb

from .cards import FULL_DECK, cards_str, check_no_duplicates
from .evaluator import CARD_KEY, describe, score_accumulator

MAX_PLAYERS = 8
DEFAULT_TRIALS = 100_000

#: Enumerate exactly while runouts x players stays under this many evaluations.
DEFAULT_EXACT_BUDGET = 1_500_000


@dataclass
class HandEquity:
    index: int
    cards: tuple
    wins: int
    ties: int
    equity: float
    trials: int
    best_hand: str = ""

    @property
    def label(self):
        return cards_str(self.cards)

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
    if len(board) > 5:
        raise ValueError("the board holds at most 5 cards, got %d" % len(board))
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

    return wins, ties, equity, trials, last_scores


def equity(hands, board=(), trials=DEFAULT_TRIALS, seed=None,
           mode="auto", exact_budget=DEFAULT_EXACT_BUDGET):
    """Compute equity for two or more Hold'em hands.

    ``hands`` is a sequence of two-card sequences and ``board`` holds 0-5
    community cards, all as card ints from :mod:`holdem.cards`.

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
    needed = 5 - len(board)

    runouts = comb(len(deck), needed)
    if mode == "auto":
        mode = "exact" if runouts * len(hands) <= exact_budget else "monte-carlo"
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

    wins, ties, pots, total, last_scores = _tally(hands, board, draws)

    report = EquityReport(board=board, mode=mode, trials=total)
    for i, hand in enumerate(hands):
        report.hands.append(HandEquity(
            index=i,
            cards=hand,
            wins=wins[i],
            ties=ties[i],
            equity=pots[i],
            trials=total,
            # Only meaningful when the board is already complete, where the one
            # runout is the real one.
            best_hand=describe(last_scores[i]) if len(board) == 5 else "",
        ))
    return report
