import requests
import os

PAGE_URL = (
    "https://www.ireland.ie/en/india/newdelhi/services/"
    "visas/processing-times-and-decisions/"
)

headers = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

response = requests.get(
    PAGE_URL,
    headers=headers,
    timeout=30,
    allow_redirects=True
)

print("STATUS CODE:", response.status_code)
print("FINAL URL:", response.url)
print("PAGE LENGTH:", len(response.text))

print("\n===== FIRST 5000 CHARACTERS =====\n")
print(response.text[:5000])

raise Exception("STOP FOR DEBUG")
