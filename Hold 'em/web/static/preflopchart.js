"use strict";

/* Preflop chart: a hand-vs-hand equity table for every one of the 169
   starting hands. The layout is the standard 13 x 13: pairs down the
   diagonal, suited hands above it, offsuit hands below.

   The left chart is the hero. Click a cell and every cell on the right
   colours by that hero's equity against it; hands outside the opponent's
   range go grey, so the range being averaged over is visible rather than
   implied.

   Ranges are measured in combinations, never in names. There are 1,326
   hands you can be dealt: a pair is 6 of them, a suited hand 4, an offsuit
   hand 12. "Top 10%" therefore means the strongest tenth of those 1,326,
   which is what a range means at a table, and not the strongest tenth of
   the 169 names -- those are two different sets, because the names at the
   top of the ranking are mostly pairs and suited hands and carry the
   fewest combinations each. */

const RANKS = "AKQJT98765432";

// Hand types in the same order as the chart file. Kept in one place so the
// grids -- data, hero, opponent, percentile -- always index the same hand.
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
// hand 4 (one per suit), an offsuit 12 (4 * 3). Weighting by these matches
// the frequency each hand actually comes up in a deal.
function combosOf(label) {
  if (label[0] === label[1]) return 6;
  return label.endsWith("s") ? 4 : 12;
}

//: 13 * 6 + 78 * 4 + 78 * 12. The whole deal, in combinations.
const TOTAL_COMBOS = HAND_ORDER.reduce((sum, l) => sum + combosOf(l), 0);

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
const pctEl = document.getElementById("pct-grid");
const pickerEl = document.getElementById("range-picker");
const pickedEl = document.getElementById("picked");
const answerEl = document.getElementById("answer");
const progressEl = document.getElementById("progress");
const sliderEl = document.getElementById("range-slider");
const bandEl = document.getElementById("range-band");
const loEl = document.getElementById("handle-lo");
const hiEl = document.getElementById("handle-hi");
const readoutEl = document.getElementById("range-readout");

let chart = null;      // { hero: { villain: equity, ... }, ... }
let heroPick = null;   // the label the user has selected as their own hand
let rangeLo = 0;       // the range is a band of the field, in whole percent
let rangeHi = 100;

const heroCells = new Map();  // label -> cell element
const oppCells = new Map();
const pctCells = new Map();

const strengthRank = new Map();   // label -> position, 0 is strongest
const bandStart = new Map();      // label -> percentile it opens at
const bandEnd = new Map();        // label -> percentile it closes at

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
  buildGrid(pctEl, pctCells, onPickHero);
  wireSlider();
  reportProgress();
  refresh();
}

// Each hand's average equity against every other hand (weighted by combos):
// that is a hand's overall preflop strength, and it sorts the field. The
// running total of combos down that order is what a percentile means here.
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

  let cumulative = 0;
  scores.forEach(([label], i) => {
    strengthRank.set(label, i);
    bandStart.set(label, 100 * cumulative / TOTAL_COMBOS);
    cumulative += combosOf(label);
    bandEnd.set(label, 100 * cumulative / TOTAL_COMBOS);
  });
}

function buildRangePicker() {
  for (const pct of RANGE_PERCENTS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "range-btn";
    button.dataset.pct = String(pct);
    button.textContent = "Top " + pct + "%";
    button.addEventListener("click", () => setRange(0, pct));
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
  for (const [name, cell] of pctCells) {
    cell.classList.toggle("picked", name === label);
  }
  refresh();
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

/* ---------- the range ---------- */

// A hand is in range when its slice of the field overlaps the band. Slices are
// combinations, so a range of "10% to 40%" is 30% of the hands you can be
// dealt, not 30% of the 169 names.
function inRange() {
  return new Set(HAND_ORDER.filter((label) =>
    bandEnd.get(label) > rangeLo && bandStart.get(label) < rangeHi));
}

function setRange(lo, hi) {
  rangeLo = Math.max(0, Math.min(100, Math.round(lo)));
  rangeHi = Math.max(0, Math.min(100, Math.round(hi)));
  if (rangeLo > rangeHi) [rangeLo, rangeHi] = [rangeHi, rangeLo];
  refresh();
}

function refresh() {
  const range = inRange();
  paintSlider();
  paintOpponents(range);
  paintPercentiles(range);
  updatePicked();
  updateAnswer(range);
  for (const button of pickerEl.querySelectorAll(".range-btn")) {
    const pct = Number(button.dataset.pct);
    button.classList.toggle("on", rangeLo === 0 && rangeHi === pct);
  }
}

function updatePicked() {
  pickedEl.textContent = heroPick
    ? "You hold " + prettyHand(heroPick) + "."
    : "Pick a hand from either grid.";
}

function updateAnswer(range) {
  if (!heroPick) { answerEl.textContent = ""; return; }
  const row = chart.grid[heroPick];
  if (!row) { answerEl.textContent = ""; return; }

  let total = 0;
  let weight = 0;
  let names = 0;
  for (const opponent of range) {
    if (opponent === heroPick) continue;  // exclude the hero from its own range
    const value = row[opponent];
    if (value == null) continue;
    const w = combosOf(opponent);
    total += value * w;
    weight += w;
    names++;
  }
  if (!weight) { answerEl.textContent = ""; return; }
  answerEl.innerHTML = (total / weight).toFixed(2) + "%" +
    "<span class=\"against\"> against " + describeRange() + ", " +
    names + " hands and " + weight.toLocaleString() + " combos</span>";
}

function describeRange() {
  if (rangeLo === 0 && rangeHi === 100) return "the whole field";
  if (rangeLo === 0) return "the top " + rangeHi + "%";
  return rangeLo + "% to " + rangeHi + "%";
}

/* ---------- painting ---------- */

// Colour every opponent cell by hero's equity against it. Hands outside the
// range go grey: they are not in the average, so they should not read as if
// they were.
function paintOpponents(range) {
  for (const [label, cell] of oppCells) {
    const val = cell.querySelector(".val");
    const inside = range.has(label);
    cell.classList.toggle("in-range", inside);
    cell.classList.toggle("out-range", !inside);

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
    cell.style.background = inside ? equityColour(value) : "";
  }
}

// The percentile grid says where each hand sits in the field, and shades by
// how much of the selected band it falls inside.
function paintPercentiles(range) {
  for (const [label, cell] of pctCells) {
    const val = cell.querySelector(".val");
    const inside = range.has(label);
    val.textContent = formatPercentile(bandEnd.get(label));
    cell.classList.toggle("in-range", inside);
    cell.classList.toggle("out-range", !inside);
    cell.style.background = inside ? percentileColour(bandEnd.get(label)) : "";
  }
}

// Under ten percent the first decimal is the whole story -- the top handful of
// hands all round to the same integer otherwise.
function formatPercentile(pct) {
  return pct < 10 ? pct.toFixed(1) : pct.toFixed(0);
}

// A green-to-red heatmap: 50% is neutral, dominant hands green, dominated red.
function equityColour(pct) {
  const t = Math.max(0, Math.min(1, (pct - 25) / 50));  // clamp to a working range
  const r = Math.round(224 * (1 - t) + 63 * t);
  const g = Math.round(82 * (1 - t) + 178 * t);
  const b = Math.round(82 * (1 - t) + 127 * t);
  return "rgba(" + r + "," + g + "," + b + ", 0.28)";
}

// Strongest hands densest; the shade fades as the percentile falls away.
function percentileColour(pct) {
  const t = Math.max(0, Math.min(1, 1 - pct / 100));
  return "rgba(63, 178, 127, " + (0.06 + t * 0.42).toFixed(3) + ")";
}

function explainOpponent(label) {
  if (!heroPick) { onPickHero(label); return; }
  const value = chart.grid[heroPick][label];
  if (value == null) return;
  answerEl.innerHTML = value.toFixed(2) + "%" +
    "<span class=\"against\"> as " + prettyHand(heroPick) +
    " against " + prettyHand(label) + "</span>";
}

/* ---------- the band slider ---------- */

function paintSlider() {
  loEl.style.left = rangeLo + "%";
  hiEl.style.left = rangeHi + "%";
  bandEl.style.left = rangeLo + "%";
  bandEl.style.width = (rangeHi - rangeLo) + "%";
  loEl.setAttribute("aria-valuenow", String(rangeLo));
  hiEl.setAttribute("aria-valuenow", String(rangeHi));
  readoutEl.textContent = rangeLo + "% – " + rangeHi + "%";
}

function pctFromEvent(event) {
  const box = sliderEl.getBoundingClientRect();
  return Math.round(100 * (event.clientX - box.left) / box.width);
}

function wireSlider() {
  let dragging = null;   // "lo", "hi" or "band"
  let grabbedAt = 0;     // where in the band the drag started
  let bandWidth = 0;

  function move(event) {
    if (!dragging) return;
    const at = pctFromEvent(event);
    if (dragging === "lo") setRange(Math.min(at, rangeHi), rangeHi);
    else if (dragging === "hi") setRange(rangeLo, Math.max(at, rangeLo));
    else {
      // Dragging the band keeps its width and stops at either end.
      let lo = Math.max(0, Math.min(100 - bandWidth, at - grabbedAt));
      setRange(lo, lo + bandWidth);
    }
  }

  function release() {
    dragging = null;
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", release);
  }

  function grab(what) {
    return (event) => {
      event.preventDefault();
      dragging = what;
      bandWidth = rangeHi - rangeLo;
      grabbedAt = pctFromEvent(event) - rangeLo;
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", release);
    };
  }

  loEl.addEventListener("pointerdown", grab("lo"));
  hiEl.addEventListener("pointerdown", grab("hi"));
  bandEl.addEventListener("pointerdown", grab("band"));

  // A click on the bare track brings the nearer handle to it.
  sliderEl.addEventListener("pointerdown", (event) => {
    if (event.target !== sliderEl && !event.target.classList.contains("track")) return;
    const at = pctFromEvent(event);
    if (Math.abs(at - rangeLo) <= Math.abs(at - rangeHi)) setRange(at, rangeHi);
    else setRange(rangeLo, at);
  });

  // Arrow keys nudge a handle a point at a time, which is the whole reason
  // the scale is in whole percent.
  for (const [el, which] of [[loEl, "lo"], [hiEl, "hi"]]) {
    el.addEventListener("keydown", (event) => {
      const step = event.key === "ArrowLeft" || event.key === "ArrowDown" ? -1
                 : event.key === "ArrowRight" || event.key === "ArrowUp" ? 1 : 0;
      if (!step) return;
      event.preventDefault();
      if (which === "lo") setRange(Math.min(rangeLo + step, rangeHi), rangeHi);
      else setRange(rangeLo, Math.max(rangeHi + step, rangeLo));
    });
  }
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
