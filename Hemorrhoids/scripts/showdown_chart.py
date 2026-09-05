"""Showdown chart for HMRDS: every hand shape against every other, by top card.

Suits are irrelevant in HMRDS -- ``hmrds.cards`` says so outright, nothing in
the game ever reads one -- and the order of cards within a hand does not matter
either. A hand is therefore a multiset of five ranks, and there are 6,175 of
them once no rank may appear more than four times.

That is 19,062,225 unordered pairs. Each matchup is solved exactly, walking
every runout of the ten card board, and an exact solve averages about 0.76
seconds. The whole pairing is therefore roughly 168 days of single core work,
so this script does not attempt it.

What it does instead: the chart being built is only 13 x 13 -- the row is the
highest card in one hand, the column the highest card in the other -- so a cell
is an average over a great many matchups and does not need all of them to
settle. Cells are sampled round robin, one new matchup each per pass, so the
grid stays evenly covered and every cell carries the same weight no matter when
the run is stopped. Every matchup that is counted was walked exactly; it is the
choice of which pairs to walk that is sampled, never the runouts inside one.

Run it and leave it::

    python scripts/showdown_chart.py               # until interrupted
    python scripts/showdown_chart.py --hours 12    # or for a fixed spell

Progress prints every fifteen seconds and the chart is written every minute, so
stopping it at any moment -- Ctrl-C, a closed laptop, a power cut -- costs at
most a minute and leaves a chart that is already readable. Re-running resumes
from whatever is on disk and keeps drawing fresh pairs.
"""

import argparse
import json
import os
import random
import signal
import sys
import time
from collections import Counter
from itertools import combinations_with_replacement
from pathlib import Path

# ``hmrds`` sits one level up; the script runs from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hmrds.cards import HAND_SIZE, RANK_CHARS, make_card
from hmrds.equity import equity

#: Rank characters best first, which is the order the grid is drawn in.
RANKS = "AKQJT98765432"

#: Rank index 0..12 is deuce..ace, so the chart's row 0 is index 12.
ORDER = [RANK_CHARS.index(r) for r in RANKS]

HERE = Path(__file__).resolve().parent.parent
OUTPUT = HERE / "web" / "static" / "showdown-chart.json"
PARTIAL = OUTPUT.with_suffix(".json.part")

CHECKPOINT_SECONDS = 60
PROGRESS_SECONDS = 15


def hand_shapes():
    """Every five card hand as a sorted rank multiset, no rank more than four."""
    return [shape for shape in combinations_with_replacement(range(13), HAND_SIZE)
            if max(Counter(shape).values()) <= 4]


def label(shape):
    """``(12, 12, 11, 3, 3)`` reads as ``AAK55``, best card first."""
    return "".join(RANK_CHARS[r] for r in sorted(shape, reverse=True))


def compatible(left, right):
    """True when both hands can be dealt from one deck at the same time."""
    counts = Counter(left) + Counter(right)
    return max(counts.values()) <= 4


def deal(left, right):
    """Concrete cards for two shapes, suits assigned so nothing collides.

    Any assignment does, since no part of HMRDS reads a suit; this one just
    hands out the next unused suit of each rank.
    """
    used = Counter()
    out = []
    for shape in (left, right):
        cards = []
        for rank in shape:
            cards.append(make_card(rank, used[rank]))
            used[rank] += 1
        out.append(cards)
    return out


def solve(task):
    """One matchup, walked exactly. Returns the equity share of each side."""
    left, right = task
    hands = deal(left, right)
    report = equity(hands, mode="exact")
    return left, right, report.hands[0].equity_pct, report.hands[1].equity_pct


class Chart:
    """The 13 x 13 grid, plus enough state to stop and start again."""

    def __init__(self):
        # totals[row][col] is the summed equity of hands topped by RANKS[row]
        # against hands topped by RANKS[col]; counts is how many went into it.
        self.totals = [[0.0] * 13 for _ in range(13)]
        self.counts = [[0] * 13 for _ in range(13)]
        self.seen = set()
        self.matchups = 0
        self.started = time.time()
        self.seconds = 0.0

    def add(self, left, right, left_pct, right_pct):
        row = ORDER.index(max(left))
        col = ORDER.index(max(right))
        self.totals[row][col] += left_pct
        self.counts[row][col] += 1
        self.totals[col][row] += right_pct
        self.counts[col][row] += 1
        self.matchups += 1

    def payload(self, complete=False, finished=False):
        grid = {}
        for row in range(13):
            for col in range(13):
                count = self.counts[row][col]
                if not count:
                    continue
                grid[RANKS[row] + RANKS[col]] = {
                    "equity": round(self.totals[row][col] / count, 4),
                    "matchups": count,
                }
        return {
            "version": 1,
            "game": "HMRDS",
            "ranks": list(RANKS),
            "grid": grid,
            "matchups": self.matchups,
            "pairs_total": 19062225,
            # complete: every pair walked. finished: the run stopped of its own
            # accord rather than being checkpointed mid-flight. A chart can be
            # finished without being complete, which is the usual case here.
            "complete": complete,
            "finished": finished or complete,
            "started": self.started,
            "updated": time.time(),
            "seconds": round(self.seconds, 1),
        }

    def write(self, complete=False, finished=False):
        PARTIAL.parent.mkdir(parents=True, exist_ok=True)
        PARTIAL.write_text(json.dumps(self.payload(complete, finished), indent=2),
                           encoding="utf-8")
        os.replace(PARTIAL, OUTPUT)

    def load(self):
        """Pick up where an earlier run left off, if it left anything."""
        if not OUTPUT.exists():
            return False
        try:
            data = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except ValueError:
            return False
        if data.get("version") != 1:
            return False
        for key, cell in data.get("grid", {}).items():
            row, col = RANKS.index(key[0]), RANKS.index(key[1])
            self.counts[row][col] = cell["matchups"]
            self.totals[row][col] = cell["equity"] * cell["matchups"]
        self.matchups = data.get("matchups", 0)
        self.started = data.get("started", self.started)
        self.seconds = data.get("seconds", 0.0)
        return True


def draw(rng, by_top, row, col, seen, attempts=60):
    """A pair not walked before: one hand topped by ``row``, one by ``col``."""
    left_pool, right_pool = by_top[row], by_top[col]
    if not left_pool or not right_pool:
        return None
    for _ in range(attempts):
        left = rng.choice(left_pool)
        right = rng.choice(right_pool)
        if left == right or not compatible(left, right):
            continue
        key = (left, right) if left <= right else (right, left)
        if key in seen:
            continue
        seen.add(key)
        return left, right
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=float, default=None,
                        help="stop after this long; runs until interrupted otherwise")
    parser.add_argument("--workers", type=int, default=None,
                        help="worker processes (default: one per core, less one)")
    parser.add_argument("--seed", type=int, default=1, help="sampling seed")
    args = parser.parse_args()

    shapes = hand_shapes()
    by_top = {row: [s for s in shapes if ORDER.index(max(s)) == row]
              for row in range(13)}
    live = [(row, col) for row in range(13) for col in range(13)
            if by_top[row] and by_top[col]]

    print("%d hand shapes, %d live cells of 169" % (len(shapes), len(live)))
    empty = [RANKS[r] for r in range(13) if not by_top[r]]
    if empty:
        print("no hand can be topped by: %s" % ", ".join(empty))

    chart = Chart()
    if chart.load():
        print("resuming: %d matchups already walked" % chart.matchups)

    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    print("walking with %d workers, writing to %s" % (workers, OUTPUT.name))
    print("every matchup is exact; the pairs walked are sampled", flush=True)

    stopping = {"now": False}

    def stop(signum, frame):
        stopping["now"] = True
        print("\nstopping, finishing the batch in flight...", flush=True)

    signal.signal(signal.SIGINT, stop)

    rng = random.Random(args.seed)
    exhausted = set()   # cells with no pair left to draw
    misses = {}         # consecutive failed draws, per cell
    deadline = time.time() + args.hours * 3600 if args.hours else None
    begin = time.time()
    # `begin` restarts at every checkpoint so machine time accumulates cleanly.
    # Progress needs a clock that does not, or the rate reads as the whole run's
    # matchups over one minute and comes out ten thousand a second.
    session_begin = begin
    session_base = chart.matchups
    last_checkpoint = last_progress = begin

    # A pool is only worth its overhead because a single exact walk is slow;
    # batches are one pass over the live cells, which keeps coverage even.
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=workers) as pool:
        while not stopping["now"]:
            if deadline and time.time() > deadline:
                print("\nreached the time asked for", flush=True)
                break

            batch = []
            for row, col in live:
                if (row, col) in exhausted:
                    continue
                pair = draw(rng, by_top, row, col, chart.seen)
                if pair:
                    batch.append(pair)
                    misses.pop((row, col), None)
                    continue
                # A low cell runs dry fast: only four hands can be topped by a
                # three, and most pairs of those want more than four of a rank.
                misses[(row, col)] = misses.get((row, col), 0) + 1
                if misses[(row, col)] >= 3:
                    exhausted.add((row, col))
            if not batch:
                print("\nevery pair has been walked", flush=True)
                chart.seconds += time.time() - begin
                chart.write(complete=True)
                return

            for left, right, left_pct, right_pct in pool.map(solve, batch, chunksize=1):
                chart.add(left, right, left_pct, right_pct)

            now = time.time()
            if now - last_progress >= PROGRESS_SECONDS:
                spent = now - session_begin
                rate = (chart.matchups - session_base) / spent if spent else 0
                open_cells = sorted(chart.counts[r][c] for r, c in live
                                    if (r, c) not in exhausted)
                middle = open_cells[len(open_cells) // 2] if open_cells else 0
                print("%8d matchups  %5.1f/s  median cell %d  %d cells full  %s elapsed"
                      % (chart.matchups, rate, middle, len(exhausted), human(spent)),
                      flush=True)
                last_progress = now
            if now - last_checkpoint >= CHECKPOINT_SECONDS:
                chart.seconds += now - begin
                begin = now
                chart.write()
                last_checkpoint = now

    chart.seconds += time.time() - begin
    chart.write(finished=True)
    print("wrote %d matchups to %s" % (chart.matchups, OUTPUT), flush=True)


def human(seconds):
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%dh%02dm" % (hours, minutes)
    return "%dm%02ds" % (minutes, secs)


if __name__ == "__main__":
    main()
