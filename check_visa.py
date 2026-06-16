import requests

url = "https://www.ireland.ie/en/india/newdelhi/services/visas/processing-times-and-decisions/"

html = requests.get(url, timeout=30).text

print("NEW DELHI COUNT:", html.lower().count("new delhi"))
print("ODS COUNT:", html.lower().count(".ods"))

lines = html.splitlines()

for i, line in enumerate(lines):
    if "ods" in line.lower():
        print("\nLINE", i)
        print(line)

raise Exception("DEBUG COMPLETE")
