const $ = (id) => document.getElementById(id);

async function loadText(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`No se pudo cargar ${path}`);
  return r.text();
}

function csvRows(csv) {
  const lines = csv.trim().split(/\r?\n/);
  if (!lines.length) return [];
  const h = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const c = line.split(",");
    const o = {};
    h.forEach((k, i) => (o[k] = (c[i] ?? "").trim()));
    return o;
  });
}

const toNum = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const fmt = (v, d = 1) => (v == null ? "n/a" : v.toFixed(d));
const HELP = {
  "run-summary": "Resumen del bloque running. Busca progresión de km, estabilidad del ritmo medio y crecimiento gradual de tirada larga.",
  "run-visuals": "Estas gráficas muestran tendencia de volumen, relación ritmo-FC y proyección estimada de maratón.",
  "run-volume-chart": "Mira continuidad semanal. Saltos muy bruscos suelen aumentar fatiga y riesgo.",
  "run-pace-hr-chart": "Si mejoras ritmo con FC similar o menor, suele ser señal de mejora aeróbica.",
  "run-marathon-band-chart": "Banda de escenarios (agresivo/base/conservador). Usa la banda base para planificar.",
  "run-weekly-table": "Detalle semanal para detectar semanas vacías, bajones o picos de carga.",
  "run-targets-table": "Rangos objetivo por semana hasta octubre. Mejor estar dentro del rango que forzar el máximo.",
  "combined-summary": "Integra running + fútbol para entender interacción de cargas.",
  "combined-visuals": "Visuales para ver estrés global, gap al objetivo y adherencia al plan.",
  "combined-stress-chart": "Si suben a la vez carga de fútbol y running, vigila recuperación y sueño.",
  "combined-gap-chart": "Mide cuánto falta para alcanzar volumen objetivo de octubre.",
  "combined-adherence-chart": "Compara plan vs real por semana. Importa más la tendencia que una semana aislada.",
  "combined-plan-table": "Tabla completa para ajustar próximas semanas con criterio.",
  "football-summary": "Resumen exclusivo de fútbol: sesiones, carga total, distancia y HIR.",
  "football-weekly-table": "Control semanal de carga futbolística para detectar picos exigentes.",
};

function cards(id, data) {
  $(id).innerHTML = data
    .map((x) => `<div class="kpi"><div class="label">${x.label}</div><div class="value">${x.value}</div>${x.note ? `<div class="note">${x.note}</div>` : ""}</div>`)
    .join("");
}

function table(id, rows, order = []) {
  if (!rows.length) return void ($(id).innerHTML = "<p>Sin datos.</p>");
  const headers = [...order.filter((k) => k in rows[0]), ...Object.keys(rows[0]).filter((k) => !order.includes(k))];
  const head = headers.map((k) => `<th>${k}</th>`).join("");
  const body = rows.map((r) => `<tr>${headers.map((k) => `<td>${r[k] ?? ""}</td>`).join("")}</tr>`).join("");
  $(id).innerHTML = `<div class="tableWrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function corr(a, b) {
  const p = a.map((v, i) => [toNum(v), toNum(b[i])]).filter(([x, y]) => x != null && y != null);
  if (p.length < 3) return null;
  const xs = p.map((q) => q[0]);
  const ys = p.map((q) => q[1]);
  const xm = xs.reduce((s, v) => s + v, 0) / xs.length;
  const ym = ys.reduce((s, v) => s + v, 0) / ys.length;
  const cov = xs.reduce((s, v, i) => s + (v - xm) * (ys[i] - ym), 0);
  const sx = Math.sqrt(xs.reduce((s, v) => s + (v - xm) ** 2, 0));
  const sy = Math.sqrt(ys.reduce((s, v) => s + (v - ym) ** 2, 0));
  return sx && sy ? cov / (sx * sy) : null;
}

function nav() {
  const activate = (feed) => {
    document.querySelectorAll(".feedBtn").forEach((b) => b.classList.toggle("active", b.dataset.feed === feed));
    document.querySelectorAll(".feed").forEach((s) => s.classList.toggle("visible", s.classList.contains(`feed-${feed}`)));
  };
  document.querySelectorAll(".feedBtn").forEach((b) => b.addEventListener("click", () => activate(b.dataset.feed)));
  activate("run");
}

function setupHelpModal() {
  const modal = $("helpModal");
  const title = $("helpTitle");
  const body = $("helpBody");
  const close = () => {
    modal.classList.remove("visible");
    modal.setAttribute("aria-hidden", "true");
  };
  $("helpClose").addEventListener("click", close);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });
  document.querySelectorAll(".infoBtn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.help;
      title.textContent = "How to read this";
      body.textContent = HELP[key] || "No explanation available for this block.";
      modal.classList.add("visible");
      modal.setAttribute("aria-hidden", "false");
    });
  });
}

async function main() {
  const [metaTxt, weeklyTxt, planTxt, targetTxt] = await Promise.all([
    loadText("data/meta.json"),
    loadText("data/weekly_metrics.csv"),
    loadText("data/plan_vs_actual.csv"),
    loadText("data/target_ranges_to_october.csv"),
  ]);
  const meta = JSON.parse(metaTxt);
  const weekly = csvRows(weeklyTxt);
  const plan = csvRows(planTxt);
  const targets = csvRows(targetTxt);

  $("meta").textContent = `Actualizado: ${meta.generated_at}`;
  nav();
  setupHelpModal();

  const run = weekly.map((x) => ({ s: toNum(x.run_sessions) || 0, km: toNum(x.run_dist_km), pace: toNum(x.run_avg_pace), long: toNum(x.longest_run_km) }));
  cards("runningAnalysis", [
    { label: "Sesiones running", value: `${run.reduce((s, x) => s + x.s, 0)}` },
    { label: "KM acumulados", value: `${fmt(run.reduce((s, x) => s + (x.km || 0), 0), 1)} km` },
    { label: "Tirada más larga", value: `${fmt(run.reduce((m, x) => Math.max(m, x.long || 0), 0), 1)} km` },
    {
      label: "Ritmo medio semanal",
      value: (() => {
        const p = run.map((x) => x.pace).filter((x) => x != null);
        return p.length ? `${fmt(p.reduce((s, x) => s + x, 0) / p.length, 2)} min/km` : "n/a";
      })(),
    },
  ]);

  const fb = weekly.map((x) => ({ s: toNum(x.fb_sessions) || 0, load: toNum(x.fb_load), dist: toNum(x.fb_dist_km), hir: toNum(x.fb_hir_km) }));
  const fbDist = fb.reduce((s, x) => s + (x.dist || 0), 0);
  const fbHir = fb.reduce((s, x) => s + (x.hir || 0), 0);
  cards("footballAnalysis", [
    { label: "Sesiones fútbol", value: `${fb.reduce((s, x) => s + x.s, 0)}` },
    { label: "Carga total", value: fmt(fb.reduce((s, x) => s + (x.load || 0), 0), 0) },
    { label: "Distancia total", value: `${fmt(fbDist, 1)} km` },
    { label: "HIR % sobre distancia", value: fbDist ? `${fmt((fbHir / fbDist) * 100, 1)}%` : "n/a" },
  ]);

  const ad = plan.map((x) => toNum(x.run_adherence_pct)).filter((x) => x != null);
  const adMean = ad.length ? ad.reduce((s, x) => s + x, 0) / ad.length : null;
  const c = corr(weekly.map((x) => x.fb_load), weekly.map((x) => x.run_dist_km));
  cards("combinedAnalysis", [
    { label: "Correlación fútbol vs running", value: c == null ? "n/a" : fmt(c, 2) },
    { label: "Adherencia media al plan", value: adMean == null ? "n/a" : `${fmt(adMean, 1)}%` },
    { label: "Interpretación", value: c == null ? "Datos insuficientes" : c > 0.6 ? "Suben/bajan juntos" : c < -0.2 ? "Compiten entre sí" : "Relación débil" },
  ]);

  table("weeklyTable", weekly, ["week", "run_dist_km", "run_avg_pace", "longest_run_km", "run_sessions"]);
  table("targetsTable", targets, ["week", "target_weekly_km_min", "target_weekly_km_max", "target_long_run_km_min", "target_long_run_km_max"]);
  table("planTable", plan, ["week", "fase", "plan_run_km", "run_dist_km", "run_adherence_pct", "run_km_gap"]);
  table(
    "footballTable",
    weekly.map((x) => ({ week: x.week, fb_sessions: x.fb_sessions, fb_load: x.fb_load, fb_dist_km: x.fb_dist_km, fb_hir_km: x.fb_hir_km })),
    ["week", "fb_sessions", "fb_load", "fb_dist_km", "fb_hir_km"]
  );
}

main().catch((e) => {
  $("meta").textContent = `Error cargando dashboard: ${e.message}`;
});
