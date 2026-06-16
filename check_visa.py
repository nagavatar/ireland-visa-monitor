import json
import requests
import pandas as pd
import smtplib
import os

from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ---------------- CONFIG ----------------
TARGET_ID = os.environ["TARGET_ID"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

STATE_FILE = "state.json"
BASE_URL = "https://www.ireland.ie/4811/"

MAX_LOOKBACK_DAYS = 7
HISTORY_DAYS = 90


# ---------------- TIME ----------------
now = datetime.now(timezone.utc)
is_weekend = now.weekday() >= 5


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
        print("State load failed, resetting:", str(e))
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


# ---------------- FILE CHECK ----------------
def check_file(url):
    try:
        r = requests.head(url, timeout=10)
        return r.status_code == 200
    except:
        return False


# ---------------- FIND LATEST FILE ----------------
def find_latest_ods():
    for i in range(MAX_LOOKBACK_DAYS):
        date = now - timedelta(days=i)
        date_str = date.strftime("%Y%m%d")

        url = f"{BASE_URL}{date_str}_NDVO_Visa_Decisions.ods"

        if check_file(url):
            return url, date_str

    return None, None


# ---------------- HISTORY SCAN (LAST 3 MONTHS) ----------------
def scan_history():
    print("\n===== VISA FILE HISTORY (LAST 90 DAYS) =====\n")

    available = []
    missing = []

    for i in range(HISTORY_DAYS):
        date = now - timedelta(days=i)
        date_str = date.strftime("%Y%m%d")

        url = f"{BASE_URL}{date_str}_NDVO_Visa_Decisions.ods"

        if check_file(url):
            available.append(date_str)
            print(f"AVAILABLE   {date_str}")
        else:
            missing.append(date_str)
            print(f"MISSING     {date_str}")

    print("\n===== SUMMARY =====")
    print(f"Available: {len(available)}")
    print(f"Missing:   {len(missing)}\n")

    return available, missing


# ---------------- MAIN ----------------
state = load_state()

# 1. Scan history (always runs)
available, missing = scan_history()

# 2. Find latest usable file
ODS_URL, file_date = find_latest_ods()

# ---------------- NO FILE FOUND ----------------
if not ODS_URL:

    if is_weekend:
        send_email(
            "Visa Update - Weekend Delay (Expected)",
            f"""
            <h2>No Visa File Published</h2>
            <p>Weekend detected — no updates expected.</p>
            <p><b>Date:</b> {now.date()}</p>
            """
        )
    else:
        send_email(
            "Visa Update - No File Found",
            f"""
            <h2>No Visa File Found</h2>
            <p>Checked last {MAX_LOOKBACK_DAYS} days.</p>
            <p><b>Date:</b> {now.date()}</p>
            """
        )

    raise SystemExit("No file found")


# ---------------- DOWNLOAD ----------------
response = requests.get(ODS_URL, timeout=30)
response.raise_for_status()

with open("visa.ods", "wb") as f:
    f.write(response.content)

df = pd.read_excel("visa.ods", engine="odf")


# ---------------- SEARCH TARGET ----------------
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
                <p><b>File Date:</b> {file_date}</p>
                <pre>{text}</pre>
                """
            )

            state["notified"] = True
            save_state(state)

        break
