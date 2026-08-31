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

// allInputs is built in dealing order, so it doubles as the fill order:
// hand 1, hand 2, the board, then hands 3-8.
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

// The ranks the board has turned. A card matching one of these is discarded
// face up, which is the whole game.
function turnedRanks() {
  const ranks = new Set();
  for (const input of boardInputs) {
    if (isCard(input.value)) ranks.add(input.value[0]);
  }
  return ranks;
}

/* ---------- the slot the deck deals into ---------- */

function setActive(input) {
  if (active !== input) {
    active = input;
    allInputs.forEach((slot) => slot.classList.toggle("active", slot === active));
  }
  if (input) input.focus();
}

// The next empty slot after the given position in dealing order, wrapping
// round to the start.
function nextEmpty(from) {
  for (let step = 1; step <= allInputs.length; step++) {
    const slot = allInputs[(from + step) % allInputs.length];
    if (slot.value === "") return slot;
  }
  return null;
}

// A deck click deals into the highlighted slot and moves on to the next empty
// one; clicking a card that is already out takes it back off the table.
function pick(card) {
  const holder = allInputs.find((slot) => slot.value === card);
  if (holder) {
    holder.value = "";
    refresh();
    setActive(holder);
    return;
  }
  if (!active) return;

  const from = allInputs.indexOf(active);
  active.value = card;
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

  // Clicking a slot that holds a card sends that card back to the deck. Either
  // way the slot is left armed, so the next deck click deals into it.
  input.addEventListener("click", () => {
    if (input.value !== "") {
      input.value = "";
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

  const number = document.createElement("div");
  number.className = "seat";
  number.textContent = "Hand " + (seat + 1);

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
  players.push({ row, inputs, note, result });
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

// Marks anything unparseable, plus every copy of a card used more than once,
// greys out the deck cards that are already on the table, and strikes through
// the hand cards the board has already discarded.
function refresh() {
  const seen = new Map();
  allInputs.forEach((input) => {
    const value = input.value;
    if (!isCard(value)) return;
    seen.set(value, (seen.get(value) || 0) + 1);
  });

  allInputs.forEach((input) => {
    const value = input.value;
    const bad = value !== "" && (!isCard(value) || seen.get(value) > 1);
    input.classList.toggle("invalid", bad);
    input.classList.remove("suit-s", "suit-h", "suit-d", "suit-c");
    if (isCard(value)) input.classList.add("suit-" + value[1]);
  });

  const turned = turnedRanks();
  players.forEach((player) => {
    let held = 0;
    let faceUp = 0;
    player.inputs.forEach((input) => {
      const gone = isCard(input.value) && turned.has(input.value[0]);
      input.classList.toggle("discarded", gone);
      if (isCard(input.value)) gone ? faceUp++ : held++;
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
  const board = [];
  for (const input of boardInputs) {
    if (input.value === "") continue;
    if (!isCard(input.value)) throw new Error("'" + input.value + "' is not a card.");
    board.push(input.value);
  }
  const turned = new Set(board.map((card) => card[0]));

  const seats = [];
  players.forEach((player, seat) => {
    const cards = player.inputs.map((input) => input.value).filter((value) => value !== "");
    if (!cards.length) return;
    if (cards.some((value) => !isCard(value))) {
      throw new Error("Hand " + (seat + 1) + " has a card that will not parse.");
    }
    const discarded = cards.filter((card) => turned.has(card[0]));
    const held = cards.filter((card) => !turned.has(card[0]));
    // A seat counts once it is fully dealt, or once anything of its is face up
    // -- a player you can only read by their discards is still a player. A seat
    // part way through being typed is neither, so it waits.
    if (cards.length < HAND_SIZE && !discarded.length) {
      throw new Error("Hand " + (seat + 1) + " is still being dealt.");
    }
    seats.push({ seat, held: held.join(""), discarded: discarded.join("") });
  });

  if (seats.length < 2) throw new Error("Enter at least two hands.");

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
    pct.textContent = result.equity.toFixed(2) + "%";

    const bar = document.createElement("div");
    bar.className = "bar";
    const fill = document.createElement("span");
    fill.style.width = Math.max(result.equity, 0) + "%";
    bar.appendChild(fill);

    const scoop = document.createElement("div");
    scoop.className = "breakdown";
    scoop.textContent = "Scoop " + result.scoop.toFixed(2) + "%";

    const rest = document.createElement("div");
    rest.className = "breakdown";
    rest.textContent = "Out " + result.out.toFixed(1) + "%  Keep " + result.keep.toFixed(1) + "%";

    player.result.append(pct, bar, scoop, rest);

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
// can take a second or more, so the table is given a moment to settle first --
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
  try {
    const response = await fetch("/hmrs/api/equity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Trials and mode are left off; the server picks its own defaults.
      body: JSON.stringify({
        hands: input.seats.map((s) => s.held),
        discards: input.seats.map((s) => s.discarded),
        board: input.board.join(""),
      }),
    });
    const payload = await response.json();
    if (ticket !== latest) return;
    if (!response.ok) throw new Error(payload.detail || "Calculation failed.");

    render(input.seats, payload.hands);
    const how = payload.mode === "exact"
      ? "exact"
      : Math.round(payload.trials).toLocaleString() + " simulations";
    setStatus(how + " in " + payload.seconds + " seconds");
  } catch (error) {
    if (ticket !== latest) return;
    clearResults();
    setStatus(error.message, true);
  }
}

function clearAll() {
  allInputs.forEach((input) => { input.value = ""; });
  refresh();
  setStatus("");
  setActive(allInputs[0]);
}

// Build order is dealing order: hand 1, hand 2, the board, then hands 3-8.
buildSeat(0);
buildSeat(1);
buildBoard();
for (let seat = 2; seat < MAX_PLAYERS; seat++) buildSeat(seat);
buildDeck();

clearBtn.addEventListener("click", clearAll);
setStatus("");
setActive(allInputs[0]);
