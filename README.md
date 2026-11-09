# 澳門酒店業品牌分析面板

由 GitHub Actions 每 6 小時自動抓取公開數據，部署在 GitHub Pages。
介面配色和版面參考 NYU 官網風格，本項目與紐約大學無關。

## 數據來源
- OpenStreetMap（Overpass API）：酒店位置、名稱、品牌、星級
- Wikimedia Pageviews：英、中、粵、日、韓、葡文維基百科條目瀏覽量
- Google News RSS：中英文新聞報導，逐次累積，最長保留 90 日
- Yahoo Finance（yfinance）：六大承批公司上市主體的股價和年度損益表
- GDELT（可選）：新聞語調
- SEC EDGAR（可選）：美國母公司季度收入，需要設定 SEC_CONTACT

沒有數據的圖表會自動隱藏，抓取狀態顯示在頁面頂部。

## 本地執行
pip install -r requirements.txt
python scripts/fetch_all.py
python -m http.server -d docs 8000

## 自訂
- 集團、維基條目、新聞查詢詞、股票代號、匯率：scripts/config.py
- 配色：docs/style.css 的 :root 變數，以及 docs/app.js 的 ECharts 主題
- 修改 app.js 或 style.css 後，把 index.html 裡的 ?v= 數字加 1
