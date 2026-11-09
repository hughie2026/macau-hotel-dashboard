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

# 英文維基百科條目 -> 集團。條目不存在時會被跳過並記錄在 pageviews.json 的 missing 欄位
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

# Yahoo Finance 代號 -> 集團
TICKERS = {
    "1928.HK": "sands",
    "0027.HK": "galaxy",
    "2282.HK": "mgm",
    "1128.HK": "wynn",
    "0880.HK": "sjm",
    "MLCO": "melco",
}
