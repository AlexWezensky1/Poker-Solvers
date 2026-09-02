"""Red River hand evaluator for 5-, 6- or 7-card hands.

Every hand is reduced to a single int; a bigger int is a better hand, and equal
ints are a genuine chop.  The score packs a category into the high bits followed
by up to five kicker ranks, four bits each:

    category << 20 | k1 << 16 | k2 << 12 | k3 << 8 | k4 << 4 | k5

The hot path avoids touching the individual cards.  Each card contributes a
precomputed constant to a single accumulator (:data:`CARD_KEY`) that carries a
3-bit count per rank in the low 39 bits and a 4-bit count per suit above them.
Accumulators are additive, so a shared board is summed once and each player's
hole cards are simply added on top.  Non-flush hands then come straight out of a
memo table keyed by the rank half of the accumulator.
"""

from .cards import RANK_CHARS

HIGH_CARD = 0
PAIR = 1
TWO_PAIR = 2
TRIPS = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
QUADS = 7
STRAIGHT_FLUSH = 8

CATEGORY_NAMES = {
    HIGH_CARD: "high card",
    PAIR: "pair",
    TWO_PAIR: "two pair",
    TRIPS: "three of a kind",
    STRAIGHT: "straight",
    FLUSH: "flush",
    FULL_HOUSE: "full house",
    QUADS: "four of a kind",
    STRAIGHT_FLUSH: "straight flush",
}

#: The categories as a player counts them, best first. A royal flush is not a
#: category of its own to the evaluator -- it is a straight flush to the ace --
#: but it is the one everybody wants named, so it gets its own bucket here.
BUCKET_NAMES = (
    "royal flush",
    "straight flush",
    "four of a kind",
    "full house",
    "flush",
    "straight",
    "three of a kind",
    "two pair",
    "pair",
    "high card",
)


def bucket(hand_score):
    """Index into :data:`BUCKET_NAMES`: 0 is a royal flush, 9 is high card."""
    cat = hand_score >> 20
    if cat == STRAIGHT_FLUSH:
        return 0 if (hand_score >> 16) & 15 == 12 else 1
    return 1 + (STRAIGHT_FLUSH - cat)


_SUIT_SHIFT = 39
_RANK_MASK = (1 << _SUIT_SHIFT) - 1

#: Per-card contribution to a hand accumulator.
CARD_KEY = tuple(
    (1 << (3 * (c >> 2))) + (1 << (_SUIT_SHIFT + 4 * (c & 3))) for c in range(52)
)


def _straight_high(mask):
    """Highest rank completing a straight in a 13-bit rank mask, else -1."""
    for hi in range(12, 3, -1):
        run = 0b11111 << (hi - 4)
        if mask & run == run:
            return hi
    if mask & 0x100F == 0x100F:  # the wheel: A-2-3-4-5
        return 3
    return -1


_STRAIGHT = tuple(_straight_high(m) for m in range(1 << 13))


def _pack(category, k1=0, k2=0, k3=0, k4=0, k5=0):
    return (category << 20) | (k1 << 16) | (k2 << 12) | (k3 << 8) | (k4 << 4) | k5


def _top(mask):
    return mask.bit_length() - 1


def _top_n(mask, n):
    out = []
    while len(out) < n and mask:
        hi = mask.bit_length() - 1
        out.append(hi)
        mask &= ~(1 << hi)
    while len(out) < n:
        out.append(0)
    return out


def _score_ranks(key):
    """Score the non-flush hand described by the rank half of an accumulator."""
    mask = quads = trips = pairs = 0
    for r in range(13):
        count = (key >> (3 * r)) & 7
        if not count:
            continue
        bit = 1 << r
        mask |= bit
        if count == 4:
            quads |= bit
        elif count == 3:
            trips |= bit
        elif count == 2:
            pairs |= bit

    if quads:
        q = _top(quads)
        return _pack(QUADS, q, _top(mask & ~(1 << q)))

    if trips:
        top_trip = _top(trips)
        under = pairs | (trips & ~(1 << top_trip))
        if under:
            return _pack(FULL_HOUSE, top_trip, _top(under))

    high = _STRAIGHT[mask]
    if high >= 0:
        return _pack(STRAIGHT, high)

    if trips:
        t = _top(trips)
        k1, k2 = _top_n(mask & ~(1 << t), 2)
        return _pack(TRIPS, t, k1, k2)

    if pairs:
        p1 = _top(pairs)
        others = pairs & ~(1 << p1)
        if others:
            p2 = _top(others)
            return _pack(TWO_PAIR, p1, p2, _top(mask & ~(1 << p1) & ~(1 << p2)))
        k1, k2, k3 = _top_n(mask & ~(1 << p1), 3)
        return _pack(PAIR, p1, k1, k2, k3)

    return _pack(HIGH_CARD, *_top_n(mask, 5))


def _score_flush(cards):
    """Score a hand already known to hold five or more cards of one suit.

    Ten cards or more can carry two suits five deep at once, and the longer of
    them is not always the better -- six low spades lose to five high hearts --
    so every suit that gets there is scored and the best kept. Seven cards can
    only ever hold one, which is why this used to take the longest and stop.
    """
    masks = [0, 0, 0, 0]
    counts = [0, 0, 0, 0]
    for card in cards:
        suit = card & 3
        counts[suit] += 1
        masks[suit] |= 1 << (card >> 2)

    best = -1
    for suit in range(4):
        if counts[suit] < 5:
            continue
        high = _STRAIGHT[masks[suit]]
        value = (_pack(STRAIGHT_FLUSH, high) if high >= 0
                 else _pack(FLUSH, *_top_n(masks[suit], 5)))
        if value > best:
            best = value
    return best


_CACHE = {}


def score_accumulator(acc, hole, board):
    """Score a hand from its accumulator.

    ``hole`` and ``board`` are only read on the rare flush branch, which needs
    to know which suit each card belongs to.

    Holding a flush does not settle it: the same cards can make a full house or
    quads that beat it, and then the ranks are the better hand. Seven cards can
    never do both at once -- five suited cards are five distinct ranks, and the
    two left over cannot lift any rank past three -- so Hold'em got away with
    stopping at the flush. Eight can: 8d 4s 6s 8h 5s 9s 6c 8s is a nine-high
    flush and eights full of sixes, and the full house wins.
    """
    key = acc & _RANK_MASK
    best = _CACHE.get(key)
    if best is None:
        best = _CACHE[key] = _score_ranks(key)
    if ((acc >> _SUIT_SHIFT) + 0x3333) & 0x8888:
        flush = _score_flush(list(hole) + list(board))
        if flush > best:
            return flush
    return best


def score(cards):
    """Score 5, 6 or 7 cards.  Higher is better; ties are exact chops."""
    acc = 0
    for card in cards:
        acc += CARD_KEY[card]
    return score_accumulator(acc, cards, ())


def category(hand_score):
    """The category constant of a score."""
    return hand_score >> 20


def describe(hand_score):
    """A human readable name for a score, e.g. ``full house, kings full of nines``."""
    cat = hand_score >> 20
    k = [(hand_score >> shift) & 15 for shift in (16, 12, 8, 4, 0)]
    name = lambda r: RANK_CHARS[r]  # noqa: E731

    if cat == STRAIGHT_FLUSH:
        return "royal flush" if k[0] == 12 else "straight flush, %s high" % name(k[0])
    if cat == QUADS:
        return "four of a kind, %ss" % name(k[0])
    if cat == FULL_HOUSE:
        return "full house, %ss full of %ss" % (name(k[0]), name(k[1]))
    if cat == FLUSH:
        return "flush, %s high" % name(k[0])
    if cat == STRAIGHT:
        return "straight, %s high" % name(k[0])
    if cat == TRIPS:
        return "three of a kind, %ss" % name(k[0])
    if cat == TWO_PAIR:
        return "two pair, %ss and %ss" % (name(k[0]), name(k[1]))
    if cat == PAIR:
        return "pair of %ss" % name(k[0])
    return "high card %s" % name(k[0])
