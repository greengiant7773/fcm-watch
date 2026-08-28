"""
FCM WATCH — 規制アップデートをnoteに自動投稿するスクリプト

流れ：
  1. updates.json（monitor.pyが生成する規制アップデート一覧）を読む
  2. まだnoteに投稿していない新着だけを抽出（posted_to_note.json で管理）
  3. 1件ずつ、短いnote記事に整形してnote_client.py経由で下書き作成→即公開
  4. 投稿済みとして posted_to_note.json に記録する

このスクリプトは monitor.py の後に実行する想定
（GitHub Actionsのワークフローで直列に呼び出す）。
"""

import json
import os

from note_client import NoteClient

UPDATES_FILE = "updates.json"
POSTED_FILE = "posted_to_note.json"
HP_URL = "https://fcm-watch.com"
ARTICLE_PRICE = 300  # 円。0にすると無料公開になる


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_key(item):
    """同じ更新かどうかを判定するためのキー。リンクが最も確実。"""
    return item.get("link") or f"{item.get('region')}|{item.get('title')}"


def format_article(item):
    title = f"【規制アップデート】{item.get('title', '')}"
    body = (
        f"{item.get('regionLabel', '')}の規制アップデートです。\n\n"
        f"{item.get('body', '')}\n\n"
        f"詳細・原文リンクはFCM WATCH（{HP_URL}）でも随時更新しています。\n\n"
        f"※本記事は一般的な情報提供を目的としたものであり、法的助言ではありません。"
    )
    return title, body


def main():
    # NOTE_SESSION_COOKIE が未設定の場合、ここで例外で落ちると
    # 後続の「Commit and push」までスキップされ、サイトの規制フィード更新
    # まで止まってしまう。未設定時は警告を出して投稿だけスキップする。
    if not os.environ.get("NOTE_SESSION_COOKIE"):
        print("[warn] NOTE_SESSION_COOKIE が未設定のため、note投稿をスキップします")
        print("[warn] GitHubリポジトリの Settings > Secrets and variables > Actions で登録してください")
        return

    updates = load_json(UPDATES_FILE, [])
    posted = load_json(POSTED_FILE, [])
    posted_keys = {p["key"] for p in posted}

    new_items = [u for u in updates if make_key(u) not in posted_keys]
    if not new_items:
        print("[info] 新着なし、投稿スキップ")
        return

    client = NoteClient()

    for item in new_items:
        key = make_key(item)
        title, body = format_article(item)
        try:
            result = client.create_and_publish(title, body, price=ARTICLE_PRICE)
            print(f"[ok] posted (price={ARTICLE_PRICE}): {title}")
            posted.append({"key": key, "title": title})
        except Exception as e:
            # 1件失敗しても他の投稿は続ける。次回実行時にリトライされる。
            print(f"[error] failed to post '{title}': {e}")

    save_json(POSTED_FILE, posted)


if __name__ == "__main__":
    main()
