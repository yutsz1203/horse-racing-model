import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

CHINESE_CHAR = re.compile(r"[^\u4e00-\u9fa5\u3006\u3007]+")
BASE_URL = "https://racing.hkjc.com"
SEASON_START_DATE = pd.Timestamp("2025-09-07")

idx_map = {
    "1000": 2,
    "1200": 2,
    "1400": 3,
    "1600": 3,
    "1650": 3,
    "1800": 4,
    "2000": 4,
    "2200": 5,
    "2400": 5,
}

track_translate = {"草地": "grass", "全天候": "dirt"}


def main():
    """
    1. Prompt user to input racedate, racecourse, and total no. of races
    2. For each of the race, parse_race_card to get home pages and race df
    3. For each of the home page (horse), get indv match pages
    4. For each of the indv match, parse the sectional time page
    5. Combine all information and build df for each horse with their race history
    6. Build final df that shows last x match of each of the horses with the same distance and racecourse
    """
    # "2026/02/04"
    date = input("Input race date in this format (yyyy/mm/dd): ")
    formatted_date = "".join(date.split("/"))
    racecourse = input("Input racecourse (ST/HV): ")
    total_race = input("Input total number of matches: ")

    for rn in range(1, int(total_race) + 1):
        raceno = str(rn)
        home_pages, racecard_df, track, dist = parse_race_card(date, racecourse, raceno)

        print(
            f"Processing race no. {raceno}, {dist}m match on {date} at {racecourse}..."
        )

        Path(f"data/{formatted_date}").mkdir(parents=True, exist_ok=True)
        Path(f"data/{formatted_date}/{raceno}").mkdir(exist_ok=True)
        Path(f"data/{formatted_date}/final").mkdir(exist_ok=True)

        for home_page, horse, horseno in zip(
            home_pages, racecard_df["馬名"].values, racecard_df["馬匹編號"].values
        ):
            print(f"Processing {horse} match history...")
            indv_matches, indv_df = parse_home_page(home_page)
            if indv_matches:
                df = indv_df.copy()
                df.drop(
                    columns=["評分", "練馬師", "頭馬距離", "獨贏賠率", "配備"],
                    inplace=True,
                )

                for indv_match in indv_matches:
                    parsed_url = urlparse(indv_match)
                    params = parse_qs(parsed_url.query)

                    racedate = params.get("racedate", [None])[0]
                    past_raceno = params.get("RaceNo", [None])[0]

                    yr, mth, day = racedate.split("/")
                    racedate_formatted = f"{day}/{mth}/{yr}"

                    print(f"Processing the match on {racedate}")

                    distance, pace, top_3, last_section_time = parse_sectional_time(
                        horse, racedate_formatted, past_raceno
                    )
                    racedate_idx = pd.to_datetime(racedate_formatted, format="%d/%m/%Y")
                    df.loc[racedate_idx, "日期"] = racedate_formatted
                    df.loc[racedate_idx, "該仗步速"] = pace
                    df.loc[racedate_idx, "第一名"] = top_3[0]
                    df.loc[racedate_idx, "第二名"] = top_3[1]
                    df.loc[racedate_idx, "第三名"] = top_3[2]
                    df.loc[racedate_idx, "該仗末段"] = last_section_time

                df["馬名"] = horse
                df["馬匹編號"] = horseno
                df["今仗檔位"] = racecard_df.loc[
                    racecard_df["馬名"] == horse, "檔位"
                ].iloc[0]
                df["今仗騎師"] = racecard_df.loc[
                    racecard_df["馬名"] == horse, "騎師"
                ].iloc[0]
                df["今仗負磅"] = racecard_df.loc[
                    racecard_df["馬名"] == horse, "負磅"
                ].iloc[0]

                df.loc[df["馬場/跑道/賽道"].str.contains("跑馬地"), "馬場"] = "HV"
                df.loc[df["馬場/跑道/賽道"].str.contains("沙田"), "馬場"] = "ST"
                df.loc[df["馬場/跑道/賽道"].str.contains("草地"), "跑道"] = "grass"
                df.loc[df["馬場/跑道/賽道"].str.contains("全天候"), "跑道"] = "dirt"

                df.loc[df["賽事班次"].str.contains("G"), "賽事班次"] = "0"

                standard_time_df = pd.read_csv("data/standard_time.csv")
                standard_time_df["total_time"] = standard_time_df["total_time"].apply(
                    parse_time
                )
                standard_time_df = standard_time_df.astype(
                    {"class": "str", "distance": "str"}
                )

                df = df.merge(
                    standard_time_df,
                    left_on=["賽事班次", "馬場", "途程", "跑道"],
                    right_on=["class", "race_course", "distance", "type"],
                    how="left",
                )
                df.dropna(inplace=True)
                df["last_section_idx"] = df["途程"].map(idx_map)
                df["完成時間"] = df["完成時間"].apply(parse_time)
                df["該仗步速"] = df["該仗步速"].apply(parse_time)

                col_indices = (df["last_section_idx"] + 28).astype(int).values

                row_indices = np.arange(len(df))
                df["該仗頭段"] = round(df["完成時間"] - df["該仗末段"], 2)
                df["比標準頭段"] = round(
                    df["該仗頭段"]
                    - (df["total_time"] - df.values[row_indices, col_indices]),
                    2,
                )
                df["比標準末段"] = round(
                    df["該仗末段"] - df.values[row_indices, col_indices], 2
                )
                df["比標準時間"] = round(df["完成時間"] - df["total_time"], 2)

                cols_to_drop = list(standard_time_df.columns) + [
                    "last_section_idx",
                ]
                df.drop(
                    columns=cols_to_drop,
                    inplace=True,
                )
                df = df.rename(
                    columns={
                        "檔位": "上仗檔位",
                        "騎師": "上仗騎師",
                        "實際負磅": "上仗負磅",
                    }
                )
                df = df[
                    [
                        "馬場",
                        "跑道",
                        "場地狀況",
                        "途程",
                        "場次",
                        "日期",
                        "名次",
                        "馬名",
                        "馬匹編號",
                        "今仗檔位",
                        "上仗檔位",
                        "該仗步速",
                        "該仗頭段",
                        "比標準頭段",
                        "該仗末段",
                        "比標準末段",
                        "完成時間",
                        "比標準時間",
                        "沿途走位",
                        "第一名",
                        "第二名",
                        "第三名",
                        "上仗騎師",
                        "今仗騎師",
                        "賽事班次",
                        "上仗負磅",
                        "今仗負磅",
                    ]
                ]
                df["日期"] = pd.to_datetime(
                    df["日期"], dayfirst=True, format="%d/%m/%Y"
                )
                df.set_index("日期", inplace=True)
                df.to_csv(f"data/{''.join(date.split("/"))}/{raceno}/{horse}.csv")

        final_df, avg_df = concat_df(
            Path(f"data/{formatted_date}/{raceno}"), racecourse, dist, track, 2
        )
        final_df.to_csv(f"{Path(f"data/{formatted_date}/final")}/{raceno}_final.csv")
        avg_df.to_csv(
            f"{Path(f"data/{formatted_date}/final")}/{raceno}_avg.csv", index=False
        )
        # print(final_df.head())
        # print(avg_df.head())


def parse_race_card(date, racecourse, raceno):
    url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date}&Racecourse={racecourse}&RaceNo={raceno}"

    try:
        response = requests.get(url)

        if response.status_code == 200:
            content = response.text
            soup = BeautifulSoup(content, "lxml")

            info_box = soup.find(class_="f_fs13")
            info = info_box.text.split(",")
            if len(info[3]) == 8:  # turf
                track_info = track_translate[info[3][-2:]]
                dist_info = int(info[5][1:5])
            else:  # AWT
                track_info = track_translate[info[3][6:9]]
                dist_info = int(info[4][1:5])

            racecard = soup.find(class_="starter f_tac f_fs13 draggable hiddenable")
            pattern = r"horse"
            home_pages = []
            for anchor in racecard.find_all("a"):
                home_page = anchor.get("href")
                if re.search(pattern, home_page):
                    home_pages.append(home_page)
            data = []
            header = racecard.find("thead")
            if header:
                cols = header.find("tr").find_all("td")
                header_cols = [ele.get_text().strip() for ele in cols]

            table = racecard.find("tbody")
            if table:
                rows = table.find_all("tr")
                for row in rows:
                    cols = [
                        ele.get_text().strip() for ele in row.find_all(["td", "th"])
                    ]

                    if cols:
                        data.append(cols)

                df = pd.DataFrame(data, columns=header_cols)
                df.drop(
                    columns=[
                        "綵衣",
                        "烙號",
                        "可能超磅",
                        "國際評分",
                        "分齡讓磅",
                        "性別",
                        "今季獎金",
                        "優先參賽次序",
                        "馬主",
                        "父系",
                        "母系",
                        "進口類別",
                    ],
                    inplace=True,
                )
                # df.to_excel(f"data/{date.replace("/", "")}_{racecourse}_{race_no}.xlsx", index=False)
        else:
            print("Failed to retrieve the contents.")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

    return home_pages, df, track_info, dist_info


def parse_home_page(home_page):
    url = f"{BASE_URL}{home_page}"

    try:
        response = requests.get(url)

        if response.status_code == 200:
            content = response.text
            soup = BeautifulSoup(content, "lxml")
            results = soup.find(class_="bigborder")
            if results:
                rows = results.find_all("tr")
                data = []
                for row in rows:
                    cols = [ele.get_text().strip() for ele in row.find_all(["td"])]
                    if len(cols) > 1:
                        data.append(cols)
                header_col = data[0]
                data = data[1:]
                df = pd.DataFrame(data, columns=header_col)
                df.drop(columns=["排位體重", "賽事重播"], inplace=True)
                df["日期"] = pd.to_datetime(
                    df["日期"], dayfirst=True, format="%d/%m/%y"
                )
                df.set_index("日期", inplace=True)
                df.sort_index(inplace=True)

                indv_matches = []
                pattern = r"localresults"
                for anchor in results.find_all("a"):
                    indv_match = anchor.get("href")
                    if re.search(pattern, indv_match):
                        indv_matches.append(indv_match)

        else:
            print("Failed to retrieve the contents.")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

    return indv_matches, df


def parse_sectional_time(target, racedate, raceno):
    url = f"{BASE_URL}/zh-hk/local/information/displaysectionaltime?racedate={racedate}&RaceNo={raceno}"
    try:
        response = requests.get(url)

        if response.status_code == 200:
            content = response.text
            soup = BeautifulSoup(content, "lxml")
            general = soup.find(class_="f_tac f_fl f_fs13")
            if general:
                # add logic to extract the second last section for different racecourse/distance/type combinations
                distance = (
                    soup.find(class_="f_fl f_fs13")
                    .get_text()
                    .split("-")[1]
                    .strip()[:-1]
                )
                idx = idx_map[distance]
                pace = re.sub(
                    r"[()]",
                    "",
                    [time.get_text().strip() for time in general.find_all("td")][idx],
                )
                pace = pace.replace(":", ".")
            race_table = soup.find(class_="table_bd f_tac race_table")
            if race_table:
                tbody = race_table.find("tbody")
                rows = tbody.find_all("tr")
                top_3 = []
                last_section_time = None
                for row in rows:
                    horse_name = row.find("a")
                    horse_name = CHINESE_CHAR.sub("", horse_name.text)
                    if len(top_3) < 3:
                        top_3.append(horse_name)
                    if horse_name == target:
                        # extract last sectional time
                        last_section = row.find_all("td")[idx + 3].find(
                            class_="sectional_200"
                        )
                        if last_section:
                            last_section_time = last_section.text.split("\n", 1)[0]
                            if last_section_time != "":
                                last_section_time = float(last_section_time)
                            else:
                                last_section_time = None

        else:
            print("Failed to retrieve the contents.")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

    return distance, pace, top_3, last_section_time


def parse_time(time_str):
    """
    Docstring for parse_time

    Input: e.g. 1.20.35 (string)
    Output: e.g. 80.35 (float)
    """
    if time_str == "--":
        return None
    else:
        components = time_str.split(".")
        if len(components) == 2:
            m = 0
            s, h = map(float, components)
        else:
            m, s, h = map(float, time_str.split("."))
        return (m * 60) + s + (h / 100)


def create_standard_time_data():
    """
    Use this function when standard times are updated.
    Create an excel file of standard time manually and then uncomment the following codes.
    Reference: https://racingking.hk/topic/article/54071
    """
    pass
    # df = pd.read_excel("data/standard_time.xlsx")
    # df.to_csv("data/standard_time.csv", index=False)


def concat_df(dir: Path, racecourse, dist, track, recent_x):
    all_dfs = []
    avg = []

    for file_path in dir.glob("*.csv"):
        tmp_df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        cond = (
            (tmp_df.index >= SEASON_START_DATE)
            & (tmp_df["馬場"] == racecourse)
            & (tmp_df["跑道"] == track)
            & (tmp_df["途程"] == dist)
        )
        filtered_df = tmp_df.loc[cond]

        if not filtered_df.empty:
            filtered_df.sort_index(ascending=False, inplace=True)
            filtered_df = filtered_df.iloc[: min(recent_x, len(filtered_df))]
            filtered_df.sort_values(by="比標準時間", inplace=True)
            avg.append(
                {
                    "馬匹編號": filtered_df["馬匹編號"].values[0],
                    "馬名": filtered_df["馬名"].values[0],
                    "完成時間": filtered_df["完成時間"].mean().round(2),
                }
            )
            all_dfs.append(filtered_df)

    if all_dfs:
        final_df = pd.concat(all_dfs)
        final_df.sort_values(by=["完成時間", "比標準時間"], inplace=True)

        avg_df = pd.DataFrame(avg)
        avg_df.sort_values(by="完成時間", inplace=True)
    else:
        final_df = pd.DataFrame()
        avg_df = pd.DataFrame()

    return final_df, avg_df


if __name__ == "__main__":
    main()
