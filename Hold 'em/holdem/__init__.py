"""A Texas Hold'em equity solver."""

from .cards import card_str, cards_str, parse_card, parse_cards
from .equity import DEFAULT_TRIALS, MAX_PLAYERS, EquityReport, HandEquity, equity
from .evaluator import describe, score

__all__ = [
    "DEFAULT_TRIALS",
    "MAX_PLAYERS",
    "EquityReport",
    "HandEquity",
    "card_str",
    "cards_str",
    "describe",
    "equity",
    "parse_card",
    "parse_cards",
    "score",
]
