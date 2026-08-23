# FCM WATCH — セットアップ手順

## 全体の仕組み
- サイト本体：`index.html`（静的1ファイル、GitHub Pagesでホスト）
- データ：`updates.json`（サイトが表示する規制アップデートの中身）
- 自動更新：`monitor.py` を GitHub Actions が毎日実行し、`updates.json` を書き換えてpush
  → push されると GitHub Pages が自動で再公開される、という流れ

サーバーは不要。GitHubの無料枠だけで完結する。

## 差し替えが必要なプレースホルダー
`index.html`内に、まだ仮のリンクが3箇所ある（`href="#"`のまま）：
`id="linkedin-link"`（ヘッダー）、`id="linkedin-link-mobile"`（スマホメニュー）、
`id="linkedin-link-plan"`（詳細版セクション）。
LinkedInニュースレターのURLが決まったら、この3つを実際のURLに置き換える。

## 1. GitHubリポジトリを作る
1. GitHubで新規リポジトリを作成（Public推奨。Privateでも動くが設定が一手間増える）
2. このフォルダの中身（`index.html`, `flags/`, `monitor.py`, `requirements.txt`,
   `updates.json`, `CNAME`, `.github/workflows/update.yml`）をそのままpush

## 2. GitHub Pagesを有効化
1. リポジトリの Settings → Pages
2. Source を「Deploy from a branch」、Branch を `main` / `(root)` に設定
3. 数分待つと `https://<ユーザー名>.github.io/<リポジトリ名>/` で見えるようになる

## 3. 独自ドメイン（fcm-watch.com）を接続
1. ドメインのレジストラ（Cloudflare RegistrarやNamecheapなど）のDNS設定画面で、
   以下のAレコードを4つとも追加：
   ```
   185.199.108.153
   185.199.109.153
   185.199.110.153
   185.199.111.153
   ```
2. GitHubのSettings → Pages → Custom domain に `fcm-watch.com` を入力して保存
   （リポジトリに含まれている `CNAME` ファイルがこの設定を反映する）
3. DNSが反映されたら（数分〜数時間）、Pages設定画面で「Enforce HTTPS」にチェック

## 4. EUR-LexのRSSアラートを作る（EU側の自動収集に必要）
1. https://eur-lex.europa.eu/ にアクセスし、Advanced Search
2. 検索条件を設定（例：Subject matter = "food contact materials"、
   もしくは Regulation (EU) No 10/2011 や 1935/2004 のCELEX番号を指定）
3. 検索結果画面の「Create RSS alert」をクリックして発行されたURLをコピー
4. `monitor.py` 内の `EU_RSS_URL = ""` に貼り付けてpush

これを設定するまでは、EU側のアップデートは収集されない（USのFDA分だけ動く）。

## 5. 動作確認
1. GitHubのActionsタブ → 「Update regulation feed」→ 「Run workflow」で手動実行
2. 成功したら `updates.json` が更新されているはず
3. 数分後、サイトをリロードして反映を確認

以降は毎日自動で実行される（cronは `.github/workflows/update.yml` で調整可能）。

## 対象国について
現在はEU・米国のみを対象にしている（中国は当面スコープ外）。
中国を再度対象に含める場合は、WTOのePing（SPS&TBT通知プラットフォーム、
https://eping.wto.org）で Notifying Member = China、ICS Code = `67.250`
（食品接触材料）で登録し、メールアラートを受け取る方法が使える。

## noteへの自動投稿について（要注意）
noteは公式の投稿APIを公開していない（公式ヘルプに「公開予定は未定」と明記）。
`note_client.py` / `post_to_note.py` は、有志が解析した非公式エンドポイントを
使っており、**動作保証はない**。仕様変更で突然動かなくなる可能性、
利用規約上グレーな行為である点は理解した上で使うこと。

セットアップ：
1. ブラウザでnote.comにログインした状態でDevToolsを開き、Cookie一覧から
   セッションを保持しているCookie（`note_client.py`内の`COOKIE_NAME`を参照。
   名前が違っていたらコード側を書き換える）の値をコピーする
2. GitHubリポジトリの Settings → Secrets and variables → Actions →
   「New repository secret」で、名前 `NOTE_SESSION_COOKIE`、値に
   コピーしたCookieの値を登録する
3. これで、毎回の自動実行時に新しい規制アップデートがあれば、
   自動で下書き作成→即公開まで行われる

投稿済みの記録は `posted_to_note.json` に残るので、同じ内容を二重投稿する
ことはない。エラーになった場合はGitHub Actionsのログ（Post new updates to
noteのステップ）にレスポンス内容が出るので、そこからpayloadの調整が必要。

## アクセス解析（Cloudflare Web Analytics）
`index.html`の末尾に、Cloudflare Web Analyticsのビーコンを埋め込み済み
（`token`はプレースホルダーなので差し替えが必要）。
Cookieを使わず、IPアドレスも保存しない、プライバシー重視の無料アクセス解析。
ドメインをCloudflareのDNSに移す必要はない。

1. https://dash.cloudflare.com で無料アカウントを作成（まだなら）
2. ダッシュボード左メニューから「Analytics & Logs」→「Web Analytics（Web分析）」を開く
3. 「Add a site（サイトを追加する）」→ ホスト名に `fcm-watch.com` を入力
4. セットアップ方法は「Manual Setup（手動セットアップ）」を選ぶ
   （自動セットアップはCloudflareのDNS/プロキシを使っている場合向けなので、
   今回はDNSをお名前.comで管理しているため手動を選ぶ）
5. 発行されたビーコンスクリプトの中の `token` の値をコピー
6. `index.html` 末尾の `PASTE_YOUR_TOKEN_HERE` をコピーした値に置き換えて保存
7. 数分〜数時間ほどアクセスが集まったら、Cloudflareダッシュボードの
   「Web Analytics」→ `fcm-watch.com` でページビューや流入元が見られる


## 動作未検証について
`monitor.py` はFederal Register APIの公開ドキュメントを基に書いているが、
このやり取りの環境にはインターネット接続がなく実行確認ができていない。
最初にGitHub Actionsで動かしたとき、レスポンス形式のズレ等でエラーが出たら
その内容を教えてもらえれば直す。
