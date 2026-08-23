"""
note.com 非公式APIクライアント

note.comは公式の投稿APIを公開していない（公式ヘルプに「公開予定は未定」と明記）。
このモジュールは、有志が解析した非公式のエンドポイントを利用する。

【重要】非公式のため、以下のリスクを理解した上で使うこと：
  - note側の仕様変更で予告なく動かなくなる可能性がある
  - 利用規約上グレーな行為であり、最悪アカウント停止のリスクがある
  - エンドポイントの正確な仕様が公開されていないため、動作未確認。
    422エラー等が出た場合はpayloadの調整が必要になる可能性が高い

【認証方法】
公式OAuth等は無いため、ログイン済みブラウザのセッションCookieを流用する。
取得方法：
  1. ブラウザでnote.comにログインした状態でDevTools（検証）を開く
  2. Application（Chrome）/ Storage（Firefox）タブ → Cookies → note.com
  3. セッションを保持しているCookie（過去の実装例では `_note_session_v5` という
     名前のことが多いが、現在の名前は自分の環境で確認すること）の値をコピー
  4. その値をGitHub Secretsに `NOTE_SESSION_COOKIE` として保存する
     （Cookie名が違っていたらこのファイルのCOOKIE_NAMEを書き換える）

このCookieは自分のログイン情報そのものなので、コードに直接書いたり
リポジトリにコミットしたりしないこと。必ず環境変数 / GitHub Secrets経由で渡す。
"""

import os
import requests

NOTE_BASE = "https://note.com/api"
COOKIE_NAME = "_note_session_v5"  # 実際の名前と違ったらここを書き換える


class NoteClient:
    def __init__(self, session_cookie=None):
        session_cookie = session_cookie or os.environ.get("NOTE_SESSION_COOKIE")
        if not session_cookie:
            raise ValueError("NOTE_SESSION_COOKIE が設定されていない")

        self.session = requests.Session()
        self.session.cookies.set(COOKIE_NAME, session_cookie, domain=".note.com")
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; fcm-watch-bot/1.0)",
            "Content-Type": "application/json",
        })

    def create_draft(self, title, body, price=0):
        """下書きを作成する。price=0なら無料、1以上なら有料記事として作成を試みる。

        note側の有料記事APIの正確なフィールド名は非公開で確認できていないため、
        `price` というキー名は推測。動かない場合はレスポンス内容を見て調整する。
        """
        payload = {"name": title, "body": body, "status": "draft"}
        if price > 0:
            payload["price"] = price
        resp = self.session.post(f"{NOTE_BASE}/v1/text_notes", json=payload)
        if not resp.ok:
            print(f"[error] create_draft failed: {resp.status_code} {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()

    def publish(self, note_key):
        """下書きを公開する。"""
        resp = self.session.post(f"{NOTE_BASE}/v2/notes/{note_key}/publish")
        if not resp.ok:
            print(f"[error] publish failed: {resp.status_code} {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()

    def create_and_publish(self, title, body, price=0):
        draft = self.create_draft(title, body, price=price)
        note_key = draft.get("data", {}).get("key") or draft.get("key")
        if not note_key:
            raise RuntimeError(f"note_keyが取得できなかった。レスポンス: {draft}")
        return self.publish(note_key)
