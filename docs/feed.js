const $ = (id) => document.getElementById(id);

async function loadText(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`No se pudo cargar ${path}`);
  return r.text();
}

async function loadOptionalText(path, fallback = "") {
  try {
    return await loadText(path);
  } catch {
    return fallback;
  }
}

function csvRows(csv) {
  const raw = (csv || "").trim();
  if (!raw) return [];
  const lines = raw.split(/\r?\n/);
  const h = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const c = line.split(",");
    const o = {};
    h.forEach((k, i) => {
      o[k] = (c[i] ?? "").trim();
    });
    return o;
  });
}

const toNum = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const toBool = (v) => String(v).toLowerCase() === "true";
const fmt = (v, d = 1) => (v == null ? "n/a" : v.toFixed(d));
const pct = (v) => (v == null ? "n/a" : `${(v * 100).toFixed(0)}%`);
const avg = (arr) => (arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : null);
const hmsFromMinutes = (minutes) => {
  if (minutes == null) return "n/a";
  const h = Math.floor(minutes / 60);
  const m = Math.floor(minutes % 60);
  const s = Math.floor((minutes - Math.floor(minutes)) * 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
};

const HELP = {
  "run-summary": "Estado actual de la semana: cumplimiento del plan, estado de tirada larga y señal de riesgo inmediato.",
  "run-build": "Bloque de construcción del maratón: volumen, calidad, adherencia y progresión de tirada larga.",
  "run-visuals": "Tendencias de running (volumen, ritmo/FC y banda de maratón).",
  "run-volume-chart": "Compara km reales vs evolución semanal para detectar picos o semanas bajas.",
  "run-pace-hr-chart": "Si mantienes o bajas FC para ritmo similar, suele ser señal de mejora aeróbica.",
  "run-marathon-band-chart": "Banda de estimación del maratón (agresivo-base-conservador), no un número único.",
  "run-weekly-table": "Detalle semanal completo para revisar cumplimiento y estados actual/estimado/desconocido.",
  "run-targets-table": "Rangos orientativos hacia octubre para volumen y tirada larga.",
  "combined-summary": "Carga running + fútbol separada y combinada de forma normalizada para leer fatiga.",
  "predictions-summary": "Probabilidades de completar la siguiente semana y estado de readiness actual.",
  "predictions-confidence": "Las predicciones incluyen degradación explícita de confianza cuando faltan datos de fútbol.",
  "combined-visuals": "Visuales de estrés combinado, gap de objetivo y adherencia plan-real.",
  "combined-stress-chart": "Si suben juntos running y fútbol, vigila sueño, recuperación y downscale preventivo.",
  "combined-gap-chart": "Distancia entre tu nivel actual y el rango objetivo hacia octubre.",
  "combined-adherence-chart": "Adherencia al plan por semana para ajustar carga sin improvisar.",
  "combined-plan-table": "Tabla de plan vs real para validar si estás en línea o necesitas ajustar.",
  "football-summary": "Resumen exclusivo de fútbol con cobertura y recencia de dato.",
  "football-impact": "Impacto del fútbol sobre la carrera: muestra fallback si no hay suficiente dato real.",
  "football-weekly-table": "Semana a semana de fútbol con estado actual/estimado/not expected.",
};

function cards(id, data) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = data
    .map((x) => `<div class="kpi"><div class="label">${x.label}</div><div class="value">${x.value}</div>${x.note ? `<div class="note">${x.note}</div>` : ""}</div>`)
    .join("");
}

function quickGlance(feed, dataByFeed) {
  const data = dataByFeed[feed] || [];
  cards("quickGlance", data);
}

function table(id, rows, order = []) {
  const el = $(id);
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = "<p>Sin datos.</p>";
    return;
  }
  const headers = [...order.filter((k) => k in rows[0]), ...Object.keys(rows[0]).filter((k) => !order.includes(k))];
  const head = headers.map((k) => `<th>${k}</th>`).join("");
  const body = rows.map((r) => `<tr>${headers.map((k) => `<td>${r[k] ?? ""}</td>`).join("")}</tr>`).join("");
  el.innerHTML = `<div class="tableWrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function nav(onChange) {
  const activate = (feed) => {
    document.querySelectorAll(".feedBtn").forEach((b) => b.classList.toggle("active", b.dataset.feed === feed));
    document.querySelectorAll(".feed").forEach((s) => s.classList.toggle("visible", s.classList.contains(`feed-${feed}`)));
    if (typeof onChange === "function") onChange(feed);
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

function setupChartModal() {
  const modal = $("chartModal");
  const title = $("chartTitle");
  const img = $("chartModalImage");
  const close = () => {
    modal.classList.remove("visible");
    modal.setAttribute("aria-hidden", "true");
    img.src = "";
  };
  $("chartClose").addEventListener("click", close);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });
  document.querySelectorAll(".chartImage").forEach((el) => {
    el.addEventListener("click", () => {
      title.textContent = el.dataset.chartTitle || "Chart";
      img.src = el.getAttribute("src");
      img.alt = el.getAttribute("alt") || "Expanded chart";
      modal.classList.add("visible");
      modal.setAttribute("aria-hidden", "false");
    });
  });
}

function footballStatusLabel(s) {
  const v = String(s || "").toLowerCase();
  if (v === "actual") return "actual";
  if (v === "estimated") return "estimated";
  if (v === "not_expected") return "not expected";
  return "unknown";
}

async function main() {
  const [metaTxt, weeklyTxt, planTxt, targetTxt, predTxt] = await Promise.all([
    loadText("data/meta.json"),
    loadText("data/weekly_metrics.csv"),
    loadOptionalText("data/plan_vs_actual.csv"),
    loadOptionalText("data/target_ranges_to_october.csv"),
    loadOptionalText("data/predictions.json", "{}"),
  ]);
  const meta = JSON.parse(metaTxt);
  const weekly = csvRows(weeklyTxt);
  const plan = csvRows(planTxt);
  const targets = csvRows(targetTxt);
  const predictions = JSON.parse(predTxt || "{}");
  const glance = { run: [], combined: [], football: [] };

  $("meta").textContent = `Actualizado: ${meta.generated_at}`;
  setupHelpModal();
  setupChartModal();

  const runRows = weekly.map((x) => ({
    sessions: toNum(x.run_sessions) || 0,
    km: toNum(x.run_dist_km) || 0,
    pace: toNum(x.run_avg_pace),
    long: toNum(x.longest_run_km) || 0,
    adherence: toNum(x.run_adherence_pct),
    compliance: toNum(x.plan_compliance_score),
    rolling4: toNum(x.rolling_4w_km),
    rolling8: toNum(x.rolling_8w_km),
    qualityDone: toNum(x.actual_quality_sessions) || 0,
    qualityPlan: toNum(x.planned_quality_sessions) || 0,
  }));
  const last = weekly.length ? weekly[weekly.length - 1] : {};
  const thisWeek = {
    week: last.semana_plan || "n/a",
    phase: last.fase || "n/a",
    plannedSessions: toNum(last.planned_run_sessions) || 0,
    doneSessions: toNum(last.run_sessions) || 0,
    runKm: toNum(last.run_dist_km),
    runTarget: toNum(last.plan_run_km),
    longDone: toBool(last.long_run_completed),
    footballStatus: footballStatusLabel(last.football_status),
    qualityProb: toNum(predictions?.probabilities?.next_quality_completion_probability),
  };
  cards("thisWeekAnalysis", [
    { label: "Plan week", value: `${thisWeek.week}` },
    { label: "Running km vs target", value: `${fmt(thisWeek.runKm, 1)} / ${fmt(thisWeek.runTarget, 1)} km` },
    { label: "Long run status", value: thisWeek.longDone ? "completed" : "pending" },
    { label: "Next key-session readiness", value: pct(thisWeek.qualityProb) },
  ]);
  glance.run = [
    { label: "Plan week", value: `${thisWeek.week}` },
    { label: "Running km vs target", value: `${fmt(thisWeek.runKm, 1)} / ${fmt(thisWeek.runTarget, 1)} km` },
    { label: "Long run", value: thisWeek.longDone ? "completed" : "pending" },
    { label: "Readiness", value: pct(thisWeek.qualityProb) },
  ];

  cards("runningAnalysis", [
    { label: "Current phase", value: `${thisWeek.phase}` },
    { label: "Planned / completed sessions", value: `${thisWeek.plannedSessions} / ${thisWeek.doneSessions}` },
    { label: "Football status", value: thisWeek.footballStatus },
    { label: "Running sessions", value: `${runRows.reduce((s, x) => s + x.sessions, 0)}` },
    { label: "Total running km", value: `${fmt(runRows.reduce((s, x) => s + x.km, 0), 1)} km` },
    { label: "Longest run", value: `${fmt(Math.max(0, ...runRows.map((x) => x.long)), 1)} km` },
    { label: "4w / 8w volume", value: `${fmt(toNum(last.rolling_4w_km), 1)} / ${fmt(toNum(last.rolling_8w_km), 1)} km` },
    { label: "Compliance trend (last 4w)", value: `${fmt(avg(runRows.map((x) => x.compliance).filter((x) => x != null).slice(-4)), 1)}` },
    {
      label: "Quality completion",
      value: `${fmt(toNum(last.actual_quality_sessions), 0)} / ${fmt(toNum(last.planned_quality_sessions), 0)}`,
      note: "actual / planned",
    },
  ]);
  const runNarrative = $("runNarrative");
  if (runNarrative) {
    const comp = toNum(last.plan_compliance_score);
    const longDone = toBool(last.long_run_completed);
    const fatigue = String(last.fatigue_status || "n/a");
    const footballStatus = footballStatusLabel(last.football_status);
    const messages = [];
    if (comp != null) {
      if (comp >= 90) messages.push("You are largely on plan this week.");
      else if (comp >= 75) messages.push("You are close to plan but slightly below targets.");
      else messages.push("This week is under target vs plan. Consider a controlled catch-up.");
    }
    messages.push(longDone ? "Long run target appears completed." : "Long run target is still pending.");
    messages.push(`Fatigue signal is currently ${fatigue}.`);
    messages.push(`Football input is marked as ${footballStatus} for this week.`);
    runNarrative.innerHTML = `<ul>${messages.map((m) => `<li>${m}</li>`).join("")}</ul>`;
  }

  const fbRows = weekly.map((x) => ({
    sessions: toNum(x.fb_sessions) || 0,
    load: toNum(x.fb_load) || 0,
    dist: toNum(x.fb_dist_km) || 0,
    hir: toNum(x.fb_hir_km) || 0,
    sprint: toNum(x.fb_sprint_km) || 0,
    acc: toNum(x.fb_accelerations) || 0,
    dec: toNum(x.fb_decelerations) || 0,
    status: footballStatusLabel(x.football_status),
    actual: toBool(x.football_actual_available),
  }));
  const fbCoverage = toNum(meta.football_coverage_pct);
  const fbDaysSince = toNum(meta.football_days_since_last);
  const actualWeeks = fbRows.filter((x) => x.actual);
  cards("footballAnalysis", [
    { label: "Current status", value: footballStatusLabel(last.football_status) },
    { label: "Coverage", value: fbCoverage == null ? "n/a" : `${fmt(fbCoverage, 1)}%` },
    { label: "Days since last actual", value: fbDaysSince == null ? "n/a" : `${fbDaysSince}` },
    { label: "Football total load", value: fmt(fbRows.reduce((s, x) => s + x.load, 0), 0) },
    { label: "Total football distance", value: `${fmt(fbRows.reduce((s, x) => s + x.dist, 0), 1)} km` },
  ]);
  glance.football = [
    { label: "Coverage", value: fbCoverage == null ? "n/a" : `${fmt(fbCoverage, 1)}%` },
    { label: "Status", value: footballStatusLabel(last.football_status) },
    { label: "Last actual data", value: fbDaysSince == null ? "n/a" : `${fbDaysSince} days` },
    { label: "Total football load", value: fmt(fbRows.reduce((s, x) => s + x.load, 0), 0) },
  ];

  cards("combinedAnalysis", [
    { label: "Combined normalized load", value: fmt(toNum(last.combined_normalized_load), 0) },
    { label: "Hybrid fatigue score", value: fmt(toNum(last.hybrid_fatigue_score), 1) },
    { label: "Fatigue flag", value: last.fatigue_status || "n/a" },
    { label: "Prediction confidence", value: `${fmt(toNum(meta.prediction_confidence_score), 1)}/100` },
  ]);
  glance.combined = [
    { label: "Combined load", value: fmt(toNum(last.combined_normalized_load), 0) },
    { label: "Hybrid fatigue", value: fmt(toNum(last.hybrid_fatigue_score), 1) },
    { label: "Fatigue flag", value: last.fatigue_status || "n/a" },
    { label: "Prediction confidence", value: `${fmt(toNum(meta.prediction_confidence_score), 1)}/100` },
  ];
  const combinedNarrative = $("combinedNarrative");
  if (combinedNarrative) {
    const downscaleProb = toNum(predictions?.probabilities?.next_week_downscale_probability);
    const confScore = toNum(meta.prediction_confidence_score);
    const readiness = predictions?.readiness?.marathon_readiness || "n/a";
    const lines = [
      `Current marathon readiness is ${readiness}.`,
      `Combined load this week is ${fmt(toNum(last.combined_normalized_load), 0)}.`,
      `Prediction confidence is ${fmt(confScore, 1)}/100.`,
    ];
    if (downscaleProb != null) {
      if (downscaleProb >= 0.55) lines.push("Downscale probability is elevated: keep flexibility in next week plan.");
      else lines.push("Downscale probability is moderate/low based on recent consistency.");
    }
    if (footballStatusLabel(last.football_status) === "estimated") {
      lines.push("Football load is estimated this week, so hybrid conclusions have lower certainty.");
    }
    combinedNarrative.innerHTML = `<ul>${lines.map((m) => `<li>${m}</li>`).join("")}</ul>`;
  }

  const p = predictions?.probabilities || {};
  const ready = predictions?.readiness || {};
  const mar = predictions?.marathon_prediction || {};
  const pace = predictions?.pace_recommendations || {};
  cards("predictionsAnalysis", [
    { label: "Readiness", value: ready.marathon_readiness || "n/a" },
    { label: "Next-week volume completion", value: pct(toNum(p.next_week_volume_completion_probability)) },
    { label: "Next long run completion", value: pct(toNum(p.next_long_run_completion_probability)) },
    { label: "Next quality completion", value: pct(toNum(p.next_quality_completion_probability)) },
  ]);

  cards("predictionsDetails", [
    { label: "Downscale probability", value: pct(toNum(p.next_week_downscale_probability)) },
    { label: "Aerobic status", value: ready.aerobic_fitness_status || "n/a" },
    { label: "Durability status", value: ready.durability_status || "n/a" },
    {
      label: "Marathon range",
      value: `${hmsFromMinutes(toNum(mar.aggressive))} - ${hmsFromMinutes(toNum(mar.conservative))}`,
      note: `fitness ${hmsFromMinutes(toNum(mar.fitness_based))} | durability-adjusted ${hmsFromMinutes(toNum(mar.durability_adjusted))}`,
    },
    {
      label: "Pace recommendations",
      value: pace.marathon || "n/a",
      note: `easy ${pace.easy || "n/a"} | steady ${pace.steady || "n/a"} | threshold ${pace.threshold || "n/a"}`,
    },
  ]);

  const notes = Array.isArray(predictions?.confidence_notes) ? predictions.confidence_notes : ["Confidence explanation unavailable."];
  const conf = $("confidenceNotes");
  if (conf) {
    conf.innerHTML = `<ul>${notes.map((n) => `<li>${n}</li>`).join("")}</ul>`;
  }

  const impactEl = $("footballImpactMessage");
  if (impactEl) {
    if (actualWeeks.length >= 4) {
      const recent = actualWeeks.slice(-4);
      const hirTrend = avg(recent.map((x) => x.hir));
      const sprintTrend = avg(recent.map((x) => x.sprint));
      impactEl.innerHTML = `
        <p>Enough actual football data is available to inspect impact trends.</p>
        <ul>
          <li>Recent HIR (4w avg): ${fmt(hirTrend, 2)} km</li>
          <li>Recent sprint distance (4w avg): ${fmt(sprintTrend, 2)} km</li>
          <li>Recent accelerations/decelerations: ${fmt(avg(recent.map((x) => x.acc)), 0)} / ${fmt(avg(recent.map((x) => x.dec)), 0)}</li>
        </ul>
      `;
    } else {
      impactEl.innerHTML = `
        <p>Football impact panel is in fallback mode: not enough recent actual football data.</p>
        <p>Estimates are shown where expected weeks exist, and unknown values remain clearly marked.</p>
      `;
    }
  }

  table("weeklyTable", weekly, [
    "week",
    "semana_plan",
    "fase",
    "run_dist_km",
    "plan_run_km",
    "run_sessions",
    "planned_run_sessions",
    "plan_compliance_score",
    "football_status",
    "fatigue_status",
  ]);
  table("targetsTable", targets, ["week", "target_weekly_km_min", "target_weekly_km_max", "target_long_run_km_min", "target_long_run_km_max"]);
  table("planTable", plan, ["week", "fase", "plan_run_km", "run_dist_km", "run_adherence_pct", "run_km_gap", "football_status", "plan_compliance_score"]);
  table(
    "footballTable",
    weekly.map((x) => ({
      week: x.week,
      football_status: footballStatusLabel(x.football_status),
      fb_sessions: x.fb_sessions,
      fb_load: x.fb_load,
      fb_dist_km: x.fb_dist_km,
      fb_hir_km: x.fb_hir_km,
      fb_sprint_km: x.fb_sprint_km,
      fb_accelerations: x.fb_accelerations,
      fb_decelerations: x.fb_decelerations,
      fb_match_sessions: x.fb_match_sessions,
      fb_training_sessions: x.fb_training_sessions,
    })),
    ["week", "football_status", "fb_sessions", "fb_load", "fb_dist_km", "fb_hir_km", "fb_sprint_km", "fb_accelerations", "fb_decelerations", "fb_training_sessions", "fb_match_sessions"]
  );

  nav((feed) => quickGlance(feed, glance));
}

main().catch((e) => {
  $("meta").textContent = `Error cargando dashboard: ${e.message}`;
});
