"""FastAPI front end for the Hold'em equity solver.

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

from redriver.cards import cards_str, parse_cards
from redriver.evaluator import BUCKET_NAMES
from redriver.equity import DEFAULT_TRIALS, MAX_PLAYERS, equity, holdem_made

#: A ceiling rather than a budget: it stops a hand-written request asking for a
#: run that never comes back. Precise asks for the million when the walk is not
#: on offer, which is the only time anything asks for this much.
MAX_TRIALS = 10_000_000

#: The longest a caller may ask to be kept waiting.
MAX_SECONDS = 60.0

#: Two engines answer one request -- the variant's own figures and the Hold'em
#: ones beside them -- so a budget covers both. The variant's are the answer
#: being asked for and take the larger share.
MAIN_SHARE = 0.7

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Red River Solver", docs_url="/redriver/api/docs", redoc_url=None)


class EquityRequest(BaseModel):
    hands: list[str] = Field(..., description="Two card hands, e.g. ['AsKs', 'QhQd']")
    board: str = Field("", description="0-5 community cards, e.g. 'Jh Ts 2c'")
    dead: str = Field(
        "",
        description="Cards out of the deck but not in any hand still in the pot -- a folded hand's. Not scored, but not dealt to anybody either.",
    )
    trials: int = Field(DEFAULT_TRIALS, ge=1, le=MAX_TRIALS)
    seconds: float | None = Field(
        None, gt=0, le=MAX_SECONDS,
        description="Cap the answer at this many seconds. Trials then act as a "
                    "ceiling and the answer reports how many it managed.",
    )
    mode: Literal["auto", "exact"] = Field(
        "exact", description="'auto' samples instead of enumerating when a runout count is large"
    )


class CategoryOdds(BaseModel):
    name: str
    pct: float


class HandResponse(BaseModel):
    index: int
    hand: str
    equity: float
    win: float
    tie: float
    #: Half-width of the 95% interval on `equity`, in points. Zero when every
    #: runout was walked.
    margin: float = 0.0
    best_hand: str = ""
    made: list[CategoryOdds] = Field(
        default_factory=list,
        description="How often the hand ends as each category, best first. "
                    "Counted over every runout, so it sums to 100%.",
    )
    made_holdem: list[CategoryOdds] = Field(
        default_factory=list,
        description="The same figures under ordinary Hold'em rules -- same "
                    "hole cards, same board, but stopping at five community "
                    "cards. A baseline to read this game's own numbers against.",
    )


class EquityResponse(BaseModel):
    board: str
    mode: str
    trials: int
    seconds: float
    hands: list[HandResponse]


@app.get("/redriver/api/health")
def health():
    return {"status": "ok", "max_players": MAX_PLAYERS, "max_trials": MAX_TRIALS}


@app.post("/redriver/api/equity", response_model=EquityResponse)
def calculate(request: EquityRequest):
    try:
        hands = []
        for i, text in enumerate(request.hands):
            cards = parse_cards(text)
            if len(cards) != 2:
                raise ValueError("hand %d has %d cards, expected 2" % (i + 1, len(cards)))
            hands.append(cards)
        board = parse_cards(request.board)
        dead = parse_cards(request.dead)

        started = perf_counter()
        report = equity(hands, board, dead=dead,
                        trials=request.trials, mode=request.mode,
                        seconds=request.seconds and request.seconds * MAIN_SHARE)
        # The same deal read as ordinary Hold'em, for the column beside it.
        baseline = holdem_made(hands, board, dead=dead,
                               trials=request.trials, mode=request.mode,
                               seconds=request.seconds and
                               request.seconds * (1 - MAIN_SHARE))
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
                margin=round(hand.margin, 3),
                win=round(hand.win_pct, 2),
                tie=round(hand.tie_pct, 2),
                made=[CategoryOdds(name=name, pct=round(pct, 2))
                      for name, pct in hand.made_pct],
                made_holdem=[
                    CategoryOdds(name=label, pct=round(100 * share, 2))
                    for label, share in zip(BUCKET_NAMES, baseline[hand.index])
                ],
                best_hand=hand.best_hand,
            )
            for hand in report.hands
        ],
    )


@app.get("/", include_in_schema=False)
def index():
    """The solver lives under /redriver; keep the bare domain pointing at it."""
    return RedirectResponse("/redriver/")


app.mount("/redriver", StaticFiles(directory=STATIC_DIR, html=True), name="static")
