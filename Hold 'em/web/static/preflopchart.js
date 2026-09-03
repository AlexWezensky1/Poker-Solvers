"use strict";

/* Preflop chart: a hand-vs-hand equity table for every one of the 169
   starting hands. The layout is the standard 13 x 13: pairs down the
   diagonal, suited hands above it, offsuit hands below.

   The left chart is the hero. Click a cell and every cell on the right
   colours by that hero's equity against it. A range button (top 5 %,
   top 10 %, ...) picks a subset of opponent hands and shows the weighted
   average equity of the hero against exactly those hands. Weighting is by
   combos: pairs are 6 each, suited 4, offsuit 12, so the answer matches
   what one would get by dealing at random. */

const RANKS = "AKQJT98765432";

// Hand types in the same order as the chart file. Kept in one place so the
// three grids -- data, hero, opponent -- always index the same hand.
const HAND_ORDER = (() => {
  const list = [];
  for (const r of RANKS) list.push(r + r);
  for (let i = 0; i < RANKS.length; i++) {
    for (let j = i + 1; j < RANKS.length; j++) list.push(RANKS[i] + RANKS[j] + "s");
  }
  for (let i = 0; i < RANKS.length; i++) {
    for (let j = i + 1; j < RANKS.length; j++) list.push(RANKS[i] + RANKS[j] + "o");
  }
  return list;
})();

// Standard combo counts: a pair has C(4,2) = 6 possible pairings, a suited
// hand 4 (one per suit), an offsuit 12 (4 * 3). Weighting the averages by
// these matches the frequency each hand comes up in a real deal.
function combosOf(label) {
  if (label[0] === label[1]) return 6;
  return label.endsWith("s") ? 4 : 12;
}

// The 13 x 13 layout: cell (row, col) with row <= col is the "col-row" suited
// hand (or the pair when row == col), and row > col is the offsuit hand.
// So AKs sits at (0, 1), AK offsuit at (1, 0), pairs run down the diagonal.
function labelAt(row, col) {
  if (row === col) return RANKS[row] + RANKS[row];
  if (row < col) return RANKS[row] + RANKS[col] + "s";
  return RANKS[col] + RANKS[row] + "o";
}

const RANGE_PERCENTS = [5, 10, 15, 20, 25, 50, 100];

const loadingEl = document.getElementById("loading");
const missingEl = document.getElementById("missing");
const contentEl = document.getElementById("content");
const heroEl = document.getElementById("hero-grid");
const oppEl = document.getElementById("opp-grid");
const pickerEl = document.getElementById("range-picker");
const pickedEl = document.getElementById("picked");
const answerEl = document.getElementById("answer");
const progressEl = document.getElementById("progress");

let chart = null;      // { hero: { villain: equity, ... }, ... }
let heroPick = null;   // the label the user has selected as their own hand
let rangePct = 100;    // top X% of opponent hands, ranked by strength vs random

const heroCells = new Map();  // label -> cell element
const oppCells = new Map();

const strengthRank = new Map();  // label -> position, 0 is strongest

async function load() {
  try {
    const response = await fetch("preflop-chart.json", { cache: "no-store" });
    if (!response.ok) throw new Error(response.status);
    chart = await response.json();
  } catch (err) {
    loadingEl.hidden = true;
    missingEl.hidden = false;
    return;
  }
  loadingEl.hidden = true;
  contentEl.hidden = false;

  rankByStrength();
  buildRangePicker();
  buildGrid(heroEl, heroCells, onPickHero);
  buildGrid(oppEl, oppCells, null);
  reportProgress();
  colourOpponents();
}

// Each hand's average equity against every other hand (weighted by combos):
// that is a hand's overall preflop strength, and it sorts the range picker.
function rankByStrength() {
  const scores = [];
  for (const label of HAND_ORDER) {
    let total = 0;
    let weight = 0;
    const row = chart.grid[label];
    if (!row) { scores.push([label, 0]); continue; }
    for (const other of HAND_ORDER) {
      const value = row[other];
      if (value == null) continue;
      const w = combosOf(other);
      total += value * w;
      weight += w;
    }
    scores.push([label, weight > 0 ? total / weight : 0]);
  }
  scores.sort((a, b) => b[1] - a[1]);
  scores.forEach(([label], i) => strengthRank.set(label, i));
}

function buildRangePicker() {
  for (const pct of RANGE_PERCENTS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "range-btn" + (pct === rangePct ? " on" : "");
    button.textContent = "Top " + pct + "%";
    button.addEventListener("click", () => {
      rangePct = pct;
      pickerEl.querySelectorAll(".range-btn")
        .forEach((b) => b.classList.toggle("on", b === button));
      updateAnswer();
      colourOpponents();
    });
    pickerEl.appendChild(button);
  }
}

function buildGrid(container, store, onClick) {
  for (let row = 0; row < 13; row++) {
    for (let col = 0; col < 13; col++) {
      const label = labelAt(row, col);
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "cell";
      if (row === col) cell.classList.add("pair");

      const name = document.createElement("span");
      name.className = "label";
      name.textContent = label;
      cell.appendChild(name);

      const val = document.createElement("span");
      val.className = "val";
      cell.appendChild(val);

      if (onClick) cell.addEventListener("click", () => onClick(label));
      else cell.addEventListener("click", () => explainOpponent(label));

      container.appendChild(cell);
      store.set(label, cell);
    }
  }
}

function onPickHero(label) {
  heroPick = label;
  for (const [name, cell] of heroCells) {
    cell.classList.toggle("picked", name === label);
  }
  updatePicked();
  updateAnswer();
  colourOpponents();
}

function updatePicked() {
  pickedEl.textContent = heroPick
    ? "You hold " + prettyHand(heroPick) + "."
    : "Pick a hand from the grid on the left.";
}

function prettyHand(label) {
  if (label[0] === label[1]) return "pocket " + rankWord(label[0]);
  return label[0] + label[1] + (label.endsWith("s") ? " suited" : " offsuit");
}

function rankWord(char) {
  const words = { A: "aces", K: "kings", Q: "queens", J: "jacks", T: "tens",
                  9: "nines", 8: "eights", 7: "sevens", 6: "sixes", 5: "fives",
                  4: "fours", 3: "threes", 2: "deuces" };
  return words[char] || char + "s";
}

// The set of opponent hands at the current top-X% range, ranked by strength.
function inRange() {
  const size = Math.round(HAND_ORDER.length * rangePct / 100);
  return new Set(HAND_ORDER.filter((label) => strengthRank.get(label) < size));
}

function updateAnswer() {
  if (!heroPick) { answerEl.textContent = ""; return; }
  const range = inRange();
  const row = chart.grid[heroPick];
  if (!row) { answerEl.textContent = ""; return; }

  let total = 0;
  let weight = 0;
  let cells = 0;
  for (const opponent of range) {
    if (opponent === heroPick) continue;  // exclude the hero from its own range
    const value = row[opponent];
    if (value == null) continue;
    const w = combosOf(opponent);
    total += value * w;
    weight += w;
    cells++;
  }
  if (!weight) { answerEl.textContent = ""; return; }
  const pct = total / weight;
  answerEl.innerHTML = pct.toFixed(2) + "%<span class=\"against\">" +
    " against top " + rangePct + "% (" + cells + " hands)</span>";
}

// Colour every opponent cell by hero's equity against it, and mark which
// cells sit inside the current range.
function colourOpponents() {
  const range = inRange();
  for (const [label, cell] of oppCells) {
    const val = cell.querySelector(".val");
    cell.classList.toggle("in-range", range.has(label));
    if (!heroPick) {
      val.textContent = "";
      cell.style.background = "";
      cell.classList.remove("absent");
      continue;
    }
    const value = chart.grid[heroPick] ? chart.grid[heroPick][label] : null;
    if (value == null) {
      val.textContent = "";
      cell.style.background = "";
      cell.classList.add("absent");
      continue;
    }
    cell.classList.remove("absent");
    val.textContent = value.toFixed(0) + "%";
    cell.style.background = equityColour(value);
  }
}

// A green-to-red heatmap: 50% is neutral, dominant hands green, dominated red.
function equityColour(pct) {
  const t = Math.max(0, Math.min(1, (pct - 25) / 50));  // clamp to a working range
  const r = Math.round(224 * (1 - t) + 63 * t);
  const g = Math.round(82 * (1 - t) + 178 * t);
  const b = Math.round(82 * (1 - t) + 127 * t);
  return "rgba(" + r + "," + g + "," + b + ", 0.28)";
}

function explainOpponent(label) {
  if (!heroPick) { onPickHero(label); return; }
  const value = chart.grid[heroPick][label];
  if (value == null) return;
  answerEl.innerHTML = value.toFixed(2) + "%" +
    "<span class=\"against\"> as " + prettyHand(heroPick) +
    " against " + prettyHand(label) + "</span>";
}

function reportProgress() {
  const total = HAND_ORDER.length * HAND_ORDER.length;
  let filled = 0;
  for (const row of Object.values(chart.grid || {})) filled += Object.keys(row).length;
  if (chart.complete) {
    progressEl.textContent = "";
    return;
  }
  const pct = (100 * filled / total).toFixed(1);
  progressEl.textContent = "Partial chart: " + filled + " of " + total +
    " cells walked (" + pct + "%). Missing cells will not colour.";
}

load();
