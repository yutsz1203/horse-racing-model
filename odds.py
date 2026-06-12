import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import selenium
from dotenv import load_dotenv
from rich import console, print
from rich.progress import track
from rich.prompt import IntPrompt, Prompt
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()
TOKEN = os.getenv("TELEGRAM_API_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

con = console.Console()


def safe_get(driver, url, locator, timeout=20):
    driver.get(url)
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))


# --- Disproportionate flow detection thresholds ---
# Starting guesses. Calibrate against historical data once you have enough.
# All values in HK$.
WIN_POOL_MIN = 0  # Minimum total win pool to trust the signal
PLACE_POOL_MIN = 0  # Minimum total place pool
HORSE_INFLOW_MIN = 0  # Minimum dollar inflow per horse per window
FLOW_RATIO_MIN = 1.4  # Horse must capture late money at >=1.5x its prior share


def process_odds(
    url: str,
    driver: WebDriver,
    wait: WebDriverWait,
    raceno: str,
    date: str,
    fetch_type: str,
) -> datetime | None:

    win_pool = safe_get(driver, url, (By.ID, "poolInvWIN"))

    if fetch_type == "live":
        raceno = driver.current_url.split("/")[-1]

    _wait_for_odds_loaded(driver, raceno)

    while True:
        try:
            win_pool = float(win_pool.text.split()[2].replace(",", ""))
            break
        except ValueError as e:
            print(e)

    place_pool = float(
        driver.find_element(By.ID, "poolInvPLA").text.split()[2].replace(",", "")
    )

    print(f"As at: {datetime.now().strftime('%H:%M')}")
    print(f"Win pool investment: {win_pool}")
    print(f"Place pool investment: {place_pool}")

    csv_path = f"output/{fetch_type}_odds/{date}/{fetch_type}_{raceno}.csv"

    if Path(csv_path).exists():

        df = pd.read_csv(csv_path)
        df.sort_values(by="horse_no", inplace=True)

        prev_win_pool = (
            float(df["win_pool"].iloc[0]) if "win_pool" in df.columns else None
        )
        prev_place_pool = (
            float(df["place_pool"].iloc[0]) if "place_pool" in df.columns else None
        )

        win_odds, place_odds, win_amounts, place_amounts, drop_horses = (
            [],
            [],
            [],
            [],
            [],
        )
        for j in range(1, 15):
            try:
                while True:
                    try:
                        horse_name = driver.find_element(
                            By.ID, f"horseName_{raceno}_{j}"
                        ).text
                        break
                    except ValueError as e:
                        print(e)

                while True:
                    win_odd_text = driver.find_element(
                        By.ID, f"odds_WIN_{raceno}_{j}"
                    ).text
                    if win_odd_text != "":
                        break
                if win_odd_text == "退出":
                    drop_horses.append(j)
                    continue

                win_odd = float(win_odd_text)
                place_odd = float(
                    driver.find_element(By.ID, f"odds_PLA_{raceno}_{j}").text
                )
                win_odds.append(win_odd)
                place_odds.append(place_odd)
                win_amounts.append(round(0.825 * (1 / win_odd) * win_pool, 2))
                place_amounts.append(round(0.825 * (1 / place_odd) * place_pool, 2))

            except selenium.common.exceptions.NoSuchElementException:
                break

        if len(df) != len(win_odds):
            df = df[~df["horse_no"].isin(drop_horses)]

        df["prev_win_odds"] = df["win_odds"]
        df["prev_place_odds"] = df["place_odds"]
        df["prev_win_amount"] = df["win_amount"]
        df["prev_place_amount"] = df["place_amount"]

        df["win_odds"] = win_odds
        df["place_odds"] = place_odds
        df["win_amount"] = win_amounts
        df["place_amount"] = place_amounts

        df["win_amount_increase"] = df["win_amount"] - df["prev_win_amount"]
        df["place_amount_increase"] = df["place_amount"] - df["prev_place_amount"]

        df["win_odds_change"] = (df["win_odds"] - df["prev_win_odds"]) / df[
            "prev_win_odds"
        ]
        df["place_odds_change"] = (df["place_odds"] - df["prev_place_odds"]) / df[
            "prev_place_odds"
        ]

        df["average_odds_change"] = (
            df["win_odds_change"] + df["place_odds_change"]
        ) / 2

        # ===== DISPROPORTIONATE FLOW DETECTION =====
        if prev_win_pool is not None and prev_place_pool is not None:
            new_win_money = win_pool - prev_win_pool
            new_place_money = place_pool - prev_place_pool

            # Each horse's share of the pool BEFORE this window
            df["win_prior_share"] = df["prev_win_amount"] / prev_win_pool
            df["place_prior_share"] = df["prev_place_amount"] / prev_place_pool

            # Each horse's share of NEW money flowing in during this window
            if new_win_money > 0:
                df["win_late_share"] = df["win_amount_increase"] / new_win_money
            else:
                df["win_late_share"] = 0.0
            if new_place_money > 0:
                df["place_late_share"] = df["place_amount_increase"] / new_place_money
            else:
                df["place_late_share"] = 0.0

            # Flow ratio: how disproportionate the late inflow is vs prior share.
            # Ratio > 1 means horse is attracting late money faster than its
            # existing position would predict.
            df["win_flow_ratio"] = df["win_late_share"] / df["win_prior_share"].replace(
                0, pd.NA
            )
            df["place_flow_ratio"] = df["place_late_share"] / df[
                "place_prior_share"
            ].replace(0, pd.NA)

            # Flag horses meeting ALL three conditions
            df["win_flagged"] = (
                (df["win_flow_ratio"].fillna(0) >= FLOW_RATIO_MIN)
                & (df["win_amount_increase"] >= HORSE_INFLOW_MIN)
                & (win_pool >= WIN_POOL_MIN)
            )
            df["place_flagged"] = (
                (df["place_flow_ratio"].fillna(0) >= FLOW_RATIO_MIN)
                & (df["place_amount_increase"] >= HORSE_INFLOW_MIN)
                & (place_pool >= PLACE_POOL_MIN)
            )
        else:
            # No prior pool data -> can't compute flow ratio this snapshot.
            # Will populate from next run onward.
            df["win_prior_share"] = pd.NA
            df["place_prior_share"] = pd.NA
            df["win_late_share"] = pd.NA
            df["place_late_share"] = pd.NA
            df["win_flow_ratio"] = pd.NA
            df["place_flow_ratio"] = pd.NA
            df["win_flagged"] = False
            df["place_flagged"] = False
        # ===========================================

        # Drop only rows missing core data, not rows where derived columns are NA
        df.dropna(
            subset=["win_odds", "place_odds", "win_amount", "place_amount"],
            inplace=True,
        )

        # Round numeric columns (booleans pass through unchanged)
        df = df.round(4)

        # Save current pool sizes so the NEXT snapshot can compute deltas
        df["win_pool"] = win_pool
        df["place_pool"] = place_pool

        df.sort_values(
            by=["average_odds_change", "win_odds_change", "place_odds_change"],
            inplace=True,
        )
        df = df[
            [
                "horse_no",
                "horses",
                "average_odds_change",
                "win_odds",
                "prev_win_odds",
                "win_odds_change",
                "win_amount",
                "prev_win_amount",
                "win_amount_increase",
                "win_prior_share",
                "win_late_share",
                "win_flow_ratio",
                "win_flagged",
                "place_odds",
                "prev_place_odds",
                "place_odds_change",
                "place_amount",
                "prev_place_amount",
                "place_amount_increase",
                "place_prior_share",
                "place_late_share",
                "place_flow_ratio",
                "place_flagged",
                "win_pool",
                "place_pool",
            ]
        ]
        df.to_csv(csv_path, index=False)

        filtered_df = df[df["win_odds"] < 30]
        flagged_win = df[df["win_flagged"]]["horse_no"].to_list()
        flagged_place = df[df["place_flagged"]]["horse_no"].to_list()

        message = ""

        if flagged_win:
            # Include flow ratio for context
            ratios = filtered_df[filtered_df["win_flagged"]][
                ["horse_no", "win_flow_ratio"]
            ]
            ratio_str = ", ".join(
                f"#{r['horse_no']}({r['win_flow_ratio']:.2f}x)"
                for _, r in ratios.iterrows()
            )
            message += f"\n🔥 Disprop. Win flow: {ratio_str}\n"
        if flagged_place:
            ratios = filtered_df[filtered_df["place_flagged"]][
                ["horse_no", "place_flow_ratio"]
            ]
            ratio_str = ", ".join(
                f"#{r['horse_no']}({r['place_flow_ratio']:.2f}x)"
                for _, r in ratios.iterrows()
            )
            message += f"\n🔥 Disprop. Place flow: {ratio_str}\n"

        message += (
            f"R{raceno}\n"
            f"Average: {filtered_df.iloc[:4]['horse_no'].to_list()}\n"
            f"Win: {filtered_df.sort_values('win_odds_change').iloc[:4]['horse_no'].to_list()}\n"
            f"Place: {filtered_df.sort_values('place_odds_change').iloc[:4]['horse_no'].to_list()}"
        )
        print(message)
        send_telegram_message(message)

    else:
        total = 15
        horses, win_odds, place_odds, win_amounts, place_amounts = (
            [],
            [],
            [],
            [],
            [],
        )
        for j in range(1, 15):
            try:
                while True:
                    try:
                        horse_name = driver.find_element(
                            By.ID, f"horseName_{raceno}_{j}"
                        ).text
                        break
                    except ValueError as e:
                        print(e)
                win_odd_text = driver.find_element(By.ID, f"odds_WIN_{raceno}_{j}").text
                if win_odd_text == "":
                    print(j)
                    continue
                if win_odd_text == "退出":
                    horses.append(None)
                    win_odds.append(None)
                    place_odds.append(None)
                    win_amounts.append(None)
                    place_amounts.append(None)
                    continue
                win_odd = float(win_odd_text)
                place_odd = float(
                    driver.find_element(By.ID, f"odds_PLA_{raceno}_{j}").text
                )
                horses.append(horse_name)
                win_odds.append(win_odd)
                place_odds.append(place_odd)
                win_amounts.append(round(0.825 * (1 / win_odd) * win_pool, 2))
                place_amounts.append(round(0.825 * (1 / place_odd) * place_pool, 2))

                print(f"{j}: {horse_name}; WIN: {win_odd}; PLACE: {place_odd}")
            except selenium.common.exceptions.NoSuchElementException:
                total = j
                break

        df = pd.DataFrame(
            {
                "horse_no": range(1, total),
                "horses": horses,
                "win_odds": win_odds,
                "win_amount": win_amounts,
                "place_odds": place_odds,
                "place_amount": place_amounts,
            }
        )
        df.dropna(inplace=True)

        # Save pool sizes so the next snapshot can compute deltas / flow ratio
        df["win_pool"] = win_pool
        df["place_pool"] = place_pool

        df.sort_values("win_amount", ascending=False, inplace=True)
        df.to_csv(csv_path, index=False)
        message = (
            f"R{raceno}\n"
            f"Win: {df.iloc[:4]['horse_no'].to_list()}\n"
            f"Place: {df.sort_values('place_amount', ascending=False).iloc[:4]['horse_no'].to_list()}\n"
        )
        send_telegram_message(message)

    if fetch_type == "live":
        race_time = (
            driver.find_element(By.CLASS_NAME, "meeting-info-content-text")
            .text.split(",")[1]
            .strip()
        )
        race_time = datetime.strptime(race_time, "%H:%M")
        return race_time
    else:
        return None


def _get_race_info(url: str, driver: WebDriver) -> tuple[int, datetime]:
    race_time = (
        safe_get(driver, url, (By.CLASS_NAME, "meeting-info-content-text"))
        .text.split(",")[1]
        .strip()
    )
    race_time = datetime.strptime(race_time, "%H:%M")
    race_no = int(driver.current_url.split("/")[-1])
    racecourse_code = driver.current_url.split("/")[-2]
    return race_no, race_time, racecourse_code


def _next_aligned_boundary(now: datetime, interval_min: int) -> datetime:
    """Return the next wall-clock time aligned to interval_min minutes.
    If now is already exactly on a boundary, returns now + interval_min."""
    floored = now.replace(second=0, microsecond=0)
    floored = floored - timedelta(minutes=floored.minute % interval_min)
    return floored + timedelta(minutes=interval_min)


def _sleep_until(target: datetime) -> None:
    """Sleep until target wall-clock time. No-op if already past."""
    remaining = (target - datetime.now()).total_seconds()
    if remaining <= 0:
        return
    for _ in track(
        range(int(remaining)),
        description=f"Waiting until {target.strftime('%H:%M:%S')}",
    ):
        time.sleep(1)
    leftover = (target - datetime.now()).total_seconds()
    if leftover > 0:
        time.sleep(leftover)


def _wait_for_odds_loaded(driver, raceno, timeout=20):
    def any_odds_ready(d):
        for j in range(1, 15):
            try:
                if d.find_element(By.ID, f"odds_WIN_{raceno}_{j}").text.strip():
                    return True
            except selenium.common.exceptions.NoSuchElementException:
                continue
        return False

    WebDriverWait(driver, timeout).until(any_odds_ready)


def fetch_odds(fetch_type, date, racecourse, total_race, driver, wait):

    formatted_date = date.replace("-", "")
    Path(f"output/{fetch_type}_odds/{formatted_date}").mkdir(exist_ok=True)

    if fetch_type == "overnight":
        for i in range(1, total_race + 1):
            url = f"https://bet.hkjc.com/ch/racing/wp/{date}/{racecourse}/{i}"
            process_odds(url, driver, wait, str(i), formatted_date, fetch_type)
        return

    # ===== Live mode =====
    url = "https://bet.hkjc.com/ch/racing/wp/"
    prev_raceno = 0

    while True:
        curr_raceno, race_time, racecourse_code = _get_race_info(url, driver)

        if racecourse_code != racecourse:
            for i in track(
                range(300),
                description="Waiting for international match to wrap up...",
            ):
                time.sleep(1)
            continue

        if curr_raceno == prev_raceno:
            for i in track(
                range(60),
                description=f"Waiting for R{curr_raceno} to wrap up...",
            ):
                if curr_raceno == total_race:
                    print(f"All {total_race} matches are finished.")
                    return
                time.sleep(1)
            continue

        while True:
            curr_raceno, race_time, racecourse_code = _get_race_info(url, driver)
            now = datetime.now()
            race_time = race_time.replace(year=now.year, month=now.month, day=now.day)
            # Guard for late-night scraping of next-day races
            if race_time < now - timedelta(hours=12):
                race_time += timedelta(days=1)
            final_shot_time = race_time + timedelta(seconds=30)
            tier_switch = race_time - timedelta(minutes=10)

            print(f"Race scheduled at: {race_time.strftime('%H:%M:%S')}")
            print(f"Switch to 5-min tier at: {tier_switch.strftime('%H:%M:%S')}")
            print(f"Final snapshot at: {final_shot_time.strftime('%H:%M:%S')}")

            if now >= race_time:
                _sleep_until(final_shot_time)
                process_odds(url, driver, wait, 0, formatted_date, fetch_type)
                print("Final snapshot taken. Proceeding to next match.")
                break

            # Pick interval based on which tier we're in
            if now < tier_switch:
                interval_min = 15  # 30-10 min before race
            else:
                interval_min = 10  # 10-0 min before race

            next_boundary = _next_aligned_boundary(now, interval_min)

            # If the next boundary lands at or past race time, skip straight to final
            if next_boundary >= race_time:
                _sleep_until(final_shot_time)
                process_odds(url, driver, wait, 0, formatted_date, fetch_type)
                print("Final snapshot taken. Proceeding to next match.")
                break

            # else
            _sleep_until(next_boundary)
            process_odds(url, driver, wait, 0, formatted_date, fetch_type)

        prev_raceno = curr_raceno


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    # Make a GET request to the Telegram API
    response = requests.get(url, params=params)
    if response.status_code == 200:
        con.log("Message sent successfully!")
    else:
        con.log(f"Failed to send message. Status code: {response.status_code}")
        con.log(response.json())


if __name__ == "__main__":
    date = Prompt.ask("Race date (yyyy-mm-dd)")
    racecourse = Prompt.ask("Racecourse", choices=["ST", "HV"])
    total_race = IntPrompt.ask("Total no. of races")
    fetch_type = Prompt.ask("Fetch type", choices=["live", "overnight"])

    driver = webdriver.Chrome(service=Service())
    wait = WebDriverWait(driver, 600)

    try:
        fetch_odds(fetch_type, date, racecourse, total_race, driver, wait)
    except Exception as e:
        send_telegram_message(e)
