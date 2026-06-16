import json
import requests
import pandas as pd
import smtplib

from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from urllib.parse import urljoin
import os

TARGET_ID = os.environ["TARGET_ID"]

EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

PAGE_URL = (
    "https://www.ireland.ie/en/india/newdelhi/services/"
    "visas/processing-times-and-decisions/"
)

STATE_FILE = "state.json"


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"notified": False}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def send_email(status, row_text):

    html = f"""
    <html>
    <body>
        <h2>Ireland Visa Decision Found</h2>

        <p><b>Application:</b> {TARGET_ID}</p>

        <p><b>Status:</b> {status}</p>

        <pre>{row_text}</pre>
    </body>
    </html>
    """

    msg = MIMEText(html, "html")
    msg["Subject"] = f"Ireland Visa Update - {status}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)


headers = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

html = requests.get(
    PAGE_URL,
    headers=headers,
    timeout=30
).text

soup = BeautifulSoup(html, "html.parser")
ods_url = None

print("Searching for ODS link...")

for a in soup.find_all("a", href=True):

    href = a["href"]
    text = a.get_text(" ", strip=True)

    if ".ods" in href.lower():
        ods_url = urljoin(PAGE_URL, href)
        print("Found ODS:", ods_url)
        break

if not ods_url:

    print("\nAvailable links on page:\n")

    for a in soup.find_all("a", href=True):
        print(
            f"TEXT=[{a.get_text(' ', strip=True)}] "
            f"HREF=[{a['href']}]"
        )

    raise Exception("ODS file not found")

with open("visa.ods", "wb") as f:
    f.write(requests.get(
    ods_url,
    headers=headers,
    timeout=30
).content)

df = pd.read_excel("visa.ods", engine="odf")

state = load_state()

for _, row in df.iterrows():

    text = " ".join(str(x) for x in row.values)

    if TARGET_ID in text:

        if not state["notified"]:

            lower = text.lower()

            if "granted" in lower:
                status = "GRANTED"
            elif "refused" in lower:
                status = "REFUSED"
            else:
                status = "FOUND"

            send_email(status, text)

            state["notified"] = True
            save_state(state)

        break
