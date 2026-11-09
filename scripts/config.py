"""品牌/集團設定。酒店歸屬靠關鍵字比對名稱、品牌、營運商，可自行增刪。"""

GROUPS = {
    "galaxy": {
        "name": "銀河娛樂",
        "color": "#c99700",
        "keywords": [
            "galaxy", "銀河", "银河", "starworld", "星際", "星际",
            "banyan tree", "悅榕莊", "悦榕庄", "ritz-carlton", "麗思卡爾頓", "丽思卡尔顿",
            "jw marriott", "okura", "大倉", "大仓", "broadway", "百老匯", "百老汇",
            "andaz", "raffles", "萊佛士", "莱佛士",
        ],
    },
    "sands": {
        "name": "金沙中國",
        "color": "#1f5aa6",
        "keywords": [
            "venetian", "威尼斯人", "parisian", "巴黎人", "londoner", "倫敦人", "伦敦人",
            "sands", "金沙", "conrad", "康萊德", "康莱德", "four seasons", "四季",
            "sheraton", "喜來登", "喜来登", "st. regis", "st regis", "瑞吉",
        ],
    },
    "melco": {
        "name": "新濠博亞",
        "color": "#57068c",
        "keywords": [
            "city of dreams", "新濠", "morpheus", "摩珀斯", "nüwa", "nuwa",
            "grand hyatt", "君悅", "君悦", "studio city", "altira", "melco",
        ],
    },
    "mgm": {
        "name": "美高梅中國",
        "color": "#b5121b",
        "keywords": ["mgm", "美高梅"],
    },
    "wynn": {
        "name": "永利澳門",
        "color": "#d36b00",
        "keywords": ["wynn", "永利", "encore"],
    },
    "sjm": {
        "name": "澳門博彩控股",
        "color": "#00857c",
        "keywords": [
            "lisboa", "葡京", "sjm", "澳博", "karl lagerfeld",
            "versace", "范思哲", "ponte 16", "十六浦",
        ],
        # 澳門葡京人 (Lisboeta) 不屬於澳博，名稱卻含「葡京」
        "exclude": ["lisboeta", "葡京人"],
    },
}

# 英文維基百科條目 -> 集團。其他語言的標題會透過維基百科的跨語言連結自動查出
WIKI_ARTICLES = {
    "The_Venetian_Macao": "sands",
    "The_Parisian_Macao": "sands",
    "The_Londoner_Macao": "sands",
    "Galaxy_Macau": "galaxy",
    "City_of_Dreams_(Macau)": "melco",
    "Studio_City_(Macau)": "melco",
    "Altira_Macau": "melco",
    "MGM_Macau": "mgm",
    "MGM_Cotai": "mgm",
    "Wynn_Macau": "wynn",
    "Wynn_Palace": "wynn",
    "Grand_Lisboa": "sjm",
    "Hotel_Lisboa": "sjm",
    "Grand_Lisboa_Palace": "sjm",
}

# 要比較的維基百科語言版本。代碼必須與維基百科子域名一致（例如 zh-yue 是粵語維基）
WIKI_LANGS = {
    "en": {"name": "英文", "color": "#57068c"},
    "zh": {"name": "中文", "color": "#b5121b"},
    "zh-yue": {"name": "粵語", "color": "#d36b00"},
    "ja": {"name": "日文", "color": "#1f5aa6"},
    "ko": {"name": "韓文", "color": "#00857c"},
    "pt": {"name": "葡文", "color": "#c99700"},
}

# GDELT 新聞查詢。用完整詞組避免誤中，例如只寫 "Galaxy" 會混入三星手機的新聞。
# 語法：詞組用雙引號，多個詞組用 OR 連接並放在括號內
GDELT_QUERIES = {
    "galaxy": '("Galaxy Macau" OR "Galaxy Entertainment" OR "StarWorld Macau" OR "Broadway Macau")',
    "sands": '("Sands China" OR "Venetian Macao" OR "Venetian Macau" OR "Parisian Macao" OR "Londoner Macao")',
    "melco": '("Melco Resorts" OR "City of Dreams Macau" OR "Studio City Macau" OR "Morpheus Macau")',
    "mgm": '("MGM China" OR "MGM Macau" OR "MGM Cotai")',
    "wynn": '("Wynn Macau" OR "Wynn Palace")',
    "sjm": '("SJM Holdings" OR "SJM Resorts" OR "Grand Lisboa")',
}

# Yahoo Finance 代號 -> 集團
TICKERS = {
    "1928.HK": "sands",
    "0027.HK": "galaxy",
    "2282.HK": "mgm",
    "1128.HK": "wynn",
    "0880.HK": "sjm",
    "MLCO": "melco",
}

# 在美國 SEC 申報的母公司（美股代號）。CIK 編號會自動從 SEC 的代號表查出
SEC_COMPANIES = {
    "LVS": {"group": "sands", "name": "Las Vegas Sands"},
    "WYNN": {"group": "wynn", "name": "Wynn Resorts"},
    "MGM": {"group": "mgm", "name": "MGM Resorts"},
    "MLCO": {"group": "melco", "name": "Melco Resorts"},
}
