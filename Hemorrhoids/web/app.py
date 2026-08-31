"""FastAPI front end for the HMRDS equity solver.

Serves the single page UI from ``web/static`` and one JSON endpoint the page
calls when you press Calculate.
"""

from pathlib import Path
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hmrds.cards import BOARD_SIZE, HAND_SIZE, cards_str, parse_cards
from hmrds.equity import DEFAULT_TRIALS, MAX_PLAYERS, equity

#: The default is already this high, so this is a ceiling rather than a budget:
#: it stops a hand-written request asking for a run that never comes back.
MAX_TRIALS = 250_000

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="HMRDS Solver", docs_url="/hmrds/api/docs", redoc_url=None)


class EquityRequest(BaseModel):
    hands: list[str] = Field(
        ..., description="Cards each player still holds, e.g. ['AsKsQsJsTs', '2h3h4h5h6h']"
    )
    discards: list[str] = Field(
        default_factory=list,
        description="Cards each player has turned face up, in the same seat order. "
                    "Whatever hands and discards leave unnamed is dealt at random.",
    )
    board: str = Field("", description="0-10 community cards in dealing order")
    trials: int = Field(DEFAULT_TRIALS, ge=1, le=MAX_TRIALS)
    mode: Literal["auto", "exact", "monte-carlo"] = Field(
        "auto", description="'auto' samples instead of walking when the runouts are too wide"
    )


class HandResponse(BaseModel):
    index: int
    hand: str
    unknown: int
    equity: float
    high: float
    low: float
    scoop: float
    out: float
    keep: float
    detail: str = ""


class EquityResponse(BaseModel):
    board: str
    mode: str
    trials: float
    seconds: float
    hands: list[HandResponse]


@app.get("/hmrds/api/health")
def health():
    return {
        "status": "ok",
        "max_players": MAX_PLAYERS,
        "max_trials": MAX_TRIALS,
        "hand_size": HAND_SIZE,
        "board_size": BOARD_SIZE,
    }


@app.post("/hmrds/api/equity", response_model=EquityResponse)
def calculate(request: EquityRequest):
    try:
        hands = [parse_cards(text) for text in request.hands]
        discards = [
            parse_cards(request.discards[i] if i < len(request.discards) else "")
            for i in range(len(hands))
        ]
        board = parse_cards(request.board)

        started = perf_counter()
        report = equity(hands, board, discards=discards,
                        trials=request.trials, mode=request.mode)
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
                unknown=hand.unknown,
                equity=round(hand.equity_pct, 2),
                high=round(hand.high_pct, 2),
                low=round(hand.low_pct, 2),
                scoop=round(hand.scoop_pct, 2),
                out=round(hand.out_pct, 2),
                keep=round(hand.keep_pct, 2),
                detail=hand.detail,
            )
            for hand in report.hands
        ],
    )


@app.get("/", include_in_schema=False)
def index():
    """The solver lives under /hmrds; keep the bare domain pointing at it."""
    return RedirectResponse("/hmrds/")


app.mount("/hmrds", StaticFiles(directory=STATIC_DIR, html=True), name="static")
