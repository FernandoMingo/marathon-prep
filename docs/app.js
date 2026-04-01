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

function renderAnalysisCards(containerId, cards) {
  document.getElementById(containerId).innerHTML = cards.map(c => `
    <div class="kpi">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      ${c.note ? `<div class="note">${c.note}</div>` : ""}
    </div>
  `).join("");
}

function corr(valuesA, valuesB) {
  const pairs = [];
  for (let i = 0; i < valuesA.length; i++) {
    const a = num(valuesA[i]);
    const b = num(valuesB[i]);
    if (a != null && b != null) pairs.push([a, b]);
  }
  if (pairs.length < 3) return null;
  const ax = pairs.map(p => p[0]);
  const by = pairs.map(p => p[1]);
  const am = ax.reduce((s, v) => s + v, 0) / ax.length;
  const bm = by.reduce((s, v) => s + v, 0) / by.length;
  const cov = ax.reduce((s, v, i) => s + (v - am) * (by[i] - bm), 0);
  const va = Math.sqrt(ax.reduce((s, v) => s + (v - am) ** 2, 0));
  const vb = Math.sqrt(by.reduce((s, v) => s + (v - bm) ** 2, 0));
  if (va === 0 || vb === 0) return null;
  return cov / (va * vb);
}

function renderSplitAnalysis(weekly, plan) {
  const w = weekly.map(r => ({
    fb_sessions: num(r.fb_sessions) || 0,
    fb_load: num(r.fb_load),
    fb_hir_km: num(r.fb_hir_km),
    run_sessions: num(r.run_sessions) || 0,
    run_dist_km: num(r.run_dist_km),
    run_avg_pace: num(r.run_avg_pace),
    longest_run_km: num(r.longest_run_km),
  }));

  const fbSessions = w.reduce((a, r) => a + r.fb_sessions, 0);
  const fbLoadTotal = w.reduce((a, r) => a + (r.fb_load || 0), 0);
  const fbLoadPerSession = fbSessions > 0 ? fbLoadTotal / fbSessions : null;
  const fbHir = w.reduce((a, r) => a + (r.fb_hir_km || 0), 0);
  renderAnalysisCards("footballAnalysis", [
    { label: "Sesiones fútbol", value: `${fbSessions}` },
    { label: "Carga total fútbol", value: fmt(fbLoadTotal, 0) },
    { label: "Carga media por sesión", value: fmt(fbLoadPerSession, 1) },
    { label: "HIR total", value: `${fmt(fbHir, 1)} km` },
  ]);

  const runSessions = w.reduce((a, r) => a + r.run_sessions, 0);
  const runKm = w.reduce((a, r) => a + (r.run_dist_km || 0), 0);
  const longest = w.reduce((m, r) => Math.max(m, r.longest_run_km || 0), 0);
  const paceVals = w.map(r => r.run_avg_pace).filter(v => v != null);
  const avgPace = paceVals.length ? paceVals.reduce((a, b) => a + b, 0) / paceVals.length : null;
  renderAnalysisCards("runningAnalysis", [
    { label: "Sesiones running", value: `${runSessions}` },
    { label: "KM acumulados running", value: `${fmt(runKm, 1)} km` },
    { label: "Tirada más larga", value: `${fmt(longest, 1)} km` },
    { label: "Ritmo medio semanal", value: avgPace == null ? "n/a" : `${fmt(avgPace, 2)} min/km` },
  ]);

  const c = corr(w.map(r => r.fb_load), w.map(r => r.run_dist_km));
  const last4 = w.slice(-4).reduce((a, r) => a + (r.run_dist_km || 0), 0);
  const prev4 = w.slice(-8, -4).reduce((a, r) => a + (r.run_dist_km || 0), 0);
  const trend = prev4 > 0 ? last4 / prev4 : null;
  const planRows = plan.filter(r => num(r.plan_run_km) != null);
  const adherenceVals = planRows.map(r => num(r.run_adherence_pct)).filter(v => v != null);
  const adherence = adherenceVals.length ? adherenceVals.reduce((a, b) => a + b, 0) / adherenceVals.length : null;
  renderAnalysisCards("combinedAnalysis", [
    { label: "Correlación carga fútbol vs km running", value: c == null ? "n/a" : fmt(c, 2) },
    { label: "Ratio últimos 4 vs previos 4 semanas (km)", value: trend == null ? "n/a" : fmt(trend, 2), note: "1.00 = estable, >1 subiendo, <1 bajando" },
    { label: "Adherencia media al plan", value: adherence == null ? "n/a" : `${fmt(adherence, 1)}%` },
    { label: "Interpretación", value: c == null ? "Datos insuficientes" : (c > 0.6 ? "Suben/bajan juntos" : (c < -0.2 ? "Compiten entre sí" : "Relación débil")) },
  ]);
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
    renderSplitAnalysis(weekly, plan);
    renderTable("planTable", plan, ["week", "fase", "plan_run_km", "run_dist_km", "run_adherence_pct", "run_km_gap"]);
    renderTable("weeklyTable", weekly, ["week", "run_dist_km", "run_avg_pace", "longest_run_km", "fb_load"]);
    renderTable("targetsTable", targets, ["week", "target_weekly_km_min", "target_weekly_km_max", "target_long_run_km_min", "target_long_run_km_max"]);
  } catch (err) {
    metaEl.textContent = `Error cargando dashboard: ${err.message}`;
  }
}

main();
