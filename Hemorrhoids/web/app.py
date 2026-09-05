"""FastAPI front end for the HMRDS equity solver.

Serves the single page UI from ``web/static`` and one JSON endpoint the page
calls when you press Calculate.
"""

from pathlib import Path
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hmrds.cards import BOARD_SIZE, HAND_SIZE, cards_str, parse_cards
from hmrds.equity import DEFAULT_TRIALS, MAX_PLAYERS, equity

#: A ceiling rather than a budget: it stops a hand-written request asking for a
#: run that never comes back. It is a ceiling rather than a target now: the page
#: asks for a wall clock budget and the count is whatever fits inside it, so this
#: only has to be higher than the fastest table can reach in `MAX_SECONDS`.
MAX_TRIALS = 10_000_000

#: The longest a caller may ask to be kept waiting.
MAX_SECONDS = 60.0

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
    dead: str = Field(
        "",
        description="Cards out of the deck but belonging to nobody still in the "
                    "pot -- a folded hand's. Not scored, but not dealt either.",
    )
    trials: int = Field(DEFAULT_TRIALS, ge=1, le=MAX_TRIALS)
    seconds: float | None = Field(
        None, gt=0, le=MAX_SECONDS,
        description="Cap the sampling at this many seconds. Trials then act as a "
                    "ceiling and the answer reports how many it managed.",
    )
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
    #: Half-width of the 95% interval on `equity`, in points. Zero when every
    #: runout was walked.
    margin: float = 0.0
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
        dead = parse_cards(request.dead)

        started = perf_counter()
        report = equity(hands, board, discards=discards, dead=dead,
                        trials=request.trials, mode=request.mode,
                        seconds=request.seconds)
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
                margin=round(hand.margin, 3),
                detail=hand.detail,
            )
            for hand in report.hands
        ],
    )


@app.get("/hmrds/range", include_in_schema=False)
def range_chart():
    """The showdown chart. Named on its own because a bare path under the
    static mount would not resolve either on its own."""
    return FileResponse(STATIC_DIR / "range.html")


@app.get("/", include_in_schema=False)
def index():
    """The solver lives under /hmrds; keep the bare domain pointing at it."""
    return RedirectResponse("/hmrds/")


app.mount("/hmrds", StaticFiles(directory=STATIC_DIR, html=True), name="static")
