import json
import requests
import pandas as pd
import smtplib
import os

from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ---------------- CONFIG ----------------
TARGET_ID = os.environ["TARGET_ID"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

STATE_FILE = "state.json"

BASE_URL = "https://www.ireland.ie/4811/"

# ---------------- DATE LOGIC ----------------
today = datetime.utcnow()

date_str = today.strftime("%Y%m%d")

ODS_URL = f"{BASE_URL}{date_str}_NDVO_Visa_Decisions.ods"

is_weekend = today.weekday() >= 5  # 5=Saturday, 6=Sunday


# ---------------- STATE ----------------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"notified": False}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


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


# ---------------- CHECK FILE ----------------
def check_ods_exists(url):
    try:
        r = requests.head(url, timeout=20)
        return r.status_code == 200
    except:
        return False


# ---------------- MAIN LOGIC ----------------
state = load_state()

if not check_ods_exists(ODS_URL):

    if is_weekend:
        send_email(
            "Visa Update - Weekend Delay (Expected)",
            f"""
            <h2>No Visa File Published</h2>
            <p><b>Date:</b> {today.date()}</p>
            <p><b>Reason:</b> Weekend (Saturday/Sunday) — no updates expected.</p>
            <p><b>Checked URL:</b> {ODS_URL}</p>
            """
        )
    else:
        send_email(
            "Visa Update - File Not Found",
            f"""
            <h2>No Visa File Found</h2>
            <p><b>Date:</b> {today.date()}</p>
            <p>The expected ODS file was not found.</p>
            <p><b>Checked URL:</b> {ODS_URL}</p>
            """
        )

    raise SystemExit("No file available today")


# ---------------- DOWNLOAD FILE ----------------
ods_data = requests.get(ODS_URL, timeout=30).content

with open("visa.ods", "wb") as f:
    f.write(ods_data)

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
                <pre>{text}</pre>
                """
            )

            state["notified"] = True
            save_state(state)

        break
