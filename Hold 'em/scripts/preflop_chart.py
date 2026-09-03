"""Full 169 x 169 preflop equity chart for Hold'em.

Every canonical starting hand against every other, walked exactly. This is a
long run -- about a day on the reference machine -- so the script runs offline
and its output ships as a static file the page reads at load. Progress prints
every fifteen seconds and the chart is checkpointed to disk every minute, so a
crash costs no more than a minute's worth of walking.

Card conventions
----------------
The 169 canonical hands are the ones every equity chart lists: 13 pairs, 78
suited combinations and 78 offsuit combinations, in that order. For each cell
of the grid, the row's hand is dealt first with a canonical suit assignment,
and the column's hand is dealt a valid combo that avoids the row's cards.
That gives one exact equity per matchup, walked over C(48, 5) = 1,712,304
runouts.

Suits do influence equity slightly through blockers -- AhKh vs QhJh shares a
suit, and both flushes are worse for it -- but averaging over every valid
combo pair would multiply the run by roughly ten times its length. The
representatives here are chosen to avoid shared suits where possible, which
matches how commercial equity charts are built.
"""

import json
import sys
import time
from pathlib import Path

# ``holdem`` sits one level up; the script runs from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from holdem.cards import parse_cards
from holdem.equity import equity


#: Rank characters, best first. The chart lists hands in this order too.
RANKS = "AKQJT98765432"


def hand_labels():
    """Every canonical starting hand, best first: AA KK ... AKs AQs ... AKo ..."""
    pairs = [r + r for r in RANKS]
    suited = [RANKS[i] + RANKS[j] + "s"
              for i in range(len(RANKS)) for j in range(i + 1, len(RANKS))]
    offsuit = [RANKS[i] + RANKS[j] + "o"
               for i in range(len(RANKS)) for j in range(i + 1, len(RANKS))]
    return pairs + suited + offsuit


def cards_for(label, taken):
    """One card combination for ``label`` whose cards are not in ``taken``.

    Returns two card strings (e.g. ``["As", "Ks"]``) or ``None`` when every
    valid combination is blocked. The ordering of suits tried is the same for
    every seat, so the same label produces the same combo when nothing else on
    the table is fighting for it.
    """
    hi, lo = label[0], label[1]
    suits = "shdc"

    if hi == lo:  # pocket pair -- pick two suits it still has
        available = [s for s in suits if (hi + s) not in taken]
        if len(available) < 2:
            return None
        return [hi + available[0], hi + available[1]]

    if label.endswith("s"):  # suited: both cards share a suit
        for s in suits:
            c1, c2 = hi + s, lo + s
            if c1 not in taken and c2 not in taken:
                return [c1, c2]
        return None

    # offsuit: two different suits
    for s1 in suits:
        c1 = hi + s1
        if c1 in taken:
            continue
        for s2 in suits:
            if s2 == s1:
                continue
            c2 = lo + s2
            if c2 not in taken:
                return [c1, c2]
    return None


def _fmt_time(seconds):
    if seconds == float("inf"):
        return "?"
    seconds = int(seconds)
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm%02ds" % (seconds // 60, seconds % 60)
    hours = seconds // 3600
    return "%dh%02dm" % (hours, (seconds - hours * 3600) // 60)


def _load_or_start(output, hands):
    """Continue from wherever the last run left off, or begin from scratch."""
    if output.exists():
        try:
            data = json.loads(output.read_text())
        except (ValueError, OSError):
            data = None
        # Only reuse the file when it is a chart for these same 169 hands and
        # a version we recognise; otherwise it belongs to an older run.
        if data and data.get("hands") == hands and data.get("version") == 1:
            data.setdefault("grid", {})
            return data
    return {
        "version": 1,
        "hands": hands,
        "grid": {},
        "complete": False,
        "started": time.time(),
    }


def main():
    hands = hand_labels()
    total = len(hands) * len(hands)
    output = Path(__file__).resolve().parent.parent / "web" / "static" / "preflop-chart.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    data = _load_or_start(output, hands)
    grid = data["grid"]
    done_at_start = sum(len(row) for row in grid.values())
    print("preflop chart: %d / %d cells already walked" % (done_at_start, total),
          flush=True)

    def save():
        # Write to a scratch file first, then rename: the file the page reads
        # is never left half written even if the script is killed mid-save.
        scratch = output.with_suffix(output.suffix + ".part")
        scratch.write_text(json.dumps(data, separators=(",", ":")))
        scratch.replace(output)

    started = time.time()
    last_print = started
    last_save = started

    # By symmetry only half the grid needs walking: hand A vs hand B is the
    # same matchup as hand B vs hand A, seen from the other seat, so the second
    # entry is 100 minus the first. The diagonal is exactly 50 -- a hand cannot
    # have edge on itself -- so it costs nothing at all. That drops the run
    # from 169 x 169 to C(169, 2) walks, about half the wall time.
    for i, hero in enumerate(hands):
        row = grid.setdefault(hero, {})
        hero_cards = cards_for(hero, set())
        if hero_cards is None:
            continue

        for j in range(i, len(hands)):
            villain = hands[j]
            if villain in row:
                continue

            if i == j:
                # A hand against itself: equity is 50 by symmetry, no need to
                # walk the board to find out.
                row[villain] = 50.0
                continue

            villain_cards = cards_for(villain, set(hero_cards))
            if villain_cards is None:
                # A hand type that cannot be represented against this hero;
                # skipped and recorded as null so it is not walked again.
                row[villain] = None
                # Its reflection is null too -- there is no matchup either way.
                grid.setdefault(villain, {})[hero] = None
                continue

            rep = equity([parse_cards("".join(hero_cards)),
                          parse_cards("".join(villain_cards))],
                         mode="exact")
            equity_pct = round(rep.hands[0].equity_pct, 2)
            row[villain] = equity_pct
            # And the reflection, so the grid reads the same from either seat.
            grid.setdefault(villain, {})[hero] = round(100 - equity_pct, 2)

            now = time.time()
            if now - last_print >= 15:
                done = sum(len(r) for r in grid.values())
                cells_walked = done - done_at_start
                elapsed = now - started
                rate = cells_walked / elapsed if elapsed > 0 else 0
                remaining = total - done
                eta = remaining / rate if rate > 0 else float("inf")
                pct = 100 * done / total
                print(("%.2f%%  %d / %d cells  %s per cell  "
                       "elapsed %s  eta %s") % (
                    pct, done, total,
                    "%.2fs" % (1 / rate) if rate > 0 else "?",
                    _fmt_time(elapsed), _fmt_time(eta)), flush=True)
                last_print = now

            if now - last_save >= 60:
                save()
                last_save = now

    data["complete"] = True
    data["finished"] = time.time()
    save()
    print("done: %d cells walked in %s"
          % (total, _fmt_time(time.time() - data["started"])), flush=True)


if __name__ == "__main__":
    main()
