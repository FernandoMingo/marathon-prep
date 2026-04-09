# Update the existing marathon + football webapp analysis and UI

I already have a working webapp. Do **not** rebuild the project from scratch.

Your task is to **modify the existing analysis script and the existing HTML/JavaScript UI** so the app supports a new **plan-aware hybrid marathon analysis model**.

## Important constraints

- The webapp already exists
- The Strava/Garmin running ingestion already exists and updates every 2 days
- The football CSV import already exists or partially exists
- The UI already exists
- I do **not** want a greenfield redesign
- I want targeted, maintainable changes to the current codebase
- Reuse existing structure, components, styles, and file organization where possible
- Keep the current app working while extending it

Your job is to:
1. inspect the current codebase
2. understand the current data flow
3. update the analysis logic
4. update the HTML/JS to surface the new analysis
5. preserve backward compatibility as much as possible

---

## Product context

I am training for a marathon while also playing football at an intense level.

### My training reality
- football training: **2x per week**
- football match: **Sunday**
- usually **not a starter**
- running: **2–3x per week**
- summer: **no football**, only running
- I also have a **training plan CSV**

### Data reality
#### Running
- pulled automatically from Strava/Garmin every 2 days
- this is the most up-to-date data source
- should power recurring analysis

#### Football
- comes from PlayerData GPS CSV
- only available occasionally, maybe monthly
- recent football data will often be missing
- analysis must remain useful when football is missing
- when football CSV arrives later, historical weeks should be backfilled with actuals

#### Plan
- I have a CSV training plan
- it contains the intended weekly progression and hybrid structure
- this should become a first-class input in the analysis

---

## Main objective

Transform the current analysis from a simple activity summary into a **plan-aware hybrid training analysis system**.

The app should answer questions like:
- Am I following the marathon plan?
- Is football interfering with key running sessions?
- Am I building marathon readiness?
- What is my current fatigue/readiness?
- How confident are these conclusions if football data is missing?

---

# What to change

## 1. Update the analysis layer

Modify the current analysis script so it supports:

### A. Plan-aware analysis
The script should no longer only summarize completed activities.

It should compare:
- planned
- completed
- adjusted
- missed

At minimum, compute for each week:
- planned running km
- actual running km
- planned number of runs
- actual number of runs
- planned long run distance
- actual long run distance
- planned key/quality session
- actual key/quality session completed
- expected football week: yes/no
- football actual available: yes/no
- football estimated: yes/no

### B. Hybrid training logic
Running and football must be treated as different stressors.

Do **not** just combine them as mileage.

Keep separate concepts for:
- running volume
- football load
- combined normalized load

### C. Missing-football logic
The analysis must support 3 modes:

#### Mode 1: running-only / always-on
Use:
- running data
- plan data

This should still produce useful recurring analysis.

#### Mode 2: hybrid actual
Use:
- running data
- plan data
- actual football data

#### Mode 3: hybrid estimated
When football data is missing, estimate football exposure using:
- expected football schedule from the plan or known routine
- historical averages from prior football data
- optional simple heuristics

Do **not** fabricate precise football metrics when they are unavailable.

Allowed estimated football outputs:
- expected football session count
- expected football minutes
- football load bucket (`low`, `normal`, `high`)
- match exposure approximation

Do **not** estimate with fake precision:
- sprint distance
- HIR distance
- accelerations
- decelerations
- exact session load

Those must remain:
- actual
- estimated
- unknown
- historical average

### D. Backfill logic
When a new football CSV is loaded:
- replace prior football estimates with actuals where applicable
- recompute hybrid load
- recompute fatigue/readiness
- recompute interference analysis
- optionally expose that earlier estimates were updated

---

## 2. Build these analyses into the existing script

### A. Weekly plan compliance
Add logic for:
- weekly compliance score
- long run completion
- quality session completion
- run frequency completion
- under-completed / over-completed weeks
- correctly adjusted weeks due to fatigue or match load if this can be inferred

### B. Running progression
Add recurring metrics such as:
- rolling 7-day running km
- rolling 28-day running km
- run frequency in last 7 / 14 / 28 days
- long run progression
- longest run in last 4 / 8 weeks
- easy pace trend
- pace at similar HR
- pace/HR efficiency trend
- consistency score

### C. Football load
When actual football data exists, calculate:
- weekly football minutes
- football session load
- training vs match split
- HIR distance
- sprint distance
- sprints
- top speed
- accelerations
- decelerations
- metres per minute

### D. Football interference
When enough football data exists, calculate:
- next-day run quality after football training vs match
- 24h / 48h / 72h lag effects
- whether high football load harms next run pace/HR
- whether match exposure affects long run quality

### E. Durability
Add marathon-durability metrics:
- consecutive weeks with 2+ runs
- consecutive weeks with long run completed
- long-run progression slope
- percentage of planned volume absorbed
- percentage of planned long runs completed
- weeks where football likely forced a downscale

---

## 3. Add prediction logic to the analysis script

Predictions should be useful in a recurring way.

### A. Next-week completion prediction
Estimate:
- probability of completing next week’s planned running volume
- probability of completing the next long run
- probability of completing the next quality session
- probability of needing to downscale

Use:
- recent run consistency
- recent load
- long-run history
- recent football actual or estimated
- plan phase
- data completeness

### B. Readiness prediction
Produce structured outputs for:
- aerobic fitness status: `improving`, `stable`, `declining`
- durability status: `insufficient`, `building`, `strong`, `race-ready`
- fatigue status: `low`, `medium`, `high`
- marathon readiness: `low`, `moderate`, `strong`

### C. Marathon prediction
Produce:
- fitness-based marathon estimate
- durability-adjusted marathon estimate
- realistic range
- confidence score

This should account for:
- recent race/workout evidence if present
- long-run development
- consistency
- football load
- missing football data penalties

Do **not** output a single overconfident number.

### D. Pace recommendations
Add weekly recommended pace bands for:
- easy
- steady
- marathon pace
- threshold

These should adapt based on:
- recent running
- fatigue
- plan phase
- football interference
- recent consistency

### E. Confidence layer
Every prediction should include:
- confidence score
- explanation
- explicit degradation when football data is stale or missing

Example:
- “Confidence reduced because football actuals are missing for the last 24 days.”

---

## 4. Update the frontend HTML/JavaScript

Do not rebuild the UI from scratch.

Modify the current HTML/JS to reflect the new analysis.

Reuse the existing layout/components where possible.

### Add or update these views/cards/sections

## A. This Week
Show:
- current plan week
- current phase
- planned sessions this week
- completed sessions this week
- running km vs target
- long run status
- football status: `actual`, `estimated`, or `missing`
- next key-session readiness
- key warnings / insights

## B. Marathon Build
Show:
- weekly planned vs actual running km
- long run progression
- quality session completion
- rolling 4-week and 8-week running volume
- compliance trend
- phase progression

## C. Load & Fatigue
Show:
- running load
- football load actual/estimated
- combined normalized load
- acute vs chronic load if implemented
- fatigue flags
- data confidence

## D. Football Impact
When enough football data exists, show:
- training vs match load
- HIR trend
- sprint trend
- acceleration/deceleration trend
- next-day / 48h run impact

If football data is missing or stale, show a graceful fallback message rather than a broken panel.

## E. Predictions
Show:
- current readiness
- next-week completion probabilities
- long-run completion probability
- marathon prediction range
- pace recommendations
- confidence explanations

---

## 5. UI behavior requirements

### A. Distinguish actual vs estimated vs unknown
The frontend must clearly label values as:
- actual
- estimated
- unknown

Do not visually present estimates as measured values.

### B. Prioritize interpretation
The app should not just show charts.

It should also surface useful text such as:
- “You are on plan this week.”
- “Long run progression is lagging behind plan.”
- “Football load is estimated because recent PlayerData is unavailable.”
- “Prediction confidence is reduced due to stale football data.”
- “Your current readiness is moderate: aerobic fitness is improving, but durability is still building.”

### C. Use ranges and confidence
Where appropriate, show:
- probability
- confidence
- ranges
instead of fake precision

### D. Summer logic
During summer / no-football phases:
- football should be ignored or suppressed where appropriate
- running-only readiness becomes primary
- UI should not imply missing football is a problem if football is not expected in that phase

---

## 6. Data/model requirements

## Unified session model
Refactor or extend the current analysis pipeline so it produces a normalized session model, ideally one row/object per session with fields such as:
- date
- sport
- subtype
- planned vs unplanned
- duration
- distance
- pace
- avg_hr
- relative_effort
- football_session_load
- HIR
- sprint_distance
- accelerations
- decelerations
- source
- data_confidence

## Derived scores
Implement and expose the following:

### Plan Compliance Score
Based on:
- planned vs actual run volume
- long run completion
- quality session completion
- frequency completion
- appropriate adjustment logic where possible

### Marathon Readiness Score
Based on:
- consistency
- long-run development
- marathon-specific work
- durability
- fatigue

### Hybrid Fatigue Score
Based on:
- running load
- football load actual or estimated
- density of hard sessions
- lag effects if measurable

### Prediction Confidence Score
Based on:
- data completeness
- recency of football data
- quantity of recent running data
- amount of estimated vs actual data
- phase relevance

---

## 7. Cleaning and matching requirements

### Running data
Keep or improve current cleaning logic to:
- keep relevant running sessions
- identify long runs and workouts if possible
- handle missing HR
- handle bad fragments or accidental short sessions
- normalize dates

### Football data
Improve current cleaning logic to:
- avoid double counting segment rows
- prefer the row representing the full session
- separate training vs match if possible
- ignore broken/empty rows
- keep actual vs estimated clearly separated

### Plan data
Parse the plan CSV so it can support:
- current week identification
- current phase
- weekly targets
- long-run targets
- key session targets
- adaptation logic if inferable

### Session matching
Implement practical matching between:
- planned session and actual session
- plan week and actual week
- long run target and completed long run
- quality target and actual quality-like run

Use robust heuristics rather than brittle exact matching.

---

## 8. Implementation approach

Please work in this order:

1. inspect the current codebase and identify:
   - current analysis script(s)
   - current HTML/JS files
   - current data flow
   - existing computed metrics
2. propose a targeted refactor plan
3. implement the backend analysis changes
4. wire the new outputs into the frontend
5. preserve existing functionality where possible
6. add clear comments where logic is non-obvious

Do not introduce unnecessary new frameworks.

Prefer minimal, maintainable modifications over broad rewrites.

---

## 9. Deliverables

I want you to produce:

1. Updated analysis logic in the existing script(s)
2. Updated HTML/JavaScript to display the new analysis
3. Any required helper functions/utilities
4. Clear comments for new logic
5. A short summary of:
   - what changed
   - which files changed
   - any assumptions made
   - any remaining limitations

---

## 10. Acceptance criteria

The work is successful if:

- the app still runs
- running-only analysis works even without recent football data
- football-aware analysis improves when football CSV is present
- plan vs actual tracking is visible
- readiness/fatigue/prediction outputs exist
- the UI clearly distinguishes actual vs estimated vs unknown
- the app handles summer running-only periods correctly
- the changes are integrated into the current codebase rather than replacing it

Please start by inspecting the existing project structure and identifying exactly which files should be updated before making code changes.