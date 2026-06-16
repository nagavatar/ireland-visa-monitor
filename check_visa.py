import json
import requests
import pandas as pd
import smtplib
import os

from bs4 import BeautifulSoup
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin

# ---------------- CONFIG ----------------
TARGET_ID = os.environ["TARGET_ID"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

PAGE_URL = "https://www.ireland.ie/en/india/newdelhi/services/visas/processing-times-and-decisions/"
STATE_FILE = "state.json"


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
def send_email(status, row_text):

    msg = MIMEMultipart()
    msg["Subject"] = f"Ireland Visa Update - {status}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER

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

    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)


# ---------------- FETCH PAGE ----------------
html = requests.get(PAGE_URL, timeout=30).text
soup = BeautifulSoup(html, "html.parser")

# ✅ Direct + safe extraction (based on known structure)
ods_url = None

for a in soup.select("a[href]"):
    href = a["href"]
    if "Visa_Decisions" in href and href.endswith(".ods"):
        ods_url = urljoin(PAGE_URL, href)
        break

if not ods_url:
    raise Exception("ODS file not found")

# ---------------- DOWNLOAD ODS ----------------
ods_data = requests.get(ods_url, timeout=30).content

with open("visa.ods", "wb") as f:
    f.write(ods_data)

# ---------------- READ ODS ----------------
df = pd.read_excel("visa.ods", engine="odf")

state = load_state()

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

            send_email(status, text)

            state["notified"] = True
            save_state(state)

        break
