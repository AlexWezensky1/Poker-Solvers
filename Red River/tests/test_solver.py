"""Tests for the Red River evaluator and equity engine.

Run with pytest, or directly: ``python tests/test_solver.py``.
"""

import os
import random
import sys
from collections import Counter
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from redriver.cards import FULL_DECK, parse_cards  # noqa: E402
from redriver.cards import is_red  # noqa: E402
from redriver.equity import (  # noqa: E402
    MAX_BOARD, equity, holdem_made, is_complete, _sample,
)
from redriver.evaluator import (  # noqa: E402
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


def test_a_suit_thirteen_deep_is_still_a_flush():
    """The board can run long enough to hold every card of a suit. The quick
    flush test adds three to each four bit count and reads the top bit, which
    carries out of the nibble at thirteen -- so this used to come back as a
    high card while holding a royal flush."""
    hand = parse_cards("As Ks Qs Js Ts 9s 8s 7s 6s 5s 4s 3s 2s 2d 3d 4d 5d")
    assert describe(score(hand)) == "royal flush", describe(score(hand))


def test_a_board_is_finished_only_when_it_ends_black():
    for text, done in [
        ("Jh Ts 2c 5d 7s", True),    # the river came black straight away
        ("Jh Ts 2c 5d 7h", False),   # red, so another card follows
        ("Jh Ts 2c 5d 7h 8c", True),  # and it came black
        ("Jh Ts 2c 5d 7h 8d", False),  # two reds, still going
        ("Jh Ts 2c", False),         # the turn is not even out
    ]:
        assert is_complete(parse_cards(text)) is done, text


def test_a_black_card_cannot_have_cards_after_it():
    """A black river ends the hand, so nothing can have been dealt behind it."""
    hands = [parse_cards("AsKs"), parse_cards("QhQd")]
    equity(hands, parse_cards("Jh Ts 2c 5d 7h 8c"))  # fine: black is last
    try:
        equity(hands, parse_cards("Jh Ts 2c 5d 7s 8h"))
    except ValueError as exc:
        assert "ends there" in str(exc), exc
    else:
        raise AssertionError("a card dealt after a black river should be refused")


def test_a_finished_board_is_one_runout():
    report = equity([parse_cards("2c 3d"), parse_cards("2h 3s")],
                    parse_cards("As Ks Qh Jd Tc"), mode="exact")
    assert report.exact and report.trials == 1
    assert report.hands[0].equity_pct == 50.0
    assert report.hands[1].equity_pct == 50.0
    assert report.hands[0].best_hand == "straight, A high"


def test_the_extra_cards_count_towards_the_hand():
    """The sixth board card is as real as the fifth. Here it makes the flush
    that the five-card board alone does not."""
    hands = [parse_cards("AsKs"), parse_cards("QhQd")]
    five = equity(hands, parse_cards("2s 7s 9d Jc 4c"), mode="exact")
    six = equity(hands, parse_cards("2s 7s 9d Jc 4h 5s"), mode="exact")
    assert "flush" not in five.hands[0].best_hand, five.hands[0].best_hand
    assert five.hands[0].equity_pct == 0.0
    assert six.hands[0].best_hand.startswith("flush"), six.hands[0].best_hand
    assert six.hands[0].equity_pct == 100.0


def test_every_sampled_board_ends_black_and_is_long_enough():
    rng = random.Random(4)
    hands = [parse_cards("AsKs"), parse_cards("QhQd")]
    dead = {c for hand in hands for c in hand}
    deck = [c for c in FULL_DECK if c not in dead]
    lengths = set()
    for _ in range(3000):
        drawn = _sample((), deck, rng)
        assert len(drawn) >= 5, drawn
        assert len(drawn) <= MAX_BOARD, drawn
        assert not is_red(drawn[-1]), "a board has to finish on a black card"
        lengths.add(len(drawn))
    # Five is the common case, but the river does run on.
    assert 5 in lengths and max(lengths) > 5, lengths


def test_longer_boards_get_rarer_by_about_half():
    """Each extra card needs another red, so the tail should roughly halve."""
    rng = random.Random(11)
    hands = [parse_cards("AsKs"), parse_cards("QhQd")]
    dead = {c for hand in hands for c in hand}
    deck = [c for c in FULL_DECK if c not in dead]
    counts = Counter(len(_sample((), deck, rng)) for _ in range(20000))
    for length in (5, 6, 7):
        ratio = counts[length + 1] / counts[length]
        assert 0.4 < ratio < 0.65, (length, ratio, counts)


def test_monte_carlo_tracks_the_finished_board():
    """Sampling a board that cannot move must land on its one answer."""
    hands = [parse_cards("AsKs"), parse_cards("QhQd"), parse_cards("7c7d")]
    board = parse_cards("Ah Kd Qc Jh Tc")
    walked = equity(hands, board, mode="exact")
    sampled = equity(hands, board, mode="monte-carlo", trials=200, seed=7)
    for a, b in zip(walked.hands, sampled.hands):
        assert abs(a.equity_pct - b.equity_pct) < 1e-9, (a.label, a.equity_pct)


def test_forcing_the_walk_falls_back_while_the_river_can_still_run():
    report = equity([parse_cards("AsKs"), parse_cards("QhQd")],
                    parse_cards("Jh Ts 2c 5d"), mode="exact",
                    trials=2_000, seed=3)
    assert report.mode == "monte-carlo", report.mode


def test_equities_sum_to_one_hundred():
    hands = [parse_cards(t) for t in ("AsKs", "QhQd", "7c7d", "JdTd")]
    report = equity(hands, trials=4_000, seed=5)
    assert abs(sum(h.equity_pct for h in report.hands) - 100.0) < 1e-6


def test_made_odds_cover_every_runout():
    report = equity([parse_cards("AsKs"), parse_cards("QhQd")],
                    trials=4_000, seed=2)
    for hand in report.hands:
        assert abs(sum(pct for _, pct in hand.made_pct) - 100.0) < 1e-6


def test_rejects_duplicate_cards():
    try:
        equity([parse_cards("AsKs"), parse_cards("AsQd")])
    except ValueError as exc:
        assert "As" in str(exc), exc
    else:
        raise AssertionError("a card used twice should be refused")


def test_rejects_bad_input():
    for hands, board, expected in (
        ([parse_cards("AsKs")], (), "at least 2"),
        ([parse_cards("AsKs"), parse_cards("Qh")], (), "expected 2"),
    ):
        try:
            equity(hands, board)
        except ValueError as exc:
            assert expected in str(exc), (expected, exc)
        else:
            raise AssertionError("expected %r to be refused" % expected)


def test_holdem_baseline_stops_at_five_community_cards():
    """Red River's river runs on; the baseline is the same deal read as
    Hold'em, which stops at the fifth card whatever colour it was."""
    hands = [parse_cards("AsKs"), parse_cards("QhQd")]
    board = parse_cards("Jh Ts 2c 5d 7h 8c")   # six out: 7h kept it alive, 8c ended it

    there = holdem_made(hands, board, mode="exact")
    for row in there:
        # Five cards are already out, so the baseline has nothing to walk and
        # each hand lands in exactly one category.
        assert sorted(row)[-1] == 1.0
        assert abs(sum(row) - 1.0) < 1e-9


def test_holdem_baseline_walks_what_is_still_to_come():
    hands = [parse_cards("AsKs"), parse_cards("QhQd")]
    board = parse_cards("Jh Ts 2c")   # a flop; two cards still to come
    rows = holdem_made(hands, board, mode="exact")
    for row in rows:
        assert abs(sum(row) - 1.0) < 1e-9
    # Spread across more than one category, since the board is not settled.
    assert sum(1 for share in rows[0] if share > 0) > 1

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
