const VIOLET = "#57068c";
const VIOLET_DARK = "#330662";
const RED = "#b5121b";
const OTHER = { name: "其他 / 獨立", color: "#9a9a9a" };
const SOURCES = {
  osm: "OpenStreetMap",
  pageviews: "維基瀏覽量",
  gdelt: "GDELT 新聞",
  stocks: "股價",
  sec: "SEC 財報",
};

// ECharts 主題：紫灰配色，與頁面一致
const FONT = getComputedStyle(document.body).fontFamily;
const axisBase = {
  axisLine: { lineStyle: { color: "#b3b3b3" } },
  axisTick: { show: false },
  axisLabel: { color: "#404040" },
  splitLine: { show: false },
};
echarts.registerTheme("nyu", {
  color: [VIOLET, "#8900e1", VIOLET_DARK, "#b8a4d4", "#6d6d6d"],
  backgroundColor: "transparent",
  textStyle: { fontFamily: FONT, color: "#222" },
  categoryAxis: axisBase,
  timeAxis: axisBase,
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: "#6d6d6d" },
    splitLine: { lineStyle: { color: "#e6e6e6" } },
  },
  legend: { textStyle: { color: "#404040" } },
  tooltip: {
    backgroundColor: VIOLET_DARK,
    borderWidth: 0,
    textStyle: { color: "#fff" },
  },
});

async function load(name) {
  try {
    const r = await fetch(`data/${name}.json?t=${Date.now()}`);
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) {
    console.warn(`載入 ${name} 失敗`, e);
    return null;
  }
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const fmtTime = (iso) =>
  iso ? new Date(iso).toLocaleString("zh-HK", { timeZone: "Asia/Macau", hour12: false }) : "";

const toYi = (v) => +(v / 1e8).toFixed(2); // 美元 -> 億美元

function chart(id, option) {
  const c = echarts.init(document.getElementById(id), "nyu");
  c.setOption(option);
  window.addEventListener("resize", () => c.resize());
  return c;
}

function empty(id, msg = "暫無數據") {
  const el = document.getElementById(id);
  el.replaceChildren();
  const p = document.createElement("p");
  p.className = "empty";
  p.textContent = msg;
  el.appendChild(p);
}

function movingAvg(points, n, digits = 0) {
  return points.map((p, i) => {
    const win = points.slice(Math.max(0, i - n + 1), i + 1);
    return [p[0], +(win.reduce((s, x) => s + x[1], 0) / win.length).toFixed(digits)];
  });
}

const sortedPoints = (m) => [...m.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1));

const lineLegend = { type: "scroll", icon: "rect", itemWidth: 14, itemHeight: 4 };

(async function main() {
  const [meta, osm, views, stocks, news, sec] = await Promise.all(
    ["meta", "osm_hotels", "pageviews", "stocks", "gdelt", "sec"].map(load));

  const groups = meta?.groups ?? {};
  const gInfo = (k) => groups[k] ?? OTHER;
  const groupKeys = [...Object.keys(groups), null];

  renderStatus(meta);
  renderKpis(osm, stocks, news);

  if (osm?.hotels?.length) {
    renderMap(osm.hotels, groupKeys, gInfo);
    renderCount(osm.hotels, groupKeys, gInfo);
    renderBrands(osm.hotels);
    renderTable(osm.hotels, gInfo);
  } else {
    ["map", "chart-count", "chart-brands"].forEach((id) => empty(id));
  }

  if (views?.articles) {
    renderViews(views, gInfo);
    renderLangs(views, gInfo);
  } else {
    ["chart-views", "chart-langs", "chart-langmix"].forEach((id) => empty(id));
  }

  if (news?.groups && Object.keys(news.groups).length) {
    renderNews(news, gInfo);
  } else {
    ["chart-news", "chart-sov", "chart-tone"].forEach((id) => empty(id));
    renderNewsList({ groups: {} }, gInfo);
  }

  if (stocks?.tickers) {
    renderStocks(stocks.tickers, gInfo);
    renderChange(stocks.tickers, gInfo);
  } else {
    empty("chart-stocks");
    empty("chart-change");
  }

  if (sec?.companies && Object.keys(sec.companies).length) {
    renderSec(sec, gInfo);
  } else {
    empty("chart-sec-rev");
    empty("chart-sec-ni");
  }
})();

function renderStatus(meta) {
  const el = document.getElementById("status");
  if (!meta) {
    el.textContent = "尚未有數據：請到 GitHub 的 Actions 頁面手動執行 Update data。";
    return;
  }
  for (const [key, label] of Object.entries(SOURCES)) {
    const m = meta[key] ?? {};
    const span = document.createElement("span");
    span.className = "badge " + (m.ok ? "ok" : "bad");
    span.textContent = m.ok
      ? `${label} · 更新於 ${fmtTime(m.updated)}`
      : `${label} · 最近一次抓取失敗${m.updated ? `，顯示 ${fmtTime(m.updated)} 的數據` : ""}`;
    if (!m.ok && m.last_error) span.title = m.last_error;
    el.appendChild(span);
  }
}

function renderKpis(osm, stocks, news) {
  const items = [];
  if (osm?.hotels) {
    const n = osm.hotels.length;
    const inGroups = osm.hotels.filter((h) => h.group).length;
    items.push(["OSM 收錄酒店", n.toLocaleString(), "間"]);
    items.push(["六大集團旗下", inGroups.toLocaleString(), `間，佔 ${n ? Math.round((inGroups / n) * 100) : 0}%`]);
  }
  if (news?.groups) {
    const total = Object.values(news.groups).reduce((s, g) => s + (g.total || 0), 0);
    items.push(["近 3 個月相關新聞", total.toLocaleString(), "篇，GDELT 收錄"]);
  }
  if (stocks?.tickers) {
    const list = Object.values(stocks.tickers);
    const up = list.filter((s) => s.change_1y_pct >= 0).length;
    items.push(["一年上漲的上市集團", `${up} / ${list.length}`, "家"]);
  }

  const box = document.getElementById("kpis");
  for (const [label, value, unit] of items) {
    const div = document.createElement("div");
    div.className = "kpi";
    const l = document.createElement("div");
    l.className = "kpi-label";
    l.textContent = label;
    const v = document.createElement("div");
    v.className = "kpi-value";
    v.textContent = value;
    const u = document.createElement("div");
    u.className = "kpi-unit";
    u.textContent = unit;
    div.append(l, v, u);
    box.appendChild(div);
  }
}

function renderMap(hotels, keys, gInfo) {
  const map = L.map("map", { scrollWheelZoom: false }).setView([22.165, 113.56], 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap contributors",
  }).addTo(map);

  // 先畫獨立酒店，集團酒店疊在上層
  const sorted = hotels.slice().sort((a, b) => (a.group ? 1 : 0) - (b.group ? 1 : 0));
  for (const h of sorted) {
    const g = gInfo(h.group);
    L.circleMarker([h.lat, h.lon], {
      radius: h.group ? 8 : 4,
      color: "#fff",
      weight: h.group ? 1.5 : 0.5,
      fillColor: g.color,
      fillOpacity: h.group ? 0.95 : 0.7,
    })
      .bindPopup(
        `<div class="popup-group" style="border-color:${g.color}">${esc(g.name)}</div>` +
        `<strong>${esc(h.name)}</strong>` +
        (h.name_en ? `<br>${esc(h.name_en)}` : "") +
        (h.brand ? `<br>品牌：${esc(h.brand)}` : "") +
        (h.stars ? `<br>星級：${esc(h.stars)}` : ""))
      .addTo(map);
  }

  const legend = document.getElementById("map-legend");
  for (const k of keys) {
    const g = gInfo(k);
    const item = document.createElement("span");
    item.className = "legend-item";
    const dot = document.createElement("span");
    dot.className = "legend-dot";
    dot.style.background = g.color;
    item.append(dot, document.createTextNode(g.name));
    legend.appendChild(item);
  }
}

function barChart(id, labels, values, colors) {
  chart(id, {
    tooltip: {},
    grid: { left: 110, right: 50, top: 10, bottom: 30 },
    xAxis: { type: "value" },
    yAxis: { type: "category", data: labels, inverse: true },
    series: [{
      type: "bar",
      barMaxWidth: 22,
      data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
      label: { show: true, position: "right", color: "#222", fontWeight: 600 },
    }],
  });
}

function renderCount(hotels, keys, gInfo) {
  const counts = keys.map((k) => hotels.filter((h) => (h.group ?? null) === k).length);
  barChart("chart-count", keys.map((k) => gInfo(k).name), counts, keys.map((k) => gInfo(k).color));
}

function renderBrands(hotels) {
  const m = new Map();
  for (const h of hotels) if (h.brand) m.set(h.brand, (m.get(h.brand) || 0) + 1);
  const top = [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15);
  if (!top.length) return empty("chart-brands", "OSM 中暫無 brand 標籤");
  barChart("chart-brands", top.map((x) => x[0]), top.map((x) => x[1]), top.map(() => VIOLET));
}

function renderViews(pv, gInfo) {
  const byGroup = {};
  for (const a of Object.values(pv.articles)) {
    const pts = a.views?.en;
    if (!pts) continue;
    const m = (byGroup[a.group] ??= new Map());
    for (const [d, v] of pts) m.set(d, (m.get(d) || 0) + v);
  }
  const series = Object.entries(byGroup).map(([g, m]) => ({
    name: gInfo(g).name, type: "line", showSymbol: false, smooth: true,
    lineStyle: { width: 2.5 },
    color: gInfo(g).color, data: movingAvg(sortedPoints(m), 7),
  }));
  if (!series.length) return empty("chart-views");
  chart("chart-views", {
    tooltip: { trigger: "axis" },
    legend: lineLegend,
    grid: { left: 60, right: 30, top: 50, bottom: 40 },
    xAxis: { type: "time" },
    yAxis: { type: "value", name: "日瀏覽量", nameTextStyle: { color: "#6d6d6d" } },
    series,
  });
  if (pv.missing?.length) {
    document.getElementById("views-note").textContent +=
      ` 以下條目不存在，已跳過：${pv.missing.join("、")}`;
  }
}

function renderLangs(pv, gInfo) {
  const langs = Object.entries(pv.langs || {});
  const articles = Object.values(pv.articles);

  let latest = "";
  for (const a of articles)
    for (const pts of Object.values(a.views || {}))
      for (const [d] of pts) if (d > latest) latest = d;
  if (!latest || !langs.length) {
    empty("chart-langs");
    empty("chart-langmix");
    return;
  }
  const cutDate = new Date(`${latest}T00:00:00Z`);
  cutDate.setUTCDate(cutDate.getUTCDate() - 29);
  const cut = cutDate.toISOString().slice(0, 10);

  const totals = {}; // 集團 -> 語言 -> 30 日瀏覽量
  for (const a of articles) {
    const t = (totals[a.group] ??= {});
    for (const [lang, pts] of Object.entries(a.views || {}))
      for (const [d, v] of pts) if (d >= cut) t[lang] = (t[lang] || 0) + v;
  }
  const gKeys = Object.keys(totals);
  const labels = gKeys.map((k) => gInfo(k).name);
  const base = {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0, type: "scroll" },
    grid: { left: 110, right: 30, top: 40, bottom: 30 },
    yAxis: { type: "category", data: labels, inverse: true },
  };

  chart("chart-langs", {
    ...base,
    xAxis: { type: "value" },
    series: langs.map(([code, l]) => ({
      name: l.name, type: "bar", stack: "v", color: l.color, barMaxWidth: 26,
      data: gKeys.map((g) => totals[g][code] || 0),
    })),
  });

  chart("chart-langmix", {
    ...base,
    tooltip: { ...base.tooltip, valueFormatter: (v) => `${v}%` },
    xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
    series: langs.map(([code, l]) => ({
      name: l.name, type: "bar", stack: "p", color: l.color, barMaxWidth: 26,
      data: gKeys.map((g) => {
        const sum = Object.values(totals[g]).reduce((s, x) => s + x, 0);
        return sum ? +(((totals[g][code] || 0) / sum) * 100).toFixed(1) : 0;
      }),
    })),
  });

  const coverage = langs
    .map(([code, l]) => `${l.name} ${articles.filter((a) => a.titles?.[code]).length}/${articles.length}`)
    .join("、");
  document.getElementById("langs-note").textContent =
    `統計期間：${cut} 至 ${latest}。有對應語言條目的度假村數量：${coverage}。`;
}

function renderNews(news, gInfo) {
  const entries = Object.entries(news.groups);

  chart("chart-news", {
    tooltip: { trigger: "axis" },
    legend: lineLegend,
    grid: { left: 50, right: 30, top: 50, bottom: 40 },
    xAxis: { type: "time" },
    yAxis: { type: "value", name: "篇 / 日", nameTextStyle: { color: "#6d6d6d" } },
    series: entries.map(([g, d]) => ({
      name: gInfo(g).name, type: "line", showSymbol: false, smooth: true,
      lineStyle: { width: 2.5 }, color: gInfo(g).color,
      data: movingAvg(d.volume || [], 7, 1),
    })),
  });

  chart("chart-sov", {
    tooltip: { trigger: "item", formatter: "{b}<br>{c} 篇（{d}%）" },
    legend: { bottom: 0, type: "scroll" },
    series: [{
      type: "pie",
      radius: ["45%", "70%"],
      center: ["50%", "45%"],
      itemStyle: { borderColor: "#fff", borderWidth: 2 },
      label: { formatter: "{d}%", fontWeight: 600 },
      data: entries.map(([g, d]) => ({
        name: gInfo(g).name, value: d.total || 0, itemStyle: { color: gInfo(g).color },
      })),
    }],
  });

  const toneRows = entries
    .filter(([, d]) => d.avg_tone != null)
    .sort((a, b) => b[1].avg_tone - a[1].avg_tone);
  if (toneRows.length) {
    chart("chart-tone", {
      tooltip: { formatter: (p) => `${p.name}<br>平均語調 ${p.value}` },
      grid: { left: 110, right: 60, top: 10, bottom: 30 },
      xAxis: { type: "value" },
      yAxis: { type: "category", inverse: true, data: toneRows.map(([g]) => gInfo(g).name) },
      series: [{
        type: "bar",
        barMaxWidth: 22,
        data: toneRows.map(([, d]) => ({
          value: d.avg_tone,
          itemStyle: { color: d.avg_tone >= 0 ? VIOLET : RED },
        })),
        label: { show: true, position: "right", color: "#222", fontWeight: 600 },
      }],
    });
  } else {
    empty("chart-tone");
  }

  const stale = entries.filter(([, d]) => d.stale).map(([g]) => gInfo(g).name);
  if (stale.length) {
    document.getElementById("news-note").textContent +=
      ` 以下集團本次抓取失敗，顯示上次成功的數據：${stale.join("、")}。`;
  }

  renderNewsList(news, gInfo);
}

function renderNewsList(news, gInfo) {
  const ul = document.getElementById("news-list");
  const items = Object.entries(news.groups)
    .flatMap(([g, d]) => (d.articles || []).map((a) => ({ ...a, group: g })))
    .sort((a, b) => (b.date || "").localeCompare(a.date || ""));

  // 同一篇報導可能同時命中多個集團，按網址去重
  const seen = new Set();
  const list = items
    .filter((a) => /^https?:\/\//i.test(a.url) && !seen.has(a.url) && seen.add(a.url))
    .slice(0, 24);

  if (!list.length) {
    const li = document.createElement("li");
    li.className = "news-empty";
    li.textContent = "暫無報導";
    ul.replaceChildren(li);
    return;
  }

  ul.replaceChildren(...list.map((a) => {
    const g = gInfo(a.group);
    const li = document.createElement("li");
    const tag = document.createElement("span");
    tag.className = "group-tag";
    tag.style.borderColor = g.color;
    tag.textContent = g.name;
    const link = document.createElement("a");
    link.href = a.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = a.title || a.url;
    const info = document.createElement("span");
    info.className = "news-meta";
    info.textContent = [a.domain, a.country, fmtTime(a.date)].filter(Boolean).join(" · ");
    li.append(tag, link, info);
    return li;
  }));
}

function renderStocks(tickers, gInfo) {
  const series = Object.entries(tickers).map(([t, s]) => {
    const base = s.data[0][1];
    return {
      name: `${gInfo(s.group).name} ${t}`, type: "line", showSymbol: false,
      lineStyle: { width: 2.5 },
      color: gInfo(s.group).color,
      data: s.data.map(([d, p]) => [d, +((p / base) * 100).toFixed(2)]),
    };
  });
  chart("chart-stocks", {
    tooltip: { trigger: "axis" },
    legend: lineLegend,
    grid: { left: 50, right: 30, top: 50, bottom: 40 },
    xAxis: { type: "time" },
    yAxis: { type: "value", scale: true },
    series,
  });
}

function renderChange(tickers, gInfo) {
  const rows = Object.entries(tickers).sort((a, b) => b[1].change_1y_pct - a[1].change_1y_pct);
  chart("chart-change", {
    tooltip: { formatter: (p) => `${p.name}<br>${p.value}%` },
    grid: { left: 140, right: 60, top: 10, bottom: 30 },
    xAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
    yAxis: {
      type: "category", inverse: true,
      data: rows.map(([t, s]) => `${gInfo(s.group).name} ${t}`),
    },
    series: [{
      type: "bar",
      barMaxWidth: 22,
      data: rows.map(([, s]) => ({
        value: s.change_1y_pct,
        itemStyle: { color: s.change_1y_pct >= 0 ? VIOLET : RED },
      })),
      label: { show: true, position: "right", formatter: "{c}%", color: "#222", fontWeight: 600 },
    }],
  });
}

function renderSec(sec, gInfo) {
  const cos = Object.entries(sec.companies);
  const label = (t, c) => `${c.name}（${t}）`;
  const yi = (v) => (v == null ? "—" : `${v} 億美元`);

  const withQ = cos.filter(([, c]) => c.revenue?.quarterly?.length);
  if (withQ.length) {
    chart("chart-sec-rev", {
      tooltip: { trigger: "axis", valueFormatter: yi },
      legend: lineLegend,
      grid: { left: 50, right: 30, top: 50, bottom: 40 },
      xAxis: { type: "time" },
      yAxis: { type: "value" },
      series: withQ.map(([t, c]) => ({
        name: label(t, c), type: "line", symbolSize: 5,
        lineStyle: { width: 2.5 }, color: gInfo(c.group).color,
        data: c.revenue.quarterly.map(([e, v]) => [e, toYi(v)]),
      })),
    });
  } else {
    empty("chart-sec-rev", "暫無季度收入數據");
  }

  const withNi = cos.filter(([, c]) => c.net_income?.annual?.length);
  if (withNi.length) {
    const years = [...new Set(withNi.flatMap(([, c]) => c.net_income.annual.map(([e]) => e.slice(0, 4))))].sort();
    chart("chart-sec-ni", {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: yi },
      legend: { type: "scroll" },
      grid: { left: 50, right: 30, top: 50, bottom: 40 },
      xAxis: { type: "category", data: years },
      yAxis: { type: "value" },
      series: withNi.map(([t, c]) => {
        const m = new Map(c.net_income.annual.map(([e, v]) => [e.slice(0, 4), toYi(v)]));
        return {
          name: label(t, c), type: "bar", barMaxWidth: 16, color: gInfo(c.group).color,
          data: years.map((y) => m.get(y) ?? null),
        };
      }),
    });
  } else {
    empty("chart-sec-ni", "暫無淨利潤數據");
  }

  if (sec.missing?.length) {
    document.getElementById("sec-note").textContent +=
      ` 以下公司沒有取得數據：${sec.missing.join("、")}。`;
  }
}

function renderTable(hotels, gInfo) {
  const tbody = document.querySelector("#table tbody");
  const countEl = document.getElementById("table-count");
  const rows = hotels.slice().sort(
    (a, b) => (a.group ? 0 : 1) - (b.group ? 0 : 1) || a.name.localeCompare(b.name, "zh-Hant"));

  function draw(q) {
    const query = q.trim().toLowerCase();
    const list = rows.filter((h) =>
      !query ||
      [h.name, h.name_en, h.brand, gInfo(h.group).name].join(" ").toLowerCase().includes(query));
    countEl.textContent = `顯示 ${list.length} / ${rows.length} 間酒店`;
    tbody.replaceChildren(...list.map((h) => {
      const tr = document.createElement("tr");
      const g = gInfo(h.group);
      for (const [i, v] of [h.name, h.name_en, g.name, h.stars, h.brand].entries()) {
        const td = document.createElement("td");
        if (i === 2) {
          const tag = document.createElement("span");
          tag.className = "group-tag";
          tag.style.borderColor = g.color;
          tag.textContent = v;
          td.appendChild(tag);
        } else {
          td.textContent = v ?? "";
        }
        tr.appendChild(td);
      }
      const td = document.createElement("td");
      const a = document.createElement("a");
      a.href = `https://www.openstreetmap.org/${h.osm}`;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = "查看 →";
      td.appendChild(a);
      tr.appendChild(td);
      return tr;
    }));
  }

  document.getElementById("search").addEventListener("input", (e) => draw(e.target.value));
  draw("");
}
