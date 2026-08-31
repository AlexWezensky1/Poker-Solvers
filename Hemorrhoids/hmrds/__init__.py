"""An HMRDS equity solver."""

from .cards import card_str, cards_str, mask_str, parse_card, parse_cards, rank_mask
from .equity import DEFAULT_TRIALS, MAX_PLAYERS, EquityReport, HandEquity, equity
from .scoring import HIGH_VALUE, LOW_VALUE, build_profile, describe, resolve, showdown

__all__ = [
    "DEFAULT_TRIALS",
    "HIGH_VALUE",
    "LOW_VALUE",
    "MAX_PLAYERS",
    "EquityReport",
    "HandEquity",
    "build_profile",
    "card_str",
    "cards_str",
    "describe",
    "equity",
    "mask_str",
    "parse_card",
    "parse_cards",
    "rank_mask",
    "resolve",
    "showdown",
]
