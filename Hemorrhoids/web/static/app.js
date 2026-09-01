"use strict";

const RANKS = "23456789TJQKA";
const SUITS = "shdc";
const MAX_PLAYERS = 8;
const HAND_SIZE = 5;
// Community cards come four, then three, then two, then one.
const STREETS = [4, 3, 2, 1];

// The deck grid: one row per suit, ranks running high to low.
const DECK_RANKS = "AKQJT98765432";
const SUIT_PIPS = { s: "♠", h: "♥", d: "♦", c: "♣" };

const boardEl = document.getElementById("board");
const playersEl = document.getElementById("players");
const deckEl = document.getElementById("deck");
const statusEl = document.getElementById("status");
const clearBtn = document.getElementById("clear");
const speedEl = document.getElementById("speed");

// Fast walks every runout when that is cheap and samples 250,000 of them when
// it is not, so a settled board still answers exactly and instantly; precise
// always walks. Sampling lands within about 0.1% of the true number and takes
// about a second, where an exact opening deal can take ten.
const FAST_TRIALS = 250000;
const PRECISE_TRIALS = 1000000;
let speed = "fast";

// Every slot on the table, in the order they are laid out. The order deck
// clicks travel in is a different thing entirely -- see fillOrder below.
const allInputs = [];
const boardInputs = [];
const players = [];
const deckButtons = new Map();

// The slot the next deck click lands in.
let active = null;

/* ---------- card text handling ---------- */

function isCard(value) {
  return value.length === 2 && RANKS.includes(value[0]) && SUITS.includes(value[1]);
}

// A slot shows its card with a suit pip but is read by its plain code, so the
// letters stay out of sight while everything downstream still speaks "As".
function cardOf(slot) {
  return slot.dataset.card || "";
}

function setCard(slot, card) {
  slot.dataset.card = card;
  slot.value = card ? card[0] + SUIT_PIPS[card[1]] : "";
}

// The ranks the board has turned. A card matching one of these is discarded
// face up, which is the whole game.
function turnedRanks() {
  const ranks = new Set();
  for (const input of boardInputs) {
    const card = cardOf(input);
    if (card) ranks.add(card[0]);
  }
  return ranks;
}

/* ---------- the slot the deck deals into ---------- */

function setActive(input) {
  if (active === input) return;
  active = input;
  allInputs.forEach((slot) => slot.classList.toggle("active", slot === active));
  // Deliberately no focus() here. Arming a slot is a paint job -- the outline
  // says where the next card lands -- and moving the caret to it made the
  // browser drag that slot into view, so dealing from the deck scrolled the
  // deck off the screen. preventScroll would cover it on desktop, but Safari
  // on iOS ignores that, and the slots are readOnly so focus earns nothing.
  // Tapping a slot still focuses it the ordinary way, and the focus listener
  // below picks that up, which is what keeps Tab working.
}

function inHand(seat) {
  return players[seat].box.checked;
}

// Board slots plus the seats still in the pot: what is actually on the table.
function liveInputs() {
  const live = [...boardInputs];
  players.forEach((player, seat) => {
    if (inHand(seat)) live.push(...player.inputs);
  });
  return live;
}

// The order a run of deck clicks fills the table in: your own hand, then the
// four community cards that open the game, then the rest of the seats, and the
// later streets last. It is not how the cards are dealt -- everybody is dealt
// before any community card is -- but it is the order they become known to
// somebody sitting at the table, which is the order they get entered in.
const fillOrder = [];

function buildFillOrder() {
  fillOrder.length = 0;
  fillOrder.push(...players[0].inputs);
  fillOrder.push(...boardInputs.slice(0, STREETS[0]));
  for (let seat = 1; seat < players.length; seat++) {
    if (inHand(seat)) fillOrder.push(...players[seat].inputs);
  }
  fillOrder.push(...boardInputs.slice(STREETS[0]));
}

// The next empty slot after the given position in fill order, wrapping round
// to the start.
function nextEmpty(from) {
  for (let step = 1; step <= fillOrder.length; step++) {
    const slot = fillOrder[(from + step) % fillOrder.length];
    if (!cardOf(slot)) return slot;
  }
  return null;
}

// A deck click deals into the highlighted slot and moves on to the next empty
// one; clicking a card that is already out takes it back off the table.
function pick(card) {
  const holder = allInputs.find((slot) => cardOf(slot) === card);
  if (holder) {
    setCard(holder, "");
    refresh();
    setActive(holder);
    return;
  }
  if (!active) return;

  const from = fillOrder.indexOf(active);
  setCard(active, card);
  refresh();
  setActive(nextEmpty(from));
}

/* ---------- building the form ---------- */

function makeCardInput() {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "card";
  input.placeholder = "?";
  input.readOnly = true;  // cards only ever arrive from the deck
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("aria-label", "card");
  setCard(input, "");

  // Clicking a slot that holds a card sends that card back to the deck. Either
  // way the slot is left armed, so the next deck click deals into it.
  input.addEventListener("click", () => {
    if (cardOf(input)) {
      setCard(input, "");
      refresh();
    }
    setActive(input);
  });

  input.addEventListener("focus", () => setActive(input));

  allInputs.push(input);
  return input;
}

function buildBoard() {
  STREETS.forEach((size, street) => {
    for (let i = 0; i < size; i++) {
      const slot = document.createElement("div");
      slot.className = "slot";
      // Stand each street off from the one before, so they read at a glance.
      if (i === 0 && street > 0) slot.classList.add("street");
      const input = makeCardInput();
      slot.appendChild(input);
      boardEl.appendChild(slot);
      boardInputs.push(input);
    }
  });
}

function buildSeat(seat) {
  const row = document.createElement("div");
  row.className = "player";

  // Seat 1 is whoever is asking, so it is always in and its box is fixed on.
  const number = document.createElement("label");
  number.className = "seat";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.className = "in";
  box.checked = seat < 2;
  box.disabled = seat === 0;
  box.addEventListener("change", () => {
    buildFillOrder();
    refresh();
    if (!inHand(seat)) setActive(fillOrder[0]);
  });
  const name = document.createElement("span");
  name.textContent = "Hand " + (seat + 1);
  number.append(box, name);

  const holecards = document.createElement("div");
  holecards.className = "holecards";
  const inputs = [];
  for (let i = 0; i < HAND_SIZE; i++) inputs.push(makeCardInput());
  holecards.append(...inputs);

  // Says what the seat is missing: cards already face up, cards still unknown.
  const note = document.createElement("div");
  note.className = "note";

  const result = document.createElement("div");
  result.className = "result empty";

  row.append(number, holecards, note, result);
  playersEl.appendChild(row);
  players.push({ row, inputs, note, result, box });
}

function buildDeck() {
  for (const suit of SUITS) {
    for (const rank of DECK_RANKS) {
      const card = rank + suit;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "deck-card suit-" + suit;
      button.setAttribute("aria-label", card);

      const face = document.createElement("span");
      face.textContent = rank;
      const pip = document.createElement("span");
      pip.className = "pip";
      pip.textContent = SUIT_PIPS[suit];

      button.append(face, pip);
      button.addEventListener("click", () => pick(card));
      deckEl.appendChild(button);
      deckButtons.set(card, button);
    }
  }
}

/* ---------- validation ---------- */

// Marks every copy of a card used more than once, greys out the deck cards that
// are already on the table, and strikes through the hand cards the board has
// already discarded.
function refresh() {
  // A seat nobody has checked is not in the pot, so its slots are shut and the
  // cards sitting in them go back to the deck for everybody else to use.
  players.forEach((player, seat) => {
    const out = !inHand(seat);
    player.row.classList.toggle("out", out);
    player.inputs.forEach((input) => { input.disabled = out; });
  });

  const seen = new Map();
  liveInputs().forEach((input) => {
    const card = cardOf(input);
    if (card) seen.set(card, (seen.get(card) || 0) + 1);
  });

  allInputs.forEach((input) => {
    const card = cardOf(input);
    input.classList.toggle("invalid", Boolean(card) && seen.get(card) > 1);
    input.classList.remove("suit-s", "suit-h", "suit-d", "suit-c");
    if (card) input.classList.add("suit-" + card[1]);
  });

  const turned = turnedRanks();
  players.forEach((player) => {
    let held = 0;
    let faceUp = 0;
    player.inputs.forEach((input) => {
      const card = cardOf(input);
      const gone = Boolean(card) && turned.has(card[0]);
      input.classList.toggle("discarded", gone);
      if (card) gone ? faceUp++ : held++;
    });
    const parts = [];
    if (faceUp) parts.push(faceUp + " face up");
    // An untouched seat is simply not playing, so it says nothing.
    if (held + faceUp) {
      const unknown = HAND_SIZE - held - faceUp;
      if (unknown) parts.push(unknown + " unknown");
    }
    player.note.textContent = parts.join(" · ");
  });

  deckButtons.forEach((button, card) => button.classList.toggle("used", seen.has(card)));

  clearResults();
  autoCalculate();
}

function clearResults() {
  players.forEach((player) => {
    player.result.className = "result empty";
    player.result.textContent = "";
    player.row.classList.remove("leader");
  });
}

function setStatus(message, isError) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", Boolean(isError));
}

/* ---------- calculating ---------- */

function collect() {
  const board = boardInputs.map(cardOf).filter(Boolean);
  const turned = new Set(board.map((card) => card[0]));

  const seats = [];
  players.forEach((player, seat) => {
    if (!inHand(seat)) return;
    const cards = player.inputs.map(cardOf).filter(Boolean);
    const discarded = cards.filter((card) => turned.has(card[0]));
    const held = cards.filter((card) => !turned.has(card[0]));
    // Whatever a checked seat has not been given is simply unknown, and the
    // solver deals it at random out of the cards the board has not turned --
    // which is to say it is taken to have discarded nothing.
    seats.push({ seat, held: held.join(""), discarded: discarded.join("") });
  });

  if (seats.length < 2) throw new Error("Check at least two hands.");

  // The opening community cards are enough to solve from, however little is
  // known about the seats. Short of them, wait until every hand in the pot is
  // dealt -- an empty table has nothing to say.
  const allDealt = seats.every(
    (s) => (s.held.length + s.discarded.length) / 2 === HAND_SIZE);
  if (board.length < STREETS[0] && !allDealt) {
    throw new Error("Deal the first " + STREETS[0] + " community cards.");
  }

  const used = [...board, ...seats.flatMap((s) => [s.held, s.discarded].join("").match(/../g) || [])];
  const duplicate = used.find((card, i) => used.indexOf(card) !== i);
  if (duplicate) throw new Error(duplicate + " is used more than once.");

  return { board, seats };
}

function render(seats, results) {
  const best = Math.max(...results.map((r) => r.equity));
  results.forEach((result, i) => {
    const player = players[seats[i].seat];
    player.result.className = "result";
    player.result.innerHTML = "";

    const pct = document.createElement("div");
    pct.className = "equity-pct";
    pct.textContent = result.equity.toFixed(1) + "%";

    const bar = document.createElement("div");
    bar.className = "bar";
    const fill = document.createElement("span");
    fill.style.width = Math.max(result.equity, 0) + "%";
    bar.appendChild(fill);

    const halves = document.createElement("div");
    halves.className = "breakdown";
    halves.textContent = "High " + result.high.toFixed(1) + "%  Low " + result.low.toFixed(1) + "%";

    const scoop = document.createElement("div");
    scoop.className = "breakdown";
    scoop.textContent = "Scoop " + result.scoop.toFixed(1) + "%";

    const rest = document.createElement("div");
    rest.className = "breakdown";
    rest.textContent = "Out " + result.out.toFixed(1) + "%  Keep " + result.keep.toFixed(1) + "%";

    player.result.append(pct, bar, halves, rest, scoop);

    if (result.detail) {
      const made = document.createElement("div");
      made.className = "breakdown";
      made.textContent = result.detail;
      made.title = result.detail;  // the seat is narrow, so it may be clipped
      player.result.appendChild(made);
    }

    player.row.classList.toggle("leader", result.equity >= best - 1e-9);
  });
}

// Cards can land faster than the server answers, so each run takes a ticket
// and a stale reply is dropped rather than painted over a newer table.
let latest = 0;
let settling = 0;

// Every card change lands here. Dealing a hand is a burst of clicks and a run
// can take a few seconds, so the table is given a moment to settle first --
// otherwise every card in the burst queues a run that is stale before it
// finishes, and they all fight each other for the same core.
function autoCalculate() {
  latest++;  // strand any answer still in flight for the old table
  clearTimeout(settling);
  settling = setTimeout(fire, 180);
}

// Two ready hands is the trigger; anything short of that is a half dealt table,
// so it waits quietly rather than complaining about input the player is still
// in the middle of giving.
function fire() {
  let input;
  try {
    input = collect();
  } catch (error) {
    setStatus("");
    return;
  }
  run(input);
}

async function run(input) {
  const ticket = ++latest;
  setStatus("Calculating…");

  // Precise always asks for the walk. Cards nobody has named can be walked
  // too -- one walk per way of filling them in, and suits collapse those to
  // rank multisets -- but only while there are few enough of them, so the
  // server is what decides and the answer says which it did.
  const precise = speed === "precise";
  try {
    const response = await fetch("/hmrds/api/equity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hands: input.seats.map((s) => s.held),
        discards: input.seats.map((s) => s.discarded),
        board: input.board.join(""),
        mode: precise ? "exact" : "auto",
        trials: precise ? PRECISE_TRIALS : FAST_TRIALS,
      }),
    });
    const payload = await response.json();
    if (ticket !== latest) return;
    if (!response.ok) throw new Error(payload.detail || "Calculation failed.");

    render(input.seats, payload.hands);
    const how = payload.mode === "exact"
      ? "Exact"
      : Math.round(payload.trials).toLocaleString() + " simulations";
    // Say why Precise sampled, so the button does not look like it was ignored.
    const why = precise && payload.mode !== "exact" ? "Too many unknowns, " : "";
    setStatus(why + how + " in " + payload.seconds + " seconds");
  } catch (error) {
    if (ticket !== latest) return;
    clearResults();
    setStatus(error.message, true);
  }
}

function clearAll() {
  allInputs.forEach((input) => setCard(input, ""));
  refresh();
  setStatus("");
  setActive(fillOrder[0]);
}

// Laid out board first so it sits above the seats; the order clicks fill in
// is set separately, once every slot exists.
buildBoard();
for (let seat = 0; seat < MAX_PLAYERS; seat++) buildSeat(seat);
buildDeck();
buildFillOrder();

for (const button of speedEl.querySelectorAll(".seg")) {
  button.addEventListener("click", () => {
    if (speed === button.dataset.speed) return;
    speed = button.dataset.speed;
    speedEl.querySelectorAll(".seg").forEach((b) => b.classList.toggle("on", b === button));
    autoCalculate();  // the table has not changed, but the answer will
  });
}

clearBtn.addEventListener("click", clearAll);
// Nothing has happened yet, but the seats nobody has checked still have to be
// shut before the first click rather than after it.
refresh();
setStatus("");
setActive(fillOrder[0]);
