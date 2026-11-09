"""抓取所有數據源，輸出到 docs/data/*.json。
單一來源失敗時保留上次成功的數據，並在 meta.json 記錄錯誤。"""

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

from config import GROUPS, TICKERS, WIKI_ARTICLES

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# Wikimedia 和 Overpass 要求可識別的 User-Agent
REPO = os.environ.get("GITHUB_REPOSITORY", "your-name/macau-hotel-dashboard")
SESSION = requests.Session()
SESSION.headers["User-Agent"] = f"MacauHotelDashboard/1.0 (https://github.com/{REPO})"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def save(name: str, payload: dict) -> None:
    path = OUT / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def match_group(text: str):
    t = text.lower()
    for key, g in GROUPS.items():
        if any(x in t for x in g.get("exclude", [])):
            continue
        if any(k in t for k in g["keywords"]):
            return key
    return None


# ---------- OpenStreetMap ----------
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_QUERY = """
[out:json][timeout:90];
area["ISO3166-1"="MO"]->.mo;
nwr["tourism"="hotel"](area.mo);
out center tags;
"""


def fetch_osm():
    last_err = None
    for url in OVERPASS_URLS:
        try:
            r = SESSION.post(url, data={"data": OVERPASS_QUERY}, timeout=120)
            r.raise_for_status()
            elements = r.json()["elements"]
            break
        except Exception as e:  # 換下一個鏡像
            last_err = e
    else:
        raise RuntimeError(f"所有 Overpass 鏡像失敗: {last_err}")

    hotels = []
    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None or lon is None:
            continue
        text = " ".join(
            tags.get(k, "")
            for k in ("name", "name:en", "name:zh", "name:zh-Hant", "name:pt", "brand", "operator")
        )
        hotels.append({
            "osm": f"{el['type']}/{el['id']}",
            "name": tags.get("name") or tags.get("name:zh") or tags.get("name:en") or "(未命名)",
            "name_en": tags.get("name:en", ""),
            "brand": tags.get("brand", ""),
            "operator": tags.get("operator", ""),
            "stars": tags.get("stars", ""),
            "rooms": tags.get("rooms", ""),
            "lat": lat,
            "lon": lon,
            "group": match_group(text),
        })

    if not hotels:
        raise RuntimeError("Overpass 返回 0 間酒店，不覆蓋舊數據")
    save("osm_hotels", {
        "updated": now_iso(),
        "source": "© OpenStreetMap contributors (ODbL)",
        "hotels": hotels,
    })
    return {"hotels": len(hotels)}


# ---------- Wikidata ----------
SPARQL = """
SELECT ?hotel ?hotelLabel ?enLabel ?operatorLabel ?ownerLabel ?rooms ?opening ?coord WHERE {
  ?hotel wdt:P131* wd:Q14773 .
  ?hotel wdt:P31/wdt:P279* wd:Q27686 .
  OPTIONAL { ?hotel rdfs:label ?enLabel . FILTER(LANG(?enLabel) = "en") }
  OPTIONAL { ?hotel wdt:P137 ?operator . }
  OPTIONAL { ?hotel wdt:P127 ?owner . }
  OPTIONAL { ?hotel wdt:P8733 ?rooms . }
  OPTIONAL { ?hotel wdt:P1619 ?opening . }
  OPTIONAL { ?hotel wdt:P625 ?coord . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh-hant,zh,en". }
}
"""


def fetch_wikidata():
    r = SESSION.get(
        "https://query.wikidata.org/sparql",
        params={"query": SPARQL, "format": "json"},
        timeout=90,
    )
    r.raise_for_status()
    rows = r.json()["results"]["bindings"]

    hotels = {}
    for row in rows:
        def v(key, row=row):
            return row.get(key, {}).get("value")

        qid = v("hotel").rsplit("/", 1)[-1]
        h = hotels.setdefault(qid, {
            "qid": qid, "name": v("hotelLabel"), "name_en": v("enLabel") or "",
            "operators": set(), "rooms": None, "opened": None, "lat": None, "lon": None,
        })
        for k in ("operatorLabel", "ownerLabel"):
            if v(k):
                h["operators"].add(v(k))
        if v("rooms") and h["rooms"] is None:
            try:
                h["rooms"] = int(float(v("rooms")))
            except ValueError:
                pass
        if v("opening") and h["opened"] is None:
            h["opened"] = v("opening")[:4]
        if v("coord") and h["lat"] is None:
            lon, lat = v("coord").removeprefix("Point(").removesuffix(")").split()
            h["lat"], h["lon"] = float(lat), float(lon)

    out = []
    for h in hotels.values():
        h["operators"] = sorted(h["operators"])
        h["group"] = match_group(" ".join([h["name"] or "", h["name_en"], *h["operators"]]))
        out.append(h)

    if not out:
        raise RuntimeError("Wikidata 返回 0 間酒店，不覆蓋舊數據")
    save("wikidata_hotels", {"updated": now_iso(), "source": "Wikidata (CC0)", "hotels": out})
    return {"hotels": len(out), "with_rooms": sum(1 for h in out if h["rooms"])}


# ---------- 維基百科瀏覽量 ----------
def fetch_pageviews(days: int = 180):
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    articles, missing = {}, []
    for title, group in WIKI_ARTICLES.items():
        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/user/{quote(title, safe='')}/daily/"
            f"{start:%Y%m%d}/{end:%Y%m%d}"
        )
        r = SESSION.get(url, timeout=30)
        if r.status_code == 404:
            missing.append(title)
            continue
        r.raise_for_status()
        articles[title] = {
            "group": group,
            "data": [
                [f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}", i["views"]]
                for i in r.json()["items"]
            ],
        }
        time.sleep(0.2)

    if not articles:
        raise RuntimeError("所有維基條目都抓取失敗")
    save("pageviews", {
        "updated": now_iso(),
        "source": "Wikimedia Pageviews API (en.wikipedia, user agent)",
        "articles": articles,
        "missing": missing,
    })
    return {"articles": len(articles), "missing": missing}


# ---------- 股價 ----------
def fetch_stocks():
    import yfinance as yf

    df = yf.download(
        list(TICKERS), period="1y", interval="1d",
        auto_adjust=True, progress=False, threads=False,
    )
    if df.empty:
        raise RuntimeError("yfinance 沒有返回數據")
    close = df["Close"]

    out = {}
    for ticker, group in TICKERS.items():
        if ticker not in close:
            continue
        s = close[ticker].dropna()
        if s.empty:
            continue
        out[ticker] = {
            "group": group,
            "currency": "HKD" if ticker.endswith(".HK") else "USD",
            "last": round(float(s.iloc[-1]), 4),
            "change_1y_pct": round(float(s.iloc[-1] / s.iloc[0] - 1) * 100, 2),
            "data": [[d.strftime("%Y-%m-%d"), round(float(p), 4)] for d, p in s.items()],
        }

    if not out:
        raise RuntimeError("所有股票代號都沒有數據")
    save("stocks", {"updated": now_iso(), "source": "Yahoo Finance via yfinance", "tickers": out})
    return {"tickers": len(out)}


def main():
    meta_path = OUT / "meta.json"
    meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else {}

    jobs = {
        "osm": fetch_osm,
        "wikidata": fetch_wikidata,
        "pageviews": fetch_pageviews,
        "stocks": fetch_stocks,
    }
    failed = 0
    for name, fn in jobs.items():
        print(f"[{name}] 抓取中…", flush=True)
        try:
            info = fn()
            meta[name] = {"ok": True, "updated": now_iso(), "info": info}
            print(f"[{name}] 完成: {info}")
        except Exception as e:
            failed += 1
            prev = meta.get(name, {})
            meta[name] = {
                **prev, "ok": False,
                "last_error": f"{type(e).__name__}: {e}",
                "last_attempt": now_iso(),
            }
            print(f"[{name}] 失敗: {e}", file=sys.stderr)

    meta["groups"] = {k: {"name": g["name"], "color": g["color"]} for k, g in GROUPS.items()}
    save("meta", meta)
    sys.exit(1 if failed == len(jobs) else 0)


if __name__ == "__main__":
    main()
