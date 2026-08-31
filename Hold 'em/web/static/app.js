"use strict";

const RANKS = "23456789TJQKA";
const SUITS = "shdc";
const MAX_PLAYERS = 8;
const BOARD_LABELS = ["Flop", "Flop", "Flop", "Turn", "River"];

// The deck grid: one row per suit, ranks running high to low.
const DECK_RANKS = "AKQJT98765432";
const SUIT_PIPS = { s: "♠", h: "♥", d: "♦", c: "♣" };

// Seat ring, as a percentage of the table box. Hand 1 sits at the bottom and
// the rest run clockwise around it; the board sits in the middle.
const RING_X = 38;
const RING_Y = 34;

const boardEl = document.getElementById("board");
const playersEl = document.getElementById("players");
const deckEl = document.getElementById("deck");
const statusEl = document.getElementById("status");
const calculateBtn = document.getElementById("calculate");
const clearBtn = document.getElementById("clear");
const trialsEl = document.getElementById("trials");

// allInputs is built in dealing order, so it doubles as the fill order:
// hand 1, hand 2, flop, turn, river, hands 3-8.
const allInputs = [];
const boardInputs = [];
const players = [];
const deckButtons = new Map();

// The slot the next deck click lands in.
let active = null;

/* ---------- card text handling ---------- */

// Strips anything that cannot be part of a card and spells "10" as "T".
// Length is left alone; the caller decides what to keep and what spills over.
function clean(value) {
  const v = value.replace(/[^0-9a-zA-Z]/g, "");
  return v.slice(0, 2) === "10" ? "T" + v.slice(2) : v;
}

// Canonical "Ah" casing for a partial or complete card.
function shape(value) {
  if (value.length >= 1) value = value[0].toUpperCase() + value.slice(1);
  if (value.length >= 2) value = value[0] + value[1].toLowerCase();
  return value;
}

function isCard(value) {
  return value.length === 2 && RANKS.includes(value[0]) && SUITS.includes(value[1]);
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
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("aria-label", "card");

  // A slot keeps one card and hands the rest to the slot after it, so typing
  // or pasting "AsKsQhQd" straight into the first box fills four boxes.
  input.addEventListener("input", () => {
    const chars = clean(input.value);
    input.value = shape(chars.slice(0, 2));
    const overflow = chars.slice(2);

    if (isCard(input.value)) {
      const next = allInputs[allInputs.indexOf(input) + 1];
      if (next) {
        next.focus();
        if (overflow) {
          next.value = overflow;
          next.dispatchEvent(new Event("input"));
          return;  // that call finishes the chain, refresh included
        }
      }
    }
    refresh();
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Backspace" && input.value === "") {
      const prev = allInputs[allInputs.indexOf(input) - 1];
      if (prev) { prev.focus(); prev.select(); event.preventDefault(); }
    } else if (event.key === "Enter") {
      calculate();
    }
  });

  input.addEventListener("focus", () => { input.select(); setActive(input); });

  allInputs.push(input);
  return input;
}

function buildBoard() {
  BOARD_LABELS.forEach((label) => {
    const slot = document.createElement("div");
    slot.className = "slot";
    const input = makeCardInput();
    const caption = document.createElement("span");
    caption.className = "slot-label";
    caption.textContent = label;
    slot.append(input, caption);
    boardEl.appendChild(slot);
    boardInputs.push(input);
  });
}

// Where a seat sits on the ring, counted clockwise from the bottom.
function seatPosition(index) {
  const angle = (index / MAX_PLAYERS) * 2 * Math.PI;
  return {
    left: 50 - RING_X * Math.sin(angle),
    top: 50 + RING_Y * Math.cos(angle),
  };
}

function buildSeat(seat) {
  const row = document.createElement("div");
  row.className = "player";
  const spot = seatPosition(seat);
  row.style.left = spot.left + "%";
  row.style.top = spot.top + "%";

  const number = document.createElement("div");
  number.className = "seat";
  number.textContent = "Hand " + (seat + 1);

  const holecards = document.createElement("div");
  holecards.className = "holecards";
  const inputs = [makeCardInput(), makeCardInput()];
  holecards.append(...inputs);

  const result = document.createElement("div");
  result.className = "result empty";

  row.append(number, holecards, result);
  playersEl.appendChild(row);
  players.push({ row, inputs, result });
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
// and greys out the deck cards that are already on the table.
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

  deckButtons.forEach((button, card) => button.classList.toggle("used", seen.has(card)));

  clearResults();
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

  const hands = [];
  players.forEach((player, seat) => {
    const [a, b] = player.inputs.map((input) => input.value);
    if (a === "" && b === "") return;
    if (!isCard(a) || !isCard(b)) {
      throw new Error("Hand " + (seat + 1) + " needs two cards, like As Ks.");
    }
    hands.push({ seat, text: a + b });
  });

  if (hands.length < 2) throw new Error("Enter at least two hands.");

  const used = [...board, ...hands.flatMap((hand) => [hand.text.slice(0, 2), hand.text.slice(2)])];
  const duplicate = used.find((card, i) => used.indexOf(card) !== i);
  if (duplicate) throw new Error(duplicate + " is used more than once.");

  return { board, hands };
}

function render(hands, results) {
  const best = Math.max(...results.map((r) => r.equity));
  results.forEach((result, i) => {
    const player = players[hands[i].seat];
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

    const breakdown = document.createElement("div");
    breakdown.className = "breakdown";
    breakdown.textContent = "win " + result.win.toFixed(2) + "%  ·  tie " + result.tie.toFixed(2) + "%";

    player.result.append(pct, bar, breakdown);

    if (result.best_hand) {
      const made = document.createElement("div");
      made.className = "breakdown";
      made.textContent = result.best_hand;
      made.title = result.best_hand;  // the seat is narrow, so it may be clipped
      player.result.appendChild(made);
    }

    player.row.classList.toggle("leader", result.equity >= best - 1e-9);
  });
}

async function calculate() {
  let input;
  try {
    input = collect();
  } catch (error) {
    clearResults();
    setStatus(error.message, true);
    return;
  }

  calculateBtn.disabled = true;
  setStatus("Calculating…");
  try {
    const response = await fetch("/holdem/api/equity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hands: input.hands.map((hand) => hand.text),
        board: input.board.join(""),
        // "exact" leaves trials unused; the server enumerates every runout.
        mode: trialsEl.value === "exact" ? "exact" : "auto",
        trials: trialsEl.value === "exact" ? 1 : Number(trialsEl.value),
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Calculation failed.");

    render(input.hands, payload.hands);
    const runs = payload.trials.toLocaleString();
    setStatus(runs + " runouts in " + payload.seconds + " seconds");
  } catch (error) {
    clearResults();
    setStatus(error.message, true);
  } finally {
    calculateBtn.disabled = false;
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

calculateBtn.addEventListener("click", calculate);
clearBtn.addEventListener("click", clearAll);
setStatus("");
setActive(allInputs[0]);
