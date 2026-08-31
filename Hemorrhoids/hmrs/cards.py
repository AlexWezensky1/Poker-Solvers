"""Card representation and parsing.

A card is a plain int in 0..51 where ``rank = card >> 2`` (0 = deuce .. 12 = ace)
and ``suit = card & 3``.  Suits are dealt and displayed but nothing in HMRS ever
reads one: community cards match by rank and hands score by rank.  The hot loops
therefore work on 13 bit rank masks, one bit per rank, so "which of my cards
survive this board" is a single AND.
"""

import re

RANK_CHARS = "23456789TJQKA"
SUIT_CHARS = "shdc"

SUIT_NAMES = {"s": "spades", "h": "hearts", "d": "diamonds", "c": "clubs"}
RANK_NAMES = {
    "2": "deuce", "3": "trey", "4": "four", "5": "five", "6": "six",
    "7": "seven", "8": "eight", "9": "nine", "T": "ten", "J": "jack",
    "Q": "queen", "K": "king", "A": "ace",
}

FULL_DECK = tuple(range(52))

#: Cards dealt to each player.
HAND_SIZE = 5

#: Community cards turned per betting round: four, then three, then two, then one.
STREETS = (4, 3, 2, 1)

BOARD_SIZE = sum(STREETS)

#: ``RANK_BIT[card]`` is the rank mask bit that card sets.
RANK_BIT = tuple(1 << (card >> 2) for card in FULL_DECK)

ALL_RANKS = (1 << 13) - 1


def make_card(rank, suit):
    """Build a card from a rank index (0..12) and suit index (0..3)."""
    return (rank << 2) | suit


def card_str(card):
    """Render a card as e.g. ``As``."""
    return RANK_CHARS[card >> 2] + SUIT_CHARS[card & 3]


def cards_str(cards):
    """Render a sequence of cards as e.g. ``As Kh``."""
    return " ".join(card_str(c) for c in cards)


def rank_mask(cards):
    """The 13 bit mask of every rank present in ``cards``."""
    mask = 0
    for card in cards:
        mask |= RANK_BIT[card]
    return mask


def mask_str(mask):
    """Render a rank mask high to low, e.g. ``A K T``."""
    return " ".join(RANK_CHARS[r] for r in range(12, -1, -1) if mask >> r & 1)


def parse_card(token):
    """Parse a single two-character card such as ``As`` or ``th``."""
    token = token.strip()
    if len(token) != 2:
        raise ValueError("%r is not a card (expected two characters like 'As')" % token)
    rank, suit = token[0].upper(), token[1].lower()
    if rank not in RANK_CHARS:
        raise ValueError("%r is not a rank (use one of %s)" % (token[0], RANK_CHARS))
    if suit not in SUIT_CHARS:
        raise ValueError("%r is not a suit (use one of %s)" % (token[1], SUIT_CHARS))
    return make_card(RANK_CHARS.index(rank), SUIT_CHARS.index(suit))


def parse_cards(text):
    """Parse a run of cards.

    Accepts ``AsKh``, ``As Kh``, ``as,kh`` and spells ``10`` as a ten.
    """
    packed = re.sub(r"[\s,]+", "", text or "")
    packed = packed.replace("10", "T").replace("1O", "T")
    if len(packed) % 2:
        raise ValueError("%r has a leftover character; cards come in rank+suit pairs" % text)
    return [parse_card(packed[i:i + 2]) for i in range(0, len(packed), 2)]


def street_of(index):
    """Which street the board card at ``index`` (0 based) is turned on."""
    seen = 0
    for street, size in enumerate(STREETS):
        seen += size
        if index < seen:
            return street
    raise ValueError("the board holds at most %d cards" % BOARD_SIZE)


def check_no_duplicates(groups):
    """Raise if any card appears twice across ``groups`` of (label, cards)."""
    seen = {}
    for label, cards in groups:
        for card in cards:
            if card in seen:
                raise ValueError(
                    "%s is used twice (%s and %s)" % (card_str(card), seen[card], label)
                )
            seen[card] = label
