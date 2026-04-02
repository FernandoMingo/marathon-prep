import argparse
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "analysis.log"
MIN_FOOTBALL_COVERAGE_FOR_COMBINED = 0.35

DAY_COLS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DAY_OFFSETS = {"lunes": 0, "martes": 1, "miércoles": 2, "jueves": 3, "viernes": 4, "sábado": 5, "domingo": 6}
QUALITY_PATTERN = r"series|tempo|umbral|ritmo 10k|rm|progresivo"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan-aware hybrid marathon analysis")
    parser.add_argument("--football", default="export.csv", help="Football CSV export path")
    parser.add_argument("--strava", default="export_149118275/activities.csv", help="Strava activities CSV path")
    parser.add_argument("--plan", default="plan_maraton_hibrido_corregido.csv", help="Training plan CSV path")
    parser.add_argument("--plan-pdf", default="plan_maraton_hibrido_visual.pdf", help="Plan PDF path for website")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--outdir", default="analysis_output", help="Output folder")
    parser.add_argument("--site-dir", default="docs", help="GitHub Pages output directory")
    return parser.parse_args()


def safe_ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    if pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return float(a / b)


def clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def format_hms(minutes: float | None) -> str:
    if minutes is None or pd.isna(minutes):
        return "n/a"
    h = int(minutes // 60)
    m = int(minutes % 60)
    s = int((minutes - int(minutes)) * 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def parse_km_range(text: str | None) -> tuple[float | None, float | None]:
    if text is None:
        return None, None
    raw = str(text).lower().replace(",", ".")
    m_range = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)(?:\s*km)?", raw)
    if m_range:
        return float(m_range.group(1)), float(m_range.group(2))
    m_single = re.search(r"(\d+(?:\.\d+)?)(?:\s*km)?$", raw)
    if m_single:
        v = float(m_single.group(1))
        return v, v
    return None, None


def extract_planned_km(raw_text: str | None) -> tuple[float | None, float | None]:
    if raw_text is None:
        return None, None
    text = str(raw_text).lower().replace(",", ".")
    total_match = re.search(r"total\s*(\d+(?:\.\d+)?)\s*km", text)
    if total_match:
        v = float(total_match.group(1))
        return v, v
    m_range = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*km", text)
    if m_range:
        return float(m_range.group(1)), float(m_range.group(2))
    m_single = re.search(r"(\d+(?:\.\d+)?)\s*km", text)
    if m_single:
        v = float(m_single.group(1))
        return v, v
    return None, None


def classify_plan_session(raw_text: str | None) -> str:
    if raw_text is None:
        return "unknown"
    t = str(raw_text).lower()
    if "maratón" in t or "maraton" in t:
        return "race"
    if "fútbol" in t or "futbol" in t or "partido" in t:
        return "football"
    if "descanso" in t and "km" not in t:
        return "rest"
    if re.search(QUALITY_PATTERN, t):
        return "quality_run"
    if "tirada larga" in t:
        return "long_run"
    if "km" in t:
        return "run"
    return "other"


def prep_football(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if not path.exists():
        logging.warning("Football file missing. Running in running-only mode.")
        return pd.DataFrame()

    df = pd.read_csv(path)
    if df.empty:
        return df
    df["Start Date"] = pd.to_datetime(df.get("Start Date"), dayfirst=True, errors="coerce")
    df = df[df["Start Date"].notna()].copy()
    df = df[(df["Start Date"] >= start) & (df["Start Date"] <= end)].copy()
    if df.empty:
        return df

    df["Segment Name"] = df.get("Segment Name", "").astype(str)
    segment_priority = {"Whole Session": 0, "Total of Segments": 1}
    df["segment_priority"] = df["Segment Name"].map(segment_priority).fillna(9)
    df = df.sort_values(["Start Date", "Session Type", "segment_priority"]).drop_duplicates(
        subset=["Start Date", "Session Type"], keep="first"
    )

    numeric_cols = [
        "Duration (mins)",
        "Session Load",
        "Distance (m)",
        "High Intensity Running (m)",
        "Sprint Distance (m)",
        "Top Speed (kph)",
        "Avg Speed (kph)",
        "Accelerations",
        "Decelerations",
        "No. of Sprints",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["football_subtype"] = np.where(df["Session Type"].astype(str).str.contains("match", case=False), "match", "training")
    df["football_load_est"] = np.where(
        df.get("Session Load").notna() & (df.get("Session Load") > 0),
        df.get("Session Load"),
        np.where(df.get("Duration (mins)").notna(), df.get("Duration (mins)") * 9.0, df.get("Distance (m)").fillna(0) / 8.0),
    )
    df["week"] = df["Start Date"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    df["source"] = "football_actual"
    return df.reset_index(drop=True)


def prep_runs(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Strava CSV not found: {path}")

    runs = pd.read_csv(path)
    runs["Activity Date"] = pd.to_datetime(runs.get("Activity Date"), errors="coerce")
    runs = runs[runs["Activity Date"].notna()].copy()
    runs = runs[runs.get("Activity Type", "").astype(str).str.strip().eq("Run")].copy()
    dist_col = "Distance.1" if "Distance.1" in runs.columns else "Distance"
    runs["Distance"] = pd.to_numeric(runs.get(dist_col), errors="coerce")
    runs["Moving Time"] = pd.to_numeric(runs.get("Moving Time"), errors="coerce")
    runs["Average Heart Rate"] = pd.to_numeric(runs.get("Average Heart Rate"), errors="coerce")
    runs["Relative Effort"] = pd.to_numeric(runs.get("Relative Effort"), errors="coerce")
    runs = runs[(runs["Activity Date"] >= start) & (runs["Activity Date"] <= end)].copy()
    runs = runs[runs["Distance"] > 200].copy()
    if runs.empty:
        return runs

    runs["dist_km"] = runs["Distance"] / 1000.0
    runs["pace_min_km"] = (runs["Moving Time"] / 60.0) / runs["dist_km"]
    runs["week"] = runs["Activity Date"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    name = runs.get("Activity Name", "").astype(str).str.lower()
    runs["is_quality"] = (
        name.str.contains(QUALITY_PATTERN, regex=True)
        | name.str.contains("interval|fartlek|tempo", regex=True)
        | (runs["Relative Effort"].fillna(0) >= 70)
    )
    runs["is_long"] = runs["dist_km"] >= 14.0
    runs["sport"] = "run"
    runs["source"] = "strava"
    return runs.sort_values("Activity Date").reset_index(drop=True)


def football_data_quality(football: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float | int | bool | None]:
    week_range = pd.date_range(start.normalize(), end.normalize(), freq="W-SUN")
    total_weeks = int(len(week_range))
    if football.empty:
        return {
            "weeks_total": total_weeks,
            "weeks_with_football_data": 0,
            "coverage_ratio": 0.0,
            "coverage_pct": 0.0,
            "last_football_date": None,
            "days_since_last_football": None,
            "is_sufficient_for_combined": False,
            "coverage_threshold_pct": MIN_FOOTBALL_COVERAGE_FOR_COMBINED * 100.0,
        }

    weeks_with_data = int(football["week"].dropna().nunique())
    coverage_ratio = (weeks_with_data / total_weeks) if total_weeks > 0 else 0.0
    last_date = football["Start Date"].max()
    days_since = int((end.normalize() - pd.Timestamp(last_date).normalize()).days) if pd.notna(last_date) else None
    return {
        "weeks_total": total_weeks,
        "weeks_with_football_data": weeks_with_data,
        "coverage_ratio": float(coverage_ratio),
        "coverage_pct": float(coverage_ratio * 100.0),
        "last_football_date": None if pd.isna(last_date) else pd.Timestamp(last_date).date().isoformat(),
        "days_since_last_football": days_since,
        "is_sufficient_for_combined": bool(coverage_ratio >= MIN_FOOTBALL_COVERAGE_FOR_COMBINED),
        "coverage_threshold_pct": MIN_FOOTBALL_COVERAGE_FOR_COMBINED * 100.0,
    }


def clean_training_plan(plan_path: Path, outdir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not plan_path.exists():
        logging.warning("Plan file missing: %s", plan_path)
        return pd.DataFrame(), pd.DataFrame()

    plan = pd.read_csv(plan_path)
    plan["inicio_semana"] = pd.to_datetime(plan.get("inicio_semana"), errors="coerce")
    rows: list[dict] = []
    for _, r in plan.iterrows():
        week_start = r.get("inicio_semana")
        if pd.isna(week_start):
            continue
        vol_min, vol_max = parse_km_range(r.get("volumen_objetivo_aprox_km"))
        no_football_phase = "sin fútbol" in str(r.get("fase", "")).lower() or "sin futbol" in str(r.get("fase", "")).lower()
        for day_col in DAY_COLS:
            raw = str(r.get(day_col, "")).strip()
            if raw == "" or raw.lower() == "nan":
                continue
            km_min, km_max = extract_planned_km(raw)
            km = (km_min + km_max) / 2.0 if km_min is not None and km_max is not None else km_min
            subtype = classify_plan_session(raw)
            rows.append(
                {
                    "semana": r.get("semana"),
                    "fecha": (week_start + pd.Timedelta(days=DAY_OFFSETS[day_col])).normalize(),
                    "dia": day_col,
                    "fase": r.get("fase"),
                    "sesion_plan": raw,
                    "subtype": subtype,
                    "planned": True,
                    "km_objetivo_min": km_min,
                    "km_objetivo_max": km_max,
                    "km_objetivo": km,
                    "is_quality_target": bool(re.search(QUALITY_PATTERN, raw.lower())),
                    "is_long_target": ("tirada larga" in raw.lower()),
                    "expected_football_session": (subtype == "football") and not no_football_phase,
                    "summer_running_only": no_football_phase,
                    "volumen_semana_objetivo_min": vol_min,
                    "volumen_semana_objetivo_max": vol_max,
                    "tirada_larga_plan_km": pd.to_numeric(r.get("tirada_larga_km"), errors="coerce"),
                }
            )

    clean = pd.DataFrame(rows).sort_values("fecha").reset_index(drop=True)
    if clean.empty:
        return clean, pd.DataFrame()
    clean["week"] = clean["fecha"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    run_like = clean["subtype"].isin(["run", "quality_run", "long_run", "race"])
    weekly = (
        clean.groupby("week", as_index=False)
        .agg(
            semana_plan=("semana", "first"),
            fase=("fase", "last"),
            plan_run_km=("km_objetivo", lambda s: s[run_like.loc[s.index]].sum(skipna=True)),
            planned_run_sessions=("subtype", lambda s: int(s.isin(["run", "quality_run", "long_run", "race"]).sum())),
            planned_quality_sessions=("is_quality_target", "sum"),
            planned_long_run_km=("tirada_larga_plan_km", "max"),
            plan_football_days=("expected_football_session", "sum"),
            phase_summer_running_only=("summer_running_only", "max"),
            vol_objetivo_min=("volumen_semana_objetivo_min", "max"),
            vol_objetivo_max=("volumen_semana_objetivo_max", "max"),
        )
    )
    weekly["plan_vol_objetivo_km"] = (weekly["vol_objetivo_min"] + weekly["vol_objetivo_max"]) / 2.0
    weekly["planned_long_run_km"] = weekly["planned_long_run_km"].fillna(0.0)
    weekly["planned_quality_sessions"] = weekly["planned_quality_sessions"].fillna(0).astype(int)
    weekly["expected_football_week"] = (weekly["plan_football_days"].fillna(0) > 0) & (~weekly["phase_summer_running_only"].astype(bool))

    outdir.mkdir(parents=True, exist_ok=True)
    clean.to_csv(outdir / "plan_limpio_sesiones.csv", index=False)
    weekly.to_csv(outdir / "plan_limpio_semanal.csv", index=False)
    return clean, weekly


def summarize_weekly(runs: pd.DataFrame, football: pd.DataFrame, weekly_plan: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    cal_weeks = pd.DataFrame({"week": pd.date_range(start.normalize(), end.normalize(), freq="W-SUN")})
    run_w = pd.DataFrame()
    if not runs.empty:
        run_w = (
            runs.groupby("week", as_index=False)
            .agg(
                run_sessions=("Activity Date", "count"),
                run_dist_km=("dist_km", "sum"),
                run_time_h=("Moving Time", lambda s: s.sum(skipna=True) / 3600.0),
                run_avg_pace=("pace_min_km", "mean"),
                longest_run_km=("dist_km", "max"),
                run_avg_hr=("Average Heart Rate", "mean"),
                actual_quality_sessions=("is_quality", "sum"),
            )
            .sort_values("week")
        )
    fb_w = pd.DataFrame()
    if not football.empty:
        fb_w = (
            football.groupby("week", as_index=False)
            .agg(
                fb_sessions_actual=("Start Date", "count"),
                fb_minutes_actual=("Duration (mins)", "sum"),
                fb_load_actual=("football_load_est", "sum"),
                fb_dist_km=("Distance (m)", lambda s: s.sum(skipna=True) / 1000.0),
                fb_hir_km=("High Intensity Running (m)", lambda s: s.sum(skipna=True) / 1000.0),
                fb_sprint_km=("Sprint Distance (m)", lambda s: s.sum(skipna=True) / 1000.0),
                fb_accelerations=("Accelerations", "sum"),
                fb_decelerations=("Decelerations", "sum"),
                fb_sprints=("No. of Sprints", "sum"),
                fb_top_speed=("Top Speed (kph)", "max"),
            )
            .sort_values("week")
        )
        fb_sub = (
            football.pivot_table(index="week", columns="football_subtype", values="Start Date", aggfunc="count")
            .rename(columns={"training": "fb_training_sessions", "match": "fb_match_sessions"})
            .reset_index()
        )
        fb_w = fb_w.merge(fb_sub, on="week", how="left")

    weekly = cal_weeks.merge(weekly_plan, on="week", how="left").merge(run_w, on="week", how="left").merge(fb_w, on="week", how="left")
    weekly = weekly.sort_values("week").reset_index(drop=True)
    weekly["run_sessions"] = weekly["run_sessions"].fillna(0).astype(int)
    weekly["run_dist_km"] = weekly["run_dist_km"].fillna(0.0)
    weekly["actual_quality_sessions"] = weekly["actual_quality_sessions"].fillna(0).astype(int)
    weekly["longest_run_km"] = weekly["longest_run_km"].fillna(0.0)
    weekly["football_actual_available"] = weekly["fb_sessions_actual"].fillna(0) > 0
    weekly["fb_data_available"] = weekly["football_actual_available"]

    hist = weekly[weekly["football_actual_available"]].copy()
    hist_sessions = float(hist["fb_sessions_actual"].median()) if not hist.empty else 3.0
    hist_minutes = float(hist["fb_minutes_actual"].median()) if not hist.empty and hist["fb_minutes_actual"].notna().any() else 160.0
    hist_load = float(hist["fb_load_actual"].median()) if not hist.empty and hist["fb_load_actual"].notna().any() else 1200.0
    hist_match = float(hist.get("fb_match_sessions", pd.Series(dtype=float)).median()) if "fb_match_sessions" in hist else 1.0
    hist_training = float(hist.get("fb_training_sessions", pd.Series(dtype=float)).median()) if "fb_training_sessions" in hist else 2.0

    weekly["football_estimated"] = False
    weekly["football_status"] = "missing"
    weekly["fb_sessions"] = weekly["fb_sessions_actual"]
    weekly["fb_minutes"] = weekly["fb_minutes_actual"]
    weekly["fb_load"] = weekly["fb_load_actual"]
    weekly["fb_training_sessions"] = weekly.get("fb_training_sessions", pd.Series(0, index=weekly.index)).fillna(0)
    weekly["fb_match_sessions"] = weekly.get("fb_match_sessions", pd.Series(0, index=weekly.index)).fillna(0)

    for idx, row in weekly.iterrows():
        expected = bool(row.get("expected_football_week", False))
        summer = bool(row.get("phase_summer_running_only", False))
        if summer:
            weekly.at[idx, "football_status"] = "not_expected"
            weekly.at[idx, "fb_sessions"] = 0.0
            weekly.at[idx, "fb_minutes"] = 0.0
            weekly.at[idx, "fb_load"] = 0.0
            continue
        if bool(row["football_actual_available"]):
            weekly.at[idx, "football_status"] = "actual"
            continue
        if expected:
            weekly.at[idx, "football_estimated"] = True
            weekly.at[idx, "football_status"] = "estimated"
            weekly.at[idx, "fb_sessions"] = row.get("plan_football_days", np.nan) if pd.notna(row.get("plan_football_days")) else hist_sessions
            weekly.at[idx, "fb_minutes"] = hist_minutes
            weekly.at[idx, "fb_load"] = hist_load
            weekly.at[idx, "fb_match_sessions"] = hist_match
            weekly.at[idx, "fb_training_sessions"] = hist_training
        else:
            weekly.at[idx, "football_status"] = "missing"

    q1 = weekly["fb_load"].quantile(0.33) if weekly["fb_load"].notna().any() else 800.0
    q2 = weekly["fb_load"].quantile(0.66) if weekly["fb_load"].notna().any() else 1500.0
    weekly["football_load_bucket"] = np.where(
        weekly["fb_load"] <= q1, "low", np.where(weekly["fb_load"] <= q2, "normal", "high")
    )
    weekly["football_actual_available"] = weekly["football_actual_available"].astype(bool)
    weekly["football_estimated"] = weekly["football_estimated"].astype(bool)
    weekly["football_unknown"] = weekly["football_status"].eq("missing")
    return weekly


def add_running_progression(weekly: pd.DataFrame, runs: pd.DataFrame, end: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, float | None]]:
    weekly = weekly.copy()
    weekly["rolling_4w_km"] = weekly["run_dist_km"].rolling(4, min_periods=1).sum()
    weekly["rolling_8w_km"] = weekly["run_dist_km"].rolling(8, min_periods=1).sum()
    weekly["longest_last_4w"] = weekly["longest_run_km"].rolling(4, min_periods=1).max()
    weekly["longest_last_8w"] = weekly["longest_run_km"].rolling(8, min_periods=1).max()
    weekly["weeks_2plus_runs"] = (weekly["run_sessions"] >= 2).astype(int)
    weekly["consistency_score"] = (
        (weekly["weeks_2plus_runs"].rolling(8, min_periods=1).mean() * 70.0)
        + (100.0 - weekly["run_dist_km"].rolling(8, min_periods=2).std().fillna(0).clip(upper=40) * 2.0)
    ).clip(lower=0, upper=100)
    if runs.empty:
        return weekly, {
            "rolling_7d_running_km": None,
            "rolling_28d_running_km": None,
            "run_frequency_7d": None,
            "run_frequency_14d": None,
            "run_frequency_28d": None,
            "easy_pace_trend": None,
            "pace_hr_efficiency_trend": None,
        }

    runs_daily = runs.assign(day=runs["Activity Date"].dt.floor("D")).groupby("day", as_index=False).agg(day_km=("dist_km", "sum"), day_runs=("Activity Date", "count"))
    idx = pd.date_range(runs_daily["day"].min(), end, freq="D")
    daily = runs_daily.set_index("day").reindex(idx, fill_value=0).rename_axis("day").reset_index()
    last7 = daily[daily["day"] > (end - pd.Timedelta(days=7))]
    last14 = daily[daily["day"] > (end - pd.Timedelta(days=14))]
    last28 = daily[daily["day"] > (end - pd.Timedelta(days=28))]
    easy_runs = runs[~runs["is_quality"]].dropna(subset=["pace_min_km"])
    easy_trend = None
    if len(easy_runs) >= 4:
        easy_trend = float(np.polyfit(np.arange(len(easy_runs)), easy_runs["pace_min_km"], 1)[0])
    eff_trend = None
    if runs["Average Heart Rate"].notna().sum() >= 4:
        tmp = runs.dropna(subset=["Average Heart Rate", "pace_min_km"]).copy()
        tmp["eff"] = (60.0 / tmp["pace_min_km"]) / tmp["Average Heart Rate"]
        if len(tmp) >= 4:
            eff_trend = float(np.polyfit(np.arange(len(tmp)), tmp["eff"], 1)[0])
    return weekly, {
        "rolling_7d_running_km": float(last7["day_km"].sum()),
        "rolling_28d_running_km": float(last28["day_km"].sum()),
        "run_frequency_7d": int(last7["day_runs"].sum()),
        "run_frequency_14d": int(last14["day_runs"].sum()),
        "run_frequency_28d": int(last28["day_runs"].sum()),
        "easy_pace_trend": easy_trend,
        "pace_hr_efficiency_trend": eff_trend,
    }


def add_compliance_and_scores(weekly: pd.DataFrame) -> pd.DataFrame:
    weekly = weekly.copy()
    weekly["plan_run_km"] = weekly["plan_run_km"].fillna(0.0)
    weekly["planned_run_sessions"] = weekly["planned_run_sessions"].fillna(0.0)
    weekly["planned_quality_sessions"] = weekly["planned_quality_sessions"].fillna(0.0)
    weekly["planned_long_run_km"] = weekly["planned_long_run_km"].fillna(0.0)
    weekly["run_adherence_pct"] = np.where(weekly["plan_run_km"] > 0, weekly["run_dist_km"] / weekly["plan_run_km"] * 100.0, np.nan)
    weekly["run_km_gap"] = weekly["run_dist_km"] - weekly["plan_run_km"]
    weekly["planned_vs_actual_runs_gap"] = weekly["run_sessions"] - weekly["planned_run_sessions"]
    weekly["long_run_completed"] = np.where(
        weekly["planned_long_run_km"] > 0, weekly["longest_run_km"] >= (weekly["planned_long_run_km"] * 0.9), False
    )
    weekly["quality_completed"] = weekly["actual_quality_sessions"] >= weekly["planned_quality_sessions"]
    weekly["frequency_completed"] = weekly["run_sessions"] >= weekly["planned_run_sessions"]
    km_ratio = np.where(weekly["plan_run_km"] > 0, weekly["run_dist_km"] / weekly["plan_run_km"], 1.0)
    freq_ratio = np.where(weekly["planned_run_sessions"] > 0, weekly["run_sessions"] / weekly["planned_run_sessions"], 1.0)
    long_ratio = np.where(weekly["planned_long_run_km"] > 0, weekly["longest_run_km"] / weekly["planned_long_run_km"], 1.0)
    quality_ratio = np.where(weekly["planned_quality_sessions"] > 0, weekly["actual_quality_sessions"] / weekly["planned_quality_sessions"], 1.0)
    weekly["plan_compliance_score"] = (
        np.clip(km_ratio, 0, 1.15) * 40
        + np.clip(freq_ratio, 0, 1.15) * 20
        + np.clip(long_ratio, 0, 1.15) * 25
        + np.clip(quality_ratio, 0, 1.15) * 15
    ).clip(0, 100)
    weekly["completion_label"] = np.where(
        weekly["plan_compliance_score"] < 75,
        "under-completed",
        np.where(weekly["plan_compliance_score"] > 115, "over-completed", "on-plan"),
    )
    weekly["combined_normalized_load"] = weekly["run_dist_km"] * 12.0 + weekly["fb_load"].fillna(0.0) * 0.35
    chronic = weekly["combined_normalized_load"].rolling(4, min_periods=1).mean()
    acute = weekly["combined_normalized_load"]
    weekly["hybrid_fatigue_score"] = ((safe_series_div(acute, chronic) - 1.0).fillna(0.0) * 65 + 40).clip(0, 100)
    weekly["fatigue_status"] = np.where(
        weekly["hybrid_fatigue_score"] >= 70, "high", np.where(weekly["hybrid_fatigue_score"] >= 45, "medium", "low")
    )
    weekly["weeks_football_forced_downscale"] = (
        (weekly["football_status"].isin(["actual", "estimated"]))
        & (weekly["plan_compliance_score"] < 80)
        & (weekly["run_sessions"] < weekly["planned_run_sessions"])
    ).astype(int)
    return weekly


def safe_series_div(a: pd.Series, b: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=a.index)
    mask = b != 0
    out.loc[mask] = a.loc[mask] / b.loc[mask]
    return out


def football_interference(runs: pd.DataFrame, football: pd.DataFrame) -> dict[str, float | str | None]:
    if runs.empty or football.empty:
        return {"status": "insufficient_data", "next_day_pace_delta_min_km": None, "within_48h_pace_delta_min_km": None, "within_72h_pace_delta_min_km": None}
    base_pace = runs["pace_min_km"].median()
    deltas_24: list[float] = []
    deltas_48: list[float] = []
    deltas_72: list[float] = []
    for _, fb in football.iterrows():
        dt = fb["Start Date"]
        post = runs[(runs["Activity Date"] > dt) & (runs["Activity Date"] <= (dt + pd.Timedelta(hours=72)))].copy()
        if post.empty:
            continue
        p24 = post[post["Activity Date"] <= (dt + pd.Timedelta(hours=24))]
        p48 = post[post["Activity Date"] <= (dt + pd.Timedelta(hours=48))]
        p72 = post
        if not p24.empty:
            deltas_24.append(float(p24["pace_min_km"].mean() - base_pace))
        if not p48.empty:
            deltas_48.append(float(p48["pace_min_km"].mean() - base_pace))
        deltas_72.append(float(p72["pace_min_km"].mean() - base_pace))
    if not deltas_72:
        return {"status": "insufficient_data", "next_day_pace_delta_min_km": None, "within_48h_pace_delta_min_km": None, "within_72h_pace_delta_min_km": None}
    return {
        "status": "ok",
        "next_day_pace_delta_min_km": float(np.mean(deltas_24)) if deltas_24 else None,
        "within_48h_pace_delta_min_km": float(np.mean(deltas_48)) if deltas_48 else None,
        "within_72h_pace_delta_min_km": float(np.mean(deltas_72)),
    }


def riegel_from_runs(runs: pd.DataFrame, end: pd.Timestamp) -> dict[str, float | int | None]:
    base = runs[runs["dist_km"] >= 5].dropna(subset=["Moving Time", "dist_km"]).copy()
    if base.empty:
        return {"aggressive_min": None, "base_min": None, "conservative_min": None, "sample_size": 0}
    base["proj_marathon_min"] = (base["Moving Time"] / 60.0) * ((42.195 / base["dist_km"]) ** 1.06)
    age_days = (end - base["Activity Date"].dt.normalize()).dt.days.clip(lower=0)
    weights = np.exp(-age_days / 50.0) * (base["dist_km"] / 10.0).clip(lower=0.5, upper=2.0)
    vals = base["proj_marathon_min"].to_numpy()
    w = weights.to_numpy()
    sorter = np.argsort(vals)
    vals = vals[sorter]
    w = w[sorter]
    cw = np.cumsum(w) / np.sum(w)
    def q(v: float) -> float:
        idx = int(np.searchsorted(cw, v, side="left"))
        idx = max(0, min(len(vals) - 1, idx))
        return float(vals[idx])
    return {"aggressive_min": q(0.2), "base_min": q(0.5), "conservative_min": q(0.8), "sample_size": int(len(base))}


def compute_confidence(weekly: pd.DataFrame, football_quality: dict[str, float | int | bool | None], runs: pd.DataFrame) -> tuple[float, list[str]]:
    score = 100.0
    explanations: list[str] = []
    run_recent = runs[runs["Activity Date"] > (runs["Activity Date"].max() - pd.Timedelta(days=28))] if not runs.empty else pd.DataFrame()
    if len(run_recent) < 6:
        score -= 20
        explanations.append("Reduced confidence: low recent running sample (<6 runs in last 28 days).")
    est_ratio = float((weekly["football_estimated"]).mean()) if not weekly.empty else 1.0
    if est_ratio > 0.5:
        score -= 15
        explanations.append("Reduced confidence: more than half of football weeks are estimated.")
    days_since = football_quality.get("days_since_last_football")
    if days_since is not None and int(days_since) > 21:
        score -= 20
        explanations.append(f"Confidence reduced because football actuals are missing for the last {int(days_since)} days.")
    if float(football_quality.get("coverage_pct", 0.0)) < (MIN_FOOTBALL_COVERAGE_FOR_COMBINED * 100.0):
        score -= 15
        explanations.append("Hybrid confidence reduced: football weekly coverage below threshold.")
    if not explanations:
        explanations.append("Confidence is stable: recent running and football data coverage are adequate.")
    return clamp(score, 20.0, 98.0), explanations


def pace_recommendations(runs: pd.DataFrame, marathon_base_min: float | None, fatigue_status: str) -> dict[str, str]:
    if runs.empty:
        return {"easy": "n/a", "steady": "n/a", "marathon": "n/a", "threshold": "n/a"}
    easy_pool = runs[~runs["is_quality"]]["pace_min_km"].dropna()
    easy_base = float(easy_pool.median()) if not easy_pool.empty else float(runs["pace_min_km"].median())
    fatigue_adj = 0.15 if fatigue_status == "high" else (0.08 if fatigue_status == "medium" else 0.0)
    mp = (marathon_base_min / 42.195) if marathon_base_min is not None else easy_base - 0.45
    easy = (easy_base + fatigue_adj, easy_base + 0.35 + fatigue_adj)
    steady = (easy_base - 0.35 + fatigue_adj, easy_base - 0.15 + fatigue_adj)
    marathon = (mp - 0.05 + fatigue_adj, mp + 0.10 + fatigue_adj)
    threshold = (mp - 0.35 + fatigue_adj, mp - 0.20 + fatigue_adj)
    return {
        "easy": f"{easy[0]:.2f}-{easy[1]:.2f} min/km",
        "steady": f"{steady[0]:.2f}-{steady[1]:.2f} min/km",
        "marathon": f"{marathon[0]:.2f}-{marathon[1]:.2f} min/km",
        "threshold": f"{threshold[0]:.2f}-{threshold[1]:.2f} min/km",
    }


def durability_metrics(weekly: pd.DataFrame) -> dict[str, float | int | None]:
    if weekly.empty:
        return {"consecutive_weeks_2plus_runs": 0, "consecutive_long_run_weeks": 0, "long_run_progression_slope": None, "planned_volume_absorbed_pct": None, "planned_long_runs_completed_pct": None, "weeks_football_forced_downscale": 0}
    cons_runs = 0
    cons_long = 0
    for _, row in weekly.sort_values("week", ascending=False).iterrows():
        if row["run_sessions"] >= 2:
            cons_runs += 1
        else:
            break
    for _, row in weekly.sort_values("week", ascending=False).iterrows():
        if bool(row["long_run_completed"]):
            cons_long += 1
        else:
            break
    lr = weekly["longest_run_km"].dropna()
    slope = float(np.polyfit(np.arange(len(lr)), lr, 1)[0]) if len(lr) >= 4 else None
    planned = weekly["plan_run_km"].sum()
    absorbed = safe_ratio(float(weekly["run_dist_km"].sum()) * 100.0, float(planned)) if planned > 0 else None
    plan_long_weeks = (weekly["planned_long_run_km"] > 0).sum()
    completed_long = weekly["long_run_completed"].sum()
    long_pct = safe_ratio(float(completed_long) * 100.0, float(plan_long_weeks)) if plan_long_weeks > 0 else None
    return {
        "consecutive_weeks_2plus_runs": int(cons_runs),
        "consecutive_long_run_weeks": int(cons_long),
        "long_run_progression_slope": slope,
        "planned_volume_absorbed_pct": absorbed,
        "planned_long_runs_completed_pct": long_pct,
        "weeks_football_forced_downscale": int(weekly["weeks_football_forced_downscale"].sum()),
    }


def readiness_statuses(weekly: pd.DataFrame, progression: dict[str, float | None], marathon_readiness_score: float) -> dict[str, str]:
    pace_tr = progression.get("easy_pace_trend")
    eff_tr = progression.get("pace_hr_efficiency_trend")
    if eff_tr is not None and eff_tr > 0:
        aerobic = "improving"
    elif pace_tr is not None and pace_tr > 0.02:
        aerobic = "declining"
    else:
        aerobic = "stable"
    cons = float(weekly["consistency_score"].tail(4).mean()) if not weekly.empty else 0.0
    longest = float(weekly["longest_run_km"].tail(4).max()) if not weekly.empty else 0.0
    if cons < 40 or longest < 14:
        durability = "insufficient"
    elif cons < 65 or longest < 20:
        durability = "building"
    elif cons < 80 or longest < 26:
        durability = "strong"
    else:
        durability = "race-ready"
    fatigue = str(weekly["fatigue_status"].iloc[-1]) if not weekly.empty else "medium"
    if marathon_readiness_score < 40:
        mr = "low"
    elif marathon_readiness_score < 65:
        mr = "moderate"
    else:
        mr = "strong"
    return {"aerobic_fitness_status": aerobic, "durability_status": durability, "fatigue_status": fatigue, "marathon_readiness": mr}


def next_week_prediction(weekly: pd.DataFrame, weekly_plan: pd.DataFrame, end: pd.Timestamp, conf: float) -> dict[str, float | str]:
    hist = weekly[weekly["week"] <= end].tail(6).copy()
    next_plan = weekly_plan[weekly_plan["week"] > end].head(1)
    compliance = float(hist["plan_compliance_score"].mean()) if not hist.empty else 50.0
    fatigue = float(hist["hybrid_fatigue_score"].tail(2).mean()) if not hist.empty else 50.0
    long_ok = float(hist["long_run_completed"].tail(6).mean()) if not hist.empty else 0.5
    quality_ok = float(hist["quality_completed"].tail(6).mean()) if not hist.empty else 0.5
    fb_risk = 0.0
    if not next_plan.empty and bool(next_plan["expected_football_week"].iloc[0]):
        fb_risk = 0.08
    p_vol = clamp(0.35 + (compliance / 200.0) - (fatigue / 250.0) - fb_risk + (conf / 500.0), 0.1, 0.92)
    p_long = clamp(0.30 + long_ok * 0.45 - (fatigue / 280.0) + (conf / 600.0), 0.1, 0.93)
    p_quality = clamp(0.28 + quality_ok * 0.45 - (fatigue / 260.0) + (conf / 650.0), 0.1, 0.9)
    p_down = clamp(1.0 - ((p_vol + p_long + p_quality) / 3.0) + (fatigue / 200.0), 0.05, 0.9)
    return {
        "next_week_volume_completion_probability": round(p_vol, 3),
        "next_long_run_completion_probability": round(p_long, 3),
        "next_quality_completion_probability": round(p_quality, 3),
        "next_week_downscale_probability": round(p_down, 3),
    }


def build_october_goal_targets(weekly: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    history = weekly[weekly["run_dist_km"].notna()].copy()
    if history.empty:
        return pd.DataFrame()
    current_weekly = float(history["run_dist_km"].tail(4).mean())
    current_long = float(history["longest_run_km"].tail(4).max())
    oct_first = pd.Timestamp(year=end.year, month=10, day=1)
    next_sunday = (end + pd.offsets.Week(weekday=6)).normalize()
    weeks = pd.date_range(next_sunday, oct_first, freq="W-SUN")
    if len(weeks) == 0:
        return pd.DataFrame()
    peak_weekly = float(np.clip(max(current_weekly * 1.5, 50.0), 35.0, 75.0))
    peak_long = float(np.clip(max(current_long * 1.35, 28.0), 18.0, 34.0))
    rows = []
    wk_target = max(18.0, current_weekly)
    lr_target = max(10.0, current_long)
    for i, wk in enumerate(weeks):
        if i > 0:
            if i % 4 == 0:
                wk_target *= 0.90
                lr_target *= 0.90
            else:
                wk_target *= 1.05
                lr_target *= 1.04
        wk_target = min(wk_target, peak_weekly)
        lr_target = min(lr_target, peak_long)
        rows.append(
            {
                "week": wk,
                "target_weekly_km_min": round(max(12.0, wk_target * 0.9), 1),
                "target_weekly_km_max": round(wk_target * 1.1, 1),
                "target_long_run_km_min": round(max(8.0, lr_target - 2.0), 1),
                "target_long_run_km_max": round(lr_target + 2.0, 1),
            }
        )
    return pd.DataFrame(rows)


def build_session_model(plan_clean: pd.DataFrame, runs: pd.DataFrame, football: pd.DataFrame) -> pd.DataFrame:
    plan_rows = pd.DataFrame()
    if not plan_clean.empty:
        plan_rows = pd.DataFrame(
            {
                "date": plan_clean["fecha"],
                "sport": np.where(plan_clean["subtype"].eq("football"), "football", "run"),
                "subtype": plan_clean["subtype"],
                "planned_vs_unplanned": "planned",
                "duration": np.nan,
                "distance_km": plan_clean["km_objetivo"],
                "pace_min_km": np.nan,
                "avg_hr": np.nan,
                "relative_effort": np.nan,
                "football_session_load": np.nan,
                "HIR_m": np.nan,
                "sprint_distance_m": np.nan,
                "accelerations": np.nan,
                "decelerations": np.nan,
                "source": "plan",
                "data_confidence": "plan",
            }
        )
    run_rows = pd.DataFrame()
    if not runs.empty:
        run_rows = pd.DataFrame(
            {
                "date": runs["Activity Date"].dt.normalize(),
                "sport": "run",
                "subtype": np.where(runs["is_long"], "long_run", np.where(runs["is_quality"], "quality_run", "easy_run")),
                "planned_vs_unplanned": "actual",
                "duration": runs["Moving Time"] / 60.0,
                "distance_km": runs["dist_km"],
                "pace_min_km": runs["pace_min_km"],
                "avg_hr": runs["Average Heart Rate"],
                "relative_effort": runs["Relative Effort"],
                "football_session_load": np.nan,
                "HIR_m": np.nan,
                "sprint_distance_m": np.nan,
                "accelerations": np.nan,
                "decelerations": np.nan,
                "source": "strava",
                "data_confidence": "actual",
            }
        )
    fb_rows = pd.DataFrame()
    if not football.empty:
        fb_rows = pd.DataFrame(
            {
                "date": football["Start Date"].dt.normalize(),
                "sport": "football",
                "subtype": football["football_subtype"],
                "planned_vs_unplanned": "actual",
                "duration": football["Duration (mins)"],
                "distance_km": football["Distance (m)"] / 1000.0,
                "pace_min_km": np.nan,
                "avg_hr": np.nan,
                "relative_effort": np.nan,
                "football_session_load": football["football_load_est"],
                "HIR_m": football["High Intensity Running (m)"],
                "sprint_distance_m": football["Sprint Distance (m)"],
                "accelerations": football["Accelerations"],
                "decelerations": football["Decelerations"],
                "source": "football_actual",
                "data_confidence": "actual",
            }
        )
    if plan_rows.empty and run_rows.empty and fb_rows.empty:
        return pd.DataFrame()
    return pd.concat([plan_rows, run_rows, fb_rows], ignore_index=True).sort_values("date")


def save_plots(weekly: pd.DataFrame, runs: pd.DataFrame, outdir: Path, targets: pd.DataFrame, bands: dict[str, float | int | None], plan_compare: pd.DataFrame) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(weekly["week"], weekly["run_dist_km"], marker="o", label="Actual run km")
    if "plan_run_km" in weekly:
        ax.plot(weekly["week"], weekly["plan_run_km"], marker="s", linestyle="--", label="Plan run km")
    ax.plot(weekly["week"], weekly["longest_run_km"], marker="^", linestyle=":", label="Longest run")
    ax.set_title("Running Progression: Weekly Volume vs Plan")
    ax.set_xlabel("Week")
    ax.set_ylabel("Distance (km)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "running_progression.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    if not runs.empty:
        ax.plot(runs["Activity Date"], runs["pace_min_km"], marker="o", linestyle="-", label="Pace")
        ax.invert_yaxis()
    ax.set_title("Running Efficiency Trend: Pace and Heart Rate")
    ax.set_xlabel("Date")
    ax.set_ylabel("Pace (min/km)")
    ax.grid(alpha=0.3)
    pace_lines, pace_labels = ax.get_legend_handles_labels()
    if not runs.empty and runs["Average Heart Rate"].notna().any():
        ax2 = ax.twinx()
        ax2.plot(runs["Activity Date"], runs["Average Heart Rate"], color="tab:red", linestyle="--", marker="x", label="HR")
        ax2.set_ylabel("Average Heart Rate (bpm)")
        hr_lines, hr_labels = ax2.get_legend_handles_labels()
        ax.legend(pace_lines + hr_lines, pace_labels + hr_labels, loc="best")
    elif pace_labels:
        ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(outdir / "pace_hr_trend.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(weekly["week"], weekly["run_dist_km"], marker="o", label="Run km")
    ax.plot(weekly["week"], weekly["fb_load"].fillna(0), marker="^", linestyle="--", label="Football load (actual/estimated)")
    ax.plot(weekly["week"], weekly["combined_normalized_load"], marker="s", linestyle="-.", label="Combined normalized load")
    ax.set_title("Load and Fatigue Context: Running + Football")
    ax.set_xlabel("Week")
    ax.set_ylabel("Load units")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "combined_stress_trend.png", dpi=140)
    plt.close(fig)

    pred_df = runs[runs["dist_km"] >= 5].copy() if not runs.empty else pd.DataFrame()
    fig, ax = plt.subplots(figsize=(10, 5))
    if not pred_df.empty:
        pred_df["proj_marathon_min"] = (pred_df["Moving Time"] / 60.0) * ((42.195 / pred_df["dist_km"]) ** 1.06)
        ax.plot(pred_df["Activity Date"], pred_df["proj_marathon_min"], marker="o", label="Run projections")
    if bands["aggressive_min"] is not None and bands["conservative_min"] is not None:
        ax.axhspan(float(bands["aggressive_min"]), float(bands["conservative_min"]), alpha=0.2, color="tab:green", label="Prediction band")
    if bands["base_min"] is not None:
        ax.axhline(float(bands["base_min"]), color="tab:blue", linestyle="--", label="Base")
    ax.set_title("Marathon Time Projection Band")
    ax.set_xlabel("Date")
    ax.set_ylabel("Projected marathon time (minutes)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "marathon_projection_band.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    if not targets.empty:
        ax.plot(weekly["week"], weekly["run_dist_km"], marker="o", label="Actual")
        ax.plot(targets["week"], targets["target_weekly_km_min"], linestyle="--", label="Target min")
        ax.plot(targets["week"], targets["target_weekly_km_max"], linestyle="--", label="Target max")
        ax.fill_between(targets["week"], targets["target_weekly_km_min"], targets["target_weekly_km_max"], alpha=0.15)
    ax.set_title("Goal Gap to October: Weekly Running Volume")
    ax.set_xlabel("Week")
    ax.set_ylabel("Distance (km)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "goal_gap_dashboard.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    if not plan_compare.empty:
        ax.plot(plan_compare["week"], plan_compare["plan_run_km"], marker="s", linestyle="--", label="Plan")
        ax.plot(plan_compare["week"], plan_compare["run_dist_km"], marker="o", label="Actual")
        ax2 = ax.twinx()
        ax2.plot(plan_compare["week"], plan_compare["run_adherence_pct"], marker="^", color="tab:green", label="Adherence %")
        ax2.set_ylabel("Adherence (%)")
    ax.set_title("Plan Compliance: Planned vs Completed Running")
    ax.set_xlabel("Week")
    ax.set_ylabel("Distance (km)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "plan_adherence_dashboard.png", dpi=140)
    plt.close(fig)


def _escape_html(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_html_report(outdir: Path, markdown_lines: list[str], weekly: pd.DataFrame, plan_compare: pd.DataFrame, targets: pd.DataFrame) -> None:
    body = []
    in_list = False
    for raw in markdown_lines:
        t = raw.strip()
        if t == "":
            if in_list:
                body.append("</ul>")
                in_list = False
            continue
        if t.startswith("# "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h1>{_escape_html(t[2:])}</h1>")
        elif t.startswith("## "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h2>{_escape_html(t[3:])}</h2>")
        elif t.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_escape_html(t[2:])}</li>")
        else:
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<p>{_escape_html(t)}</p>")
    if in_list:
        body.append("</ul>")
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Reporte</title>
<style>body{{font-family:Arial,sans-serif;margin:20px}} table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ddd;padding:6px}}</style></head><body>
<p>Generado: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
{''.join(body)}
<h2>Weekly metrics</h2>{weekly.to_html(index=False, border=0) if not weekly.empty else "<p>Sin datos</p>"}
<h2>Plan vs actual</h2>{plan_compare.to_html(index=False, border=0) if not plan_compare.empty else "<p>Sin datos</p>"}
<h2>Targets</h2>{targets.to_html(index=False, border=0) if not targets.empty else "<p>Sin datos</p>"}
</body></html>"""
    (outdir / "report.html").write_text(html, encoding="utf-8")


def build_report(weekly: pd.DataFrame, progression: dict[str, float | None], durability: dict[str, float | int | None], predictions: dict[str, float | str], readiness: dict[str, str], confidence_score: float, confidence_notes: list[str], interference: dict[str, float | str | None], marathon: dict[str, float | int | None], pace_bands: dict[str, str], start: pd.Timestamp, end: pd.Timestamp, outdir: Path) -> None:
    current_week = weekly[weekly["week"] <= end].tail(1)
    lines = [
        "# Plan-aware Hybrid Marathon Analysis",
        f"Window: {start.date()} -> {end.date()}",
        "",
        "## This Week",
    ]
    if not current_week.empty:
        cw = current_week.iloc[0]
        lines.extend(
            [
                f"- Plan week: {cw.get('semana_plan', 'n/a')}",
                f"- Phase: {cw.get('fase', 'n/a')}",
                f"- Planned sessions: {int(cw.get('planned_run_sessions', 0))}",
                f"- Completed sessions: {int(cw.get('run_sessions', 0))}",
                f"- Running km vs target: {cw.get('run_dist_km', 0):.1f} / {cw.get('plan_run_km', 0):.1f}",
                f"- Long run status: {'done' if bool(cw.get('long_run_completed', False)) else 'pending'}",
                f"- Football status: {cw.get('football_status', 'unknown')}",
                f"- Plan compliance score: {cw.get('plan_compliance_score', 0):.1f}",
            ]
        )
    lines.extend(
        [
            "",
            "## Running Progression",
            f"- Rolling 7d running km: {progression.get('rolling_7d_running_km')}",
            f"- Rolling 28d running km: {progression.get('rolling_28d_running_km')}",
            f"- Run frequency last 7/14/28: {progression.get('run_frequency_7d')}/{progression.get('run_frequency_14d')}/{progression.get('run_frequency_28d')}",
            f"- Easy pace trend (negative faster): {progression.get('easy_pace_trend')}",
            f"- Pace/HR efficiency trend: {progression.get('pace_hr_efficiency_trend')}",
            "",
            "## Durability",
            f"- Consecutive weeks with 2+ runs: {durability.get('consecutive_weeks_2plus_runs')}",
            f"- Consecutive weeks with long run completed: {durability.get('consecutive_long_run_weeks')}",
            f"- Long-run progression slope: {durability.get('long_run_progression_slope')}",
            f"- Planned volume absorbed: {durability.get('planned_volume_absorbed_pct')}",
            f"- Planned long runs completed: {durability.get('planned_long_runs_completed_pct')}",
            f"- Weeks football likely forced downscale: {durability.get('weeks_football_forced_downscale')}",
            "",
            "## Football Interference",
            f"- Status: {interference.get('status')}",
            f"- Next-day pace delta: {interference.get('next_day_pace_delta_min_km')}",
            f"- 48h pace delta: {interference.get('within_48h_pace_delta_min_km')}",
            f"- 72h pace delta: {interference.get('within_72h_pace_delta_min_km')}",
            "",
            "## Predictions",
            f"- Next-week volume completion probability: {predictions['next_week_volume_completion_probability']:.2f}",
            f"- Next long-run completion probability: {predictions['next_long_run_completion_probability']:.2f}",
            f"- Next quality completion probability: {predictions['next_quality_completion_probability']:.2f}",
            f"- Downscale probability: {predictions['next_week_downscale_probability']:.2f}",
            "",
            "## Readiness",
            f"- Aerobic fitness: {readiness['aerobic_fitness_status']}",
            f"- Durability: {readiness['durability_status']}",
            f"- Fatigue: {readiness['fatigue_status']}",
            f"- Marathon readiness: {readiness['marathon_readiness']}",
            "",
            "## Marathon Estimate",
            f"- Fitness-based: {format_hms(marathon.get('base_min'))}",
            f"- Durability-adjusted: {format_hms(marathon.get('durability_adjusted_min'))}",
            f"- Realistic range: {format_hms(marathon.get('aggressive_min'))} to {format_hms(marathon.get('conservative_min'))}",
            f"- Confidence score: {confidence_score:.1f}/100",
            "",
            "## Pace Recommendations",
            f"- Easy: {pace_bands['easy']}",
            f"- Steady: {pace_bands['steady']}",
            f"- Marathon pace: {pace_bands['marathon']}",
            f"- Threshold: {pace_bands['threshold']}",
            "",
            "## Confidence Notes",
        ]
    )
    for note in confidence_notes:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## Files generated",
            "- report.md",
            "- report.html",
            "- weekly_metrics.csv",
            "- plan_vs_actual.csv",
            "- target_ranges_to_october.csv",
            "- plan_limpio_sesiones.csv",
            "- plan_limpio_semanal.csv",
            "- session_model.csv",
            "- predictions.json",
        ]
    )
    (outdir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    write_html_report(outdir, lines, weekly, weekly, pd.DataFrame())


def publish_github_pages(outdir: Path, site_dir: Path, plan_pdf_path: Path, football_quality: dict[str, float | int | bool | None], confidence_score: float) -> None:
    site_assets = site_dir / "assets"
    site_data = site_dir / "data"
    site_assets.mkdir(parents=True, exist_ok=True)
    site_data.mkdir(parents=True, exist_ok=True)
    for name in ["running_progression.png", "pace_hr_trend.png", "combined_stress_trend.png", "marathon_projection_band.png", "goal_gap_dashboard.png", "plan_adherence_dashboard.png"]:
        src = outdir / name
        if src.exists():
            shutil.copy2(src, site_assets / name)
    for name in ["weekly_metrics.csv", "plan_vs_actual.csv", "target_ranges_to_october.csv", "plan_limpio_sesiones.csv", "plan_limpio_semanal.csv", "report.md", "predictions.json"]:
        src = outdir / name
        if src.exists():
            shutil.copy2(src, site_data / name)
    if plan_pdf_path.exists():
        shutil.copy2(plan_pdf_path, site_assets / "plan_entrenamiento.pdf")
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_outdir": str(outdir.resolve()),
        "has_plan_pdf": plan_pdf_path.exists(),
        "football_coverage_pct": football_quality.get("coverage_pct"),
        "football_weeks_with_data": football_quality.get("weeks_with_football_data"),
        "football_weeks_total": football_quality.get("weeks_total"),
        "football_days_since_last": football_quality.get("days_since_last_football"),
        "football_coverage_threshold_pct": football_quality.get("coverage_threshold_pct"),
        "football_combined_sufficient": football_quality.get("is_sufficient_for_combined"),
        "prediction_confidence_score": confidence_score,
    }
    (site_data / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    setup_logging()
    args = parse_args()
    football_path = Path(args.football)
    strava_path = Path(args.strava)
    plan_path = Path(args.plan)
    outdir = Path(args.outdir)
    site_dir = Path(args.site_dir)
    plan_pdf_path = Path(args.plan_pdf)
    today = pd.Timestamp.today().normalize()
    start = pd.Timestamp(args.start) if args.start else pd.Timestamp(year=today.year, month=2, day=1)
    end = pd.Timestamp(args.end) if args.end else today
    outdir.mkdir(parents=True, exist_ok=True)

    runs = prep_runs(strava_path, start, end)
    football = prep_football(football_path, start, end)
    football_quality = football_data_quality(football, start, end)
    plan_clean, weekly_plan = clean_training_plan(plan_path, outdir)
    weekly = summarize_weekly(runs, football, weekly_plan, start, end)
    weekly, progression = add_running_progression(weekly, runs, end)
    weekly = add_compliance_and_scores(weekly)
    durability = durability_metrics(weekly)
    interference = football_interference(runs, football)
    marathon = riegel_from_runs(runs, end)
    durability_penalty = 0.0
    if durability.get("planned_long_runs_completed_pct") is not None:
        durability_penalty += max(0.0, 20.0 - float(durability["planned_long_runs_completed_pct"]) / 5.0)
    fatigue_tail = float(weekly["hybrid_fatigue_score"].tail(2).mean()) if not weekly.empty else 50.0
    durability_penalty += max(0.0, (fatigue_tail - 45.0) * 0.35)
    marathon["durability_adjusted_min"] = (float(marathon["base_min"]) + durability_penalty) if marathon["base_min"] is not None else None
    readiness_score = clamp((float(weekly["consistency_score"].tail(4).mean()) if not weekly.empty else 40.0) - max(0.0, fatigue_tail - 45.0) * 0.8 + 20.0, 5.0, 95.0)
    readiness = readiness_statuses(weekly, progression, readiness_score)
    confidence_score, confidence_notes = compute_confidence(weekly, football_quality, runs)
    pace_bands = pace_recommendations(runs, marathon.get("base_min"), readiness["fatigue_status"])
    predictions = next_week_prediction(weekly, weekly_plan, end, confidence_score)
    targets = build_october_goal_targets(weekly, end)

    session_model = build_session_model(plan_clean, runs, football)
    if not session_model.empty:
        session_model.to_csv(outdir / "session_model.csv", index=False)

    weekly_metrics = weekly.copy()
    keep_cols = [c for c in weekly_metrics.columns if c not in {"vol_objetivo_min", "vol_objetivo_max"}]
    weekly_metrics = weekly_metrics[keep_cols]
    weekly_metrics.to_csv(outdir / "weekly_metrics.csv", index=False)
    plan_vs_actual = weekly[["week", "fase", "plan_run_km", "run_dist_km", "run_adherence_pct", "run_km_gap", "planned_run_sessions", "run_sessions", "planned_long_run_km", "longest_run_km", "planned_quality_sessions", "actual_quality_sessions", "expected_football_week", "football_actual_available", "football_estimated", "football_status", "plan_compliance_score"]].copy()
    plan_vs_actual.to_csv(outdir / "plan_vs_actual.csv", index=False)
    if not targets.empty:
        targets.to_csv(outdir / "target_ranges_to_october.csv", index=False)

    pred_payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "readiness": readiness,
        "probabilities": predictions,
        "marathon_prediction": {
            "fitness_based": marathon.get("base_min"),
            "durability_adjusted": marathon.get("durability_adjusted_min"),
            "aggressive": marathon.get("aggressive_min"),
            "conservative": marathon.get("conservative_min"),
            "confidence_score": confidence_score,
        },
        "pace_recommendations": pace_bands,
        "confidence_notes": confidence_notes,
    }
    (outdir / "predictions.json").write_text(json.dumps(pred_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_plots(weekly, runs, outdir, targets, marathon, plan_vs_actual)
    build_report(weekly, progression, durability, predictions, readiness, confidence_score, confidence_notes, interference, marathon, pace_bands, start, end, outdir)
    publish_github_pages(outdir, site_dir, plan_pdf_path, football_quality, confidence_score)

    logging.info("Analysis complete. Output: %s", outdir.resolve())
    print("Analysis complete.")
    print(f"Output folder: {outdir.resolve()}")
    print("Open analysis_output/report.md to read insights.")


if __name__ == "__main__":
    main()
