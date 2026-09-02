# Red River Solver

Equity calculator for Red River Hold'em. Hold'em until the river, and then the
river does not stop: the dealer turns a card, and if it is **red** another
follows it, and another, until a **black** one lands. So the board finishes at
five cards, or six, or seven, and the only thing known in advance is that it
ends in a club or a spade.

## Quick start

```bash
python -m redriver AsKs QhQd --board "Jh Ts 2c 5d 7h 8c"
```

Here the 7h kept the hand alive and the 8c ended it, so the board is six cards.

## How long the board runs

Each extra card needs another red, so the tail halves each time. Sampled over
30,000 boards:

| Board | 5 | 6 | 7 | 8 | 9 | 10+ |
| --- | --- | --- | --- | --- | --- | --- |
| Share | 50% | 25% | 13% | 6% | 3% | 3% |

## Exact or sampled

This is the one variant here that usually cannot be walked. Every other board
in the repo has a length fixed before the deal, so its runouts are combinations
and can be counted with a formula. Here a runout is a *sequence* -- each red
card that lands opens what is left of the deck again -- so the number of them
grows like a factorial while their probability only halves.

The upshot is that **Precise walks the board only once it has finished**, where
there is a single runout and the answer is certain. While the river can still
run, both Fast and Precise sample, and the status line says so. That is not a
shortcut anyone chose: a board four cards down genuinely has millions of ways
to end, most of them carrying a millionth of a percent each.

## Web app

`POST /redriver/api/equity`, health at `/redriver/api/health`, docs at
`/redriver/api/docs`.

## Tests

```bash
python tests/test_solver.py
```
