# Football + Strava Analytics
Window (from February onward): 2026-02-01 -> 2026-04-01

## Highlights
- Football whole sessions: 19
- Running sessions: 9
- Total run distance: 54.66 km
- Longest run: 11.50 km
- Average run pace: 4.91 min/km

## Football trends
- Training sessions: 12
- Match sessions: 7
- Avg training load: 1302.2
- Avg training distance: 8.25 km
- HIR share in training: 2.2%
- Best match top speed: 29.9 km/h

## Running trends
- Weekly run volume slope: 2.50 km/week
- Weekly pace slope: 0.246 min/km/week (negative = faster)
- Weekly football load slope: 258.5/week
- Run-volume consistency (CV): 0.67 (lower is steadier)
- Football load vs run volume correlation: 0.90

## Load balance / injury-risk style flags
- Acute 7d running load: 0.0 km
- Chronic 28d running load: 52.5 km
- ACWR (7d avg / 28d avg): 0.00
- 14d ramp ratio (last14 / prev14): 0.19
- Risk flag: detraining signal (ACWR < 0.8).

## Combined fatigue-risk model (football + running)
- Combined ACWR: 0.13
- Monotony (28d): 0.71
- Strain (7d): 281
- 7d spike ratio vs previous 7d: 0.09
- Combined risk score: 20.0/100 (low)

## Session patterns
- Runs by weekday: Mon 3, Tue 0, Wed 2, Thu 0, Fri 1, Sat 1, Sun 2
- Aerobic efficiency (speed/HR) avg: 0.0784
- Aerobic efficiency trend: -0.00002 per run

## Predictors (October marathon)
- Riegel estimate: 03:44:39 (from 7.04 km on 2026-03-06)
- ML projected weekly volume by Oct 1: 81.0 km/week
- ML projected long run by Oct 1: 57.5 km
- ML long-run projection is unrealistic; treat it as trend direction only.
- Projection confidence is low because the running history window is short.
- Marathon uncertainty band: aggressive 03:45:01, base 03:58:13, conservative 04:10:30 (n=6 runs >= 5km)
- Predicted 5k: 23:25
- Predicted 10k: 48:50
- Predicted half marathon: 01:47:44
- Predicted marathon: 03:44:39

## Goal-gap dashboard to October
- Current weekly baseline (last 4 weeks): 13.1 km
- Target weekly volume near Oct: 25.3 km
- Weekly km gap to close: 12.2 km
- Next target weeks:
  - 2026-04-05: 16.2-19.8 km, long run 9.5-13.5 km
  - 2026-04-12: 17.2-21.0 km, long run 10.1-14.1 km
  - 2026-04-19: 18.2-22.2 km, long run 10.7-14.7 km
  - 2026-04-26: 19.3-23.6 km, long run 11.3-15.3 km

## Plan de entrenamiento (limpieza y adherencia)
- Sesiones del plan limpiadas: 196
- Archivo limpio diario: plan_limpio_sesiones.csv
- Archivo limpio semanal: plan_limpio_semanal.csv
- Aún no hay solape temporal suficiente entre plan y datos reales para medir adherencia.

## Practical takeaways
- Long run is currently short for marathon prep; progress gradually each week.
- Recent weekly mileage is modest; build aerobic volume steadily.
- Weekly volume trend is increasing; keep increments controlled.

## Files generated
- report.md
- report.html
- weekly_metrics.csv
- running_progression.png
- pace_hr_trend.png
- combined_stress_trend.png
- marathon_projection_band.png
- goal_gap_dashboard.png
- target_ranges_to_october.csv
- plan_limpio_sesiones.csv
- plan_limpio_semanal.csv
- plan_vs_actual.csv
- plan_adherence_dashboard.png