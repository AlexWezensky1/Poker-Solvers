"use strict";

/* Showdown chart. A hand in HMRDS is five ranks -- suits are dealt but never
   read, and the order inside a hand does not matter -- so the only thing this
   grid keys on is the highest card each side holds. Row is yours, column is
   theirs, and the cell is the average share of the pot your side took across
   every matchup walked for that pairing.

   The chart file is written while the walk is still going, so a cell carries
   its matchup count and the page says how far along the run is. */

const RANKS = "AKQJT98765432";

async function load() {
  const loading = document.getElementById("loading");
  const missing = document.getElementById("missing");
  const content = document.getElementById("content");

  let data;
  try {
    const response = await fetch("showdown-chart.json", { cache: "no-store" });
    if (!response.ok) throw new Error(response.status);
    data = await response.json();
  } catch (err) {
    loading.hidden = true;
    missing.hidden = false;
    return;
  }

  draw(data);
  loading.hidden = true;
  content.hidden = false;
}

function draw(data) {
  const grid = document.getElementById("grid");
  const picked = document.getElementById("picked");
  grid.innerHTML = "";

  // Top-left corner, then the column headers.
  grid.appendChild(headCell(""));
  for (const rank of RANKS) grid.appendChild(headCell(rank));

  for (const row of RANKS) {
    grid.appendChild(headCell(row));
    for (const col of RANKS) {
      const entry = data.grid[row + col];
      const cell = document.createElement("div");
      cell.className = "cell";

      if (!entry) {
        cell.classList.add("blank");
        cell.title = "no hand pairing here";
        grid.appendChild(cell);
        continue;
      }

      cell.textContent = entry.equity.toFixed(1);
      cell.style.background = shade(entry.equity);
      cell.addEventListener("mouseenter", () => {
        picked.innerHTML = "A hand topped by <strong>" + row +
          "</strong> against one topped by <strong>" + col + "</strong>: " +
          "<strong>" + entry.equity.toFixed(2) + "%</strong> of the pot, " +
          "averaged over " + entry.matchups.toLocaleString() +
          (entry.matchups === 1 ? " matchup." : " matchups.");
      });
      grid.appendChild(cell);
    }
  }

  document.getElementById("progress").textContent = summary(data);
}

function headCell(text) {
  const head = document.createElement("div");
  head.className = "head";
  head.textContent = text;
  return head;
}

// Red below an even split, green above it, flat panel colour at 50%.
function shade(pct) {
  const away = Math.max(-1, Math.min(1, (pct - 50) / 50));
  if (away >= 0) return "rgba(63, 178, 127, " + (0.10 + away * 0.55).toFixed(3) + ")";
  return "rgba(224, 82, 82, " + (0.10 + -away * 0.55).toFixed(3) + ")";
}

function summary(data) {
  const walked = data.matchups.toLocaleString();
  const hours = (data.seconds / 3600).toFixed(1);
  if (data.complete) {
    return "Every pair walked: " + walked + " matchups, in " + hours +
      " hours of machine time.";
  }
  const of = data.pairs_total
    ? " of the " + data.pairs_total.toLocaleString() + " possible"
    : "";
  const state = data.finished
    ? "The run has stopped. "
    : "Still walking; the figures settle as it goes. ";
  return state + walked + of + " matchups walked exactly, in " + hours +
    " hours of machine time.";
}

load();
