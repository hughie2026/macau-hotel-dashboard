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

from config import (
    GDELT_QUERIES, GROUPS, SEC_COMPANIES, TICKERS, WIKI_ARTICLES, WIKI_LANGS,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# Wikimedia、Overpass、GDELT 要求可識別的 User-Agent
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


def load_previous(name: str) -> dict:
    path = OUT / f"{name}.json"
    try:
        return json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


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


# ---------- 多語言維基百科瀏覽量 ----------
WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


def wiki_titles(en_title: str) -> dict:
    """查出英文條目在各語言的標題，會自動跟隨重定向。條目不存在時返回空字典。"""
    r = SESSION.get(WIKI_API, params={
        "action": "query", "format": "json", "formatversion": 2,
        "redirects": 1, "prop": "langlinks", "lllimit": "max",
        "titles": en_title.replace("_", " "),
    }, timeout=30)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or pages[0].get("invalid"):
        return {}
    titles = {"en": pages[0]["title"]}
    for ll in pages[0].get("langlinks", []):
        if ll.get("lang") in WIKI_LANGS and ll.get("title"):
            titles[ll["lang"]] = ll["title"]
    return titles


def daily_views(lang: str, title: str, start: dt.date, end: dt.date):
    url = (
        f"{PAGEVIEWS_API}/{lang}.wikipedia/all-access/user/"
        f"{quote(title.replace(' ', '_'), safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}"
    )
    r = SESSION.get(url, timeout=30)
    if r.status_code == 404:  # 這段時間沒有瀏覽記錄
        return None
    r.raise_for_status()
    return [
        [f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}", i["views"]]
        for i in r.json()["items"]
    ]


def fetch_pageviews(days: int = 180):
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    articles, missing, errors = {}, [], []

    for key, group in WIKI_ARTICLES.items():
        titles = wiki_titles(key)
        time.sleep(0.1)
        if not titles:
            missing.append(key)
            continue
        views = {}
        for lang, title in titles.items():
            try:
                pts = daily_views(lang, title, start, end)
            except requests.RequestException as e:
                errors.append(f"{lang}:{title}: {e}")
                pts = None
            if pts:
                views[lang] = pts
            time.sleep(0.1)
        articles[key] = {"group": group, "titles": titles, "views": views}

    if not any(a["views"].get("en") for a in articles.values()):
        raise RuntimeError("沒有任何英文條目的瀏覽量數據，不覆蓋舊數據")
    save("pageviews", {
        "updated": now_iso(),
        "source": "Wikimedia Pageviews API (user agent)",
        "langs": WIKI_LANGS,
        "articles": articles,
        "missing": missing,
        "errors": errors[:20],
    })
    return {"articles": len(articles), "missing": missing, "errors": len(errors)}


# ---------- GDELT 新聞聲量 ----------
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def gdelt_request(query: str, mode: str, **extra) -> dict:
    params = {"query": query, "mode": mode, "format": "json", "timespan": "3months", **extra}
    for _ in range(3):
        time.sleep(6)  # GDELT 要求每 5 秒最多一次請求
        r = SESSION.get(GDELT_URL, params=params, timeout=90)
        if r.status_code == 429 or "limit requests" in r.text[:300].lower():
            time.sleep(30)
            continue
        r.raise_for_status()
        if not r.text.strip():
            return {}
        try:
            return r.json()
        except ValueError:
            # 查詢語法錯誤時 GDELT 會返回純文字說明
            raise RuntimeError(f"GDELT 回應不是 JSON：{r.text[:150]}")
    raise RuntimeError("GDELT 持續限流")


def timeline_points(data: dict, how: str) -> list:
    """把 GDELT 時間線整理成每日數據。how='sum' 加總，'mean' 取平均。"""
    series = (data.get("timeline") or [{}])[0].get("data", [])
    buckets = {}
    for p in series:
        d, v = str(p.get("date", "")), p.get("value")
        if len(d) < 8 or v is None:
            continue
        buckets.setdefault(f"{d[:4]}-{d[4:6]}-{d[6:8]}", []).append(float(v))
    out = []
    for day in sorted(buckets):
        vals = buckets[day]
        if how == "sum":
            out.append([day, int(sum(vals))])
        else:
            out.append([day, round(sum(vals) / len(vals), 3)])
    return out


def clean_article(a: dict) -> dict:
    s = str(a.get("seendate", ""))
    date = f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}Z" if len(s) >= 15 else ""
    return {
        "title": a.get("title", ""),
        "url": a["url"],
        "domain": a.get("domain", ""),
        "language": a.get("language", ""),
        "country": a.get("sourcecountry", ""),
        "date": date,
    }


def fetch_gdelt():
    prev = load_previous("gdelt").get("groups", {})
    groups, errors = {}, {}

    for key, query in GDELT_QUERIES.items():
        try:
            volume = timeline_points(gdelt_request(query, "timelinevolraw"), "sum")
            tone = timeline_points(gdelt_request(query, "timelinetone"), "mean")
            arts = gdelt_request(query, "artlist", maxrecords=10, sort="DateDesc").get("articles", [])
        except Exception as e:
            errors[key] = f"{type(e).__name__}: {e}"
            if key in prev:  # 沿用上次成功的數據
                groups[key] = {**prev[key], "stale": True}
            continue

        counts = dict(volume)
        weight = sum(counts.get(d, 0) for d, _ in tone)
        avg_tone = sum(t * counts.get(d, 0) for d, t in tone) / weight if weight else None
        groups[key] = {
            "query": query,
            "volume": volume,
            "tone": tone,
            "total": sum(counts.values()),
            "avg_tone": round(avg_tone, 3) if avg_tone is not None else None,
            "articles": [
                clean_article(a) for a in arts
                if str(a.get("url", "")).startswith(("http://", "https://"))
            ],
            "updated": now_iso(),
        }

    if not any(not g.get("stale") for g in groups.values()):
        raise RuntimeError(f"GDELT 全部查詢失敗: {errors}")
    save("gdelt", {
        "updated": now_iso(),
        "source": "The GDELT Project, DOC 2.0 API",
        "timespan": "3months",
        "groups": groups,
        "errors": errors,
    })
    return {"groups": len(groups), "errors": list(errors)}


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


# ---------- SEC EDGAR ----------
# 排在前面的標籤優先。不同公司、不同年份用的 XBRL 標籤不一樣
SEC_REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
SEC_NET_INCOME_TAGS = ["NetIncomeLoss", "ProfitLoss"]


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def sec_periods(facts: dict, tags: list, since: str = "2018-01-01") -> dict:
    best = {}  # (start, end) -> (標籤優先級, 申報日期, 數值)
    for rank, tag in enumerate(tags):
        for item in facts.get(tag, {}).get("units", {}).get("USD", []):
            s, e, val = item.get("start"), item.get("end"), item.get("val")
            if not s or not e or val is None or e < since:
                continue
            filed = item.get("filed", "")
            cur = best.get((s, e))
            # 同一期間在多份報告重複出現，取優先標籤中最新申報（含重述）的數字
            if cur is None or rank < cur[0] or (rank == cur[0] and filed > cur[1]):
                best[(s, e)] = (rank, filed, val)

    quarterly, annual = {}, {}
    for (s, e), (_, _, val) in best.items():
        n = _days(s, e)
        if 80 <= n <= 100:
            quarterly[(s, e)] = val
        elif 350 <= n <= 380:
            annual[(s, e)] = val

    # 10-K 通常不單獨報第四季，用全年減去前三季推算
    derived = {}
    for (s, e), total in annual.items():
        inside = [k for k in quarterly if k[0] >= s and k[1] <= e]
        if len(inside) == 3 and all(k[1] != e for k in inside):
            q4_start = dt.date.fromisoformat(max(k[1] for k in inside)) + dt.timedelta(days=1)
            derived[(q4_start.isoformat(), e)] = total - sum(quarterly[k] for k in inside)
    quarterly.update(derived)

    return {
        "quarterly": [[e, v] for (_, e), v in sorted(quarterly.items(), key=lambda x: x[0][1])],
        "annual": [[e, v] for (_, e), v in sorted(annual.items(), key=lambda x: x[0][1])],
    }


def fetch_sec():
    contact = os.environ.get("SEC_CONTACT", "").strip()
    if not contact:
        raise RuntimeError("未設定 SEC_CONTACT。SEC 要求 User-Agent 附上聯絡電郵，請在倉庫 Secrets 中加入")
    headers = {"User-Agent": f"MacauHotelDashboard/1.0 {contact}"}

    r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers, timeout=30)
    r.raise_for_status()
    ciks = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in r.json().values()}

    companies, missing = {}, []
    for ticker, info in SEC_COMPANIES.items():
        cik = ciks.get(ticker)
        if cik is None:
            missing.append(ticker)
            continue
        time.sleep(0.5)  # SEC 限制每秒最多 10 次請求
        r = requests.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
            headers=headers, timeout=60,
        )
        if r.status_code == 404:
            missing.append(ticker)
            continue
        r.raise_for_status()
        body = r.json()
        gaap = body.get("facts", {}).get("us-gaap", {})
        revenue = sec_periods(gaap, SEC_REVENUE_TAGS)
        if not revenue["quarterly"] and not revenue["annual"]:
            missing.append(ticker)
            continue
        companies[ticker] = {
            "group": info["group"],
            "name": info["name"],
            "entity": body.get("entityName", ""),
            "cik": cik,
            "revenue": revenue,
            "net_income": sec_periods(gaap, SEC_NET_INCOME_TAGS),
        }

    if not companies:
        raise RuntimeError(f"SEC 沒有任何公司的數據，缺少: {missing}")
    save("sec", {
        "updated": now_iso(),
        "source": "SEC EDGAR XBRL companyfacts API",
        "companies": companies,
        "missing": missing,
    })
    return {"companies": len(companies), "missing": missing}


def main():
    meta = load_previous("meta")
    meta.pop("wikidata", None)  # 清除已移除數據源的舊記錄

    jobs = {
        "osm": fetch_osm,
        "pageviews": fetch_pageviews,
        "gdelt": fetch_gdelt,
        "stocks": fetch_stocks,
        "sec": fetch_sec,
    }
    failed = 0
    for name, fn in jobs.items():
        print(f"[{name}] 抓取中…", flush=True)
        try:
            info = fn()
            meta[name] = {"ok": True, "updated": now_iso(), "info": info}
            print(f"[{name}] 完成: {info}", flush=True)
        except Exception as e:
            failed += 1
            prev = meta.get(name, {})
            meta[name] = {
                **prev, "ok": False,
                "last_error": f"{type(e).__name__}: {e}",
                "last_attempt": now_iso(),
            }
            print(f"[{name}] 失敗: {e}", file=sys.stderr, flush=True)

    meta["groups"] = {k: {"name": g["name"], "color": g["color"]} for k, g in GROUPS.items()}
    save("meta", meta)
    sys.exit(1 if failed == len(jobs) else 0)


if __name__ == "__main__":
    main()
