"""Equity calculation for HMRS.

Two engines settle the same rules.

The exact one is a DP over *live ranks* -- the ranks somebody actually holds.
Every other rank is interchangeable filler that can only ever be counted, never
identified, so a state is just "how many copies of each live rank are still in
the deck".  Which ranks have already shown up is implied by that: a rank has
appeared exactly when its count has dropped, which is why the memo key does not
need to carry the board.  Runouts that end early because somebody emptied their
hand stop expanding right there.

The Monte Carlo one deals the remaining community cards and settles the runout.
It is the fallback for the opening deal, where the live rank state space is too
wide to walk.
"""

import random
from dataclasses import dataclass, field
from math import comb

from .cards import (
    BOARD_SIZE, FULL_DECK, HAND_SIZE, RANK_BIT, STREETS,
    cards_str, check_no_duplicates, rank_mask,
)
from .scoring import LAST_STREET, build_profiles, describe, empty_seats, resolve, showdown

#: Ten community cards plus five apiece caps the table at eight.
MAX_PLAYERS = (52 - BOARD_SIZE) // HAND_SIZE
DEFAULT_TRIALS = 100_000

#: Walk the exact DP while its estimated size stays under this many steps.
DEFAULT_EXACT_BUDGET = 5_000_000


@dataclass
class HandEquity:
    index: int
    cards: tuple
    equity: float
    scoops: float
    outs: float
    keeps: float
    trials: float
    detail: str = ""

    @property
    def label(self):
        return cards_str(self.cards)

    def _pct(self, value):
        return 100.0 * value / self.trials if self.trials else 0.0

    @property
    def equity_pct(self):
        return self._pct(self.equity)

    @property
    def scoop_pct(self):
        """How often this hand takes the whole pot."""
        return self._pct(self.scoops)

    @property
    def out_pct(self):
        """How often this hand empties out, on any street."""
        return self._pct(self.outs)

    @property
    def keep_pct(self):
        """How often this hand still holds all five at the end."""
        return self._pct(self.keeps)


@dataclass
class EquityReport:
    hands: list = field(default_factory=list)
    board: tuple = ()
    mode: str = "exact"
    trials: float = 0

    @property
    def exact(self):
        return self.mode == "exact"


def _validate(hands, board):
    if len(hands) < 2:
        raise ValueError("need at least 2 hands to compare")
    if len(hands) > MAX_PLAYERS:
        raise ValueError("at most %d hands are supported" % MAX_PLAYERS)
    for i, hand in enumerate(hands):
        if len(hand) != HAND_SIZE:
            raise ValueError("hand %d has %d cards, expected %d" % (i + 1, len(hand), HAND_SIZE))
    if len(board) > BOARD_SIZE:
        raise ValueError("the board holds at most %d cards, got %d" % (BOARD_SIZE, len(board)))
    groups = [("hand %d" % (i + 1), h) for i, h in enumerate(hands)]
    check_no_duplicates(groups + [("the board", board)])


def _layout(board):
    """Split a partial board into streets.

    Returns ``(needs, known_masks)`` -- how many cards each street is still
    waiting on, and the rank mask of the cards it already has.
    """
    needs, known_masks = [], []
    seen = 0
    for size in STREETS:
        dealt = board[seen:seen + size]
        needs.append(size - len(dealt))
        known_masks.append(rank_mask(dealt))
        seen += size
    return needs, known_masks


def _cumulative(known_masks):
    """Turn per-street masks into the running mask after each street."""
    boards, turned = [], 0
    for mask in known_masks:
        turned |= mask
        boards.append(turned)
    return boards


def _street_draws(avail, bits, need, filler):
    """Every way one street can land, as ``(new_avail, ways, added_mask)``.

    ``avail`` counts the copies of each live rank left in the deck and
    ``filler`` counts the dead cards.  Filler is interchangeable, so it only
    ever enters as ``comb(filler, unfilled)``.
    """
    results = []
    width = len(avail)

    def walk(i, left, taken, ways, mask):
        if i == width:
            if left <= filler:
                results.append((tuple(taken), ways * comb(filler, left), mask))
            return
        have = avail[i]
        cap = have if have < left else left
        for count in range(cap + 1):
            taken.append(have - count)
            walk(i + 1, left - count, taken, ways * comb(have, count),
                 (mask | bits[i]) if count else mask)
            taken.pop()

    walk(0, need, [], 1, 0)
    return results


def _exact(masks, tables, avail, bits, filler, needs, known_masks):
    """Exhaust every runout as a memoised walk over live rank counts."""
    n = len(masks)
    memo = {}

    def fill(street, state, board, spare):
        key = (street, state)
        cached = memo.get(key)
        if cached is not None:
            return cached

        need = needs[street]
        denom = comb(sum(state) + spare, need)
        pot = [0.0] * n
        scoops = [0.0] * n
        outs = [0.0] * n
        keeps = [0.0] * n

        for taken, ways, added in _street_draws(state, bits, need, spare):
            chance = ways / denom
            turned = board | added

            if street < LAST_STREET:
                gone = empty_seats(masks, turned)
                if gone:
                    # Out before the last community card, so the hand ends here
                    # and nothing downstream can change the payout.
                    share = chance / len(gone)
                    for seat in gone:
                        pot[seat] += share
                        outs[seat] += chance
                        if len(gone) == 1:
                            scoops[seat] += chance
                    continue
                spent = sum(state) - sum(taken)
                sub_pot, sub_scoops, sub_outs, sub_keeps = fill(
                    street + 1, taken, turned | known_masks[street + 1],
                    spare - (need - spent))
                for seat in range(n):
                    pot[seat] += chance * sub_pot[seat]
                    scoops[seat] += chance * sub_scoops[seat]
                    outs[seat] += chance * sub_outs[seat]
                    keeps[seat] += chance * sub_keeps[seat]
            else:
                final, gone, kept = showdown(masks, tables, turned)
                for seat in range(n):
                    pot[seat] += chance * final[seat]
                    if final[seat] > 0.999999999:
                        scoops[seat] += chance
                for seat in gone:
                    outs[seat] += chance
                for seat in kept:
                    keeps[seat] += chance

        result = (pot, scoops, outs, keeps)
        memo[key] = result
        return result

    return fill(0, avail, known_masks[0], filler)


def _monte_carlo(masks, tables, deck, needs, known_masks, trials, seed):
    """Deal the rest of the board ``trials`` times and settle each runout."""
    n = len(masks)
    rng = random.Random(seed)
    sample = rng.sample
    wanted = sum(needs)
    streets = range(len(STREETS))

    pot = [0.0] * n
    scoops = [0.0] * n
    outs = [0.0] * n
    keeps = [0.0] * n

    for _ in range(trials):
        draw = sample(deck, wanted)
        boards = []
        turned = 0
        at = 0
        for street in streets:
            turned |= known_masks[street]
            for i in range(at, at + needs[street]):
                turned |= RANK_BIT[draw[i]]
            at += needs[street]
            boards.append(turned)

        share, gone, kept = resolve(masks, tables, boards)
        for seat in range(n):
            pot[seat] += share[seat]
            if share[seat] > 0.999999999:
                scoops[seat] += 1
        for seat in gone:
            outs[seat] += 1
        for seat in kept:
            keeps[seat] += 1

    return pot, scoops, outs, keeps


def _exact_cost(live, unknown, needs):
    """Rough size of the exact walk: states reachable times branching per street."""
    if unknown == 0:
        return 1
    return comb(unknown + live, live) * comb(max(needs) + live, live)


def equity(hands, board=(), trials=DEFAULT_TRIALS, seed=None,
           mode="auto", exact_budget=DEFAULT_EXACT_BUDGET):
    """Compute equity for two or more HMRS hands.

    ``hands`` is a sequence of five-card sequences and ``board`` holds 0-10
    community cards in dealing order, all as card ints from :mod:`hmrs.cards`.

    ``mode`` is ``"auto"`` (walk every runout when affordable, otherwise
    sample), ``"exact"`` to force the full walk, or ``"monte-carlo"`` to force
    sampling.
    """
    hands = [tuple(h) for h in hands]
    board = tuple(board)
    _validate(hands, board)

    dead = set(board)
    for hand in hands:
        dead.update(hand)
    deck = [c for c in FULL_DECK if c not in dead]

    needs, known_masks = _layout(board)
    unknown = sum(needs)
    if unknown > len(deck):
        raise ValueError("only %d cards left, the board still needs %d" % (len(deck), unknown))

    masks, tables = build_profiles(hands)

    live = sorted({card >> 2 for hand in hands for card in hand})
    avail = tuple(sum(1 for c in deck if c >> 2 == rank) for rank in live)
    bits = tuple(1 << rank for rank in live)
    filler = len(deck) - sum(avail)

    if mode == "auto":
        affordable = _exact_cost(len(live), unknown, needs) <= exact_budget
        mode = "exact" if affordable else "monte-carlo"

    if mode == "exact":
        pot, scoops, outs, keeps = _exact(masks, tables, avail, bits, filler, needs, known_masks)
        total = 1.0
    elif mode == "monte-carlo":
        if trials < 1:
            raise ValueError("trials must be at least 1")
        pot, scoops, outs, keeps = _monte_carlo(
            masks, tables, deck, needs, known_masks, trials, seed)
        total = float(trials)
    else:
        raise ValueError("unknown mode %r" % mode)

    # With every community card out there is a single runout, so it can be
    # narrated hand by hand.
    detail = [""] * len(hands)
    if len(board) == BOARD_SIZE:
        boards = _cumulative(known_masks)
        detail = [describe(masks, tables, boards, seat) for seat in range(len(hands))]

    report = EquityReport(board=board, mode=mode, trials=total)
    for i, hand in enumerate(hands):
        report.hands.append(HandEquity(
            index=i,
            cards=hand,
            equity=pot[i],
            scoops=scoops[i],
            outs=outs[i],
            keeps=keeps[i],
            trials=total,
            detail=detail[i],
        ))
    return report
