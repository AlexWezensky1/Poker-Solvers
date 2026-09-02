# Noah's Ark Solver

Equity calculator for Noah's Ark (2x2). Two hole cards as in Hold'em, but every
street turns **two** community cards instead of one, so six are out by the
river and the best five come from eight. Every other rule is Hold'em's.

## Quick start

```bash
python -m noahsark AsKs QhQd --board "Jh Ts 2c 5d"
```

## The board

| Street | Community cards | On the board |
| --- | --- | --- |
| Flop | 2 | 2 |
| Turn | 2 | 4 |
| River | 2 | 6 |

Six community cards make the game a good deal flatter than Hold'em. Aces over
kings runs about 78% here against the 82% it is with five, and the classic
queens against ace-king coinflip lands nearer 50/50 than 54/46: two more cards
are two more chances for the hand behind to catch up.

## Exact or sampled

The walk is on offer from the first street onward -- four cards to come is
C(46,4), about 163,000 runouts, well under a second. Before any of them are
dealt it is C(48,6), twelve million, which is over half a minute, so **Fast**
samples there and **Precise** does too rather than sit on the request. The
status line says which it did.

## Web app

`POST /noah/api/equity`, health at `/noah/api/health`, docs at `/noah/api/docs`.

## Tests

```bash
python tests/test_solver.py
```
