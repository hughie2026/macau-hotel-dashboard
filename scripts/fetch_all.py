"""抓取所有數據源，輸出到 docs/data/*.json。
單一來源失敗時保留上次成功的數據，並在 meta.json 記錄錯誤。"""

import datetime as dt
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import requests

from config import (
    FIN_CURRENCY, FX_TO_USD, GDELT_QUERIES, GROUPS, NEWS_EDITIONS, NEWS_QUERIES,
    SEC_COMPANIES, TICKERS, WIKI_ARTICLES, WIKI_LANGS,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data"
OUT.mkdir(parents=True, exist_ok=True)

REPO = os.environ.get("GITHUB_REPOSITORY", "your-name/macau-hotel-dashboard")
SESSION = requests.Session()
SESSION.headers["User-Agent"] = f"MacauHotelDashboard/1.0 (https://github.com/{REPO})"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def iso_z(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


# ---------- 年度財報（Yahoo Finance） ----------
FIN_ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "net_income": [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operation Net Minority Interest",
    ],
}


def fetch_financials():
    import yfinance as yf

    prev = load_previous("financials").get("companies", {})
    companies, errors = {}, {}

    for ticker, group in TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            df = t.income_stmt
            if df is None or df.empty:
                raise RuntimeError("沒有年度損益表")

            currency = None
            try:
                currency = (t.get_info() or {}).get("financialCurrency")
            except Exception:
                pass  # get_info 經常被限流，改用 config 裡的後備貨幣
            currency = currency or FIN_CURRENCY.get(ticker, "USD")
            rate = FX_TO_USD.get(currency)
            if rate is None:
                raise RuntimeError(f"未知的申報貨幣 {currency}，請在 FX_TO_USD 加入匯率")

            rows = {}
            for field, names in FIN_ROWS.items():
                name = next((n for n in names if n in df.index), None)
                if name is None:
                    continue
                s = df.loc[name]
                if hasattr(s, "ndim") and s.ndim > 1:
                    s = s.iloc[0]
                s = s.dropna()
                rows[field] = sorted(
                    [c.strftime("%Y-%m-%d"), round(float(v) / rate)] for c, v in s.items()
                )
            if not rows.get("revenue"):
                raise RuntimeError("損益表裡找不到收入")

            companies[ticker] = {
                "group": group,
                "currency": currency,
                "fx_to_usd": rate,
                "revenue": rows.get("revenue", []),
                "net_income": rows.get("net_income", []),
                "updated": now_iso(),
            }
            print(f"  [financials] {ticker} 完成：{len(rows['revenue'])} 年，{currency}", flush=True)
        except Exception as e:
            errors[ticker] = f"{type(e).__name__}: {e}"[:200]
            print(f"  [financials] {ticker} 失敗: {e}", flush=True)
            if ticker in prev:
                companies[ticker] = {**prev[ticker], "stale": True}
        time.sleep(1)

    if not any(not c.get("stale") for c in companies.values()):
        raise RuntimeError(f"沒有成功取得任何公司的財報: {errors}")
    save("financials", {
        "updated": now_iso(),
        "source": "Yahoo Finance annual income statement via yfinance",
        "unit": "USD",
        "companies": companies,
        "errors": errors,
    })
    return {"companies": len(companies), "errors": list(errors)}


# ---------- 新聞（Google News RSS） ----------
NEWS_URL = "https://news.google.com/rss/search"
NEWS_WINDOW = "7d"         # 每次查詢最近 7 日，結果累積到 news_store.json
NEWS_KEEP_DAYS = 90
NEWS_MAX_PER_GROUP = 3000


def parse_rss(xml_text: str, lang: str) -> list:
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        if not link.startswith(("http://", "https://")):
            continue
        try:
            date = parsedate_to_datetime(it.findtext("pubDate"))
        except (TypeError, ValueError):
            continue
        if date.tzinfo is None:
            date = date.replace(tzinfo=dt.timezone.utc)
        src = it.find("source")
        source = (src.text or "").strip() if src is not None and src.text else ""
        title = (it.findtext("title") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        items.append({"title": title, "url": link, "source": source, "lang": lang, "date": iso_z(date)})
    return items


def fetch_news():
    prev = load_previous("news_store")
    store = {
        k: {a["url"]: a for a in prev.get("groups", {}).get(k, [])}
        for k in NEWS_QUERIES
    }
    today = dt.datetime.now(dt.timezone.utc).date()
    since = prev.get("since") or (today - dt.timedelta(days=6)).isoformat()

    errors, ok_requests, new_items = {}, 0, 0
    for key, queries in NEWS_QUERIES.items():
        for lang, q in queries.items():
            params = {"q": f"{q} when:{NEWS_WINDOW}", **NEWS_EDITIONS[lang]}
            try:
                r = SESSION.get(NEWS_URL, params=params, timeout=(10, 30))
                r.raise_for_status()
                items = parse_rss(r.text, lang)
            except Exception as e:
                errors[f"{key}:{lang}"] = f"{type(e).__name__}: {e}"[:200]
                print(f"  [news] {key} {lang} 失敗: {e}", flush=True)
                continue
            ok_requests += 1
            for a in items:
                if a["url"] not in store[key]:
                    store[key][a["url"]] = a
                    new_items += 1
            print(f"  [news] {key} {lang}：{len(items)} 篇", flush=True)
            time.sleep(1.5)

    if ok_requests == 0:
        raise RuntimeError(f"Google News RSS 全部請求失敗: {errors}")

    cutoff = today - dt.timedelta(days=NEWS_KEEP_DAYS - 1)
    start = max(dt.date.fromisoformat(since), cutoff)
    days = [(start + dt.timedelta(days=i)).isoformat() for i in range((today - start).days + 1)]
    first = days[0]

    groups, kept = {}, {}
    for key, m in store.items():
        arts = sorted(
            (a for a in m.values() if a["date"][:10] >= cutoff.isoformat()),
            key=lambda a: a["date"], reverse=True,
        )[:NEWS_MAX_PER_GROUP]
        kept[key] = arts
        recent = [a for a in arts if a["date"][:10] >= first]
        daily = Counter(a["date"][:10] for a in recent)
        groups[key] = {
            "volume": [[d, daily.get(d, 0)] for d in days],
            "total": len(recent),
            "by_lang": dict(Counter(a["lang"] for a in recent)),
            "publishers": Counter(a["source"] for a in recent if a["source"]).most_common(10),
            "articles": arts[:10],
        }

    save("news_store", {"updated": now_iso(), "since": start.isoformat(), "groups": kept})
    save("news", {
        "updated": now_iso(),
        "source": "Google News RSS",
        "since": first,
        "until": days[-1],
        "days": len(days),
        "groups": groups,
        "errors": errors,
    })
    return {"requests_ok": ok_requests, "new_articles": new_items, "errors": list(errors)}


# ---------- SEC EDGAR（可選） ----------
SEC_REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
SEC_NET_INCOME_TAGS = ["NetIncomeLoss", "ProfitLoss"]
SEC_FALLBACK_CIK = {"LVS": 1300514, "WYNN": 1174922, "MGM": 789570, "MLCO": 1381640}


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


def sec_get(url: str, headers: dict) -> requests.Response:
    r = None
    for attempt in range(3):
        r = requests.get(url, headers=headers, timeout=60)
        if r.status_code == 403:
            raise RuntimeError("SEC 拒絕請求 (403)。請確認 SEC_CONTACT 是有效電郵")
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        return r
    r.raise_for_status()
    return r


def fetch_sec():
    contact = os.environ.get("SEC_CONTACT", "").strip()
    headers = {"User-Agent": f"MacauHotelDashboard {contact}", "Accept-Encoding": "gzip, deflate"}

    ciks = dict(SEC_FALLBACK_CIK)
    try:
        r = sec_get("https://www.sec.gov/files/company_tickers.json", headers)
        r.raise_for_status()
        for v in r.json().values():
            t = str(v.get("ticker", "")).upper()
            if t in SEC_COMPANIES:
                ciks[t] = int(v["cik_str"])
    except Exception as e:
        print(f"  [sec] 代號表下載失敗，改用內置 CIK: {e}", flush=True)

    companies, missing = {}, []
    for ticker, info in SEC_COMPANIES.items():
        cik = ciks.get(ticker)
        if cik is None:
            missing.append(ticker)
            continue
        time.sleep(0.5)
        r = sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers)
        if r.status_code == 404:
            missing.append(ticker)
            continue
        r.raise_for_status()
        body = r.json()
        entity = body.get("entityName", "")
        if info["name"].split()[0].lower() not in entity.lower():
            missing.append(f"{ticker}（CIK 對應到 {entity}）")
            continue
        gaap = body.get("facts", {}).get("us-gaap", {})
        revenue = sec_periods(gaap, SEC_REVENUE_TAGS)
        if not revenue["quarterly"] and not revenue["annual"]:
            missing.append(ticker)
            continue
        companies[ticker] = {
            "group": info["group"], "name": info["name"], "entity": entity, "cik": cik,
            "revenue": revenue, "net_income": sec_periods(gaap, SEC_NET_INCOME_TAGS),
        }
        print(f"  [sec] {ticker} 完成：{len(revenue['quarterly'])} 季", flush=True)

    if not companies:
        raise RuntimeError(f"SEC 沒有任何公司的數據，缺少: {missing}")
    save("sec", {
        "updated": now_iso(),
        "source": "SEC EDGAR XBRL companyfacts API",
        "companies": companies,
        "missing": missing,
    })
    return {"companies": len(companies), "missing": missing}


# ---------- GDELT 新聞語調（可選） ----------
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_TIMESPAN = "3months"
GDELT_BUDGET = int(os.environ.get("GDELT_BUDGET", "180"))
GDELT_GAP = 5.5
GDELT_TIMEOUT = (10, 40)


class GdeltOutOfTime(Exception):
    """剩餘時間不夠再發一次請求"""


class GdeltUnreachable(Exception):
    """一開始就連續連線失敗"""


class GdeltClient:
    def __init__(self, budget: int):
        self.deadline = time.monotonic() + budget
        self.next_allowed = 0.0
        self.ok_count = 0
        self.net_fail = 0

    def left(self) -> float:
        return self.deadline - time.monotonic()

    def get(self, query: str, mode: str, **extra) -> dict:
        params = {"query": query, "mode": mode, "format": "json",
                  "timespan": GDELT_TIMESPAN, **extra}
        last_err = "未知錯誤"
        for _ in range(2):
            wait = max(0.0, self.next_allowed - time.monotonic())
            if self.left() < wait + sum(GDELT_TIMEOUT):
                raise GdeltOutOfTime()
            time.sleep(wait)
            try:
                r = SESSION.get(GDELT_URL, params=params, timeout=GDELT_TIMEOUT)
            except (requests.Timeout, requests.ConnectionError) as e:
                self.next_allowed = time.monotonic() + GDELT_GAP
                self.net_fail += 1
                last_err = type(e).__name__
                if self.ok_count == 0 and self.net_fail >= 3:
                    raise GdeltUnreachable(f"連續 {self.net_fail} 次連線失敗（{last_err}）")
                continue
            self.next_allowed = time.monotonic() + GDELT_GAP
            text = r.text
            if r.status_code == 429 or "limit requests" in text[:300].lower():
                last_err = "被限流"
                self.next_allowed = time.monotonic() + 15
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}：{text[:120]}")
            self.ok_count += 1
            if not text.strip():
                return {}
            try:
                return json.loads(text, strict=False)
            except ValueError:
                raise RuntimeError(f"回應不是 JSON：{text[:150]}")
        raise RuntimeError(f"請求失敗：{last_err}")


def timeline_points(data: dict) -> list:
    """把 GDELT 時間線整理成每日平均值。"""
    series = (data.get("timeline") or [{}])[0].get("data", [])
    buckets = {}
    for p in series:
        d, v = str(p.get("date", "")), p.get("value")
        if len(d) < 8 or v is None:
            continue
        buckets.setdefault(f"{d[:4]}-{d[4:6]}-{d[6:8]}", []).append(float(v))
    return [[day, round(sum(v) / len(v), 3)] for day, v in sorted(buckets.items())]


def fetch_gdelt():
    prev = load_previous("gdelt").get("groups", {})
    client = GdeltClient(GDELT_BUDGET)
    groups = {k: prev[k] for k in GDELT_QUERIES if prev.get(k, {}).get("tone")}
    order = sorted(GDELT_QUERIES, key=lambda k: prev.get(k, {}).get("updated", ""))
    refreshed, skipped, errors = [], [], {}

    for i, key in enumerate(order):
        try:
            pts = timeline_points(client.get(GDELT_QUERIES[key], "timelinetone"))
        except GdeltOutOfTime:
            skipped = order[i:]
            print(f"  [gdelt] 時間用完，{'、'.join(skipped)} 留待下次", flush=True)
            break
        except GdeltUnreachable as e:
            errors[key] = str(e)
            skipped = order[i + 1:]
            print(f"  [gdelt] {e}，停止", flush=True)
            break
        except Exception as e:
            errors[key] = f"{type(e).__name__}: {e}"[:200]
            print(f"  [gdelt] {key} 失敗: {e}", flush=True)
            continue
        vals = [v for _, v in pts]
        groups[key] = {
            "tone": pts,
            "avg_tone": round(sum(vals) / len(vals), 3) if vals else None,
            "updated": now_iso(),
        }
        refreshed.append(key)
        print(f"  [gdelt] {key} 完成（剩餘 {int(client.left())} 秒）", flush=True)

    if not refreshed:
        raise RuntimeError(f"GDELT 本次沒有更新任何集團。錯誤: {errors}")
    save("gdelt", {
        "updated": now_iso(),
        "source": "The GDELT Project, DOC 2.0 API",
        "timespan": GDELT_TIMESPAN,
        "groups": {k: groups[k] for k in GDELT_QUERIES if k in groups},
        "errors": errors,
        "skipped": skipped,
    })
    return {"refreshed": refreshed, "skipped": skipped, "errors": list(errors)}


def main():
    meta = load_previous("meta")
    meta.pop("wikidata", None)
    meta["groups"] = {k: {"name": g["name"], "color": g["color"]} for k, g in GROUPS.items()}

    # 穩定的數據源在前，可選的 SEC 和 GDELT 在最後
    jobs = [
        ("osm", fetch_osm),
        ("pageviews", fetch_pageviews),
        ("stocks", fetch_stocks),
        ("financials", fetch_financials),
        ("news", fetch_news),
        ("sec", fetch_sec),
        ("gdelt", fetch_gdelt),
    ]
    for name, fn in jobs:
        if name == "sec" and "@" not in os.environ.get("SEC_CONTACT", ""):
            meta["sec"] = {"ok": False, "disabled": True,
                           "last_error": "未設定 SEC_CONTACT，已跳過（可選）"}
            print("[sec] 未設定 SEC_CONTACT，跳過", flush=True)
            save("meta", meta)
            continue

        print(f"[{name}] 抓取中…", flush=True)
        started = time.monotonic()
        try:
            info = fn()
            meta[name] = {"ok": True, "updated": now_iso(), "info": info}
            print(f"[{name}] 完成（{time.monotonic() - started:.0f} 秒）: {info}", flush=True)
        except Exception as e:
            prev = meta.get(name, {})
            prev.pop("disabled", None)
            meta[name] = {
                **prev, "ok": False,
                "last_error": f"{type(e).__name__}: {e}"[:300],
                "last_attempt": now_iso(),
            }
            print(f"[{name}] 失敗（{time.monotonic() - started:.0f} 秒）: {e}", file=sys.stderr, flush=True)
        save("meta", meta)  # 每完成一個數據源就保存


if __name__ == "__main__":
    main()
