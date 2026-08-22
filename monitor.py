"""
FCM WATCH — 規制アップデート自動収集スクリプト

このスクリプトは以下を行う：
  1. Federal Register API（米国, FDA）から食品接触材料・PFAS関連の新着文書を取得
  2. EUR-Lexで作成したRSSアラート（EU）から新着を取得
  3. 結果をまとめて updates.json に書き出す（index.html はこのファイルを読みに行く）

中国（GB規格）は当面スコープ外（EU・米国のみ対応）。

実行には毎回インターネット接続が必要。ローカルPCから手動実行してもいいし、
GitHub Actions（.github/workflows/update.yml）で自動実行してもいい。
"""

import json
import re
from datetime import datetime, timedelta, timezone

import requests
import feedparser

# ----------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------

# EUR-Lexで作成したRSSアラートのURL。
# 作り方：EUR-Lex → Advanced Search → 検索条件を設定（例: subject matter =
# "food contact materials", または特定のCELEX番号）→ 検索結果画面で
# "Create RSS alert" をクリック → 発行されたURLをここに貼る。
EU_RSS_URL = ""  # 例: "https://eur-lex.europa.eu/EN/display-feed.rss?..."

FDA_SEARCH_TERMS = [
    "food contact substance",
    "PFAS food packaging",
]

LOOKBACK_DAYS = 30
OUTPUT_FILE = "updates.json"
MAX_ITEMS = 30


# ----------------------------------------------------------------------
# 米国：Federal Register API（APIキー不要）
# ----------------------------------------------------------------------
def fetch_fda_updates(days=LOOKBACK_DAYS):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    base = "https://www.federalregister.gov/api/v1/documents.json"
    results = []

    for term in FDA_SEARCH_TERMS:
        params = {
            "conditions[term]": term,
            "conditions[agencies][]": "food-and-drug-administration",
            "conditions[publication_date][gte]": since,
            "order": "newest",
            "per_page": 10,
        }
        try:
            r = requests.get(base, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            print(f"[warn] FDA fetch failed for term '{term}': {e}")
            continue

        for doc in data.get("results", []):
            results.append({
                "date": doc.get("publication_date", ""),
                "region": "us",
                "flag": "flags/us.png",
                "regionLabel": "US",
                "title": doc.get("title", ""),
                "body": _clean(doc.get("abstract") or "")[:200],
                "link": doc.get("html_url", ""),
            })
    return results


# ----------------------------------------------------------------------
# EU：EUR-Lex RSSアラート（事前にEUR-Lex側で作成しておく）
# ----------------------------------------------------------------------
def fetch_eu_updates(rss_url=EU_RSS_URL):
    if not rss_url:
        print("[info] EU_RSS_URL 未設定のためEUはスキップ")
        return []

    feed = feedparser.parse(rss_url)
    results = []
    for entry in feed.entries[:10]:
        date = entry.get("published", entry.get("updated", ""))[:10]
        results.append({
            "date": date,
            "region": "eu",
            "flag": "flags/eu.png",
            "regionLabel": "EU",
            "title": entry.get("title", ""),
            "body": _clean(entry.get("summary", ""))[:200],
            "link": entry.get("link", ""),
        })
    return results


def _clean(text):
    """HTMLタグと余分な空白を除去する簡易クリーナー"""
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------------
# メイン
# ----------------------------------------------------------------------
def main():
    updates = []
    updates += fetch_fda_updates()
    updates += fetch_eu_updates()

    # 日付の新しい順に並べ、上限件数に絞る
    updates.sort(key=lambda x: x.get("date", ""), reverse=True)
    updates = updates[:MAX_ITEMS]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(updates, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(updates)} 件を {OUTPUT_FILE} に書き出しました")


if __name__ == "__main__":
    main()
