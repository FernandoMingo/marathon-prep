async function fetchText(path) {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`No se pudo cargar ${path}`);
  return res.text();
}

function parseCsv(text) {
  const rows = [];
  let cur = "";
  let row = [];
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const next = text[i + 1];
    if (ch === '"') {
      if (inQuotes && next === '"') {
        cur += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      row.push(cur);
      cur = "";
    } else if ((ch === "\n" || ch === "\r") && !inQuotes) {
      if (ch === "\r" && next === "\n") i++;
      row.push(cur);
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
      cur = "";
    } else {
      cur += ch;
    }
  }
  if (cur.length || row.length) {
    row.push(cur);
    rows.push(row);
  }
  if (!rows.length) return [];
  const headers = rows[0];
  return rows.slice(1).map(r => {
    const obj = {};
    headers.forEach((h, i) => obj[h] = (r[i] ?? "").trim());
    return obj;
  });
}

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmt(n, d = 1) {
  return n == null ? "n/a" : n.toFixed(d);
}

function renderKpis(weekly) {
  const runRows = weekly.filter(r => num(r.run_dist_km) != null);
  const totalKm = runRows.reduce((a, r) => a + (num(r.run_dist_km) || 0), 0);
  const longest = runRows.reduce((m, r) => Math.max(m, num(r.longest_run_km) || 0), 0);
  const paceRows = runRows.filter(r => num(r.run_avg_pace) != null);
  const avgPace = paceRows.length ? paceRows.reduce((a, r) => a + num(r.run_avg_pace), 0) / paceRows.length : null;
  const fbRows = weekly.filter(r => num(r.fb_load) != null);
  const totalFbLoad = fbRows.reduce((a, r) => a + (num(r.fb_load) || 0), 0);

  const cards = [
    ["Running total km", `${fmt(totalKm, 1)} km`],
    ["Longest run", `${fmt(longest, 1)} km`],
    ["Average weekly pace", avgPace == null ? "n/a" : `${fmt(avgPace, 2)} min/km`],
    ["Football load acumulado", `${fmt(totalFbLoad, 0)}`],
    ["Semanas con datos", `${weekly.length}`],
  ];
  document.getElementById("kpis").innerHTML = cards.map(([label, value]) => `
    <div class="kpi">
      <div class="label">${label}</div>
      <div class="value">${value}</div>
    </div>
  `).join("");
}

function renderTable(containerId, rows, preferredOrder = []) {
  const container = document.getElementById(containerId);
  if (!rows.length) {
    container.innerHTML = "<p>Sin datos.</p>";
    return;
  }
  const allHeaders = Object.keys(rows[0]);
  const headers = [...preferredOrder.filter(h => allHeaders.includes(h)), ...allHeaders.filter(h => !preferredOrder.includes(h))];
  const head = headers.map(h => `<th>${h}</th>`).join("");
  const body = rows.map(r => `<tr>${headers.map(h => `<td>${r[h] ?? ""}</td>`).join("")}</tr>`).join("");
  container.innerHTML = `<div class="tableWrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

async function main() {
  const metaEl = document.getElementById("meta");
  try {
    const [metaText, weeklyText, planText, targetsText] = await Promise.all([
      fetchText("data/meta.json"),
      fetchText("data/weekly_metrics.csv"),
      fetchText("data/plan_vs_actual.csv"),
      fetchText("data/target_ranges_to_october.csv"),
    ]);

    const meta = JSON.parse(metaText);
    const weekly = parseCsv(weeklyText);
    const plan = parseCsv(planText);
    const targets = parseCsv(targetsText);

    metaEl.textContent = `Actualizado: ${meta.generated_at} · fuente: ${meta.source_outdir}`;
    renderKpis(weekly);
    renderTable("planTable", plan, ["week", "fase", "plan_run_km", "run_dist_km", "run_adherence_pct", "run_km_gap"]);
    renderTable("weeklyTable", weekly, ["week", "run_dist_km", "run_avg_pace", "longest_run_km", "fb_load"]);
    renderTable("targetsTable", targets, ["week", "target_weekly_km_min", "target_weekly_km_max", "target_long_run_km_min", "target_long_run_km_max"]);
  } catch (err) {
    metaEl.textContent = `Error cargando dashboard: ${err.message}`;
  }
}

main();
