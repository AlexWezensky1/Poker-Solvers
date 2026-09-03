"use strict";

const RANKS = "23456789TJQKA";
const SUITS = "shdc";
const MAX_PLAYERS = 8;
// Two community cards on each of the three streets.
const STREETS = [2, 2, 2];
const BOARD_SIZE = STREETS.reduce((a, b) => a + b, 0);

// The deck grid: one row per suit, ranks running high to low.
const DECK_RANKS = "AKQJT98765432";
const SUIT_PIPS = { s: "♠", h: "♥", d: "♦", c: "♣" };

const boardEl = document.getElementById("board");
const playersEl = document.getElementById("players");
const deckEl = document.getElementById("deck");
const statusEl = document.getElementById("status");
const clearBtn = document.getElementById("clear");
const speedEl = document.getElementById("speed");

// Six community cards is C(48,6) runouts before the flop -- twelve million, too
// many to walk while somebody waits. Fast lets the server sample those and walk
// the rest; Precise always walks.
const FAST_TRIALS = 250000;
const PRECISE_TRIALS = 1000000;
let speed = "fast";

// allInputs is built in dealing order, so it doubles as the fill order:
// hand 1, hand 2, flop, turn, river, hands 3-8.
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

// A slot shows "A♠" but everything downstream still works in "As", so the
// canonical card rides along in a data attribute and these two are the only
// places that know the difference.
function cardOf(input) {
  return input.dataset.card || "";
}

function setCard(input, card) {
  input.dataset.card = card;
  input.value = card ? card[0] + SUIT_PIPS[card[1]] : "";
  input.setAttribute("aria-label", card || "empty card slot");
}

/* ---------- the slot the deck deals into ---------- */

function setActive(input) {
  if (active === input) return;
  active = input;
  allInputs.forEach((slot) => slot.classList.toggle("active", slot === active));
  // Deliberately no focus() here. Arming a slot is a paint job -- the outline
  // says where the next card lands -- and moving the caret to it made the
  // browser drag that slot into view, so dealing from the deck scrolled the
  // deck off the screen. The slots are readOnly, so focus earns nothing;
  // tapping one still focuses it the ordinary way, which is what keeps Tab
  // working through the focus listener below.
}

// The next empty slot after the given position in dealing order, wrapping
// round to the start.
function nextEmpty(from) {
  for (let step = 1; step <= allInputs.length; step++) {
    const slot = allInputs[(from + step) % allInputs.length];
    if (cardOf(slot) === "") return slot;
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

  const from = allInputs.indexOf(active);
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
  setCard(input, "");

  // Safari on iOS zooms the page in on a focused control whose text is under
  // 16px, and a card slot is well under. Blocking the default on mousedown
  // stops the tap taking focus, which is what it was zooming to; the click
  // still lands, and Tab still focuses the slot the ordinary way.
  input.addEventListener("mousedown", (event) => event.preventDefault());

  // Clicking a slot that holds a card sends that card back to the deck. Either
  // way the slot is left armed, so the next deck click deals into it.
  input.addEventListener("click", () => {
    if (cardOf(input) !== "") {
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
  let dealt = 0;
  const openers = new Set();
  for (const size of STREETS) { openers.add(dealt); dealt += size; }
  for (let i = 0; i < BOARD_SIZE; i++) {
    const slot = document.createElement("div");
    slot.className = "slot";
    // Each street stands off from the one before, so the pairs read at a glance.
    if (i > 0 && openers.has(i)) slot.classList.add("street");
    const input = makeCardInput();
    slot.appendChild(input);
    boardEl.appendChild(slot);
    boardInputs.push(input);
  }
}

function buildSeat(seat) {
  const row = document.createElement("div");
  row.className = "player";

  const header = document.createElement("div");
  header.className = "seat-row";

  const number = document.createElement("div");
  number.className = "seat";
  number.textContent = "Hand " + (seat + 1);

  // A folded hand is out of the pot, but its cards stay off the deck so
  // nobody else is dealt them either -- which changes everybody's equity.
  const fold = document.createElement("button");
  fold.type = "button";
  fold.className = "fold";
  fold.textContent = "Fold";
  fold.addEventListener("click", () => {
    const player = players[seat];
    setFolded(player, !player.folded);
    refresh();
  });
  header.append(number, fold);

  const holecards = document.createElement("div");
  holecards.className = "holecards";
  const inputs = [makeCardInput(), makeCardInput()];
  holecards.append(...inputs);

  const result = document.createElement("div");
  result.className = "result empty";

  row.append(header, holecards, result);
  playersEl.appendChild(row);
  players.push({ row, inputs, result, fold, folded: false });
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
function setFolded(player, folded) {
  player.folded = folded;
  player.fold.textContent = folded ? "Folded" : "Fold";
  player.fold.classList.toggle("on", folded);
  player.row.classList.toggle("folded", folded);
  player.inputs.forEach((input) => { input.disabled = folded; });
}

function refresh() {
  const seen = new Map();
  allInputs.forEach((input) => {
    const value = cardOf(input);
    if (!isCard(value)) return;
    seen.set(value, (seen.get(value) || 0) + 1);
  });

  allInputs.forEach((input) => {
    const value = cardOf(input);
    const bad = value !== "" && (!isCard(value) || seen.get(value) > 1);
    input.classList.toggle("invalid", bad);
    input.classList.remove("suit-s", "suit-h", "suit-d", "suit-c");
    if (isCard(value)) input.classList.add("suit-" + value[1]);
  });

  deckButtons.forEach((button, card) => button.classList.toggle("used", seen.has(card)));

  rememberTable();
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

function setStatus(message, isError, detail) {
  statusEl.querySelector(".status-line").textContent = message || "";
  statusEl.querySelector(".status-detail").textContent = detail || "";
  statusEl.classList.toggle("error", Boolean(isError));
}

/* ---------- calculating ---------- */

function collect() {
  const board = [];
  for (const input of boardInputs) {
    const card = cardOf(input);
    if (card === "") continue;
    if (!isCard(card)) throw new Error("'" + card + "' is not a card.");
    board.push(card);
  }

  const hands = [];
  const dead = [];
  players.forEach((player, seat) => {
    const [a, b] = player.inputs.map(cardOf);
    if (a === "" && b === "") return;
    if (!isCard(a) || !isCard(b)) {
      throw new Error("Hand " + (seat + 1) + " needs two cards, like As Ks.");
    }
    if (player.folded) dead.push(a, b);
    else hands.push({ seat, text: a + b });
  });

  if (hands.length < 2) throw new Error("Enter at least two hands.");

  const used = [...board, ...hands.flatMap((hand) => [hand.text.slice(0, 2), hand.text.slice(2)])];
  const duplicate = used.find((card, i) => used.indexOf(card) !== i);
  if (duplicate) throw new Error(duplicate + " is used more than once.");

  return { board, hands, dead };
}

// The ten categories, best first, as a fold-out table. Every runout finishes
// as something, so the column sums to 100%.
function madeOdds(made) {
  const box = document.createElement("details");
  box.className = "made";

  const head = document.createElement("summary");
  head.textContent = "Hand at showdown";
  box.appendChild(head);

  const table = document.createElement("div");
  table.className = "made-rows";
  for (const row of made) {
    const line = document.createElement("div");
    // A category it cannot make is still worth a row -- the list reads the
    // same for every seat, so two of them can be compared straight down.
    line.className = row.pct ? "made-row" : "made-row never";
    const name = document.createElement("span");
    name.textContent = row.name;
    const pct = document.createElement("span");
    pct.textContent = row.pct.toFixed(2) + "%";
    line.append(name, pct);
    table.appendChild(line);
  }
  box.appendChild(table);
  return box;
}

// The multiplication that lands at the runout count: n × (n-1) × ... × (n-k+1),
// divided by k! since a runout is a combination rather than a sequence -- the
// order of the community cards does not matter. Returned empty when there is
// nothing to spell out.
function exhaustiveFormula(deck, toCome) {
  if (toCome <= 0) return "";
  const perm = [];
  for (let i = 0; i < toCome; i++) perm.push(deck - i);
  const denom = toCome > 1 ? factorial(toCome) : 1;
  const numer = perm.join(" × ");
  return denom === 1 ? numer : numer + " ÷ " + denom;
}

function factorial(n) {
  let out = 1;
  for (let i = 2; i <= n; i++) out *= i;
  return out;
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

    const win = document.createElement("div");
    win.className = "breakdown";
    win.textContent = "Win " + result.win.toFixed(2) + "%";

    const tie = document.createElement("div");
    tie.className = "breakdown";
    tie.textContent = "Tie " + result.tie.toFixed(2) + "%";

    player.result.append(pct, bar, win, tie);

    // What the hand turns into by the river, folded away because it is ten
    // rows and most of them are usually zero.
    if (result.made && result.made.length) {
      player.result.appendChild(madeOdds(result.made));
    }

    if (result.best_hand) {
      const made = document.createElement("div");
      made.className = "breakdown";
      const label = result.best_hand[0].toUpperCase() + result.best_hand.slice(1);
      made.textContent = label;
      made.title = label;  // the seat is narrow, so it may be clipped
      player.result.appendChild(made);
    }

    player.row.classList.toggle("leader", result.equity >= best - 1e-9);
  });
}

// Cards can land faster than the server answers, so each run takes a ticket
// and a stale reply is dropped rather than painted over a newer table.
let latest = 0;

// Every card change lands here. Two complete hands is the trigger; anything
// short of that is a half dealt table, so it waits quietly rather than
// complaining about input the player is still in the middle of giving.
function autoCalculate() {
  let input;
  try {
    input = collect();
  } catch (error) {
    latest++;  // strand any answer still in flight for the old table
    setStatus("");
    return;
  }
  run(input);
}

async function run(input) {
  const ticket = ++latest;
  setStatus("Calculating…");
  try {
    const response = await fetch("/noah/api/equity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hands: input.hands.map((hand) => hand.text),
        board: input.board.join(""),
        dead: input.dead.join(""),
        mode: speed === "fast" ? "auto" : "exact",
        trials: speed === "precise" ? PRECISE_TRIALS : FAST_TRIALS,
      }),
    });
    const payload = await response.json();
    if (ticket !== latest) return;
    if (!response.ok) throw new Error(payload.detail || "Calculation failed.");

    render(input.hands, payload.hands);
    const runs = payload.trials.toLocaleString();
    const dealt = input.hands.length * 2 + input.board.length + input.dead.length;
      const deck = 52 - dealt;
      const toCome = BOARD_SIZE - input.board.length;
      const formula = exhaustiveFormula(deck, toCome);
    let how, detail = "";
    if (payload.mode !== "exact") {
      how = " simulations";
    } else {
      const noun = payload.trials === 1 ? " runout" : " runouts";
      how = " exhaustive" + noun;
      detail = formula;
    }
    setStatus(runs + how + " in " + payload.seconds + " seconds", false, detail);
  } catch (error) {
    if (ticket !== latest) return;
    clearResults();
    setStatus(error.message, true);
  }
}

/* ---------- the table in the address bar ---------- */

// Everything dealt, as a query string, so a spot can be linked to and come back
// the same. Cards travel in their canonical "As" form -- the pips are only ever
// for the screen -- and a seat with nothing in it is left out entirely.
function tableQuery() {
  const params = new URLSearchParams();
  for (const player of players) {
    const cards = player.inputs.map(cardOf).filter(Boolean).join("");
    if (!cards) continue;
    // A folded hand is out of the pot but its cards are out of the deck, so
    // it travels as `dead` -- one entry per hand rather than a loose pile,
    // which is what lets the cards go back into the seat they came from.
    params.append(player.folded ? "dead" : "ranges", cards);
  }
  const board = boardInputs.map(cardOf).filter(Boolean).join("");
  if (board) params.set("board", board);
  return params.toString();
}

// replaceState, not pushState: dealing a card is not a page the back button
// should have to walk back through one at a time.
function rememberTable() {
  const query = tableQuery();
  history.replaceState(null, "", query ? "?" + query : location.pathname);
}

// "8h7c2h" -> ["8h", "7c", "2h"], dropping anything that is not a card. The
// address bar is the one input here that somebody else may have written.
function readCards(text) {
  return (text.match(/../g) || []).filter(isCard);
}

function restoreTable() {
  const params = new URLSearchParams(location.search);
  const live = params.getAll("ranges");
  const folded = params.getAll("dead");
  const board = readCards(params.get("board") || "");
  if (!live.length && !folded.length && !board.length) return false;

  let seat = 0;
  const fill = (text, isFolded) => {
    if (seat >= players.length) return;
    const player = players[seat++];
    setFolded(player, isFolded);
    const slots = player.inputs;
    readCards(text).slice(0, slots.length)
      .forEach((card, i) => setCard(slots[i], card));
  };
  live.forEach((text) => fill(text, false));
  folded.forEach((text) => fill(text, true));
  board.slice(0, boardInputs.length)
    .forEach((card, i) => setCard(boardInputs[i], card));
  return true;
}

function clearAll() {
  players.forEach((player) => setFolded(player, false));
  allInputs.forEach((input) => setCard(input, ""));
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

for (const button of speedEl.querySelectorAll(".seg")) {
  button.addEventListener("click", () => {
    if (speed === button.dataset.speed) return;
    speed = button.dataset.speed;
    speedEl.querySelectorAll(".seg").forEach((b) => b.classList.toggle("on", b === button));
    autoCalculate();  // the table has not changed, but the answer will
  });
}

clearBtn.addEventListener("click", clearAll);

// A shared link arrives with the table already in it.
restoreTable();
refresh();
setStatus("");
setActive(nextEmpty(-1) || allInputs[0]);
