"""Command line front end for the Hold'em equity solver."""

import argparse
import json
import sys
from time import perf_counter

from .cards import cards_str, parse_cards
from .equity import DEFAULT_TRIALS, MAX_PLAYERS, equity


def _parse_hand(text):
    cards = parse_cards(text)
    if len(cards) != 2:
        raise ValueError("%r is %d cards; a Hold'em hand is exactly 2" % (text, len(cards)))
    return cards


def _prompt_for_input():
    """Ask for hands and a board when none were given on the command line."""
    print("Enter one hand per line (e.g. 'As Ks'). Blank line when done.")
    hands = []
    while len(hands) < MAX_PLAYERS:
        try:
            line = input("  hand %d: " % (len(hands) + 1)).strip()
        except EOFError:
            break
        if not line:
            break
        try:
            hands.append(_parse_hand(line))
        except ValueError as exc:
            print("    %s" % exc)
    try:
        board = parse_cards(input("  board (0-5 cards, blank for preflop): "))
    except EOFError:
        board = []
    return hands, board


def _render(report, elapsed):
    board = cards_str(report.board) or "(preflop)"
    if report.exact:
        how = "%s runout%s, exact" % (f"{report.trials:,}", "" if report.trials == 1 else "s")
    else:
        how = "%s simulations" % f"{report.trials:,}"
    print()
    print("Board: %s   %s in %.2fs" % (board, how, elapsed))
    print()

    show_hand = any(h.best_hand for h in report.hands)
    header = "  #  %-8s %9s %9s %9s" % ("Hand", "Equity", "Win", "Tie")
    if show_hand:
        header += "   Best hand"
    print(header)
    print("  " + "-" * (len(header) - 2))

    best = max(h.equity_pct for h in report.hands)
    for hand in report.hands:
        marker = "*" if hand.equity_pct >= best - 1e-9 else " "
        row = "%s %d  %-8s %8.2f%% %8.2f%% %8.2f%%" % (
            marker, hand.index + 1, hand.label,
            hand.equity_pct, hand.win_pct, hand.tie_pct,
        )
        if show_hand:
            row += "   %s" % hand.best_hand
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
                "equity": round(h.equity_pct, 4),
                "win": round(h.win_pct, 4),
                "tie": round(h.tie_pct, 4),
                "best_hand": h.best_hand,
            }
            for h in report.hands
        ],
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="holdem",
        description="Texas Hold'em equity calculator.",
        epilog="example: holdem AsKs QhQd 7c7d --board 'Jh Ts 2c'",
    )
    parser.add_argument(
        "hands", nargs="*", metavar="HAND",
        help="a two card hand such as AsKs (up to %d)" % MAX_PLAYERS,
    )
    parser.add_argument(
        "-b", "--board", default="", metavar="CARDS",
        help="0-5 community cards, e.g. 'Jh Ts 2c'",
    )
    parser.add_argument(
        "-t", "--trials", type=int, default=DEFAULT_TRIALS, metavar="N",
        help="Monte Carlo trials when the runouts cannot be enumerated (default %(default)s)",
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
            hands = [_parse_hand(h) for h in args.hands]
            board = parse_cards(args.board)
        else:
            hands, board = _prompt_for_input()
        started = perf_counter()
        report = equity(hands, board, trials=args.trials, seed=args.seed, mode=args.mode)
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
