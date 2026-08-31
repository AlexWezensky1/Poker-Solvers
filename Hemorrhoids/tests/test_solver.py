"""Tests for the HMRDS scoring rules and equity engines.

Run with pytest, or directly: ``python tests/test_solver.py``.
"""

import os
import random
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hmrds.cards import (  # noqa: E402
    FULL_DECK, HAND_SIZE, RANK_BIT, RANK_CHARS, STREETS, parse_cards, rank_mask,
)
from hmrds.equity import equity  # noqa: E402
from hmrds.scoring import (  # noqa: E402
    HIGH_VALUE, LOW_VALUE, build_profile, build_profiles, describe, resolve, showdown,
)

LAST = len(STREETS) - 1


def naive_settle(hands, board):
    """A deliberately plodding settlement to check the fast one against.

    Works on lists of cards and rank letters throughout -- no masks, no
    precomputed tables -- so it shares nothing with the engine but the rules.
    """
    n = len(hands)
    streets, at = [], 0
    for size in STREETS:
        streets.append(list(board[at:at + size]))
        at += size

    holding = [list(h) for h in hands]
    out_street = [None] * n
    turned = set()
    for street, cards in enumerate(streets):
        for card in cards:
            turned.add(RANK_CHARS[card >> 2])
        for seat in range(n):
            holding[seat] = [c for c in holding[seat] if RANK_CHARS[c >> 2] not in turned]
            if not holding[seat] and out_street[seat] is None:
                out_street[seat] = street

    def split(seats):
        pot = [0.0] * n
        for seat in seats:
            pot[seat] = 1.0 / len(seats)
        return pot

    early = [s for s in range(n) if out_street[s] is not None and out_street[s] < LAST]
    if early:
        first = min(out_street[s] for s in early)
        return split([s for s in early if out_street[s] == first])

    finished = [s for s in range(n) if out_street[s] == LAST]
    keepers = [s for s in range(n) if len(holding[s]) == HAND_SIZE]
    if finished or keepers:
        return split(finished + keepers)

    def total(seat, ace):
        score = 0
        for card in holding[seat]:
            letter = RANK_CHARS[card >> 2]
            if letter == "A":
                score += ace
            elif letter in "JQK":
                score += 10
            else:
                score += 10 if letter == "T" else int(letter)
        return score

    lows = [total(s, 1) for s in range(n)]
    highs = [total(s, 11) for s in range(n)]
    best_low, best_high = min(lows), max(highs)
    winners_low = [s for s in range(n) if lows[s] == best_low]
    winners_high = [s for s in range(n) if highs[s] == best_high]

    pot = [0.0] * n
    for seat in winners_high:
        pot[seat] += 0.5 / len(winners_high)
    for seat in winners_low:
        pot[seat] += 0.5 / len(winners_low)
    return pot


def settle(hands, board):
    """Run one complete board through the engine."""
    masks, tables = build_profiles(hands)
    boards, turned, at = [], 0, 0
    for size in STREETS:
        for card in board[at:at + size]:
            turned |= RANK_BIT[card]
        at += size
        boards.append(turned)
    return resolve(masks, tables, boards)[0]


def brute_equity(hands, board):
    """Every remaining board, choosing each street separately."""
    masks, tables = build_profiles(hands)
    dead = set(board)
    for hand in hands:
        dead.update(hand)
    deck = tuple(c for c in FULL_DECK if c not in dead)

    known, at = [], 0
    for size in STREETS:
        known.append(tuple(board[at:at + size]))
        at += size
    needs = [size - len(known[i]) for i, size in enumerate(STREETS)]

    pot = [0.0] * len(hands)
    seen = 0

    def walk(street, pool, turned, boards):
        nonlocal seen
        if street == len(STREETS):
            share = resolve(masks, tables, boards)[0]
            for i in range(len(hands)):
                pot[i] += share[i]
            seen += 1
            return
        base = turned
        for card in known[street]:
            base |= RANK_BIT[card]
        for extra in combinations(pool, needs[street]):
            mask = base
            for card in extra:
                mask |= RANK_BIT[card]
            walk(street + 1, tuple(c for c in pool if c not in extra), mask, boards + [mask])

    walk(0, deck, 0, [])
    return [100.0 * p / seen for p in pot]


def test_card_values():
    assert LOW_VALUE[0] == 2 and HIGH_VALUE[0] == 2          # deuce
    assert LOW_VALUE[8] == 10 and HIGH_VALUE[8] == 10        # ten
    for rank in (9, 10, 11):                                 # jack, queen, king
        assert LOW_VALUE[rank] == 10 and HIGH_VALUE[rank] == 10
    assert LOW_VALUE[12] == 1 and HIGH_VALUE[12] == 11       # ace


def test_every_ace_counts_both_ways():
    for text, expected in (("As", (1, 11)), ("AsAh", (2, 22)), ("AsAhAd", (3, 33))):
        mask, table = build_profile(parse_cards(text))
        _, low, high = table[mask]
        assert (low, high) == expected, (text, low, high)


def test_lone_ace_scoops_lone_jack():
    """The worked example: 1 beats 10 for the low, 11 beats 10 for the high."""
    hands = [parse_cards("As2h3h5h7h"), parse_cards("Jh2d3d5d7d")]
    board = parse_cards("2s2c3s3c5s5c7cTh9h8h")
    assert settle(hands, board) == [1.0, 0.0]


def test_high_low_ties_split_their_own_half():
    """4 vs 4 vs 36 pays 25 / 25 / 50."""
    hands = [parse_cards("4s2h3h5h7h"), parse_cards("4h2d3d5d7d"), parse_cards("KsQsJs6s7s")]
    board = parse_cards("2s2c3s3c5s5c7cTh9h8h")
    assert settle(hands, board) == [0.25, 0.25, 0.5]


def test_high_and_low_halves_are_reported_separately():
    """Same 4 / 4 / 36 board, read as two halves instead of one pot."""
    hands = [parse_cards("4s2h3h5h7h"), parse_cards("4h2d3d5d7d"), parse_cards("KsQsJs6s7s")]
    board = parse_cards("2s2c3s3c5s5c7cTh9h8h")
    report = equity(hands, board)
    assert [round(h.high_pct, 6) for h in report.hands] == [0.0, 0.0, 100.0]
    assert [round(h.low_pct, 6) for h in report.hands] == [50.0, 50.0, 0.0]
    # Nothing here is won outright, so each seat's equity is exactly half of
    # each half it takes.
    for hand in report.hands:
        assert abs(hand.equity_pct - 0.5 * (hand.high_pct + hand.low_pct)) < 1e-9


def test_a_pot_won_outright_counts_in_neither_half():
    """Out before the last card takes the lot, which is never split in two."""
    hands = [parse_cards("KsKhQsQhJs"), parse_cards("2h2d3h3d4h")]
    board = parse_cards("KcQcJcTs" "2c3c4c" "5s6s" "7s")
    winner = equity(hands, board).hands[0]
    assert winner.equity_pct == 100.0 and winner.out_pct == 100.0
    assert winner.high_pct == 0.0 and winner.low_pct == 0.0


def test_one_card_discards_every_match():
    """A single queen takes both queens out of the hand at once."""
    mask, table = build_profile(parse_cards("QsQhJs9s2s"))
    survivors = mask & ~rank_mask(parse_cards("Qc"))
    assert table[survivors][0] == 3


def test_earliest_out_wins_outright():
    hands = [parse_cards("KsKhQsQhJs"), parse_cards("2h2d3h3d4h")]
    board = parse_cards("KcQcJcTs" "2c3c4c" "5s6s" "7s")
    assert settle(hands, board) == [1.0, 0.0]


def test_simultaneous_outs_split():
    hands = [parse_cards("KsKhKdQsQh"), parse_cards("2h2d2c3h3d")]
    board = parse_cards("KcQc2s3s" "7s8s9s" "TsJs" "4s")
    assert settle(hands, board) == [0.5, 0.5]


def test_out_on_last_card_with_no_keeper_takes_everything():
    hands = [parse_cards("KsKhKdQsQh"), parse_cards("2h3h4h5h6h")]
    board = parse_cards("Kc2s3s7s" "8s9sTs" "JcJd" "Qc")
    assert settle(hands, board) == [1.0, 0.0]


def test_out_on_last_card_splits_with_a_keeper():
    hands = [parse_cards("KsKhKdQsQh"), parse_cards("2h3h4h5h6h")]
    board = parse_cards("Kc7s8s9s" "TsJcJd" "Td9d" "Qc")
    assert settle(hands, board) == [0.5, 0.5]


def test_keeper_alone_takes_everything():
    hands = [parse_cards("KsKhKdQsQh"), parse_cards("2h3h4h5h6h")]
    board = parse_cards("Kc7s8s9s" "TsJcJd" "Td9d" "Ac")
    assert settle(hands, board) == [0.0, 1.0]


def test_engine_matches_the_plodding_rules():
    """Random boards, settled twice by unrelated code paths."""
    rng = random.Random(20240817)
    for _ in range(4000):
        deck = list(FULL_DECK)
        rng.shuffle(deck)
        seats = rng.randint(2, 4)
        hands = [tuple(deck[i * HAND_SIZE:(i + 1) * HAND_SIZE]) for i in range(seats)]
        board = tuple(deck[seats * HAND_SIZE:seats * HAND_SIZE + sum(STREETS)])
        fast, slow = settle(hands, board), naive_settle(hands, board)
        assert max(abs(a - b) for a, b in zip(fast, slow)) < 1e-12, (hands, board, fast, slow)
        assert abs(sum(fast) - 1.0) < 1e-12


def test_exact_matches_brute_force():
    cases = [
        (["AsKsQsJsTs", "2h3h4h5h6h"], "2c3c4c5c7h8h9hJdQd"),
        (["AsKsQsJsTs", "2h3h4h5h6h"], "2c3c4c5c7h8h9h"),
        (["KsKhQsQhJs", "2h3h4h5h6h"], "Ac3c4c5c7h8h9h"),
        (["AsAhKsKhQs", "2h2d3h3d4h"], "Tc9c8c7c6h5d4c"),
    ]
    for texts, board_text in cases:
        hands = [parse_cards(t) for t in texts]
        board = parse_cards(board_text)
        report = equity(hands, board, mode="exact")
        reference = brute_equity(hands, board)
        for got, want in zip(report.hands, reference):
            assert abs(got.equity_pct - want) < 1e-9, (board_text, got.equity_pct, want)


def test_exact_and_sampling_agree():
    hands = [parse_cards("AsKsQsJsTs"), parse_cards("2h3h4h5h6h")]
    board = parse_cards("2s3s4s7s")
    exact = equity(hands, board, mode="exact")
    sampled = equity(hands, board, mode="monte-carlo", trials=200_000, seed=11)
    for a, b in zip(exact.hands, sampled.hands):
        assert abs(a.equity_pct - b.equity_pct) < 0.5, (a.equity_pct, b.equity_pct)


def test_equity_always_adds_up():
    for board in ("", "2s3s4s7s", "2s3s4s7s8h9hTh"):
        report = equity(
            [parse_cards("AsKsQsJsTs"), parse_cards("2h3h4h5h6h"), parse_cards("7c7d8c8d9c")],
            parse_cards(board), trials=20_000, seed=5,
        )
        assert abs(sum(h.equity_pct for h in report.hands) - 100.0) < 1e-6


def test_pairs_beat_broadway():
    """Fewer distinct ranks means fewer cards to dodge, so pairs go out far more."""
    report = equity(
        [parse_cards("KsKhQsQhJs"), parse_cards("AcKdQdJdTd")],
        trials=40_000, seed=2, mode="monte-carlo",
    )
    pairs, broadway = report.hands
    assert pairs.out_pct > broadway.out_pct
    assert pairs.equity_pct > broadway.equity_pct


def test_describe_reads_a_finished_hand():
    hands = [parse_cards("As2h3h5h7h"), parse_cards("Jh2d3d5d7d")]
    board = parse_cards("2s2c3s3c5s5c7cTh9h8h")
    report = equity(hands, board)
    assert "1 low" in report.hands[0].detail and "11 high" in report.hands[0].detail
    assert report.hands[1].detail.startswith("J ")


def test_discards_are_just_part_of_the_hand():
    """Naming a hand as held plus discarded settles exactly as the whole hand."""
    board = parse_cards("2s2c3s3c5s5c7cTh9h8h")
    whole = equity([parse_cards("As2h3h5h7h"), parse_cards("Jh2d3d5d7d")], board)
    split = equity(
        [parse_cards("As"), parse_cards("Jh")], board,
        discards=[parse_cards("2h3h5h7h"), parse_cards("2d3d5d7d")],
    )
    for a, b in zip(whole.hands, split.hands):
        assert abs(a.equity_pct - b.equity_pct) < 1e-9, (a.equity_pct, b.equity_pct)


def test_unknown_cards_cannot_be_ones_the_board_already_matched():
    """A matched card would be lying face up, so it can never be the hidden one.

    The board covers ranks 2-6 exactly. Hero holds a lone ace after four
    discards; the villain has four discards and one unknown card. That card can
    only be a rank the board has not shown, so the villain always still holds
    it and can never have gone out. Hero then scoops unless the villain happens
    to hold an ace too, which ties both halves.

    31 cards could still be hidden and 3 of them are aces, so hero's equity is
    exactly (28 + 3 * 0.5) / 31.
    """
    board = parse_cards("2s2h3s3h" "4s4h5s" "5h6s" "6h")
    report = equity(
        [parse_cards("Ah"), []], board,
        discards=[parse_cards("2d3d4d5d"), parse_cards("2c3c4c5c")],
        trials=100_000, seed=17,
    )
    assert report.hands[1].unknown == 1
    assert report.hands[1].out_pct == 0.0
    expected = 100.0 * (28 + 3 * 0.5) / 31
    assert abs(report.hands[0].equity_pct - expected) < 0.3, (
        report.hands[0].equity_pct, expected)


def test_exact_refuses_unknown_cards():
    try:
        equity([parse_cards("AsKsQsJsTs"), parse_cards("2h3h")], (), mode="exact")
    except ValueError as exc:
        assert "monte-carlo" in str(exc), exc
    else:
        raise AssertionError("exact should not accept an unknown card")


def test_rejects_bad_hands():
    good = parse_cards("AsKsQsJsTs")
    for hands, board, discards, expected in (
        ([good], (), None, "at least 2"),
        ([good, parse_cards("2h3h4h5h6h7h")], (), None, "more than the 5"),
        ([good, parse_cards("AsKsQsJsTs")], (), None, "twice"),
        ([good, parse_cards("2h3h4h5h6h")],
         parse_cards("2s3s4s5s6s7s8s9sTsJsQs"), None, "at most 10"),
        ([good, parse_cards("2h3h4h")], (), [(), parse_cards("5h6h")], "no community card"),
    ):
        try:
            equity(hands, board, discards=discards)
        except ValueError as exc:
            assert expected in str(exc), (expected, str(exc))
        else:
            raise AssertionError("%r should have been rejected" % expected)


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
