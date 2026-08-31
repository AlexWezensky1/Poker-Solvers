# HMRDS Solver

Equity calculator for HMRDS. Give it up to eight five-card hands and up to ten
community cards; it returns each hand's share of the pot, split into the high
and low halves, plus how often it scoops, how often it empties out and how often
it keeps all five. Hands can be named
only in part — a player whose discards you can see but whose remaining cards you
cannot is still a player — and the rest is dealt at random. Runs as a command
line tool and as a small web app.

## Quick start

```bash
python -m hmrds AsKsQsJsTs 2h3h4h5h6h --board "2c3c4c5c 7h8h9h"
```

```
Board: 2c 3c 4c 5c 7h 8h 9h   exact in 0.01s

  #  Hand              Equity      High       Low     Scoop       Out      Keep
  -----------------------------------------------------------------------------
  1  As Ks Qs Js Ts    44.13%    65.39%     0.00%    10.39%     0.00%    12.47%
* 2  2h 3h 4h 5h 6h    55.87%     0.00%    65.39%    22.14%    24.22%     0.00%
```

**High** and **Low** are the share of each half the hand takes, ties included, as
a fraction of every runout. A pot won outright — by emptying out early, or by
keeping all five — is never cut into halves, so those runouts count towards
neither. That is why the two columns fall short of 100% between them: the gap is
how often the hand ended before it ever reached a high/low showdown. When it
does reach one, equity is exactly half the high share plus half the low.

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

A hand may also be written `HELD/DISCARDED`, and whatever the two leave unnamed
is an unknown card still in the hand:

| Written | Means |
| --- | --- |
| `AsKsQsJsTs` | the whole hand |
| `AsKsQs/2h3h` | three held, two face up |
| `/2h3h` | two face up, three cards you cannot see |
| `AsKs` | two held, three cards you cannot see |

Unknown cards are dealt at random on every trial, out of the cards that could
still be in a hand — anything the board has already matched would be lying face
up, so it is never one of them. A discard the board cannot account for is
rejected, since a card only ever leaves your hand because a community card
matched it.

## Command line

```
python -m hmrds [HAND ...] [-b BOARD] [-t TRIALS] [-m MODE] [--seed N] [--json]
```

| Option | Meaning |
| --- | --- |
| `HAND ...` | up to 8 hands, `HELD` or `HELD/DISCARDED`; run with none to be prompted |
| `-b`, `--board` | 0-10 community cards in dealing order |
| `-t`, `--trials` | Monte Carlo trials (default 250,000) |
| `-m`, `--mode` | `auto`, `exact` or `monte-carlo` |
| `--seed` | seed the sampler so a run repeats exactly |
| `--json` | machine readable output |

Examples:

```bash
python -m hmrds KsKhQsQhJs AcKdQdJdTd                      # opening deal, sampled
python -m hmrds KsKhQsQhJs AcKdQdJdTd --mode exact         # walked in full
python -m hmrds AsKsQsJsTs 2h3h4h5h6h -b "2c3c4c5c" --json
python -m hmrds AsKsQsJsTs /2c3c -b "2s3s4s7s"             # villain read only by discards
python -m hmrds                                            # prompts for hands
```

## Web app

Click the deck to deal. Cards land in the highlighted slot and the highlight
moves on, in dealing order: the community cards first, then each seat in turn.
Click any slot to jump the highlight there — dealing the opening four and then
skipping straight to hand 1 is a click. Clicking a card that is already out
takes it back. Any card the board has matched is struck through, because it has
been discarded face up.

It recalculates on its own as soon as two seats are ready, where a seat is ready
once it holds five cards or once anything of its is face up. Leave a seat's
remaining slots empty and those cards are dealt at random, so a player you can
only read by their discards still counts.

`POST /hmrds/api/equity`

```json
{
  "hands": ["AsKsQsJsTs", ""],
  "discards": ["", "2h3h"],
  "board": "2s3s4s7s",
  "mode": "auto"
}
```

```json
{
  "board": "2s 3s 4s 7s",
  "mode": "monte-carlo",
  "trials": 250000.0,
  "seconds": 3.739,
  "hands": [
    { "index": 0, "hand": "As Ks Qs Js Ts", "unknown": 0, "equity": 53.74,
      "high": 82.27, "low": 13.76, "scoop": 11.55, "out": 0.15, "keep": 5.6,
      "detail": "" },
    { "index": 1, "hand": "-- / 2h 3h +3?", "unknown": 3, "equity": 46.26,
      "high": 7.98, "low": 76.49, "scoop": 4.32, "out": 4.04, "keep": 0.0,
      "detail": "" }
  ]
}
```

`hands` is what each seat still holds and `discards` what it has turned face up,
in the same seat order. Both may be left short; the remainder is unknown.

Bad input comes back as a `400` with a plain english `detail`. `GET /hmrds/api/health`
is a liveness probe. Interactive API docs are at `/hmrds/api/docs`.

## How it works

**Suits do not exist.** Nothing in HMRDS reads a suit — community cards match by
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
runs about 85,000 runouts a second, so the default 250,000 trials lands within
roughly 0.06% and takes about three seconds. Hands with few distinct ranks stay exact
even on the opening deal — `KKQQJ` against `23456` walks in 1.3s.

**Unknown cards** are dealt each trial before the board, which is the only order
that leaves both draws uniform, and only ever out of the cards that could still
be hidden. Profiles are cached on ranks alone, so the thousands of repeated deals
cost a dict lookup rather than a rebuild. A spot with unknown cards can only be
sampled, never walked, so `auto` picks Monte Carlo for it and `--mode exact`
refuses it outright; three unknown cards costs roughly another second on top of
the usual run.

Both engines settle through the same `hmrds.scoring.resolve`, so the rules live in
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

Unknown cards get their own check with an answer worked out by hand: a board
covering exactly ranks 2-6, hero on a lone ace, the villain on four discards and
one hidden card. That card can only be a rank the board has not shown, so hero
scoops unless the villain holds an ace too — 3 of the 31 cards that could still
be hidden — which puts hero at exactly (28 + 3 × 0.5) / 31.
