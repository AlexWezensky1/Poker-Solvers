"""Card representation and parsing.

A card is a plain int in 0..51 where ``rank = card >> 2`` (0 = deuce .. 12 = ace)
and ``suit = card & 3``.  Ints keep the evaluator's hot loop free of attribute
lookups, which matters when a preflop run scores a few million hands.
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

#: Hearts and diamonds sit at suit indices 1 and 2 of SUIT_CHARS ("shdc").
#: Red River hangs its whole rule on this: a red river card is followed by
#: another, a black one ends the hand.
RED_SUITS = frozenset({1, 2})


def is_red(card):
    """Is this card a heart or a diamond?"""
    return (card & 3) in RED_SUITS


def make_card(rank, suit):
    """Build a card from a rank index (0..12) and suit index (0..3)."""
    return (rank << 2) | suit


def card_str(card):
    """Render a card as e.g. ``As``."""
    return RANK_CHARS[card >> 2] + SUIT_CHARS[card & 3]


def cards_str(cards):
    """Render a sequence of cards as e.g. ``As Kh``."""
    return " ".join(card_str(c) for c in cards)


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
