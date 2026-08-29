"""
FCM WATCH — 規制アップデートをnoteに自動投稿するスクリプト

流れ：
  1. updates.json（monitor.pyが生成する規制アップデート一覧）を読む
  2. まだnoteに投稿していない新着だけを抽出（posted_to_note.json で管理）
  3. 1件ずつ、短いnote記事に整形してnote_client.py経由で下書き作成→即公開
  4. 投稿済みとして posted_to_note.json に記録する

このスクリプトは monitor.py の後に実行する想定
（GitHub Actionsのワークフローで直列に呼び出す）。

失敗の扱い:
  1件でも投稿に失敗したら、最後に終了コード1で終わる。
  ワークフローが赤くなり、GitHubから失敗通知メールが届く。
  （黙って失敗し続けるのを防ぐため。以前は成功扱いで気づけなかった）
  ただし記録の保存は先に済ませるので、成功した分は二重投稿にならない。
"""

import json
import os
import sys

from note_client import NoteClient, NoteError

UPDATES_FILE = "updates.json"
POSTED_FILE = "posted_to_note.json"
HP_URL = "https://fcm-watch.com"


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


TITLE_LIMIT = 100      # noteの上限は255文字。余裕をもって短くする


def make_title(raw: str) -> str:
    """noteのタイトル上限に収める。

    FDAの規制タイトルは255文字を超えることがあり、そのまま送ると
    422（タイトルは255文字以内）や500になる。
    長い場合は語の途中で切らずに縮めて末尾に…を付ける。
    """
    prefix = "【規制アップデート】"
    body = (raw or "").strip()
    room = TITLE_LIMIT - len(prefix)
    if len(body) <= room:
        return prefix + body
    cut = body[:room - 1]
    # 単語の途中で切れないよう、直前の区切りまで戻す
    for sep in ("; ", ", ", " "):
        i = cut.rfind(sep)
        if i > room * 0.6:
            cut = cut[:i]
            break
    return prefix + cut.rstrip(" ;,") + "…"


def format_article(item):
    title = make_title(item.get("title", ""))
    body = (
        f"{item.get('regionLabel', '')}の規制アップデートです。\n\n"
        f"{item.get('body', '')}\n\n"
        f"詳細・原文リンクはFCM WATCH（{HP_URL}）でも随時更新しています。\n\n"
        f"※本記事は一般的な情報提供を目的としたものであり、法的助言ではありません。"
    )
    return title, body


def main():
    if not os.environ.get("NOTE_SESSION_COOKIE"):
        print("[warn] NOTE_SESSION_COOKIE が未設定のため、note投稿をスキップします")
        print("[warn] Settings > Secrets and variables > Actions で登録してください")
        return 0

    updates = load_json(UPDATES_FILE, [])
    posted = load_json(POSTED_FILE, [])
    posted_keys = {p["key"] for p in posted}

    new_items = [u for u in updates if make_key(u) not in posted_keys]
    if not new_items:
        print("[info] 新着なし、投稿スキップ")
        return 0

    try:
        client = NoteClient()
    except NoteError as e:
        print(f"[error] noteクライアントを作れなかった: {e}")
        return 1

    failed = []
    for item in new_items:
        key = make_key(item)
        title, body = format_article(item)
        try:
            client.create_and_publish(title, body)
            print(f"[ok] 投稿しました: {title}")
            posted.append({"key": key, "title": title})
        except Exception as e:
            # 1件失敗しても他は続ける。次回実行時にリトライされる。
            print(f"[error] 投稿に失敗: '{title}': {e}")
            failed.append(title)

    # 成功した分は先に記録する（ここで落ちると二重投稿になるため）
    save_json(POSTED_FILE, posted)

    if failed:
        print(f"\n[error] {len(failed)}件が投稿できませんでした:")
        for t in failed:
            print(f"  - {t}")
        print("\nセッションCookieの期限切れが最も多い原因です。"
              "ブラウザでnoteにログインし直し、_note_session_v5 の値を"
              "NOTE_SESSION_COOKIE に再設定してください。")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
