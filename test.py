import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import selenium
from rich import console, print
from rich.prompt import IntPrompt, Prompt
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tabulate import tabulate
from webdriver_manager.chrome import ChromeDriverManager

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
wait = WebDriverWait(driver, 60)
TOKEN = "8759428672:AAHTZ0nY4HKxls2GeGr4CvByn6EU3TSp1XM"
CHAT_ID = "842065244"
MESSAGE = "Hello World."
con = console.Console()


def overnight(date, racecourse, total_race):
    for i in range(1, total_race + 1):
        url = f"https://bet.hkjc.com/ch/racing/wp/{date}/{racecourse}/{i}"
        res = driver.get(url)

        win_pool = wait.until(EC.element_to_be_clickable((By.ID, "poolInvWIN")))
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

        if Path(f"output/overnight_odds/overnight_{i}.csv").exists():

            df = pd.read_csv(f"output/overnight_odds/overnight_{i}.csv")
            df.sort_values(by="horse_no", inplace=True)
            win_odds, place_odds, win_amounts, place_amounts = (
                [],
                [],
                [],
                [],
            )
            for j in range(1, 15):
                try:
                    horse_name = driver.find_element(By.ID, f"horseName_{i}_{j}").text
                    while True:
                        try:
                            win_odd = float(
                                driver.find_element(By.ID, f"odds_WIN_{i}_{j}").text
                            )
                            break
                        except ValueError as e:
                            print(e)
                    place_odd = float(
                        driver.find_element(By.ID, f"odds_PLA_{i}_{j}").text
                    )
                    win_odds.append(win_odd)
                    place_odds.append(place_odd)
                    win_amounts.append(round(0.825 * (1 / win_odd) * win_pool, 2))
                    place_amounts.append(round(0.825 * (1 / place_odd) * place_pool, 2))

                    # print(f"{j}: {horse_name}; WIN: {win_odd}; PLACE: {place_odd}")
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
            df.to_csv(f"output/overnight_odds/overnight_{i}.csv", index=False)
            message = f"R{i}\nWin: {df.iloc[:4]["horse_no"].to_list()} \nPlace: {df.sort_values("place_amount_increase").iloc[:4]["horse_no"].to_list()}"
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
                    horse_name = driver.find_element(By.ID, f"horseName_{i}_{j}").text
                    win_odd = float(
                        driver.find_element(By.ID, f"odds_WIN_{i}_{j}").text
                    )
                    place_odd = float(
                        driver.find_element(By.ID, f"odds_PLA_{i}_{j}").text
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
            df.to_csv(f"output/overnight_odds/overnight_{i}.csv", index=False)
            send_telegram_message(df.to_string())


def live():
    raceno = input("raceno: ")

    url = f"https://bet.hkjc.com/ch/racing/wp/2026-03-18/HV/{raceno}"
    wait = WebDriverWait(driver, 60)
    very_large_win = set()
    large_win = set()
    very_large_place = set()
    large_place = set()
    while True:
        res = driver.get(url)

        win_pool = wait.until(EC.element_to_be_clickable((By.ID, "poolInvWIN")))

        win_pool = float(win_pool.text.split()[2].replace(",", ""))

        place_pool = float(
            driver.find_element(By.ID, "poolInvPLA").text.split()[2].replace(",", "")
        )
        print(f"As at: {datetime.now().strftime("%H:%M")}")
        print(f"Win pool investment: {win_pool}")
        print(f"Place pool investment: {place_pool}")

        if Path(f"live_odds/{raceno}.csv").exists():
            df = pd.read_csv(f"live_odds/{raceno}.csv")
            df.sort_values(by="horse_no", inplace=True)
            win_odds, place_odds, win_amounts, place_amounts = (
                [],
                [],
                [],
                [],
            )
            for i in range(1, 14):
                try:
                    horse_name = driver.find_element(
                        By.ID, f"horseName_{raceno}_{i}"
                    ).text
                    win_odd = float(
                        driver.find_element(By.ID, f"odds_WIN_{raceno}_{i}").text
                    )
                    place_odd = float(
                        driver.find_element(By.ID, f"odds_PLA_{raceno}_{i}").text
                    )
                    win_odds.append(win_odd)
                    place_odds.append(place_odd)
                    win_amounts.append(round(0.825 * (1 / win_odd) * win_pool, 2))
                    place_amounts.append(round(0.825 * (1 / place_odd) * place_pool, 2))

                    print(f"{i}: {horse_name}; WIN: {win_odd}; PLACE: {place_odd}")
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

            df["win_amount_increase"] = (df["win_amount"] - df["prev_win_amount"]) / df[
                "prev_win_amount"
            ]
            df["place_amount_increase"] = (
                df["place_amount"] - df["prev_place_amount"]
            ) / df["prev_place_amount"]

            df = df.round(2)
            df.sort_values(
                by=["win_amount_increase", "place_amount_increase"],
                ascending=False,
                inplace=True,
            )
            df.to_csv(f"live_odds/{raceno}.csv", index=False)
            print(df)
            for val in df.loc[df["win_amount_increase"] > 1, "horse_no"].values:
                very_large_win.add(int(val))
            for val in df.loc[df["place_amount_increase"] > 1, "horse_no"].values:
                very_large_place.add(int(val))
            for val in df.loc[
                (df["win_amount_increase"] > 0.5) & (df["win_amount_increase"] < 1),
                "horse_no",
            ].values:
                large_win.add(int(val))

            for val in df.loc[
                (df["place_amount_increase"] > 0.5) & (df["place_amount_increase"] < 1),
                "horse_no",
            ].values:
                large_place.add(int(val))

            print(f"Very large win: {very_large_win}")
            print(f"Large win: {large_win}")
            print(f"Very large place: {very_large_place}")
            print(f"Large place: {large_place}")

        else:
            horses, win_odds, place_odds, win_amounts, place_amounts = (
                [],
                [],
                [],
                [],
                [],
            )
            for i in range(1, 14):
                try:
                    horse_name = driver.find_element(
                        By.ID, f"horseName_{raceno}_{i}"
                    ).text
                    win_odd = float(
                        driver.find_element(By.ID, f"odds_WIN_{raceno}_{i}").text
                    )
                    place_odd = float(
                        driver.find_element(By.ID, f"odds_PLA_{raceno}_{i}").text
                    )

                    print(f"{i}: {horse_name}; WIN: {win_odd}; PLACE: {place_odd}")

                    horses.append(horse_name)
                    win_odds.append(win_odd)
                    place_odds.append(place_odd)
                    win_amounts.append(round(0.825 * (1 / win_odd) * win_pool, 2))
                    place_amounts.append(round(0.825 * (1 / place_odd) * place_pool, 2))
                except selenium.common.exceptions.NoSuchElementException:
                    total = i
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
            df.to_csv(f"live_odds/{raceno}.csv", index=False)

        time.sleep(60)


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
    script_dir = Path(__file__).resolve().parent
    os.chdir(script_dir)
    # date = Prompt.ask("Race date (yyyy-mm-dd)")
    # racecourse = Prompt.ask("Racecourse", choices=["ST", "HV"])
    # total_race = IntPrompt.ask("Total no. of races")

    date = "2026-03-22"
    racecourse = "ST"
    total_race = 10
    overnight(date, racecourse, total_race)
