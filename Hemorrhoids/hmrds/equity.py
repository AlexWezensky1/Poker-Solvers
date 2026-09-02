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

#: Cards nobody has named are walked too, one walk per way of filling them in,
#: so the wait is that many times a single walk. A thousand keeps the worst case
#: in the ten seconds an exact opening deal already costs; past that there are
#: too many ways to deal the unknown for walking them to beat sampling them.
MAX_HIDDEN_FILLINGS = 1_000


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


def _validate(hands, board, discards, dead):
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
    check_no_duplicates(groups + [("the board", board), ("the folded hands", dead)])


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


def _rank_multisets(avail, size):
    """Every way to pick ``size`` cards from ``avail`` counting ranks only.

    ``avail`` maps rank -> how many of it are left. Yields ``(picks, ways)``
    where ``picks`` is a tuple of ``(rank, count)`` and ``ways`` is how many
    card combinations that stands for. Suits are invisible to every rule, so
    one entry here covers all of them.
    """
    ranks = sorted(avail)

    def walk(i, left, picked, ways):
        if left == 0:
            yield picked, ways
            return
        if i == len(ranks):
            return
        rank = ranks[i]
        for take in range(min(avail[rank], left) + 1):
            yield from walk(i + 1, left - take,
                            picked + ((rank, take),) if take else picked,
                            ways * comb(avail[rank], take))

    yield from walk(0, size, (), 1)


def _hidden_fillings(pool, hidden):
    """Every way the unnamed cards could have been dealt, by rank.

    ``pool`` maps rank -> how many of it could still be in somebody's hand, and
    ``hidden`` is how many cards each seat is missing. Seats are filled in turn
    out of what the ones before them left, so the weights come out right.
    """
    seats = [seat for seat, count in enumerate(hidden) if count]

    def walk(i, avail, filling, ways):
        if i == len(seats):
            yield filling, ways
            return
        seat = seats[i]
        for picks, count in _rank_multisets(avail, hidden[seat]):
            left = dict(avail)
            for rank, take in picks:
                left[rank] -= take
                if not left[rank]:
                    del left[rank]
            yield from walk(i + 1, left, filling + ((seat, picks),), ways * count)

    yield from walk(0, pool, (), 1)


def _count_fillings(pool, hidden, cap):
    """How many fillings there are, giving up once it is clearly too many."""
    total = 0
    for _ in _hidden_fillings(pool, hidden):
        total += 1
        if total > cap:
            break
    return total


def _exact_over_hidden(known_ranks, hidden, pool, deck_ranks, needs, known_masks):
    """Walk every runout for every way the unnamed cards could have been dealt.

    Each filling is a table with every hand named, so it is the ordinary walk;
    the answers are averaged over the fillings, weighted by how many card deals
    each one stands for.
    """
    n = len(known_ranks)
    tally = [[0.0] * n for _ in range(6)]
    dealt = sum(hidden)
    spare = sum(deck_ranks.values()) - dealt
    total = 0

    for filling, ways in _hidden_fillings(pool, hidden):
        seats = [list(ranks) for ranks in known_ranks]
        left = dict(deck_ranks)
        for seat, picks in filling:
            for rank, take in picks:
                seats[seat].extend([rank] * take)
                left[rank] -= take

        masks, tables = [], []
        for ranks in seats:
            mask, table = profile_for_ranks(tuple(sorted(ranks)))
            masks.append(mask)
            tables.append(table)

        live = sorted({rank for ranks in seats for rank in ranks})
        avail = tuple(left.get(rank, 0) for rank in live)
        row = _exact(masks, tables, avail, tuple(1 << rank for rank in live),
                     spare - sum(avail), needs, known_masks)
        for k in range(6):
            for seat in range(n):
                tally[k][seat] += ways * row[k][seat]
        total += ways

    return tuple(tally) + (float(total),)


def _exact_cost(live, unknown, needs):
    """Rough size of the exact walk: states reachable times branching per street."""
    if unknown == 0:
        return 1
    return comb(unknown + live, live) * comb(max(needs) + live, live)


def equity(hands, board=(), discards=None, dead=(), trials=DEFAULT_TRIALS,
           seed=None, mode="auto", exact_budget=DEFAULT_EXACT_BUDGET):
    """Compute equity for two or more HMRDS hands.

    ``hands`` holds what each player is still known to be holding and
    ``discards`` what they have already turned face up, both as sequences of
    card ints from :mod:`hmrds.cards`.  Everyone is dealt five, so whatever the
    two do not account for is unknown and gets dealt at random each trial --
    out of the cards the board has not matched, since a matched card would be
    lying face up rather than hidden.  ``board`` holds 0-10 community cards in
    dealing order.

    ``dead`` holds cards that are out of the deck without belonging to anyone
    still in the pot -- a folded hand's.  They are not scored and they take no
    share, but they cannot be dealt to anybody either, which is the whole point
    of naming them: an unknown card is drawn from what is genuinely left.

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
    dead = tuple(dead)
    _validate(hands, board, discards, dead)

    known = [hands[i] + discards[i] for i in range(len(hands))]
    unknown = [HAND_SIZE - len(cards) for cards in known]
    hidden = sum(unknown)

    gone = set(board) | set(dead)
    for cards in known:
        gone.update(cards)
    deck = [c for c in FULL_DECK if c not in gone]

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

    # Unnamed cards can be walked as well as sampled: every filling is a table
    # with all hands named, so it is the ordinary walk, and suits collapse the
    # fillings from card combinations down to rank multisets -- ninety five
    # times fewer for a seat missing four. It is still one walk apiece, so it
    # only pays while there are few enough of them.
    fillings = 0
    if hidden:
        pool_ranks = {}
        for card in hole_pool:
            rank = card >> 2
            pool_ranks[rank] = pool_ranks.get(rank, 0) + 1
        per_walk = _exact_cost(min(13, len(live) + hidden), to_come, needs)
        # Forced, the walk is worth a wait; chosen by auto it has to stay quick.
        cap = MAX_HIDDEN_FILLINGS if mode == "exact" else min(
            MAX_HIDDEN_FILLINGS, exact_budget // max(per_walk, 1))
        fillings = _count_fillings(pool_ranks, unknown, cap)
        walkable = fillings <= cap and per_walk <= exact_budget
    else:
        walkable = False

    if mode == "auto":
        if hidden:
            mode = "exact" if walkable else "monte-carlo"
        else:
            affordable = _exact_cost(len(live), to_come, needs) <= exact_budget
            mode = "exact" if affordable else "monte-carlo"
    elif mode == "exact" and hidden and not walkable:
        # Too many ways to deal the unknown to walk them all; say so by
        # answering as monte-carlo rather than refusing outright.
        mode = "monte-carlo"

    if mode == "exact" and hidden:
        deck_ranks = {}
        for card in deck:
            rank = card >> 2
            deck_ranks[rank] = deck_ranks.get(rank, 0) + 1
        known_ranks = [sorted(card >> 2 for card in cards) for cards in known]
        pot, scoops, outs, keeps, highs, lows, total = _exact_over_hidden(
            known_ranks, unknown, pool_ranks, deck_ranks, needs, known_masks)
    elif mode == "exact":
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
