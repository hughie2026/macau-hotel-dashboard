# 澳門酒店業品牌分析面板

由 GitHub Actions 每 6 小時自動抓取公開數據，部署在 GitHub Pages。
介面配色和版面參考 NYU 官網風格，本項目與紐約大學無關。

## 數據來源
- OpenStreetMap（Overpass API）：酒店位置、名稱、品牌、星級
- Wikimedia Pageviews：英、中、粵、日、韓、葡文維基百科條目瀏覽量
- GDELT DOC 2.0 API：近 3 個月全球新聞報導量、語調和最新標題
- Yahoo Finance（yfinance）：六大承批公司股價
- SEC EDGAR XBRL API：Las Vegas Sands、Wynn Resorts、MGM Resorts、Melco 的收入和淨利潤

## 部署
1. 上傳全部檔案到新倉庫的 main 分支
2. Settings → Pages → Source 選 **GitHub Actions**
3. Settings → Secrets and variables → Actions → New repository secret，
   名稱 `SEC_CONTACT`，值填你的電郵（SEC 要求請求附上聯絡方式）
4. Actions → Update data → Run workflow
5. 打開 https://<你的帳號>.github.io/<倉庫名>/

## 本地執行
pip install -r requirements.txt
SEC_CONTACT=you@example.com python scripts/fetch_all.py
python -m http.server -d docs 8000

## 自訂
- 集團關鍵字、維基條目、語言、新聞查詢詞、股票代號、SEC 公司：scripts/config.py
- 配色：docs/style.css 開頭的 :root 變數，以及 docs/app.js 的 ECharts 主題
- 修改 app.js 或 style.css 後，把 index.html 裡的 ?v= 數字加 1，避免瀏覽器使用緩存的舊版本
