# Texas Hold'em Solver

Equity calculator for Texas Hold'em. Give it up to eight two-card hands and up
to five community cards; it returns each hand's chance to win, chop, and its
overall share of the pot. Runs as a command line tool and as a small web app.

## Quick start

```bash
python -m holdem AsKs QhQd --board "Jh Ts 2c"
```

```
Board: Jh Ts 2c   990 runouts, exact in 0.00s

  #  Hand        Equity       Win       Tie
  -----------------------------------------
  1  As Ks       32.42%    32.42%     0.00%
* 2  Qh Qd       67.58%    67.58%     0.00%
```

No dependencies are needed for the command line tool — the engine is pure
standard library. The web app needs FastAPI:

```bash
pip install -r requirements.txt
uvicorn web.app:app --reload
```

Then open http://127.0.0.1:8000.

## Card notation

A card is a rank followed by a suit, e.g. `As`, `Th`, `7d`, `2c`.

- ranks `23456789TJQKA` (`10` is accepted for `T`)
- suits `s` spades, `h` hearts, `d` diamonds, `c` clubs

Hands and boards can be written packed (`AsKs`) or spaced (`As Ks`), in any case.

## Command line

```
python -m holdem [HAND ...] [-b BOARD] [-t TRIALS] [-m MODE] [--seed N] [--json]
```

| Option | Meaning |
| --- | --- |
| `HAND ...` | up to 8 two-card hands; run with none to be prompted |
| `-b`, `--board` | 0-5 community cards |
| `-t`, `--trials` | Monte Carlo trials (default 100,000) |
| `-m`, `--mode` | `auto`, `exact` or `monte-carlo` |
| `--seed` | seed the sampler so a run repeats exactly |
| `--json` | machine readable output |

Examples:

```bash
python -m holdem AsAd KsKh                          # preflop, sampled
python -m holdem AsAd KsKh --mode exact             # all 1,712,304 runouts
python -m holdem AsKs QhQd 7c7d -b "Jh Ts 2c" --json
python -m holdem                                    # prompts for hands
```

## Web app

`POST /holdem/api/equity`

```json
{ "hands": ["AsKs", "QhQd"], "board": "Jh Ts 2c", "trials": 100000, "mode": "auto" }
```

```json
{
  "board": "Jh Ts 2c",
  "mode": "exact",
  "trials": 990,
  "seconds": 0.002,
  "hands": [
    { "index": 0, "hand": "As Ks", "equity": 32.42, "win": 32.42, "tie": 0.0, "best_hand": "" },
    { "index": 1, "hand": "Qh Qd", "equity": 67.58, "win": 67.58, "tie": 0.0, "best_hand": "" }
  ]
}
```

Bad input comes back as a `400` with a plain english `detail`. `GET /holdem/api/health`
is a liveness probe. Interactive API docs are at `/holdem/api/docs`.

## How it works

**Runouts.** With a complete board there is one runout, so the answer is a
single comparison. Otherwise every possible runout is enumerated — 990 boards on
the flop, 44 on the turn — and each hand's share is counted exactly. Preflop
that would mean over a million boards per hand, so by default the solver samples
instead, which lands within about 0.1% of the true number at 100,000 trials.
`--mode exact` enumerates preflop too, taking a couple of seconds.

**Evaluation.** Each of the 52 cards owns a precomputed constant. Adding those
constants together gives one integer holding a count for every rank and every
suit, so a shared board is summed once and each player's hole cards are simply
added on top. That integer indexes a memo table of hand scores, which is what
keeps an eight-way preflop simulation under a second in pure Python. A hand's
score is a single int, so comparing hands is `>` and a chop is `==`.

## Tests

```bash
python tests/test_solver.py
```

Covers hand categories and their ordering, the wheel, best-five-of-seven, chops,
input validation, and known equities (AA over KK at ~82%, QQ over AKs at ~53%).
The fast evaluator is also checked hand for hand against a deliberately naive
one written separately in the test file.
