# 澳門酒店業品牌分析面板

由 GitHub Actions 每 6 小時自動抓取公開數據，部署在 GitHub Pages。
介面配色和版面參考 NYU 官網風格，本項目與紐約大學無關。

## 數據來源
- OpenStreetMap（Overpass API）：酒店位置、名稱、品牌、星級
- Wikidata：營運商、客房數、開業年份
- Wikimedia Pageviews：英文維基百科條目瀏覽量
- Yahoo Finance（yfinance）：六大承批公司股價

## 部署
1. 上傳全部檔案到新倉庫的 main 分支
2. Settings → Pages → Source 選 **GitHub Actions**
3. Actions → Update data → Run workflow
4. 打開 https://<你的帳號>.github.io/<倉庫名>/

## 本地執行
pip install -r requirements.txt
python scripts/fetch_all.py
python -m http.server -d docs 8000

## 自訂
- 集團關鍵字、維基條目、股票代號：scripts/config.py
- 配色：docs/style.css 開頭的 :root 變數，以及 docs/app.js 的 ECharts 主題
