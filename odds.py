import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import selenium
from dotenv import load_dotenv
from rich import console, print
from rich.progress import track
from rich.prompt import IntPrompt, Prompt
from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()
TOKEN = os.getenv("TELEGRAM_API_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

con = console.Console()


def process_odds(
    url: str,
    driver: WebDriver,
    wait: WebDriverWait,
    raceno: str,
    date: str,
    fetch_type: str,
) -> datetime | None:

    res = driver.get(url)
    win_pool = wait.until(EC.element_to_be_clickable((By.ID, "poolInvWIN")))

    if fetch_type == "live":
        raceno = driver.current_url.split("/")[-1]

    while True:
        try:
            win_pool = float(win_pool.text.split()[2].replace(",", ""))
            break
        except ValueError as e:
            print(e)

    place_pool = float(
        driver.find_element(By.ID, "poolInvPLA").text.split()[2].replace(",", "")
    )

    print(f"As at: {datetime.now().strftime("%H:%M")}")
    print(f"Win pool investment: {win_pool}")
    print(f"Place pool investment: {place_pool}")

    if Path(f"output/{fetch_type}_odds/{date}/{fetch_type}_{raceno}.csv").exists():

        df = pd.read_csv(f"output/{fetch_type}_odds/{date}/{fetch_type}_{raceno}.csv")
        df.sort_values(by="horse_no", inplace=True)
        win_odds, place_odds, win_amounts, place_amounts = (
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
                if win_odd_text == "退出":
                    # win_odds.append(None)
                    # place_odds.append(None)
                    # win_amounts.append(None)
                    # place_amounts.append(None)
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

        df.dropna(inplace=True)
        df = df.round(2)
        df.sort_values(
            by=["win_amount_increase", "place_amount_increase"],
            ascending=False,
            inplace=True,
        )
        df = df[
            [
                "horse_no",
                "horses",
                "win_odds",
                "prev_win_odds",
                "win_odds_change",
                "win_amount",
                "prev_win_amount",
                "win_amount_increase",
                "place_odds",
                "prev_place_odds",
                "place_odds_change",
                "place_amount",
                "prev_place_amount",
                "place_amount_increase",
            ]
        ]
        df.to_csv(
            f"output/{fetch_type}_odds/{date}/{fetch_type}_{raceno}.csv", index=False
        )
        message = f"R{raceno}\nWin: {df.iloc[:4]["horse_no"].to_list()} \nPlace: {df.sort_values("place_amount_increase", ascending=False).iloc[:4]["horse_no"].to_list()}"
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
                horse_name = driver.find_element(By.ID, f"horseName_{raceno}_{j}").text
                win_odd = float(
                    driver.find_element(By.ID, f"odds_WIN_{raceno}_{j}").text
                )
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
        df.sort_values("win_amount", ascending=False, inplace=True)
        df.to_csv(
            f"output/{fetch_type}_odds/{date}/{fetch_type}_{raceno}.csv", index=False
        )
        message = f"R{raceno}\nWin: {df.iloc[:4]["horse_no"].to_list()} \nPlace: {df.sort_values("place_amount", ascending=False).iloc[:4]["horse_no"].to_list()}"
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


def fetch_odds(fetch_type, date, racecourse, total_race, driver, wait):

    formatted_date = date.replace("-", "")
    Path(f"output/{fetch_type}_odds/{formatted_date}").mkdir(exist_ok=True)
    if fetch_type == "overnight":
        for i in range(6, total_race + 1):
            url = f"https://bet.hkjc.com/ch/racing/wp/{date}/{racecourse}/{i}"
            process_odds(url, driver, wait, i, formatted_date, fetch_type)
    else:
        while True:
            now = datetime.now()

            url = f"https://bet.hkjc.com/ch/racing/wp/"
            race_time = process_odds(url, driver, wait, 0, formatted_date, fetch_type)

            race_time = race_time.replace(year=now.year, month=now.month, day=now.day)
            diff = race_time - now
            total_seconds = abs(diff.total_seconds())
            total_minutes = total_seconds / 60

            # 30 - 5 minutes before match
            if total_minutes > 5:
                freq = 5 * 60
            # 5 - 1 minutes before match
            elif total_minutes > 1:
                freq = 60
            # 1 minutes - before start of match
            elif total_minutes < 1 and total_minutes > -3:
                freq = 10
            else:
                freq = 60

            for i in track(range(freq), description="Waiting"):
                time.sleep(1)


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

    fetch_odds(fetch_type, date, racecourse, total_race, driver, wait)
