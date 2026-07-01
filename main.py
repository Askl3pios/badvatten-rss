from pathlib import Path
from datetime import datetime, timezone
from email.utils import format_datetime
import html
import requests
from feedgen.feed import FeedGenerator

API_BASE = "https://gw.havochvatten.se/external-public/bathing-waters/v2"
OUTPUT_DIR = Path("docs")
OUTPUT_DIR.mkdir(exist_ok=True)

SELECTED_WATERS = [
    {"municipality": "Karlshamn", "name": "Kollevik"},
    {"municipality": "Halmstad", "name": "Tylösand"},
    {"municipality": "Halmstad", "name": "Hagöns campingplats"},
    {"municipality": "Torsås", "name": "Fulvik"},
    {"municipality": "Malmö", "name": "Sibbarp"},
    {"municipality": "Malmö", "name": "Scaniabadplatsen, Djuphavsbadet"},
]

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "badvatten-rss/1.0"
}


def get_json(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def normalize(text):
    return (text or "").strip().casefold()


def fetch_all_bathing_waters():
    data = get_json(f"{API_BASE}/bathing-waters")
    if "waters" in data:
        return data["waters"]
    if "bathingWaters" in data:
        return data["bathingWaters"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Okänd svarstruktur från /bathing-waters: {type(data)}")


def find_selected_ids():
    waters = fetch_all_bathing_waters()
    found = []

    for wanted in SELECTED_WATERS:
        match = None
        for w in waters:
            municipality = ((w.get("municipality") or {}).get("name") or "")
            name = w.get("name") or ""
            if normalize(municipality) == normalize(wanted["municipality"]) and normalize(name) == normalize(wanted["name"]):
                match = {
                    "id": w.get("id"),
                    "name": name,
                    "municipality": municipality,
                }
                break

        if not match:
            raise RuntimeError(
                f"Kunde inte hitta badplats-ID för {wanted['municipality']} / {wanted['name']}"
            )
        found.append(match)

    return found


def fetch_details(bathing_water_id):
    return get_json(f"{API_BASE}/bathing-waters/{bathing_water_id}")


def latest_result(results):
    if not results:
        return {}
    return sorted(results, key=lambda x: x.get("takenAt", ""), reverse=True)[0]


def latest_forecast(forecasts):
    if not forecasts:
        return {}
    return sorted(forecasts, key=lambda x: int(x.get("measHour", 0)), reverse=True)[0]


def make_summary(details):
    bw = details.get("bathingWater", {})
    municipality = (bw.get("municipality") or {}).get("name", "")
    name = bw.get("name", "")
    result = latest_result(details.get("results") or [])
    forecast = latest_forecast(details.get("waterTemperature") or [])

    temp = forecast.get("waterTemp") or result.get("waterTemp") or "saknas"
    temp_source = "prognos" if forecast.get("waterTemp") else ("senaste prov" if result.get("waterTemp") else "ingen temperatur")
    taken_at = result.get("takenAt", "")
    sample_assess = result.get("sampleAssessIdText", "saknas")
    algal = result.get("algalIdText", "saknas")
    description = bw.get("description", "")

    return {
        "municipality": municipality,
        "name": name,
        "temperature": str(temp),
        "temperature_source": temp_source,
        "taken_at": taken_at,
        "sample_assess": sample_assess,
        "algal": algal,
        "description": description,
    }


def build_feed(items):
    now = datetime.now(timezone.utc)

    fg = FeedGenerator()
    fg.id("https://example.invalid/badvatten-rss")
    fg.title("Daglig badrapport")
    fg.link(href="https://example.invalid/badvatten-rss", rel="alternate")
    fg.description("Daglig RSS med vattentemperatur och badvattenstatus från utvalda svenska badplatser.")
    fg.language("sv")
    fg.updated(now)

    for item in items:
        fe = fg.add_entry()
        item_id = f"{item['municipality']}::{item['name']}"
        fe.id(item_id)
        fe.title(f"{item['name']} ({item['municipality']}): {item['temperature']}°C")
        fe.link(href="https://www.havochvatten.se/badplatser-och-badvatten.html", rel="alternate")

        summary_text = (
            f"Temperatur: {item['temperature']}°C ({item['temperature_source']}). "
            f"Senaste prov: {item['sample_assess']}. "
            f"Algstatus: {item['algal']}. "
            f"Provdatum: {item['taken_at'] or 'saknas'}."
        )

        content_html = f"""
        <p><strong>Badplats:</strong> {html.escape(item['name'])}</p>
        <p><strong>Kommun:</strong> {html.escape(item['municipality'])}</p>
        <p><strong>Vattentemperatur:</strong> {html.escape(item['temperature'])}°C ({html.escape(item['temperature_source'])})</p>
        <p><strong>Senaste provbedömning:</strong> {html.escape(item['sample_assess'])}</p>
        <p><strong>Algstatus:</strong> {html.escape(item['algal'])}</p>
        <p><strong>Provdatum:</strong> {html.escape(item['taken_at'] or 'saknas')}</p>
        <p><strong>Beskrivning:</strong> {html.escape(item['description'] or 'saknas')}</p>
        """

        fe.summary(summary_text)
        fe.content(content_html, type="CDATA")
        fe.pubDate(now)
        fe.updated(now)

    fg.rss_file(str(OUTPUT_DIR / "rss.xml"), pretty=True)


def build_index():
    html_text = """<!doctype html>
<html lang="sv">
<head>
  <meta charset="utf-8">
  <title>Daglig badrapport</title>
</head>
<body>
  <h1>Daglig badrapport</h1>
  <p>RSS-feed: <a href="./rss.xml">rss.xml</a></p>
</body>
</html>
"""
    (OUTPUT_DIR / "index.html").write_text(html_text, encoding="utf-8")


def main():
    selected = find_selected_ids()
    items = []

    for water in selected:
        details = fetch_details(water["id"])
        items.append(make_summary(details))

    build_feed(items)
    build_index()


if __name__ == "__main__":
    main()
