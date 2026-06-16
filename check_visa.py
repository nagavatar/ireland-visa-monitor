#!/usr/bin/env python3
"""
Ireland Visa Monitor - Daily visa decision checker

Monitors the Ireland Embassy New Delhi visa decisions page,
downloads the latest ODS file, searches for a specific visa
application number, and sends an email notification when found.
"""

import json
import logging
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Constants
PAGE_URL = "https://www.ireland.ie/en/india/newdelhi/services/visas/processing-times-and-decisions/"
STATE_FILE = "state.json"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
GMAIL_SMTP = "smtp.gmail.com"
GMAIL_PORT = 587

# Status keywords to search for in the ODS file
STATUS_KEYWORDS = {
    "Granted": ["granted", "visa granted", "Approved"],
    "Refused": ["Refused", "visa refused", "rejected"],
    "Found": ["decision", "found", "processed"]
}

# Setup logging
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


def get_environment_variables() -> Tuple[str, str, str]:
    """
    Retrieve required environment variables.
    
    Returns:
        Tuple of (target_id, email_user, email_password)
        
    Raises:
        ValueError: If any required environment variable is missing
    """
    target_id = os.getenv("TARGET_ID")
    email_user = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_PASSWORD")
    
    if not target_id:
        raise ValueError("TARGET_ID environment variable not set")
    if not email_user:
        raise ValueError("EMAIL_USER environment variable not set")
    if not email_password:
        raise ValueError("EMAIL_PASSWORD environment variable not set")
    
    return target_id.strip(), email_user.strip(), email_password.strip()


def find_ods_url() -> str:
    """
    Fetch the Ireland Embassy page and find the newest ODS file link.
    
    Returns:
        Full URL to the ODS file
        
    Raises:
        RuntimeError: If ODS file URL cannot be found
    """
    logger.info(f"Fetching page: {PAGE_URL}")
    
    try:
        response = requests.get(PAGE_URL, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch page: {e}")
    
    soup = BeautifulSoup(response.content, "html.parser")
    
    # Find all links that point to ODS files
    ods_links = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.lower().endswith(".ods"):
            full_url = urljoin(PAGE_URL, href)
            ods_links.append(full_url)
            logger.info(f"Found ODS link: {full_url}")
    
    if not ods_links:
        raise RuntimeError(
            "No ODS file found on the Ireland Embassy page. "
            "The page structure may have changed."
        )
    
    # Return the first (usually newest) ODS file found
    ods_url = ods_links[0]
    logger.info(f"Using ODS URL: {ods_url}")
    return ods_url


def download_ods_file(ods_url: str) -> str:
    """
    Download the ODS file and return the local file path.
    
    Args:
        ods_url: URL of the ODS file
        
    Returns:
        Path to the downloaded file
        
    Raises:
        RuntimeError: If download fails
    """
    filename = "decisions.ods"
    
    logger.info(f"Downloading ODS file from: {ods_url}")
    
    try:
        response = requests.get(ods_url, timeout=30)
        response.raise_for_status()
        
        with open(filename, "wb") as f:
            f.write(response.content)
        
        file_size = os.path.getsize(filename)
        logger.info(f"ODS file downloaded successfully. Size: {file_size} bytes")
        return filename
        
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download ODS file: {e}")
    except IOError as e:
        raise RuntimeError(f"Failed to save ODS file: {e}")


def normalize_text(text: str) -> str:
    """
    Normalize text by removing extra spaces and converting to lowercase.
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text
    """
    if not isinstance(text, str):
        return str(text).strip().lower()
    return " ".join(text.split()).strip().lower()


def search_application_id(
    ods_path: str, target_id: str
) -> Optional[Tuple[dict, str, int]]:
    """
    Search for the target application ID in the ODS file.
    
    Args:
        ods_path: Path to the ODS file
        target_id: Application ID to search for
        
    Returns:
        Tuple of (row_dict, status, sheet_index) if found, None otherwise
    """
    normalized_target = normalize_text(target_id)
    logger.info(f"Searching for application ID: {target_id}")
    
    try:
        # Read all sheets from the ODS file
        xls = pd.ExcelFile(ods_path, engine="odf")
        sheet_names = xls.sheet_names
        logger.info(f"Found {len(sheet_names)} sheet(s): {sheet_names}")
        
        for sheet_idx, sheet_name in enumerate(sheet_names):
            df = pd.read_excel(ods_path, sheet_name=sheet_name, engine="odf")
            logger.info(f"Sheet '{sheet_name}' has {len(df)} rows")
            
            # Search through all columns for the target ID
            for col in df.columns:
                for row_idx, value in df[col].items():
                    normalized_value = normalize_text(str(value))
                    
                    if normalized_value == normalized_target:
                        row_data = df.iloc[row_idx].to_dict()
                        logger.info(f"Match found in sheet '{sheet_name}' at row {row_idx}")
                        
                        # Try to detect status from the row
                        status = detect_status(row_data)
                        return (row_data, status, sheet_idx)
        
        logger.info(f"Application ID '{target_id}' not found in any sheet")
        return None
        
    except Exception as e:
        raise RuntimeError(f"Failed to read ODS file: {e}")


def detect_status(row_data: dict) -> str:
    """
    Attempt to detect the visa decision status from the row data.
    
    Args:
        row_data: Dictionary of row data
        
    Returns:
        Status string ("Granted", "Refused", or "Found")
    """
    row_text = " ".join(
        normalize_text(str(v)) for v in row_data.values() if v
    )
    
    for status, keywords in STATUS_KEYWORDS.items():
        for keyword in keywords:
            if keyword in row_text:
                return status
    
    return "Found"


def load_state() -> dict:
    """
    Load the state from the state.json file.
    
    Returns:
        State dictionary
    """
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load state file: {e}. Starting fresh.")
            return {}
    return {}


def save_state(state: dict) -> None:
    """
    Save the state to the state.json file.
    
    Args:
        state: State dictionary to save
    """
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        logger.info("State saved successfully")
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def send_email(
    email_user: str,
    email_password: str,
    target_id: str,
    row_data: dict,
    status: str,
    ods_url: str
) -> bool:
    """
    Send a formatted HTML email notification.
    
    Args:
        email_user: Sender email address
        email_password: Email password/app password
        target_id: Visa application ID
        row_data: Dictionary containing the matching row data
        status: Detected visa decision status
        ods_url: URL of the ODS file
        
    Returns:
        True if email sent successfully, False otherwise
    """
    logger.info(f"Preparing email notification for {target_id}")
    
    try:
        # Create HTML email body
        html_body = create_email_body(target_id, row_data, status, ods_url)
        
        # Create email message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎉 Ireland Visa Decision Found - {target_id}"
        msg["From"] = email_user
        msg["To"] = email_user
        
        msg.attach(MIMEText(html_body, "html"))
        
        # Send email via Gmail SMTP
        logger.info("Connecting to Gmail SMTP...")
        with smtplib.SMTP(GMAIL_SMTP, GMAIL_PORT) as server:
            server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
        
        logger.info("Email sent successfully")
        return True
        
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error occurred: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def create_email_body(
    target_id: str, row_data: dict, status: str, ods_url: str
) -> str:
    """
    Create a formatted HTML email body.
    
    Args:
        target_id: Visa application ID
        row_data: Dictionary containing the matching row data
        status: Visa decision status
        ods_url: URL of the ODS file
        
    Returns:
        HTML formatted email body
    """
    status_color = {
        "Granted": "#28a745",
        "Refused": "#dc3545",
        "Found": "#007bff"
    }.get(status, "#6c757d")
    
    row_html = ""
    for key, value in row_data.items():
        if value:
            row_html += f"<tr><td style='padding: 8px; border: 1px solid #ddd; font-weight: bold;'>{key}</td><td style='padding: 8px; border: 1px solid #ddd;'>{value}</td></tr>"
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .header {{ background-color: {status_color}; color: white; padding: 20px; border-radius: 4px; text-align: center; margin-bottom: 20px; }}
            .header h1 {{ margin: 0; font-size: 24px; }}
            .status-badge {{ display: inline-block; background-color: {status_color}; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold; margin: 10px 0; }}
            .details {{ margin: 20px 0; }}
            .details h2 {{ color: #333; margin-top: 0; }}
            table {{ width: 100%; border-collapse: collapse; }}
            .footer {{ color: #999; font-size: 12px; margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; }}
            .warning {{ background-color: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 4px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎉 Visa Decision Found!</h1>
                <p style="margin: 10px 0; font-size: 18px;">Application ID: <strong>{target_id}</strong></p>
            </div>
            
            <div class="status-badge">Status: {status}</div>
            
            <div class="details">
                <h2>Decision Details</h2>
                <table>
                    {row_html}
                </table>
            </div>
            
            <div class="warning">
                <strong>Note:</strong> Please verify this information on the official Ireland Embassy website.
            </div>
            
            <div class="footer">
                <p>Check Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                <p>Source: <a href="{ods_url}">{urlparse(ods_url).path.split('/')[-1]}</a></p>
                <p>This is an automated notification from Ireland Visa Monitor.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html


def main() -> int:
    """
    Main execution function.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Get environment variables
        target_id, email_user, email_password = get_environment_variables()
        logger.info("=" * 60)
        logger.info("Ireland Visa Monitor - Starting check")
        logger.info(f"Target Application ID: {target_id}")
        logger.info(f"Email: {email_user}")
        logger.info("=" * 60)
        
        # Find ODS URL
        ods_url = find_ods_url()
        
        # Download ODS file
        ods_path = download_ods_file(ods_url)
        
        # Search for application ID
        result = search_application_id(ods_path, target_id)
        
        # Load state
        state = load_state()
        
        if result:
            row_data, status, sheet_idx = result
            logger.info(f"Status detected: {status}")
            
            # Check if notification already sent
            notification_sent = state.get("notification_sent", False)
            
            if notification_sent:
                logger.info("Notification already sent previously. Skipping email.")
            else:
                # Send email
                email_success = send_email(
                    email_user,
                    email_password,
                    target_id,
                    row_data,
                    status,
                    ods_url
                )
                
                if email_success:
                    # Update state
                    state["notification_sent"] = True
                    state["notification_sent_at"] = datetime.now().isoformat()
                    state["status"] = status
                    save_state(state)
                    logger.info("State updated: notification sent")
                else:
                    logger.error("Failed to send email notification")
                    return 1
        else:
            logger.info(f"Application ID '{target_id}' not found in decisions list")
            state["last_check"] = datetime.now().isoformat()
            save_state(state)
        
        logger.info("=" * 60)
        logger.info("Check completed successfully")
        logger.info("=" * 60)
        return 0
        
    except (ValueError, RuntimeError) as e:
        logger.error(f"Application error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    finally:
        # Cleanup
        if os.path.exists("decisions.ods"):
            try:
                os.remove("decisions.ods")
                logger.info("Cleaned up downloaded ODS file")
            except Exception as e:
                logger.warning(f"Failed to cleanup ODS file: {e}")


if __name__ == "__main__":
    sys.exit(main())
