"""FastAPI front end for the Hold'em equity solver.

Serves the single page UI from ``web/static`` and one JSON endpoint the page
calls when you press Calculate.
"""

from pathlib import Path
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from holdem.cards import cards_str, parse_cards
from holdem.equity import DEFAULT_TRIALS, MAX_PLAYERS, equity

#: Keeps a single request from tying the server up for more than a second or two.
MAX_TRIALS = 250_000

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Texas Hold'em Solver", docs_url="/api/docs", redoc_url=None)


class EquityRequest(BaseModel):
    hands: list[str] = Field(..., description="Two card hands, e.g. ['AsKs', 'QhQd']")
    board: str = Field("", description="0-5 community cards, e.g. 'Jh Ts 2c'")
    trials: int = Field(DEFAULT_TRIALS, ge=1, le=MAX_TRIALS)
    mode: Literal["auto", "exact"] = Field(
        "auto", description="'exact' enumerates every runout, even preflop"
    )


class HandResponse(BaseModel):
    index: int
    hand: str
    equity: float
    win: float
    tie: float
    best_hand: str = ""


class EquityResponse(BaseModel):
    board: str
    mode: str
    trials: int
    seconds: float
    hands: list[HandResponse]


@app.get("/api/health")
def health():
    return {"status": "ok", "max_players": MAX_PLAYERS, "max_trials": MAX_TRIALS}


@app.post("/api/equity", response_model=EquityResponse)
def calculate(request: EquityRequest):
    try:
        hands = []
        for i, text in enumerate(request.hands):
            cards = parse_cards(text)
            if len(cards) != 2:
                raise ValueError("hand %d has %d cards, expected 2" % (i + 1, len(cards)))
            hands.append(cards)
        board = parse_cards(request.board)

        started = perf_counter()
        report = equity(hands, board, trials=request.trials, mode=request.mode)
        elapsed = perf_counter() - started
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return EquityResponse(
        board=cards_str(report.board),
        mode=report.mode,
        trials=report.trials,
        seconds=round(elapsed, 3),
        hands=[
            HandResponse(
                index=hand.index,
                hand=hand.label,
                equity=round(hand.equity_pct, 2),
                win=round(hand.win_pct, 2),
                tie=round(hand.tie_pct, 2),
                best_hand=hand.best_hand,
            )
            for hand in report.hands
        ],
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
