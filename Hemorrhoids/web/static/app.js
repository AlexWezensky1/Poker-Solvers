"use strict";

const MAX_PLAYERS = 8;
const hands = document.getElementById("hands");
const status = document.getElementById("status");
const results = document.getElementById("results");

function addHand(value) {
  if (hands.children.length >= MAX_PLAYERS) return;
  const row = document.createElement("div");
  row.className = "hand";

  const seat = document.createElement("span");
  seat.className = "seat";

  const input = document.createElement("input");
  input.placeholder = "AsKsQsJsTs";
  input.autocomplete = "off";
  input.spellcheck = false;
  if (value) input.value = value;
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") calculate(); });

  const drop = document.createElement("button");
  drop.type = "button";
  drop.textContent = "×";
  drop.title = "Remove this hand";
  drop.addEventListener("click", () => {
    if (hands.children.length > 2) { row.remove(); renumber(); }
  });

  row.append(seat, input, drop);
  hands.append(row);
  renumber();
}

function renumber() {
  [...hands.children].forEach((row, i) => { row.querySelector(".seat").textContent = i + 1; });
  document.getElementById("add").disabled = hands.children.length >= MAX_PLAYERS;
}

function show(message, isError) {
  status.textContent = message;
  status.classList.toggle("error", Boolean(isError));
}

async function calculate() {
  const texts = [...hands.querySelectorAll("input")].map((i) => i.value.trim()).filter(Boolean);
  if (texts.length < 2) { show("Enter at least two hands.", true); return; }

  show("Working…", false);
  results.hidden = true;

  let payload;
  try {
    const response = await fetch("/hmrs/api/equity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hands: texts,
        board: document.getElementById("board").value,
        mode: document.getElementById("mode").value,
        trials: Number(document.getElementById("trials").value) || 100000,
      }),
    });
    payload = await response.json();
    if (!response.ok) { show(payload.detail || "Something went wrong.", true); return; }
  } catch (err) {
    show("Could not reach the solver.", true);
    return;
  }

  const how = payload.mode === "exact"
    ? "exact"
    : `${Math.round(payload.trials).toLocaleString()} simulations`;
  show(`${payload.board || "opening deal"} — ${how} in ${payload.seconds}s`, false);

  const best = Math.max(...payload.hands.map((h) => h.equity));
  const body = results.querySelector("tbody");
  body.replaceChildren();
  for (const hand of payload.hands) {
    const tr = document.createElement("tr");
    if (hand.equity >= best - 1e-9) tr.className = "best";
    const cells = [
      hand.index + 1,
      hand.hand,
      `${hand.equity.toFixed(2)}%`,
      `${hand.scoop.toFixed(2)}%`,
      `${hand.out.toFixed(2)}%`,
      `${hand.keep.toFixed(2)}%`,
      hand.detail || "",
    ];
    cells.forEach((text, i) => {
      const td = document.createElement("td");
      td.textContent = text;
      if (i === 1) td.className = "cards";
      if (i === 6) td.className = "finish";
      tr.append(td);
    });
    body.append(tr);
  }
  results.hidden = false;
}

document.getElementById("add").addEventListener("click", () => addHand(""));
document.getElementById("go").addEventListener("click", calculate);
document.getElementById("board").addEventListener("keydown", (e) => {
  if (e.key === "Enter") calculate();
});

addHand("AsKsQsJsTs");
addHand("2h3h4h5h6h");
