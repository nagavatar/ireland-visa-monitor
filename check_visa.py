import json
import requests
import pandas as pd
import smtplib
import os

from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin
from bs4 import BeautifulSoup


# ---------------- CONFIG ----------------
TARGET_ID = os.environ["TARGET_ID"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

PAGE_URL = "https://www.ireland.ie/en/india/newdelhi/services/visas/processing-times-and-decisions/"
BASE = "https://www.ireland.ie"

STATE_FILE = "state.json"


# ---------------- TIME ----------------
now = datetime.now(timezone.utc)


# ---------------- STATE ----------------
def load_state():
    try:
        if not os.path.exists(STATE_FILE):
            return {"notified": False}

        with open(STATE_FILE, "r") as f:
            content = f.read().strip()

        if not content:
            return {"notified": False}

        return json.loads(content)

    except Exception as e:
        print("State load failed:", e)
        return {"notified": False}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# ---------------- EMAIL ----------------
def send_email(subject, body):

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER

    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)


# ---------------- GET ODS FROM PAGE ----------------
def get_ods_from_page():
    html = requests.get(PAGE_URL, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "NDVO_Visa_Decisions" in href and href.endswith(".ods"):
            return urljoin(BASE, href)

    return None


# ---------------- MAIN LOGIC ----------------
state = load_state()

# try today first (from page)
ods_url = get_ods_from_page()

# if not found, try yesterday page state (same page usually still shows latest, so fallback is same)
if not ods_url:
    send_email(
        "Visa Update - File Not Found",
        f"""
        <h2>No Visa File Found</h2>
        <p>Could not locate ODS file on page.</p>
        <p><b>Date:</b> {now.date()}</p>
        """
    )
    raise SystemExit("No ODS file found")


print("Using file:", ods_url)


# ---------------- DOWNLOAD ----------------
response = requests.get(ods_url, timeout=30)
response.raise_for_status()

with open("visa.ods", "wb") as f:
    f.write(response.content)


df = pd.read_excel("visa.ods", engine="odf")


# ---------------- SEARCH ----------------
for _, row in df.iterrows():

    text = " ".join(str(x) for x in row.values)

    if TARGET_ID in text:

        if not state.get("notified", False):

            lower = text.lower()

            if "granted" in lower:
                status = "GRANTED"
            elif "refused" in lower:
                status = "REFUSED"
            else:
                status = "FOUND"

            send_email(
                f"Ireland Visa Update - {status}",
                f"""
                <h2>Visa Decision Found</h2>
                <p><b>Application:</b> {TARGET_ID}</p>
                <p><b>Status:</b> {status}</p>
                <pre>{text}</pre>
                """
            )

            state["notified"] = True
            save_state(state)

        break
