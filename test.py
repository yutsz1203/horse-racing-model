import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

url = "https://bet.hkjc.com/ch/racing/wp/2026-03-18/HV/1"
import requests
from bs4 import BeautifulSoup

if __name__ == "__main__":
    raceno = input("raceno: ")
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--start-maximized")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )
    url = f"https://bet.hkjc.com/ch/racing/wp/2026-03-18/HV/{raceno}"
    wait = WebDriverWait(driver, 10)
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
