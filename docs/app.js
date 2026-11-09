const VIOLET = "#57068c";
const VIOLET_DARK = "#330662";
const OTHER = { name: "其他 / 獨立", color: "#9a9a9a" };
const SOURCES = {
  osm: "OpenStreetMap",
  wikidata: "Wikidata",
  pageviews: "維基瀏覽量",
  stocks: "股價",
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
  iso ? new Date(iso).toLocaleString("zh-HK", { timeZone: "Asia/Macau", hour12: false }) : "—";

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

function movingAvg(points, n) {
  return points.map((p, i) => {
    const win = points.slice(Math.max(0, i - n + 1), i + 1);
    return [p[0], Math.round(win.reduce((s, x) => s + x[1], 0) / win.length)];
  });
}

(async function main() {
  const [meta, osm, wd, views, stocks] = await Promise.all(
    ["meta", "osm_hotels", "wikidata_hotels", "pageviews", "stocks"].map(load));

  const groups = meta?.groups ?? {};
  const gInfo = (k) => groups[k] ?? OTHER;
  const groupKeys = [...Object.keys(groups), null];

  renderStatus(meta);
  renderKpis(osm, wd, stocks);

  if (osm?.hotels?.length) {
    renderMap(osm.hotels, groupKeys, gInfo);
    renderCount(osm.hotels, groupKeys, gInfo);
    renderBrands(osm.hotels);
    renderTable(osm.hotels, gInfo);
  } else {
    ["map", "chart-count", "chart-brands"].forEach((id) => empty(id));
  }

  wd?.hotels?.length ? renderRooms(wd.hotels, groupKeys, gInfo) : empty("chart-rooms");
  views?.articles ? renderViews(views, gInfo) : empty("chart-views");
  if (stocks?.tickers) {
    renderStocks(stocks.tickers, gInfo);
    renderChange(stocks.tickers, gInfo);
  } else {
    empty("chart-stocks");
    empty("chart-change");
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

function renderKpis(osm, wd, stocks) {
  const items = [];
  if (osm?.hotels) {
    const n = osm.hotels.length;
    const inGroups = osm.hotels.filter((h) => h.group).length;
    items.push(["OSM 收錄酒店", n.toLocaleString(), "間"]);
    items.push(["六大集團旗下", inGroups.toLocaleString(), `間，佔 ${n ? Math.round((inGroups / n) * 100) : 0}%`]);
  }
  if (wd?.hotels) {
    const withRooms = wd.hotels.filter((h) => h.rooms);
    const total = withRooms.reduce((s, h) => s + h.rooms, 0);
    items.push(["已知客房總數", total.toLocaleString(), `間房，來自 ${withRooms.length} 間酒店`]);
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

function renderRooms(hotels, keys, gInfo) {
  const withRooms = hotels.filter((h) => h.rooms);
  if (!withRooms.length) return empty("chart-rooms", "Wikidata 暫無客房數據");
  const sums = keys.map((k) =>
    withRooms.filter((h) => (h.group ?? null) === k).reduce((s, h) => s + h.rooms, 0));
  barChart("chart-rooms", keys.map((k) => gInfo(k).name), sums, keys.map((k) => gInfo(k).color));
  document.getElementById("rooms-note").textContent =
    `來源：Wikidata。${hotels.length} 間酒店中只有 ${withRooms.length} 間有客房數，數字偏低屬正常。`;
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
    const m = (byGroup[a.group] ??= new Map());
    for (const [d, v] of a.data) m.set(d, (m.get(d) || 0) + v);
  }
  const series = Object.entries(byGroup).map(([g, m]) => {
    const pts = [...m.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1));
    return {
      name: gInfo(g).name, type: "line", showSymbol: false, smooth: true,
      lineStyle: { width: 2.5 },
      color: gInfo(g).color, data: movingAvg(pts, 7),
    };
  });
  chart("chart-views", {
    tooltip: { trigger: "axis" },
    legend: { type: "scroll", icon: "rect", itemWidth: 14, itemHeight: 4 },
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
    legend: { type: "scroll", icon: "rect", itemWidth: 14, itemHeight: 4 },
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
        itemStyle: { color: s.change_1y_pct >= 0 ? VIOLET : "#b5121b" },
      })),
      label: { show: true, position: "right", formatter: "{c}%", color: "#222", fontWeight: 600 },
    }],
  });
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
