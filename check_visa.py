import requests
import re

url = "https://www.ireland.ie/en/india/newdelhi/services/visas/processing-times-and-decisions/"

html = requests.get(url, timeout=30).text

for m in re.finditer(r"New Delhi", html, re.IGNORECASE):
    start = max(0, m.start() - 500)
    end = min(len(html), m.start() + 3000)
    print(html[start:end])
    print("\n" + "=" * 100 + "\n")
