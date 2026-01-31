import re
import requests
import pandas as pd
from bs4 import BeautifulSoup

def main():
    pass

def parse_race_card():
    date = "2026/02/01"
    racecourse = "ST"
    race_no = "8"
    url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date}&Racecourse={racecourse}&RaceNo={race_no}"

    try:
        response = requests.get(url)

        if response.status_code == 200:
            content = response.text
            soup = BeautifulSoup(content, "lxml")
            racecard = soup.find(class_="starter f_tac f_fs13 draggable hiddenable")
            pattern = r'horse'
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
                    cols = [ele.get_text().strip() for ele in row.find_all(["td", "th"])]
                    
                    if cols:
                        data.append(cols)

                df = pd.DataFrame(data, columns=header_cols)
                df.drop(columns=['綵衣', '烙號', '可能超磅', '國際評分','分齡讓磅', '性別', '今季獎金', '優先參賽次序','馬主', '父系', '母系', '進口類別'],inplace=True)
                print(df)
                df.to_excel(f"data/{date.replace("/", "")}_{racecourse}_{race_no}.xlsx", index=False)
        else:
            print(f"Failed to retrieve the contents.")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")


def parse_home_page():
    url = "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2024_K434"

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
                df.drop(columns=['排位體重', '賽事重播'],inplace=True)
                
                indv_matches = []
                pattern = r'localresults'
                for anchor in results.find_all("a"):
                    indv_match = anchor.get("href")
                    if re.search(pattern, indv_match):
                        indv_matches.append(indv_match) 
                print(indv_matches)
                                                                          
        else:
            print(f"Failed to retrieve the contents.")
        
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

def create_standard_time_data():
    """
    Use this function when standard times are updated.
    Create an excel file of standard time manually and then uncomment the following codes.
    Reference: https://racingking.hk/topic/article/54071
    """
    pass
    # df = pd.read_excel("data/standard_time.xlsx")
    # df.to_csv("data/standard_time.csv", index=False)



if __name__ == "__main__":
    main()
