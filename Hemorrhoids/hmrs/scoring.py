"""Hand scoring and pot resolution for HMRS.

Only cards still in your hand are scored.  Deuce through ten are worth their
face value, jacks queens and kings are worth ten, and an ace is worth one for
the low and eleven for the high -- every ace, so A-A is 2/22 and A-A-A is 3/33.
Because one hand carries a separate low and high total it can win both halves,
which is how a lone ace scoops a lone jack: 1 beats 10 for the low and 11 beats
10 for the high.

The pot is settled in this order:

1. Anyone who empties their hand *before* the last community card wins outright.
   The hand would have ended the moment they went out, so the earliest street
   wins; players who go out on that same street split.
2. Otherwise the last community card is turned and the pot goes to everyone who
   either emptied their hand on it or still holds all five cards.  Those two
   groups split together, so an empty hand alone takes it all and a keeper alone
   takes it all.
3. Otherwise half the pot goes to the highest high total and half to the lowest
   low total, each half split evenly among ties.
"""

from .cards import HAND_SIZE, RANK_CHARS, STREETS

#: Rank index 0..12 is deuce..ace.  Jacks, queens and kings all count ten.
LOW_VALUE = tuple([r + 2 for r in range(9)] + [10, 10, 10] + [1])
HIGH_VALUE = LOW_VALUE[:12] + (11,)

#: The last street is the one that stops an empty hand from winning outright.
LAST_STREET = len(STREETS) - 1


def build_profile(cards):
    """Precompute everything scoring needs about one hand.

    Returns ``(mask, table)`` where ``mask`` is the hand's rank mask and
    ``table`` maps every surviving submask of it to ``(cards_left, low, high)``.
    A hand spans at most five distinct ranks, so the table holds at most 32
    rows and survival becomes ``table[mask & ~board]`` -- one AND and one dict
    lookup per player per runout.
    """
    counts = {}
    for card in cards:
        counts[card >> 2] = counts.get(card >> 2, 0) + 1
    mask = 0
    for rank in counts:
        mask |= 1 << rank

    table = {}
    sub = mask
    while True:
        left = low = high = 0
        for rank, count in counts.items():
            if sub >> rank & 1:
                left += count
                low += LOW_VALUE[rank] * count
                high += HIGH_VALUE[rank] * count
        table[sub] = (left, low, high)
        if not sub:
            break
        sub = (sub - 1) & mask
    return mask, table


def build_profiles(hands):
    """Build parallel lists of hand masks and scoring tables."""
    masks, tables = [], []
    for hand in hands:
        mask, table = build_profile(hand)
        masks.append(mask)
        tables.append(table)
    return masks, tables


def empty_seats(hand_masks, board):
    """Seats holding nothing once every rank in ``board`` has been discarded."""
    return [seat for seat, mask in enumerate(hand_masks) if not mask & ~board]


def _split(seats, n):
    """An even share of the whole pot for each seat in ``seats``."""
    pot = [0.0] * n
    share = 1.0 / len(seats)
    for seat in seats:
        pot[seat] = share
    return pot


def showdown(hand_masks, tables, board):
    """Settle the pot once the last community card is out.

    ``board`` is the rank mask of all ten community cards.  Returns
    ``(pot, out_seats, kept_seats)``.
    """
    n = len(hand_masks)
    survivors = [mask & ~board for mask in hand_masks]
    out = [seat for seat in range(n) if not survivors[seat]]
    kept = [seat for seat in range(n) if survivors[seat] == hand_masks[seat]]

    # Going out on the last card no longer wins outright, it only earns a share
    # alongside anyone who kept their whole hand -- and takes the lot when
    # nobody did.
    if out or kept:
        return _split(out + kept, n), out, kept

    scored = [tables[seat][survivors[seat]] for seat in range(n)]
    best_high = max(row[2] for row in scored)
    best_low = min(row[1] for row in scored)
    highs = [seat for seat in range(n) if scored[seat][2] == best_high]
    lows = [seat for seat in range(n) if scored[seat][1] == best_low]

    pot = [0.0] * n
    for seat in highs:
        pot[seat] += 0.5 / len(highs)
    for seat in lows:
        pot[seat] += 0.5 / len(lows)
    return pot, out, kept


def resolve(hand_masks, tables, boards):
    """Settle one whole runout.

    ``boards`` holds the cumulative community rank mask after each of the four
    streets.  Returns ``(pot, out_seats, kept_seats)``.
    """
    for street in range(LAST_STREET):
        gone = empty_seats(hand_masks, boards[street])
        if gone:
            return _split(gone, len(hand_masks)), gone, []
    return showdown(hand_masks, tables, boards[LAST_STREET])


def describe(hand_masks, tables, boards, seat):
    """A short account of how one seat finished a completed runout."""
    for street in range(LAST_STREET):
        if not hand_masks[seat] & ~boards[street]:
            return "out on street %d" % (street + 1)
    survivors = hand_masks[seat] & ~boards[LAST_STREET]
    if not survivors:
        return "out on the last card"
    left, low, high = tables[seat][survivors]
    if left == HAND_SIZE:
        return "kept all %d" % HAND_SIZE
    held = " ".join(RANK_CHARS[r] for r in range(12, -1, -1) if survivors >> r & 1)
    if low == high:
        return "%s (%d)" % (held, low)
    return "%s (%d low / %d high)" % (held, low, high)
