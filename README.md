# Horse Racing Formula

A quantitative handicapping toolkit for Hong Kong horse racing (HKJC). The project scrapes race cards, past performance data, and live parimutuel pools, then turns them into speed-figure rankings and money-flow signals to support wagering decisions at Sha Tin (ST) and Happy Valley (HV).

## What It Does So Far

### 1. Past Performance Scraper & Speed Figures (`main.py`)

For a given race day, the script:

- Fetches the race card for every race from `racing.hkjc.com` and pulls each runner's full match history from its horse home page.
- Scrapes per-race sectional times and pace data, including the winning trio and the horse's final-section time.
- Benchmarks every past run against class/course/distance/track **standard times** (`data/standard_time.csv`), producing comparison metrics such as:
  - 比標準時間 — finish time vs. standard time
  - 比標準頭段 / 比標準末段 — early-pace and final-section splits vs. standard
  - 前段位置 — early running position (pace style)
- Writes one history CSV per horse under `data/<racedate>/<raceno>/`, then aggregates each race (filtered to recent runs at the same course/track/distance) into four ranking tables under `data/<racedate>/final/`:
  - **Fastest** — best raw finish times
  - **Average** — mean finish time over recent comparable runs
  - **Standard Diff** — average margin vs. standard time
  - **Pace** — median early position
- Prints a race-day summary table highlighting the top picks from each ranking and the horses that overlap across all three.

Scraping is async (`aiohttp` + BeautifulSoup), so a full card processes in a few minutes.

### 2. Live Odds & Money Flow Monitor (`odds.py`)

A Selenium-based monitor for `bet.hkjc.com` that runs in two modes:

- **Overnight** — one-off snapshot of opening win/place odds for every race.
- **Live** — runs through the whole meeting, snapshotting each race on a tiered schedule (every 15 minutes from 30 minutes out, every 10 minutes inside 10 minutes, plus a final snapshot 30 seconds after the scheduled off time).

Each snapshot records win/place odds and pool sizes, converts odds into implied dollar amounts per horse (net of the 17.5% takeout), and computes deltas against the previous snapshot:

- Odds movement (win, place, and their average)
- Dollar inflow per horse per window
- **Disproportionate flow detection** — compares each horse's share of *new* money in the window against its prior share of the pool. A horse capturing late money at ≥1.4× its prior share (configurable thresholds) gets flagged as a potential smart-money move.

Results are saved to `output/<mode>_odds/<date>/` and pushed as **Telegram alerts**, including flagged horses with their flow ratios and the top movers by odds change.

## Project Layout

```
main.py                  # Race card + past performance scraper, speed-figure rankings
odds.py                  # Live/overnight odds scraper + money flow detector
data/
  standard_time.csv      # Class/course/distance/track standard times
  <racedate>/            # Per-meeting horse histories and final rankings
output/
  live_odds/             # Live snapshot CSVs per race
  overnight_odds/        # Opening odds CSVs per race
source/                  # Reference material (HKJC standard/sectional times)
```

## Usage

Requires Python ≥ 3.13 (managed with `uv`) and Chrome (for Selenium). Telegram alerts need `TELEGRAM_API_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.

```bash
# Build past-performance data and rankings for a race day
uv run main.py    # prompts for date, racecourse (ST/HV), number of races

# Monitor odds and money flow
uv run odds.py    # prompts for date, racecourse, number of races, mode (live/overnight)
```

## Roadmap

The current rankings are heuristic. The next stage is to evolve this project into a **multinomial logit model** that estimates each horse's *true* winning probability from race-level features (speed figures, pace profile, draw, weight, jockey/trainer effects, and more).

Model probabilities will be compared against parimutuel odds to identify **positive expected value** wagering opportunities — races where the public's implied probabilities diverge from the model's estimates by more than the takeout.

The existing money-flow detector will mature into a **real-time smart money flow monitor**, feeding late-money signals alongside model output into the final wagering decision.

Planned milestones:

1. **Database & pipeline** — consolidate scraped histories into a proper schema (races, results, horses, jockeys, trainers) with a DuckDB + Parquet pipeline.
2. **Feature engineering** — horse-, jockey-, trainer-level and interaction features (e.g. recency-weighted normalized finishing positions).
3. **Multinomial logit model** — train on historical races to output calibrated win probabilities per runner.
4. **Backtesting & calibration** — validate probability calibration and EV edge on out-of-sample meetings.
5. **Smart money integration** — calibrate flow-detection thresholds on historical pool data and run the monitor in real time on race days.
6. **Wagering strategy** — a decision framework combining model EV and money-flow signals, extending to exotic wagers.
