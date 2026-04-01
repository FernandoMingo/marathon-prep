import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze football sessions + Strava runs for marathon preparation."
    )
    parser.add_argument("--football", default="export.csv", help="Path to football CSV export")
    parser.add_argument(
        "--strava",
        default="export_149118275/activities.csv",
        help="Path to Strava activities.csv",
    )
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--plan",
        default="plan_maraton_hibrido_corregido.csv",
        help="Path to marathon training plan CSV",
    )
    parser.add_argument("--outdir", default="analysis_output", help="Output folder")
    return parser.parse_args()


def prep_football(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Start Date"] = pd.to_datetime(df["Start Date"], dayfirst=True, errors="coerce")
    df = df[df["Segment Name"].astype(str).str.strip().eq("Whole Session")].copy()
    df = df[(df["Start Date"] >= start) & (df["Start Date"] <= end)].copy()

    numeric_cols = [
        "Duration (mins)",
        "Session Load",
        "Distance (m)",
        "High Intensity Running (m)",
        "Sprint Distance (m)",
        "Top Speed (kph)",
        "Avg Speed (kph)",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["week"] = df["Start Date"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    return df


def prep_runs(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    runs = pd.read_csv(path)
    runs["Activity Date"] = pd.to_datetime(runs["Activity Date"], errors="coerce")
    runs = runs[runs["Activity Type"].astype(str).str.strip().eq("Run")].copy()

    # Strava export can include both Distance (km) and Distance.1 (meters).
    dist_col = "Distance.1" if "Distance.1" in runs.columns else "Distance"
    runs["Distance"] = pd.to_numeric(runs[dist_col], errors="coerce")

    for col in ["Distance", "Moving Time", "Average Heart Rate", "Relative Effort"]:
        if col in runs.columns:
            runs[col] = pd.to_numeric(runs[col], errors="coerce")

    runs = runs[(runs["Activity Date"] >= start) & (runs["Activity Date"] <= end)].copy()
    runs = runs[runs["Distance"] > 200].copy()

    runs["dist_km"] = runs["Distance"] / 1000.0
    runs["pace_min_km"] = (runs["Moving Time"] / 60.0) / runs["dist_km"]
    runs["week"] = runs["Activity Date"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    return runs.sort_values("Activity Date")


def aggregate_weekly(football: pd.DataFrame, runs: pd.DataFrame) -> pd.DataFrame:
    fb_w = (
        football.groupby("week", as_index=False)
        .agg(
            fb_sessions=("Start Date", "count"),
            fb_load=("Session Load", "sum"),
            fb_dist_km=("Distance (m)", lambda s: s.sum(skipna=True) / 1000.0),
            fb_hir_km=("High Intensity Running (m)", lambda s: s.sum(skipna=True) / 1000.0),
        )
    )

    run_w = (
        runs.groupby("week", as_index=False)
        .agg(
            run_sessions=("Activity ID", "count"),
            run_dist_km=("dist_km", "sum"),
            run_time_h=("Moving Time", lambda s: s.sum(skipna=True) / 3600.0),
            run_avg_pace=("pace_min_km", "mean"),
            longest_run_km=("dist_km", "max"),
            run_avg_hr=("Average Heart Rate", "mean"),
        )
    )

    weekly = fb_w.merge(run_w, on="week", how="outer").sort_values("week").reset_index(drop=True)
    return weekly


def riegel_projection(runs: pd.DataFrame) -> pd.Series | None:
    cand = runs[runs["dist_km"] >= 7].copy()
    if cand.empty:
        return None
    cand["time_min"] = cand["Moving Time"] / 60.0
    cand["marathon_min"] = cand["time_min"] * ((42.195 / cand["dist_km"]) ** 1.06)
    return cand.loc[cand["marathon_min"].idxmin()]


def linear_trend(series: pd.Series) -> float | None:
    s = series.dropna()
    if len(s) < 2:
        return None
    x = np.arange(len(s))
    return float(np.polyfit(x, s.values, 1)[0])


def safe_ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    if pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return float(a / b)


def parse_km_range(text: str) -> tuple[float | None, float | None]:
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


def extract_planned_km(raw_text: str) -> tuple[float | None, float | None]:
    if raw_text is None:
        return None, None
    text = str(raw_text).lower().replace(",", ".")
    # Prefer explicit totals in workout descriptions.
    total_match = re.search(r"total\s*(\d+(?:\.\d+)?)\s*km", text)
    if total_match:
        v = float(total_match.group(1))
        return v, v
    # For session text, require explicit km unit to avoid matching Z1-Z2.
    m_range = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*km", text)
    if m_range:
        return float(m_range.group(1)), float(m_range.group(2))
    m_single = re.search(r"(\d+(?:\.\d+)?)\s*km", text)
    if m_single:
        v = float(m_single.group(1))
        return v, v
    return None, None


def classify_session(raw_text: str) -> str:
    if raw_text is None:
        return "unknown"
    t = str(raw_text).lower()
    if "maratón" in t or "maraton" in t:
        return "race"
    if "fútbol" in t or "futbol" in t or "partido" in t:
        return "football"
    if "descanso" in t and "km" not in t:
        return "rest"
    if "fuerza" in t or "movilidad" in t:
        return "strength_mobility"
    if "km" in t:
        return "run"
    return "other"


def clean_training_plan(plan_path: Path, outdir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not plan_path.exists():
        return pd.DataFrame(), pd.DataFrame()

    plan = pd.read_csv(plan_path)
    plan["inicio_semana"] = pd.to_datetime(plan["inicio_semana"], errors="coerce")
    day_cols = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    day_offsets = {"lunes": 0, "martes": 1, "miércoles": 2, "jueves": 3, "viernes": 4, "sábado": 5, "domingo": 6}

    rows: list[dict] = []
    for _, r in plan.iterrows():
        week_start = r.get("inicio_semana")
        if pd.isna(week_start):
            continue
        vol_min, vol_max = parse_km_range(str(r.get("volumen_objetivo_aprox_km", "")))
        for dc in day_cols:
            raw = str(r.get(dc, "")).strip()
            if raw == "" or raw.lower() == "nan":
                continue
            km_min, km_max = extract_planned_km(raw)
            rows.append(
                {
                    "semana": r.get("semana"),
                    "fecha": (week_start + pd.Timedelta(days=day_offsets[dc])).normalize(),
                    "dia": dc,
                    "fase": r.get("fase"),
                    "sesion_plan": raw,
                    "modalidad": classify_session(raw),
                    "km_objetivo_min": km_min,
                    "km_objetivo_max": km_max,
                    "km_objetivo": (
                        (km_min + km_max) / 2.0 if km_min is not None and km_max is not None else km_min
                    ),
                    "volumen_semana_objetivo_min": vol_min,
                    "volumen_semana_objetivo_max": vol_max,
                }
            )

    clean = pd.DataFrame(rows).sort_values("fecha").reset_index(drop=True)
    if clean.empty:
        return clean, pd.DataFrame()
    clean["week"] = clean["fecha"].dt.to_period("W-SUN").dt.end_time.dt.normalize()

    weekly_plan = (
        clean.groupby("week", as_index=False)
        .agg(
            semana_plan=("semana", "min"),
            fase=("fase", "last"),
            plan_run_km=("km_objetivo", lambda s: s[clean.loc[s.index, "modalidad"].isin(["run", "race"])].sum(skipna=True)),
            plan_football_days=("modalidad", lambda s: int((s == "football").sum())),
            plan_quality_days=("sesion_plan", lambda s: int(s.str.contains("series|tempo|rm|umbral", case=False, regex=True).sum())),
            vol_objetivo_min=("volumen_semana_objetivo_min", "max"),
            vol_objetivo_max=("volumen_semana_objetivo_max", "max"),
        )
    )
    weekly_plan["plan_run_km"] = weekly_plan["plan_run_km"].fillna(0.0)
    weekly_plan["plan_vol_objetivo_km"] = (weekly_plan["vol_objetivo_min"] + weekly_plan["vol_objetivo_max"]) / 2.0

    outdir.mkdir(parents=True, exist_ok=True)
    clean.to_csv(outdir / "plan_limpio_sesiones.csv", index=False)
    weekly_plan.to_csv(outdir / "plan_limpio_semanal.csv", index=False)
    return clean, weekly_plan


def plan_vs_actual_weekly(weekly_actual: pd.DataFrame, weekly_plan: pd.DataFrame) -> pd.DataFrame:
    if weekly_plan.empty:
        return pd.DataFrame()
    merged = weekly_plan.merge(weekly_actual, left_on="week", right_on="week", how="left")
    merged["run_dist_km"] = merged["run_dist_km"].fillna(0.0)
    merged["run_adherence_pct"] = np.where(
        merged["plan_run_km"] > 0,
        (merged["run_dist_km"] / merged["plan_run_km"]) * 100.0,
        np.nan,
    )
    merged["run_km_gap"] = merged["run_dist_km"] - merged["plan_run_km"]
    merged["quality_gap"] = merged["run_sessions"].fillna(0.0) - merged["plan_quality_days"].fillna(0.0)
    return merged


def running_load_metrics(runs: pd.DataFrame, end: pd.Timestamp) -> dict[str, float | None]:
    if runs.empty:
        return {
            "acute_7d_km": None,
            "chronic_28d_km": None,
            "acwr": None,
            "last14_km": None,
            "prev14_km": None,
            "ramp_ratio_14d": None,
        }

    daily = (
        runs.assign(day=runs["Activity Date"].dt.floor("D"))
        .groupby("day", as_index=False)
        .agg(day_km=("dist_km", "sum"))
        .sort_values("day")
    )
    idx = pd.date_range(daily["day"].min(), end, freq="D")
    daily = daily.set_index("day").reindex(idx, fill_value=0.0).rename_axis("day").reset_index()

    recent = daily[daily["day"] > (end - pd.Timedelta(days=7))]
    chronic = daily[daily["day"] > (end - pd.Timedelta(days=28))]
    last14 = daily[daily["day"] > (end - pd.Timedelta(days=14))]
    prev14 = daily[(daily["day"] > (end - pd.Timedelta(days=28))) & (daily["day"] <= (end - pd.Timedelta(days=14)))]

    acute_7d_km = float(recent["day_km"].sum()) if not recent.empty else 0.0
    chronic_28d_km = float(chronic["day_km"].sum()) if not chronic.empty else 0.0
    acwr = safe_ratio(acute_7d_km / 7.0, chronic_28d_km / 28.0) if chronic_28d_km > 0 else None
    last14_km = float(last14["day_km"].sum()) if not last14.empty else 0.0
    prev14_km = float(prev14["day_km"].sum()) if not prev14.empty else 0.0
    ramp_ratio_14d = safe_ratio(last14_km, prev14_km) if prev14_km > 0 else None

    return {
        "acute_7d_km": acute_7d_km,
        "chronic_28d_km": chronic_28d_km,
        "acwr": acwr,
        "last14_km": last14_km,
        "prev14_km": prev14_km,
        "ramp_ratio_14d": ramp_ratio_14d,
    }


def race_predictors_from_recent(runs: pd.DataFrame) -> dict[str, float | None]:
    if runs.empty:
        return {"5k_min": None, "10k_min": None, "hm_min": None, "marathon_min": None}
    base = runs[runs["dist_km"] >= 5].copy()
    if base.empty:
        return {"5k_min": None, "10k_min": None, "hm_min": None, "marathon_min": None}

    # Use best pace among meaningful efforts (5k+) and Riegel scaling.
    best = base.loc[base["pace_min_km"].idxmin()]
    d_base = float(best["dist_km"])
    t_base = float(best["Moving Time"] / 60.0)

    def riegel(d_target: float) -> float:
        return t_base * ((d_target / d_base) ** 1.06)

    return {
        "5k_min": riegel(5.0),
        "10k_min": riegel(10.0),
        "hm_min": riegel(21.097),
        "marathon_min": riegel(42.195),
    }


def weighted_quantile(values: np.ndarray, quantile: float, weights: np.ndarray) -> float:
    sorter = np.argsort(values)
    v = values[sorter]
    w = weights[sorter]
    cumulative = np.cumsum(w) / np.sum(w)
    idx = np.searchsorted(cumulative, quantile, side="left")
    idx = min(max(idx, 0), len(v) - 1)
    return float(v[idx])


def marathon_prediction_bands(runs: pd.DataFrame, end: pd.Timestamp) -> dict[str, float | int | None]:
    base = runs[runs["dist_km"] >= 5].dropna(subset=["Moving Time", "dist_km"]).copy()
    if base.empty:
        return {
            "aggressive_min": None,
            "base_min": None,
            "conservative_min": None,
            "sample_size": 0,
        }

    base["proj_marathon_min"] = (base["Moving Time"] / 60.0) * ((42.195 / base["dist_km"]) ** 1.06)
    age_days = (end - base["Activity Date"].dt.normalize()).dt.days.clip(lower=0)
    recency_weight = np.exp(-age_days / 45.0)
    distance_weight = (base["dist_km"] / 10.0).clip(lower=0.5, upper=2.0)
    weights = (recency_weight * distance_weight).to_numpy()
    values = base["proj_marathon_min"].to_numpy()

    return {
        "aggressive_min": weighted_quantile(values, 0.2, weights),
        "base_min": weighted_quantile(values, 0.5, weights),
        "conservative_min": weighted_quantile(values, 0.8, weights),
        "sample_size": int(len(base)),
    }


def combined_fatigue_risk(football: pd.DataFrame, runs: pd.DataFrame, end: pd.Timestamp) -> dict[str, float | str | None]:
    if football.empty and runs.empty:
        return {
            "combined_acwr": None,
            "monotony_28d": None,
            "strain_7d": None,
            "spike_ratio_7d": None,
            "risk_score": None,
            "risk_level": "n/a",
        }

    run_daily = (
        runs.assign(day=runs["Activity Date"].dt.floor("D"))
        .assign(run_load=lambda d: d["dist_km"] * 10.0 + (d["Average Heart Rate"].fillna(145) - 140).clip(lower=0) * 0.5)
        .groupby("day", as_index=False)
        .agg(run_load=("run_load", "sum"))
    )

    fb = football.copy()
    fb["fb_load_calc"] = np.where(
        fb["Session Load"].notna() & (fb["Session Load"] > 0),
        fb["Session Load"],
        np.where(
            fb["Duration (mins)"].notna(),
            fb["Duration (mins)"] * 8.0,
            np.where(fb["Distance (m)"].notna(), fb["Distance (m)"] / 12.0, 450.0),
        ),
    )
    fb_daily = fb.assign(day=fb["Start Date"].dt.floor("D")).groupby("day", as_index=False).agg(fb_load=("fb_load_calc", "sum"))

    daily = run_daily.merge(fb_daily, on="day", how="outer").fillna(0.0).sort_values("day")
    if daily.empty:
        return {
            "combined_acwr": None,
            "monotony_28d": None,
            "strain_7d": None,
            "spike_ratio_7d": None,
            "risk_score": None,
            "risk_level": "n/a",
        }

    idx = pd.date_range(daily["day"].min(), end, freq="D")
    daily = daily.set_index("day").reindex(idx, fill_value=0.0).rename_axis("day").reset_index()
    daily["combined_load"] = daily["run_load"] + daily["fb_load"]

    acute = daily[daily["day"] > (end - pd.Timedelta(days=7))]["combined_load"]
    chronic = daily[daily["day"] > (end - pd.Timedelta(days=28))]["combined_load"]
    prev7 = daily[(daily["day"] > (end - pd.Timedelta(days=14))) & (daily["day"] <= (end - pd.Timedelta(days=7)))]["combined_load"]

    acwr = safe_ratio(float(acute.mean()) if len(acute) else None, float(chronic.mean()) if len(chronic) else None)
    monotony = None
    if len(chronic) >= 7 and chronic.std(ddof=0) > 0:
        monotony = float(chronic.mean() / chronic.std(ddof=0))
    strain = float(acute.sum()) * monotony if monotony is not None else None
    spike = safe_ratio(float(acute.sum()), float(prev7.sum()) if len(prev7) and prev7.sum() > 0 else None)

    score = 0.0
    if acwr is not None:
        if acwr > 1.3:
            score += min(35.0, (acwr - 1.3) * 80.0)
        elif acwr < 0.7:
            score += min(20.0, (0.7 - acwr) * 60.0)
    if monotony is not None and monotony > 2.0:
        score += min(25.0, (monotony - 2.0) * 20.0)
    if strain is not None and strain > 4500:
        score += min(20.0, (strain - 4500) / 100.0)
    if spike is not None and spike > 1.4:
        score += min(20.0, (spike - 1.4) * 40.0)
    score = float(min(100.0, score))

    if score < 25:
        level = "low"
    elif score < 50:
        level = "moderate"
    elif score < 75:
        level = "high"
    else:
        level = "very high"

    return {
        "combined_acwr": acwr,
        "monotony_28d": monotony,
        "strain_7d": strain,
        "spike_ratio_7d": spike,
        "risk_score": score,
        "risk_level": level,
    }


def build_october_goal_targets(weekly: pd.DataFrame, end: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, float | None]]:
    history = weekly[weekly["run_dist_km"].notna()].copy()
    if history.empty:
        return pd.DataFrame(), {"current_weekly_km": None, "oct_target_weekly_km": None, "gap_weekly_km": None}

    current_weekly = float(history["run_dist_km"].tail(4).mean())
    current_long = float(history["longest_run_km"].tail(4).max())
    oct_first = pd.Timestamp(year=end.year, month=10, day=1)
    next_sunday = (end + pd.offsets.Week(weekday=6)).normalize()
    target_weeks = pd.date_range(next_sunday, oct_first, freq="W-SUN")
    if len(target_weeks) == 0:
        return pd.DataFrame(), {"current_weekly_km": current_weekly, "oct_target_weekly_km": None, "gap_weekly_km": None}

    peak_weekly = float(np.clip(max(current_weekly * 1.7, 45.0), 35.0, 65.0))
    peak_long = float(np.clip(max(current_long * 1.8, 24.0), 18.0, 32.0))

    weekly_plan = []
    run_target = max(18.0, current_weekly)
    long_target = max(10.0, current_long)
    for i, wk in enumerate(target_weeks):
        if i > 0:
            if i % 4 == 0:
                run_target *= 0.88
                long_target *= 0.90
            else:
                run_target *= 1.06
                long_target *= 1.05
        run_target = min(run_target, peak_weekly)
        long_target = min(long_target, peak_long)
        weekly_plan.append(
            {
                "week": wk,
                "target_weekly_km_min": max(12.0, run_target * 0.9),
                "target_weekly_km_max": run_target * 1.1,
                "target_long_run_km_min": max(8.0, long_target - 2.0),
                "target_long_run_km_max": long_target + 2.0,
            }
        )

    targets = pd.DataFrame(weekly_plan)
    if not targets.empty:
        for col in [
            "target_weekly_km_min",
            "target_weekly_km_max",
            "target_long_run_km_min",
            "target_long_run_km_max",
        ]:
            targets[col] = targets[col].round(1)
    oct_target = float(targets["target_weekly_km_min"].iloc[-1] + targets["target_weekly_km_max"].iloc[-1]) / 2.0
    return targets, {
        "current_weekly_km": current_weekly,
        "oct_target_weekly_km": oct_target,
        "gap_weekly_km": oct_target - current_weekly,
    }


def format_hms(minutes: float) -> str:
    h = int(minutes // 60)
    m = int(minutes % 60)
    s = int((minutes - int(minutes)) * 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def ml_projection_to_october(
    weekly: pd.DataFrame,
) -> tuple[float | None, float | None, int | None, int]:
    run_df = weekly[weekly["run_dist_km"].notna()].copy()
    long_df = weekly[weekly["longest_run_km"].notna()].copy()
    if len(run_df) < 3:
        return None, None, None, len(run_df)

    run_df["x"] = np.arange(len(run_df))
    km_model = LinearRegression().fit(run_df[["x"]], run_df["run_dist_km"])

    today = pd.Timestamp.today().normalize()
    oct_first = pd.Timestamp(year=today.year, month=10, day=1)
    last_week = weekly["week"].max()
    weeks_to_oct = max(0, int((oct_first - last_week).days // 7))
    future_x_run = pd.DataFrame({"x": [len(run_df) - 1 + weeks_to_oct]})
    pred_weekly_km = float(km_model.predict(future_x_run)[0])

    pred_long = None
    if len(long_df) >= 3:
        long_df["x"] = np.arange(len(long_df))
        long_model = LinearRegression().fit(long_df[["x"]], long_df["longest_run_km"])
        future_x_long = pd.DataFrame({"x": [len(long_df) - 1 + weeks_to_oct]})
        pred_long = float(long_model.predict(future_x_long)[0])

    return pred_weekly_km, pred_long, weeks_to_oct, len(run_df)


def save_plots(
    weekly: pd.DataFrame,
    runs: pd.DataFrame,
    outdir: Path,
    targets: pd.DataFrame,
    bands: dict[str, float | int | None],
    plan_compare: pd.DataFrame,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(weekly["week"], weekly["run_dist_km"], marker="o", label="Weekly run km")
    ax1.plot(
        weekly["week"],
        weekly["longest_run_km"],
        marker="s",
        linestyle="--",
        label="Longest run (km)",
    )
    ax1.set_title("Running Volume Progression")
    ax1.set_xlabel("Week")
    ax1.set_ylabel("km")
    ax1.grid(alpha=0.3)
    ax1.legend()
    fig.tight_layout()
    fig.savefig(outdir / "running_progression.png", dpi=150)
    plt.close(fig)

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(runs["Activity Date"], runs["pace_min_km"], marker="o", linestyle="-", label="Pace (min/km)")
    ax1.invert_yaxis()
    ax1.set_title("Pace and Heart Rate Trend")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Pace (min/km)")
    ax1.grid(alpha=0.3)

    if runs["Average Heart Rate"].notna().any():
        ax2 = ax1.twinx()
        ax2.plot(
            runs["Activity Date"],
            runs["Average Heart Rate"],
            marker="x",
            linestyle="--",
            color="tab:red",
            label="Avg HR",
        )
        ax2.set_ylabel("Heart rate (bpm)")

    fig.tight_layout()
    fig.savefig(outdir / "pace_hr_trend.png", dpi=150)
    plt.close(fig)

    # Combined weekly stress proxy: run km vs football load (normalized).
    if not weekly.empty:
        plot_df = weekly.copy()
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(plot_df["week"], plot_df["run_dist_km"], marker="o", label="Run km")
        if plot_df["fb_load"].notna().any() and plot_df["fb_load"].max(skipna=True) > 0:
            fb_norm = plot_df["fb_load"] / plot_df["fb_load"].max(skipna=True) * max(
                1.0, plot_df["run_dist_km"].max(skipna=True)
            )
            ax.plot(plot_df["week"], fb_norm, marker="^", linestyle="--", label="Football load (scaled)")
        ax.set_title("Weekly Running vs Football Stress")
        ax.set_xlabel("Week")
        ax.set_ylabel("Relative load")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(outdir / "combined_stress_trend.png", dpi=150)
        plt.close(fig)

    # Marathon prediction history with uncertainty band.
    pred_df = runs[runs["dist_km"] >= 5].copy()
    if not pred_df.empty:
        pred_df["proj_marathon_min"] = (pred_df["Moving Time"] / 60.0) * ((42.195 / pred_df["dist_km"]) ** 1.06)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(pred_df["Activity Date"], pred_df["proj_marathon_min"], marker="o", label="Run-based projection")
        if bands["aggressive_min"] is not None and bands["conservative_min"] is not None:
            ax.axhspan(
                float(bands["aggressive_min"]),
                float(bands["conservative_min"]),
                alpha=0.2,
                color="tab:green",
                label="Likely band",
            )
        if bands["base_min"] is not None:
            ax.axhline(float(bands["base_min"]), linestyle="--", color="tab:blue", label="Base estimate")
        ax.set_title("Marathon Projection Uncertainty")
        ax.set_xlabel("Date")
        ax.set_ylabel("Projected marathon time (minutes)")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(outdir / "marathon_projection_band.png", dpi=150)
        plt.close(fig)

    # Goal gap dashboard to October with target range.
    if not targets.empty:
        actual = weekly[weekly["run_dist_km"].notna()].copy()
        fig, ax = plt.subplots(figsize=(11, 5))
        if not actual.empty:
            ax.plot(actual["week"], actual["run_dist_km"], marker="o", label="Actual weekly km")
        ax.plot(targets["week"], targets["target_weekly_km_min"], linestyle="--", color="tab:orange", label="Target min")
        ax.plot(targets["week"], targets["target_weekly_km_max"], linestyle="--", color="tab:red", label="Target max")
        ax.fill_between(
            targets["week"].to_numpy(),
            targets["target_weekly_km_min"].to_numpy(),
            targets["target_weekly_km_max"].to_numpy(),
            alpha=0.15,
            color="tab:orange",
        )
        ax.set_title("Goal Gap Dashboard (Weekly km to October)")
        ax.set_xlabel("Week")
        ax.set_ylabel("Weekly distance (km)")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(outdir / "goal_gap_dashboard.png", dpi=150)
        plt.close(fig)

    # Plan adherence dashboard.
    if not plan_compare.empty:
        fig, ax1 = plt.subplots(figsize=(11, 5))
        ax1.plot(plan_compare["week"], plan_compare["plan_run_km"], marker="s", linestyle="--", label="Plan run km")
        ax1.plot(plan_compare["week"], plan_compare["run_dist_km"], marker="o", label="Actual run km")
        ax1.set_xlabel("Week")
        ax1.set_ylabel("Weekly running km")
        ax1.set_title("Plan vs Actual Running Volume")
        ax1.grid(alpha=0.3)
        ax1.legend(loc="upper left")

        ax2 = ax1.twinx()
        ax2.plot(
            plan_compare["week"],
            plan_compare["run_adherence_pct"],
            marker="^",
            color="tab:green",
            label="Adherence %",
        )
        ax2.axhline(100.0, linestyle=":", color="tab:gray")
        ax2.set_ylabel("Adherence %")
        fig.tight_layout()
        fig.savefig(outdir / "plan_adherence_dashboard.png", dpi=150)
        plt.close(fig)


def build_report(
    football: pd.DataFrame,
    runs: pd.DataFrame,
    weekly: pd.DataFrame,
    targets: pd.DataFrame,
    plan_clean: pd.DataFrame,
    plan_compare: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    outdir: Path,
) -> str:
    training = football[football["Session Type"].eq("Training Session")]
    matches = football[football["Session Type"].eq("Match Session")]
    riegel = riegel_projection(runs)
    load = running_load_metrics(runs, end)
    race_pred = race_predictors_from_recent(runs)
    bands = marathon_prediction_bands(runs, end)
    fatigue = combined_fatigue_risk(football, runs, end)
    goal_summary = (
        {"current_weekly_km": None, "oct_target_weekly_km": None, "gap_weekly_km": None}
        if targets.empty
        else {
            "current_weekly_km": float(weekly["run_dist_km"].dropna().tail(4).mean()) if weekly["run_dist_km"].notna().any() else None,
            "oct_target_weekly_km": float((targets["target_weekly_km_min"].iloc[-1] + targets["target_weekly_km_max"].iloc[-1]) / 2.0),
            "gap_weekly_km": float(
                ((targets["target_weekly_km_min"].iloc[-1] + targets["target_weekly_km_max"].iloc[-1]) / 2.0)
                - (weekly["run_dist_km"].dropna().tail(4).mean() if weekly["run_dist_km"].notna().any() else 0.0)
            ),
        }
    )

    lines: list[str] = []
    lines.append("# Football + Strava Analytics")
    lines.append(f"Window (from February onward): {start.date()} -> {end.date()}")
    lines.append("")
    lines.append("## Highlights")
    lines.append(f"- Football whole sessions: {len(football)}")
    lines.append(f"- Running sessions: {len(runs)}")
    lines.append(f"- Total run distance: {runs['dist_km'].sum():.2f} km")
    lines.append(
        f"- Longest run: {runs['dist_km'].max():.2f} km"
        if not runs.empty
        else "- Longest run: n/a"
    )
    lines.append(
        f"- Average run pace: {runs['pace_min_km'].mean():.2f} min/km"
        if not runs.empty
        else "- Average run pace: n/a"
    )

    lines.append("")
    lines.append("## Football trends")
    lines.append(f"- Training sessions: {len(training)}")
    lines.append(f"- Match sessions: {len(matches)}")
    if not training.empty:
        lines.append(f"- Avg training load: {training['Session Load'].mean():.1f}")
        lines.append(f"- Avg training distance: {(training['Distance (m)'].mean()/1000):.2f} km")
        total_dist = training["Distance (m)"].sum()
        if pd.notna(total_dist) and total_dist > 0:
            hir_share = training["High Intensity Running (m)"].sum() / total_dist * 100
            lines.append(f"- HIR share in training: {hir_share:.1f}%")
    if not matches.empty:
        lines.append(f"- Best match top speed: {matches['Top Speed (kph)'].max():.1f} km/h")

    lines.append("")
    lines.append("## Running trends")
    slope_km = linear_trend(weekly["run_dist_km"])
    slope_pace = linear_trend(weekly["run_avg_pace"])
    slope_fb = linear_trend(weekly["fb_load"])
    lines.append(
        f"- Weekly run volume slope: {slope_km:.2f} km/week"
        if slope_km is not None
        else "- Weekly run volume slope: n/a"
    )
    lines.append(
        f"- Weekly pace slope: {slope_pace:.3f} min/km/week (negative = faster)"
        if slope_pace is not None
        else "- Weekly pace slope: n/a"
    )
    lines.append(
        f"- Weekly football load slope: {slope_fb:.1f}/week"
        if slope_fb is not None
        else "- Weekly football load slope: n/a"
    )
    if not weekly.empty and weekly["run_dist_km"].notna().sum() >= 3:
        cv = float(weekly["run_dist_km"].std(skipna=True) / weekly["run_dist_km"].mean(skipna=True))
        lines.append(f"- Run-volume consistency (CV): {cv:.2f} (lower is steadier)")
    if not weekly.empty and weekly["fb_load"].notna().sum() >= 3 and weekly["run_dist_km"].notna().sum() >= 3:
        pair = weekly[["fb_load", "run_dist_km"]].dropna()
        if len(pair) >= 3:
            corr = float(pair["fb_load"].corr(pair["run_dist_km"]))
            lines.append(f"- Football load vs run volume correlation: {corr:.2f}")

    lines.append("")
    lines.append("## Load balance / injury-risk style flags")
    lines.append(
        f"- Acute 7d running load: {load['acute_7d_km']:.1f} km"
        if load["acute_7d_km"] is not None
        else "- Acute 7d running load: n/a"
    )
    lines.append(
        f"- Chronic 28d running load: {load['chronic_28d_km']:.1f} km"
        if load["chronic_28d_km"] is not None
        else "- Chronic 28d running load: n/a"
    )
    lines.append(
        f"- ACWR (7d avg / 28d avg): {load['acwr']:.2f}"
        if load["acwr"] is not None
        else "- ACWR (7d avg / 28d avg): n/a"
    )
    lines.append(
        f"- 14d ramp ratio (last14 / prev14): {load['ramp_ratio_14d']:.2f}"
        if load["ramp_ratio_14d"] is not None
        else "- 14d ramp ratio (last14 / prev14): n/a"
    )
    if load["acwr"] is not None:
        if load["acwr"] > 1.5:
            lines.append("- Risk flag: acute load spike detected (>1.5 ACWR).")
        elif load["acwr"] < 0.8:
            lines.append("- Risk flag: detraining signal (ACWR < 0.8).")
        else:
            lines.append("- ACWR appears in a moderate range.")

    lines.append("")
    lines.append("## Combined fatigue-risk model (football + running)")
    lines.append(
        f"- Combined ACWR: {fatigue['combined_acwr']:.2f}"
        if fatigue["combined_acwr"] is not None
        else "- Combined ACWR: n/a"
    )
    lines.append(
        f"- Monotony (28d): {fatigue['monotony_28d']:.2f}"
        if fatigue["monotony_28d"] is not None
        else "- Monotony (28d): n/a"
    )
    lines.append(
        f"- Strain (7d): {fatigue['strain_7d']:.0f}"
        if fatigue["strain_7d"] is not None
        else "- Strain (7d): n/a"
    )
    lines.append(
        f"- 7d spike ratio vs previous 7d: {fatigue['spike_ratio_7d']:.2f}"
        if fatigue["spike_ratio_7d"] is not None
        else "- 7d spike ratio vs previous 7d: n/a"
    )
    lines.append(
        f"- Combined risk score: {fatigue['risk_score']:.1f}/100 ({fatigue['risk_level']})"
        if fatigue["risk_score"] is not None
        else "- Combined risk score: n/a"
    )

    lines.append("")
    lines.append("## Session patterns")
    if not runs.empty:
        weekday_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        wd = runs.assign(wd=runs["Activity Date"].dt.dayofweek).groupby("wd").size().to_dict()
        wd_text = ", ".join(f"{weekday_map[d]} {int(wd.get(d, 0))}" for d in range(7))
        lines.append(f"- Runs by weekday: {wd_text}")
        if runs["Average Heart Rate"].notna().sum() >= 3:
            runs_hr = runs.dropna(subset=["Average Heart Rate", "pace_min_km"]).copy()
            if not runs_hr.empty:
                runs_hr["speed_kmh"] = 60.0 / runs_hr["pace_min_km"]
                runs_hr["efficiency"] = runs_hr["speed_kmh"] / runs_hr["Average Heart Rate"]
                lines.append(f"- Aerobic efficiency (speed/HR) avg: {runs_hr['efficiency'].mean():.4f}")
                eff_trend = linear_trend(runs_hr["efficiency"])
                if eff_trend is not None:
                    lines.append(f"- Aerobic efficiency trend: {eff_trend:.5f} per run")

    lines.append("")
    lines.append("## Predictors (October marathon)")
    if riegel is not None:
        mm = float(riegel["marathon_min"])
        h = int(mm // 60)
        m = int(mm % 60)
        s = int((mm - int(mm)) * 60)
        lines.append(
            f"- Riegel estimate: {h:02d}:{m:02d}:{s:02d} "
            f"(from {riegel['dist_km']:.2f} km on {riegel['Activity Date'].date()})"
        )
    else:
        lines.append("- Riegel estimate: n/a (need at least one run >= 7 km)")

    pred_weekly_km, pred_long_km, weeks_to_oct, run_weeks = ml_projection_to_october(weekly)
    lines.append(
        f"- ML projected weekly volume by Oct 1: {pred_weekly_km:.1f} km/week"
        if pred_weekly_km is not None
        else "- ML projected weekly volume by Oct 1: n/a"
    )
    lines.append(
        f"- ML projected long run by Oct 1: {pred_long_km:.1f} km"
        if pred_long_km is not None
        else "- ML projected long run by Oct 1: n/a"
    )
    if pred_weekly_km is not None and pred_weekly_km > 120:
        lines.append("- ML weekly-volume projection is likely overstated (simple linear extrapolation).")
    if pred_long_km is not None and pred_long_km > 45:
        lines.append("- ML long-run projection is unrealistic; treat it as trend direction only.")
    if weeks_to_oct is not None and run_weeks < 8:
        lines.append("- Projection confidence is low because the running history window is short.")
    if bands["base_min"] is not None:
        lines.append(
            "- Marathon uncertainty band: "
            f"aggressive {format_hms(float(bands['aggressive_min']))}, "
            f"base {format_hms(float(bands['base_min']))}, "
            f"conservative {format_hms(float(bands['conservative_min']))} "
            f"(n={int(bands['sample_size'])} runs >= 5km)"
        )
    if race_pred["5k_min"] is not None:
        lines.append(f"- Predicted 5k: {format_hms(float(race_pred['5k_min']))}")
        lines.append(f"- Predicted 10k: {format_hms(float(race_pred['10k_min']))}")
        lines.append(f"- Predicted half marathon: {format_hms(float(race_pred['hm_min']))}")
        lines.append(f"- Predicted marathon: {format_hms(float(race_pred['marathon_min']))}")

    lines.append("")
    lines.append("## Goal-gap dashboard to October")
    lines.append(
        f"- Current weekly baseline (last 4 weeks): {goal_summary['current_weekly_km']:.1f} km"
        if goal_summary["current_weekly_km"] is not None
        else "- Current weekly baseline (last 4 weeks): n/a"
    )
    lines.append(
        f"- Target weekly volume near Oct: {goal_summary['oct_target_weekly_km']:.1f} km"
        if goal_summary["oct_target_weekly_km"] is not None
        else "- Target weekly volume near Oct: n/a"
    )
    lines.append(
        f"- Weekly km gap to close: {goal_summary['gap_weekly_km']:.1f} km"
        if goal_summary["gap_weekly_km"] is not None
        else "- Weekly km gap to close: n/a"
    )
    if not targets.empty:
        n_preview = min(4, len(targets))
        lines.append("- Next target weeks:")
        for i in range(n_preview):
            row = targets.iloc[i]
            lines.append(
                f"  - {row['week'].date()}: {row['target_weekly_km_min']:.1f}-{row['target_weekly_km_max']:.1f} km, "
                f"long run {row['target_long_run_km_min']:.1f}-{row['target_long_run_km_max']:.1f} km"
            )

    lines.append("")
    lines.append("## Plan de entrenamiento (limpieza y adherencia)")
    if not plan_clean.empty:
        lines.append(f"- Sesiones del plan limpiadas: {len(plan_clean)}")
        lines.append("- Archivo limpio diario: plan_limpio_sesiones.csv")
        lines.append("- Archivo limpio semanal: plan_limpio_semanal.csv")
        if not plan_compare.empty:
            comp_hist = plan_compare[plan_compare["week"] <= end.normalize()].copy()
            if not comp_hist.empty and comp_hist["run_adherence_pct"].notna().any():
                adherence_mean = float(comp_hist["run_adherence_pct"].dropna().mean())
                gap_mean = float(comp_hist["run_km_gap"].mean())
                lines.append(f"- Adherencia media de running: {adherence_mean:.1f}%")
                lines.append(f"- Gap medio semanal (real - plan): {gap_mean:.1f} km")
            if not comp_hist.empty:
                done = int((comp_hist["run_dist_km"] > 0).sum())
                lines.append(f"- Semanas con ejecución real detectada: {done}/{len(comp_hist)}")
            else:
                lines.append("- Aún no hay solape temporal suficiente entre plan y datos reales para medir adherencia.")
    else:
        lines.append("- No se pudo leer/limpiar el plan. Revisa el CSV de plan.")

    lines.append("")
    lines.append("## Practical takeaways")
    if not runs.empty and runs["dist_km"].max() < 14:
        lines.append("- Long run is currently short for marathon prep; progress gradually each week.")
    if weekly["run_dist_km"].notna().any() and weekly["run_dist_km"].tail(4).mean() < 25:
        lines.append("- Recent weekly mileage is modest; build aerobic volume steadily.")
    if slope_pace is not None and slope_pace < 0:
        lines.append("- Pace trend is improving; good sign if injury-free.")
    if slope_km is not None and slope_km > 0:
        lines.append("- Weekly volume trend is increasing; keep increments controlled.")

    lines.append("")
    lines.append("## Files generated")
    lines.append("- report.md")
    lines.append("- weekly_metrics.csv")
    lines.append("- running_progression.png")
    lines.append("- pace_hr_trend.png")
    lines.append("- combined_stress_trend.png")
    lines.append("- marathon_projection_band.png")
    lines.append("- goal_gap_dashboard.png")
    lines.append("- target_ranges_to_october.csv")
    if not plan_clean.empty:
        lines.append("- plan_limpio_sesiones.csv")
        lines.append("- plan_limpio_semanal.csv")
        lines.append("- plan_vs_actual.csv")
        lines.append("- plan_adherence_dashboard.png")

    report = "\n".join(lines)
    (outdir / "report.md").write_text(report, encoding="utf-8")
    weekly.to_csv(outdir / "weekly_metrics.csv", index=False)
    if not plan_compare.empty:
        plan_compare.to_csv(outdir / "plan_vs_actual.csv", index=False)
    if not targets.empty:
        targets.to_csv(outdir / "target_ranges_to_october.csv", index=False)
    return report


def main() -> None:
    args = parse_args()
    football_path = Path(args.football)
    strava_path = Path(args.strava)
    plan_path = Path(args.plan)
    outdir = Path(args.outdir)

    if not football_path.exists():
        raise FileNotFoundError(f"Football CSV not found: {football_path}")
    if not strava_path.exists():
        raise FileNotFoundError(f"Strava CSV not found: {strava_path}")

    today = pd.Timestamp.today().normalize()
    # Default window is explicitly February onward of the current year.
    start = pd.Timestamp(args.start) if args.start else pd.Timestamp(year=today.year, month=2, day=1)
    end = pd.Timestamp(args.end) if args.end else today

    football = prep_football(football_path, start, end)
    runs = prep_runs(strava_path, start, end)
    weekly = aggregate_weekly(football, runs)
    plan_clean, weekly_plan = clean_training_plan(plan_path, outdir)
    plan_compare = plan_vs_actual_weekly(weekly, weekly_plan)
    targets, _ = build_october_goal_targets(weekly, end)
    bands = marathon_prediction_bands(runs, end)

    outdir.mkdir(parents=True, exist_ok=True)
    save_plots(weekly, runs, outdir, targets, bands, plan_compare)
    _ = build_report(football, runs, weekly, targets, plan_clean, plan_compare, start, end, outdir)

    print("Analysis complete.")
    print(f"Output folder: {outdir.resolve()}")
    print("Open analysis_output/report.md to read insights.")


if __name__ == "__main__":
    main()
