"""Command line front end for the HMRDS equity solver."""

import argparse
import json
import sys
from time import perf_counter

from .cards import BOARD_SIZE, HAND_SIZE, cards_str, parse_cards
from .equity import DEFAULT_TRIALS, MAX_PLAYERS, equity


def _parse_hand(text):
    """Parse ``HELD`` or ``HELD/DISCARDED``, returning the two piles.

    Whatever the two do not account for is an unknown card still in the hand,
    so ``/2h3h`` is a player whose discards you can see but whose remaining
    three cards you cannot.
    """
    held_text, slash, discard_text = text.partition("/")
    held = parse_cards(held_text)
    discarded = parse_cards(discard_text) if slash else []
    named = len(held) + len(discarded)
    if named > HAND_SIZE:
        raise ValueError("%r names %d cards; a hand is %d" % (text, named, HAND_SIZE))
    if not named:
        raise ValueError("%r names no cards" % text)
    return held, discarded


def _prompt_for_input():
    """Ask for hands and a board when none were given on the command line."""
    print("Enter one hand per line (e.g. 'As Ks Qs Js Ts', or 'AsKs/2h3h' with discards).")
    print("Blank line when done.")
    hands, discards = [], []
    while len(hands) < MAX_PLAYERS:
        try:
            line = input("  hand %d: " % (len(hands) + 1)).strip()
        except EOFError:
            break
        if not line:
            break
        try:
            held, tossed = _parse_hand(line)
        except ValueError as exc:
            print("    %s" % exc)
            continue
        hands.append(held)
        discards.append(tossed)
    try:
        board = parse_cards(input("  board (0-%d cards, blank for the deal): " % BOARD_SIZE))
    except EOFError:
        board = []
    return hands, discards, board


def _render(report, elapsed):
    board = cards_str(report.board) or "(opening deal)"
    how = "exact" if report.exact else "%s simulations" % f"{int(report.trials):,}"
    print()
    print("Board: %s   %s in %.2fs" % (board, how, elapsed))
    print()

    show_detail = any(h.detail for h in report.hands)
    width = max(len(h.label) for h in report.hands)
    header = "  #  %-*s %9s %9s %9s %9s %9s %9s" % (
        width, "Hand", "Equity", "High", "Low", "Scoop", "Out", "Keep")
    if show_detail:
        header += "   Finish"
    print(header)
    print("  " + "-" * (len(header) - 2))

    best = max(h.equity_pct for h in report.hands)
    for hand in report.hands:
        marker = "*" if hand.equity_pct >= best - 1e-9 else " "
        row = "%s %d  %-*s %8.2f%% %8.2f%% %8.2f%% %8.2f%% %8.2f%% %8.2f%%" % (
            marker, hand.index + 1, width, hand.label,
            hand.equity_pct, hand.high_pct, hand.low_pct,
            hand.scoop_pct, hand.out_pct, hand.keep_pct,
        )
        if show_detail:
            row += "   %s" % hand.detail
        print(row)
    print()


def _as_dict(report, elapsed):
    return {
        "board": cards_str(report.board),
        "mode": report.mode,
        "trials": report.trials,
        "seconds": round(elapsed, 4),
        "hands": [
            {
                "index": h.index + 1,
                "hand": h.label,
                "unknown": h.unknown,
                "equity": round(h.equity_pct, 4),
                "high": round(h.high_pct, 4),
                "low": round(h.low_pct, 4),
                "scoop": round(h.scoop_pct, 4),
                "out": round(h.out_pct, 4),
                "keep": round(h.keep_pct, 4),
                "detail": h.detail,
            }
            for h in report.hands
        ],
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="hmrds",
        description="HMRDS equity calculator.",
        epilog="example: hmrds AsKsQsJsTs 2h3h4h5h6h --board '2c3c4c5c 7h8h9h'",
    )
    parser.add_argument(
        "hands", nargs="*", metavar="HAND",
        help="a %d card hand such as AsKsQsJsTs, or HELD/DISCARDED such as "
             "AsKsQs/2h3h; anything unnamed is an unknown card still held "
             "(up to %d hands)" % (HAND_SIZE, MAX_PLAYERS),
    )
    parser.add_argument(
        "-b", "--board", default="", metavar="CARDS",
        help="0-%d community cards in dealing order, e.g. '2c3c4c5c 7h8h9h'" % BOARD_SIZE,
    )
    parser.add_argument(
        "-t", "--trials", type=int, default=DEFAULT_TRIALS, metavar="N",
        help="Monte Carlo trials when the runouts cannot be walked (default %(default)s)",
    )
    parser.add_argument(
        "-m", "--mode", choices=("auto", "exact", "monte-carlo"), default="auto",
        help="runout strategy (default %(default)s)",
    )
    parser.add_argument("--seed", type=int, default=None, help="seed the sampler for repeatable runs")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        if args.hands:
            parsed = [_parse_hand(h) for h in args.hands]
            hands = [held for held, _ in parsed]
            discards = [tossed for _, tossed in parsed]
            board = parse_cards(args.board)
        else:
            hands, discards, board = _prompt_for_input()
        started = perf_counter()
        report = equity(hands, board, discards=discards,
                        trials=args.trials, seed=args.seed, mode=args.mode)
        elapsed = perf_counter() - started
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(_as_dict(report, elapsed), indent=2))
    else:
        _render(report, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
