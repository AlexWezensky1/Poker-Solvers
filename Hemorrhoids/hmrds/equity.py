"""Equity calculation for HMRDS.

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
    card_str, cards_str, check_no_duplicates, rank_mask,
)
from .scoring import (
    LAST_STREET, build_profiles, describe, empty_seats, profile_for_ranks, resolve, showdown,
)

#: Ten community cards plus five apiece caps the table at eight.
MAX_PLAYERS = (52 - BOARD_SIZE) // HAND_SIZE
DEFAULT_TRIALS = 250_000

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
    highs: float
    lows: float
    trials: float
    held: tuple = ()
    discarded: tuple = ()
    unknown: int = 0
    detail: str = ""

    @property
    def label(self):
        """The hand as dealt: what is held, what is face up, what is unknown."""
        text = cards_str(self.held) or "--"
        if self.discarded:
            text += " / " + cards_str(self.discarded)
        if self.unknown:
            text += " +%d?" % self.unknown
        return text

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

    @property
    def high_pct(self):
        """Share of the high half this hand takes, over all runouts.

        Runouts won outright never split into halves, so they count nothing
        here -- these two only add up across seats as often as the hand
        actually reaches a high/low showdown.
        """
        return self._pct(self.highs)

    @property
    def low_pct(self):
        """Share of the low half this hand takes, over all runouts."""
        return self._pct(self.lows)


@dataclass
class EquityReport:
    hands: list = field(default_factory=list)
    board: tuple = ()
    mode: str = "exact"
    trials: float = 0

    @property
    def exact(self):
        return self.mode == "exact"


def _validate(hands, board, discards):
    if len(hands) < 2:
        raise ValueError("need at least 2 hands to compare")
    if len(hands) > MAX_PLAYERS:
        raise ValueError("at most %d hands are supported" % MAX_PLAYERS)
    if len(board) > BOARD_SIZE:
        raise ValueError("the board holds at most %d cards, got %d" % (BOARD_SIZE, len(board)))

    turned = rank_mask(board)
    for i, held in enumerate(hands):
        named = len(held) + len(discards[i])
        if named > HAND_SIZE:
            raise ValueError("hand %d names %d cards, more than the %d dealt"
                             % (i + 1, named, HAND_SIZE))
        # A card only ever leaves your hand because a community card matched it,
        # so a discard with nothing to match it means the input disagrees with
        # the board.
        for card in discards[i]:
            if not RANK_BIT[card] & turned:
                raise ValueError("hand %d discarded %s, but no community card matches that rank"
                                 % (i + 1, card_str(card)))

    groups = []
    for i, held in enumerate(hands):
        groups.append(("hand %d" % (i + 1), held))
        groups.append(("hand %d's discards" % (i + 1), discards[i]))
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
        highs = [0.0] * n
        lows = [0.0] * n

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
                sub = fill(street + 1, taken, turned | known_masks[street + 1],
                           spare - (need - spent))
                for seat in range(n):
                    pot[seat] += chance * sub[0][seat]
                    scoops[seat] += chance * sub[1][seat]
                    outs[seat] += chance * sub[2][seat]
                    keeps[seat] += chance * sub[3][seat]
                    highs[seat] += chance * sub[4][seat]
                    lows[seat] += chance * sub[5][seat]
            else:
                final, gone, kept, high, low = showdown(masks, tables, turned)
                for seat in range(n):
                    pot[seat] += chance * final[seat]
                    if final[seat] > 0.999999999:
                        scoops[seat] += chance
                for seat in gone:
                    outs[seat] += chance
                for seat in kept:
                    keeps[seat] += chance
                if high:
                    for seat in high:
                        highs[seat] += chance / len(high)
                    for seat in low:
                        lows[seat] += chance / len(low)

        result = (pot, scoops, outs, keeps, highs, lows)
        memo[key] = result
        return result

    return fill(0, avail, known_masks[0], filler)


def _monte_carlo(known, unknown, deck, hole_pool, needs, known_masks, trials, seed):
    """Deal the rest of the board ``trials`` times and settle each runout.

    Hands that are only partly known have their missing cards dealt as well,
    out of ``hole_pool`` -- the cards that could still be in somebody's hand.
    Anything the board has already matched would have been discarded face up,
    so it cannot be one of them.
    """
    n = len(known)
    rng = random.Random(seed)
    sample = rng.sample
    wanted = sum(needs)
    hidden = sum(unknown)
    streets = range(len(STREETS))

    # Seats that are fully known keep the profile built here for every trial;
    # the rest are rebuilt each deal, which the rank cache makes cheap.
    base = [tuple(sorted(card >> 2 for card in cards)) for cards in known]
    profiles = [profile_for_ranks(ranks) for ranks in base]
    masks = [profile[0] for profile in profiles]
    tables = [profile[1] for profile in profiles]

    # The hidden cards have to be drawn before the board, or neither draw comes
    # out uniform. Shuffling just the front of `spare` picks them and leaves the
    # rest of the pool as one slice, which beats filtering the deck every trial.
    spare = list(hole_pool)
    blocked = []
    if hidden:
        hideable = set(hole_pool)
        blocked = [card for card in deck if card not in hideable]
    reach = len(spare)
    randrange = rng.randrange

    pot = [0.0] * n
    scoops = [0.0] * n
    outs = [0.0] * n
    keeps = [0.0] * n
    highs = [0.0] * n
    lows = [0.0] * n

    for _ in range(trials):
        pool = deck
        if hidden:
            for i in range(hidden):
                j = randrange(i, reach)
                spare[i], spare[j] = spare[j], spare[i]
            pool = spare[hidden:] + blocked
            at = 0
            for seat in range(n):
                missing = unknown[seat]
                if missing:
                    filled = base[seat] + tuple(c >> 2 for c in spare[at:at + missing])
                    at += missing
                    masks[seat], tables[seat] = profile_for_ranks(tuple(sorted(filled)))

        draw = sample(pool, wanted)
        boards = []
        turned = 0
        at = 0
        for street in streets:
            turned |= known_masks[street]
            for i in range(at, at + needs[street]):
                turned |= RANK_BIT[draw[i]]
            at += needs[street]
            boards.append(turned)

        share, gone, kept, high, low = resolve(masks, tables, boards)
        for seat in range(n):
            pot[seat] += share[seat]
            if share[seat] > 0.999999999:
                scoops[seat] += 1
        for seat in gone:
            outs[seat] += 1
        for seat in kept:
            keeps[seat] += 1
        if high:
            for seat in high:
                highs[seat] += 1.0 / len(high)
            for seat in low:
                lows[seat] += 1.0 / len(low)

    return pot, scoops, outs, keeps, highs, lows


def _exact_cost(live, unknown, needs):
    """Rough size of the exact walk: states reachable times branching per street."""
    if unknown == 0:
        return 1
    return comb(unknown + live, live) * comb(max(needs) + live, live)


def equity(hands, board=(), discards=None, trials=DEFAULT_TRIALS, seed=None,
           mode="auto", exact_budget=DEFAULT_EXACT_BUDGET):
    """Compute equity for two or more HMRDS hands.

    ``hands`` holds what each player is still known to be holding and
    ``discards`` what they have already turned face up, both as sequences of
    card ints from :mod:`hmrds.cards`.  Everyone is dealt five, so whatever the
    two do not account for is unknown and gets dealt at random each trial --
    out of the cards the board has not matched, since a matched card would be
    lying face up rather than hidden.  ``board`` holds 0-10 community cards in
    dealing order.

    ``mode`` is ``"auto"`` (walk every runout when affordable, otherwise
    sample), ``"exact"`` to force the full walk, or ``"monte-carlo"`` to force
    sampling.  Unknown cards can only be sampled.
    """
    hands = [tuple(h) for h in hands]
    board = tuple(board)
    if discards is None:
        discards = [()] * len(hands)
    else:
        discards = [tuple(pile) for pile in discards]
        if len(discards) != len(hands):
            raise ValueError("got %d hands but %d discard piles"
                             % (len(hands), len(discards)))
    _validate(hands, board, discards)

    known = [hands[i] + discards[i] for i in range(len(hands))]
    unknown = [HAND_SIZE - len(cards) for cards in known]
    hidden = sum(unknown)

    dead = set(board)
    for cards in known:
        dead.update(cards)
    deck = [c for c in FULL_DECK if c not in dead]

    needs, known_masks = _layout(board)
    to_come = sum(needs)
    if to_come + hidden > len(deck):
        raise ValueError("only %d cards are left but %d are still needed"
                         % (len(deck), to_come + hidden))

    # Anything the board has already matched would have been discarded, so it
    # cannot be one of the cards a player is still hiding.
    hole_pool = [c for c in deck if not RANK_BIT[c] & rank_mask(board)]
    if hidden > len(hole_pool):
        raise ValueError("only %d cards could still be in a hand but %d are unknown"
                         % (len(hole_pool), hidden))

    live = sorted({card >> 2 for cards in known for card in cards})
    if mode == "auto":
        if hidden:
            mode = "monte-carlo"
        else:
            affordable = _exact_cost(len(live), to_come, needs) <= exact_budget
            mode = "exact" if affordable else "monte-carlo"
    elif mode == "exact" and hidden:
        raise ValueError("%d card%s unknown, which only monte-carlo can deal"
                         % (hidden, " is" if hidden == 1 else "s are"))

    if mode == "exact":
        masks, tables = build_profiles(known)
        avail = tuple(sum(1 for c in deck if c >> 2 == rank) for rank in live)
        bits = tuple(1 << rank for rank in live)
        filler = len(deck) - sum(avail)
        pot, scoops, outs, keeps, highs, lows = _exact(
            masks, tables, avail, bits, filler, needs, known_masks)
        total = 1.0
    elif mode == "monte-carlo":
        if trials < 1:
            raise ValueError("trials must be at least 1")
        pot, scoops, outs, keeps, highs, lows = _monte_carlo(
            known, unknown, deck, hole_pool, needs, known_masks, trials, seed)
        total = float(trials)
    else:
        raise ValueError("unknown mode %r" % mode)

    # With every community card out and every hand named there is a single
    # runout, so it can be narrated hand by hand.
    detail = [""] * len(hands)
    if len(board) == BOARD_SIZE and not hidden:
        masks, tables = build_profiles(known)
        boards = _cumulative(known_masks)
        detail = [describe(masks, tables, boards, seat, known[seat])
                  for seat in range(len(hands))]

    report = EquityReport(board=board, mode=mode, trials=total)
    for i in range(len(hands)):
        report.hands.append(HandEquity(
            index=i,
            cards=known[i],
            equity=pot[i],
            scoops=scoops[i],
            outs=outs[i],
            keeps=keeps[i],
            highs=highs[i],
            lows=lows[i],
            trials=total,
            held=hands[i],
            discarded=discards[i],
            unknown=unknown[i],
            detail=detail[i],
        ))
    return report
