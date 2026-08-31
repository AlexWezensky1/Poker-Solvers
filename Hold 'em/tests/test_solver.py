"""Tests for the Hold'em evaluator and equity engine.

Run with pytest, or directly: ``python tests/test_solver.py``.
"""

import os
import random
import sys
from collections import Counter
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from holdem.cards import FULL_DECK, parse_cards  # noqa: E402
from holdem.equity import equity  # noqa: E402
from holdem.evaluator import (  # noqa: E402
    FLUSH, FULL_HOUSE, HIGH_CARD, PAIR, QUADS, STRAIGHT, STRAIGHT_FLUSH,
    TRIPS, TWO_PAIR, category, describe, score,
)


def naive5(cards):
    """A deliberately plodding 5-card evaluator to check the fast one against."""
    ranks = sorted((c >> 2 for c in cards), reverse=True)
    flush = len({c & 3 for c in cards}) == 1
    counts = Counter(ranks)
    distinct = sorted(counts, reverse=True)

    straight_high = None
    if len(distinct) == 5:
        if distinct[0] - distinct[4] == 4:
            straight_high = distinct[0]
        elif distinct == [12, 3, 2, 1, 0]:
            straight_high = 3

    groups = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    shape = tuple(count for _, count in groups)
    kickers = [rank for rank, _ in groups]

    if flush and straight_high is not None:
        return (STRAIGHT_FLUSH, [straight_high])
    if shape == (4, 1):
        return (QUADS, kickers)
    if shape == (3, 2):
        return (FULL_HOUSE, kickers)
    if flush:
        return (FLUSH, ranks)
    if straight_high is not None:
        return (STRAIGHT, [straight_high])
    if shape == (3, 1, 1):
        return (TRIPS, kickers)
    if shape == (2, 2, 1):
        return (TWO_PAIR, kickers)
    if shape == (2, 1, 1, 1):
        return (PAIR, kickers)
    return (HIGH_CARD, ranks)


def sign(x):
    return (x > 0) - (x < 0)


def test_known_categories():
    cases = [
        ("As Ks Qs Js Ts", STRAIGHT_FLUSH, "royal flush"),
        ("5h 4h 3h 2h Ah", STRAIGHT_FLUSH, "straight flush, 5 high"),
        ("9c 9d 9h 9s 2c", QUADS, "four of a kind, 9s"),
        ("Kc Kd Kh 4s 4c", FULL_HOUSE, "full house, Ks full of 4s"),
        ("Ad Td 8d 5d 2d", FLUSH, "flush, A high"),
        ("Ac Kd Qh Js Tc", STRAIGHT, "straight, A high"),
        ("5c 4d 3h 2s Ac", STRAIGHT, "straight, 5 high"),
        ("7c 7d 7h Ks 2c", TRIPS, "three of a kind, 7s"),
        ("Jc Jd 3h 3s Kc", TWO_PAIR, "two pair, Js and 3s"),
        ("Qc Qd 9h 5s 2c", PAIR, "pair of Qs"),
        ("Ac Jd 9h 5s 2c", HIGH_CARD, "high card A"),
    ]
    for text, expected, name in cases:
        value = score(parse_cards(text))
        assert category(value) == expected, (text, category(value), expected)
        assert describe(value) == name, (text, describe(value), name)


def test_category_ordering():
    ladder = [
        "2c 7d 9h Js 4c",       # high card
        "2c 2d 9h Js 4c",       # pair
        "2c 2d 9h 9s 4c",       # two pair
        "2c 2d 2h 9s 4c",       # trips
        "5c 6d 7h 8s 9c",       # straight
        "2c 7c 9c Jc 4c",       # flush
        "2c 2d 2h 9s 9c",       # full house
        "2c 2d 2h 2s 9c",       # quads
        "5c 6c 7c 8c 9c",       # straight flush
    ]
    values = [score(parse_cards(text)) for text in ladder]
    assert values == sorted(values), values
    assert len(set(values)) == len(values)


def test_matches_naive_evaluator():
    rng = random.Random(1234)
    deck = list(FULL_DECK)
    hands = [rng.sample(deck, 5) for _ in range(1500)]
    for a, b in zip(hands, hands[1:]):
        fast = sign(score(a) - score(b))
        slow = sign((naive5(a) > naive5(b)) - (naive5(a) < naive5(b)))
        assert fast == slow, (a, b, fast, slow)


def test_seven_cards_pick_the_best_five():
    rng = random.Random(99)
    deck = list(FULL_DECK)
    for _ in range(400):
        seven = rng.sample(deck, 7)
        best = max(score(five) for five in combinations(seven, 5))
        assert score(seven) == best, seven


def test_wheel_loses_to_six_high_straight():
    assert score(parse_cards("5c 4d 3h 2s Ac")) < score(parse_cards("6c 5d 4h 3s 2c"))


def test_flush_beats_straight_on_seven_cards():
    value = score(parse_cards("Ah Kh Qh 2h 7h 9s 9d"))
    assert category(value) == FLUSH


def test_board_plays_is_a_chop():
    report = equity(
        [parse_cards("2c 3d"), parse_cards("2h 3s")],
        parse_cards("As Ks Qh Jd Tc"),
    )
    assert report.exact and report.trials == 1
    assert report.hands[0].equity_pct == 50.0
    assert report.hands[1].equity_pct == 50.0
    assert report.hands[0].best_hand == "straight, A high"


def test_made_hand_wins_outright():
    report = equity(
        [parse_cards("AsKs"), parse_cards("2c2d")],
        parse_cards("Ah Kd 7s 3c 9h"),
    )
    assert report.hands[0].equity_pct == 100.0
    assert report.hands[1].equity_pct == 0.0
    assert report.hands[0].best_hand == "two pair, As and Ks"


def test_flop_is_enumerated_exactly():
    report = equity([parse_cards("AsKs"), parse_cards("QhQd")], parse_cards("Jh Ts 2c"))
    assert report.exact
    assert report.trials == 990  # C(45, 2)
    total = sum(h.equity_pct for h in report.hands)
    assert abs(total - 100.0) < 1e-9


def test_monte_carlo_tracks_exact_enumeration():
    hands = [parse_cards("AsKs"), parse_cards("QhQd"), parse_cards("7c7d")]
    board = parse_cards("Jh Ts 2c")
    exact = equity(hands, board, mode="exact")
    sampled = equity(hands, board, mode="monte-carlo", trials=60_000, seed=7)
    for a, b in zip(exact.hands, sampled.hands):
        assert abs(a.equity_pct - b.equity_pct) < 1.0, (a.label, a.equity_pct, b.equity_pct)


def test_preflop_pair_versus_pair():
    # AA over KK is a very well known ~82% favourite.
    report = equity(
        [parse_cards("AsAd"), parse_cards("KsKh")],
        trials=120_000, seed=11,
    )
    assert not report.exact
    assert abs(report.hands[0].equity_pct - 82.6) < 1.0, report.hands[0].equity_pct


def test_preflop_pair_versus_two_overcards():
    # The classic coinflip: QQ is about 54% against AKs.
    report = equity(
        [parse_cards("QhQd"), parse_cards("AsKs")],
        trials=120_000, seed=13,
    )
    assert abs(report.hands[0].equity_pct - 53.4) < 1.0, report.hands[0].equity_pct


def test_equities_sum_to_one_hundred():
    hands = [parse_cards(t) for t in ("AsKs", "QhQd", "7c7d", "JdTd", "9s8s", "AcAh", "2c2d", "5h4h")]
    report = equity(hands, trials=20_000, seed=5)
    assert abs(sum(h.equity_pct for h in report.hands) - 100.0) < 1e-6


def test_rejects_duplicate_cards():
    for hands, board in [
        ([parse_cards("AsKs"), parse_cards("AsQd")], []),
        ([parse_cards("AsKs"), parse_cards("QhQd")], parse_cards("As 2c 3d")),
    ]:
        try:
            equity(hands, board)
        except ValueError as exc:
            assert "twice" in str(exc), exc
        else:
            raise AssertionError("duplicate card was not rejected")


def test_rejects_bad_input():
    for bad in ("Ax", "1s", "A", "AsK"):
        try:
            parse_cards(bad)
        except ValueError:
            continue
        raise AssertionError("%r should not parse" % bad)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL %s: %s" % (test.__name__, exc))
        else:
            print("ok   %s" % test.__name__)
    print("\n%d passed, %d failed" % (len(tests) - failures, failures))
    sys.exit(1 if failures else 0)
