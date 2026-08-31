# HMRS Solver

Equity calculator for HMRS. Give it up to eight five-card hands and up to ten
community cards; it returns each hand's share of the pot, how often it scoops,
how often it empties out and how often it keeps all five. Runs as a command line
tool and as a small web app.

## Quick start

```bash
python -m hmrs AsKsQsJsTs 2h3h4h5h6h --board "2c3c4c5c 7h8h9h"
```

```
Board: 2c 3c 4c 5c 7h 8h 9h   exact in 0.01s

  #  Hand              Equity     Scoop       Out      Keep
  ---------------------------------------------------------
  1  As Ks Qs Js Ts    44.13%    10.39%     0.00%    12.47%
* 2  2h 3h 4h 5h 6h    55.87%    22.14%    24.22%     0.00%
```

No dependencies are needed for the command line tool — the engine is pure
standard library. The web app needs FastAPI:

```bash
pip install -r requirements.txt
uvicorn web.app:app --reload
```

Then open http://127.0.0.1:8000.

## The game

Everyone is dealt five cards and four community cards go straight out. Any card
in your hand whose rank matches a community card is discarded face up — one
community card takes **every** match, so a lone queen kills both of your queens
at once. Then a round of betting. Three more community cards, discard, bet. Two
more, discard, bet. Then the last single card.

Betting is ignored here; this is an equity calculator.

The pot is settled in this order:

1. **Empty out before the last community card and you win outright.** The hand
   would have ended the moment you went out, so the earliest street wins.
   Players who go out on that same street split.
2. Otherwise the last card is turned, and the pot goes to everyone who either
   emptied out on it or still holds all five. Those two groups split together —
   so an empty hand alone takes everything, and a keeper alone takes everything.
3. Otherwise half the pot goes to the highest hand and half to the lowest.

Only cards still in your hand are scored. Deuce through ten are worth face
value, jacks queens and kings are worth ten, and **every** ace counts one for
the low and eleven for the high — so `A-A` is 2/22 and `A-A-A` is 3/33. Because
one hand carries a separate low and high total it can take both halves: a lone
ace scoops a lone jack, since 1 beats 10 for the low and 11 beats 10 for the
high.

Each half is split evenly among ties on its own side. Totals of 4, 4 and 36 pay
25% / 25% / 50%: the two low hands share the low half, the 36 takes the high
half alone.

**Pairs are worth a lot.** A hand covering three distinct ranks only has to dodge
three ranks to empty out, and going out early wins the whole pot, so `KKQQJ` is
far stronger than `AKQJT` despite the card ranks.

## Card notation

A card is a rank followed by a suit, e.g. `As`, `Th`, `7d`, `2c`.

- ranks `23456789TJQKA` (`10` is accepted for `T`)
- suits `s` spades, `h` hearts, `d` diamonds, `c` clubs

Hands and boards can be written packed (`AsKsQsJsTs`) or spaced, in any case.
Board cards are read in dealing order: the first four are the opening community
cards, then three, then two, then one.

## Command line

```
python -m hmrs [HAND ...] [-b BOARD] [-t TRIALS] [-m MODE] [--seed N] [--json]
```

| Option | Meaning |
| --- | --- |
| `HAND ...` | up to 8 five-card hands; run with none to be prompted |
| `-b`, `--board` | 0-10 community cards in dealing order |
| `-t`, `--trials` | Monte Carlo trials (default 100,000) |
| `-m`, `--mode` | `auto`, `exact` or `monte-carlo` |
| `--seed` | seed the sampler so a run repeats exactly |
| `--json` | machine readable output |

Examples:

```bash
python -m hmrs KsKhQsQhJs AcKdQdJdTd                      # opening deal, sampled
python -m hmrs KsKhQsQhJs AcKdQdJdTd --mode exact         # walked in full
python -m hmrs AsKsQsJsTs 2h3h4h5h6h -b "2c3c4c5c" --json
python -m hmrs                                            # prompts for hands
```

## Web app

`POST /hmrs/api/equity`

```json
{ "hands": ["AsKsQsJsTs", "2h3h4h5h6h"], "board": "2c3c4c5c 7h8h9h", "mode": "auto" }
```

```json
{
  "board": "2c 3c 4c 5c 7h 8h 9h",
  "mode": "exact",
  "trials": 1.0,
  "seconds": 0.005,
  "hands": [
    { "index": 0, "hand": "As Ks Qs Js Ts", "equity": 44.13, "scoop": 10.39,
      "out": 0.0, "keep": 12.47, "detail": "" },
    { "index": 1, "hand": "2h 3h 4h 5h 6h", "equity": 55.87, "scoop": 22.14,
      "out": 24.22, "keep": 0.0, "detail": "" }
  ]
}
```

Bad input comes back as a `400` with a plain english `detail`. `GET /hmrs/api/health`
is a liveness probe. Interactive API docs are at `/hmrs/api/docs`.

## How it works

**Suits do not exist.** Nothing in HMRS reads a suit — community cards match by
rank and hands score by rank — so the whole engine runs on 13 bit rank masks.
Each hand precomputes a table of its own surviving submasks, at most 32 rows,
holding cards left and the low and high totals. Survival for one player against
one board is then `table[hand & ~board]`: one AND and one dict lookup. There is
no five-card evaluator, because the score is a sum.

**Exact.** Only *live* ranks matter — the ranks somebody actually holds. Every
other rank is interchangeable filler that can be counted but never identified,
so a state is just how many copies of each live rank are still in the deck. Which
ranks have already appeared falls out of that (a rank has appeared exactly when
its count has dropped), which is why the memo key does not have to carry the
board. Runouts that end early because somebody emptied out stop expanding on the
spot.

That makes everything from the first four community cards onward exact and
effectively instant — the four known cards pin the opening street, so only a few
thousand states are reachable. The opening deal is the hard case: two hands with
ten distinct ranks between them reach roughly 185M steps, about ten seconds.

**Sampling.** `auto` estimates the size of the walk and falls back to Monte Carlo
past `DEFAULT_EXACT_BUDGET`, which in practice means the opening deal. Sampling
runs about 85,000 runouts a second, so the default 100,000 trials lands within
roughly 0.1% and takes about a second. Hands with few distinct ranks stay exact
even on the opening deal — `KKQQJ` against `23456` walks in 1.3s.

Both engines settle through the same `hmrs.scoring.resolve`, so the rules live in
exactly one place.

## Tests

```bash
python tests/test_solver.py
```

Covers every scoring rule and each branch of the settlement, the two worked
examples, and the ace arithmetic. The exact engine is checked against a brute
force walk over real card combinations, and the whole rule set is checked over
4,000 random boards against a second, deliberately plodding implementation
written separately in the test file that shares nothing with the engine but the
rules.
