"""
FCM WATCH — 規制アップデートの月次まとめ下書きを作る

方針:
  - 自動で「公開」はしない。下書きまで作って止める。
    規制解説はそのまま出すと一次情報の転記にしかならず、
    有料で売るには「で、うちの容器に関係あるのか」の判定が要る。
    その判定は人がやる前提で、叩き台だけ機械が用意する。
  - 1件ごとに投稿せず、月に1本のまとめにする。
    読者が知りたいのは「今月の更新、自分に関係あるか」であって、
    個別の規制を1件ずつ買いたいわけではないため。

流れ:
  1. updates.json（monitor.pyの出力）から対象月の更新を集める
  2. 各更新について、本文中の物質名・規則名から
     articles.json の容器マッピングを引いて「関係ありそうな容器」を仮判定
  3. 月次まとめのテンプレを組み立てて note に下書き保存
  4. 人が下書きを開いて、判定を確認しながら肉付け → 手動で公開

実行:
  python monthly_draft.py            # 今月分
  python monthly_draft.py 2026-08    # 月を指定
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

from note_client import NoteClient, NoteError

UPDATES_FILE = "updates.json"
ARTICLES_FILE = "articles.json"
DRAFTED_FILE = "drafted_months.json"
HP_URL = "https://fcm-watch.com"
ARTICLES_URL = "https://fcm-watch.com/articles.html"
X_URL = "https://x.com/w_fljh"

# 容器ごとの判定キーワード。
# 規制文中にこれらが出てきたら、その容器に影響する可能性ありとして拾う。
# あくまで一次スクリーニング。最終判断は人がやる。
CONTAINER_KEYWORDS = {
    "01": ["キャップ", "cap", "closure", "ポリオレフィン", "polyolefin",
           "HDPE", "PP", "滑剤", "slip agent", "エルカ酸", "erucamide",
           "オレアミド", "oleamide", "テザー", "tethered", "着色剤", "colourant"],
    "02": ["PET", "ポリエステル", "polyester", "リサイクル", "recycl",
           "rPET", "アセトアルデヒド", "acetaldehyde", "2022/1616"],
    "03": ["ガラス", "glass", "セラミック", "ceramic", "鉛", "lead",
           "カドミウム", "cadmium"],
    "04": ["カップ", "cup", "PS", "ポリスチレン", "polystyrene",
           "スチレン", "styrene", "シール蓋", "lid"],
    "05": ["缶", "can ", "コーティング", "coating", "BPA", "ビスフェノール",
           "bisphenol", "エポキシ", "epoxy", "BADGE", "2024/3190"],
    "06": ["紙", "paper", "board", "セルロース", "cellulose", "PE",
           "ポリエチレン", "polyethylene", "複合", "multilayer"],
    "07": ["ライナー", "liner", "パッキン", "gasket", "PVC", "可塑剤",
           "plasticiser", "plasticizer", "フタル酸", "phthalate", "ESBO",
           "2023/1442"],
    "08": ["PP", "ポリプロピレン", "polypropylene", "キャップ", "cap"],
    "09": ["PP", "ポリプロピレン", "polypropylene", "ボトル", "bottle"],
    "10": ["ポリオレフィン", "polyolefin", "PE", "HDPE", "LDPE",
           "ボトル", "bottle", "着色剤", "colourant", "遮光"],
}

# 全容器に共通で効く可能性が高いキーワード。
# これが出たら「横断的な変更」として別扱いで目立たせる。
CROSS_CUTTING = [
    "10/2011", "1935/2004", "総移行量", "overall migration", "OML",
    "適合宣言", "declaration of compliance", "GMP", "2023/2006",
    "ポジティブリスト", "union list", "Annex I",
]


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def container_names():
    """articles.json から番号→容器名の対応を作る。"""
    data = load_json(ARTICLES_FILE, {})
    names = {}
    for c in data.get("containers", []):
        names[c["no"]] = c["name"]
    return names


def has_premium(no):
    """その容器の詳細版が公開済みかどうか。まとめ記事から誘導を貼るのに使う。"""
    data = load_json(ARTICLES_FILE, {})
    for c in data.get("containers", []):
        if c["no"] == no:
            return c.get("premium") or None
    return None


def screen(item):
    """1件の更新について、影響しそうな容器番号のリストと横断フラグを返す。

    タイトルと本文の両方を対象に、単純なキーワード一致で拾う。
    拾いすぎる方に倒してある（見落とすより、人が消す方が安全なため）。
    """
    text = f"{item.get('title', '')} {item.get('body', '')}".lower()
    hits = []
    for no, keywords in CONTAINER_KEYWORDS.items():
        if any(k.lower() in text for k in keywords):
            hits.append(no)
    cross = any(k.lower() in text for k in CROSS_CUTTING)
    return sorted(hits), cross


def in_month(item, ym):
    """updates.json の date が対象月かどうか。日付が無い項目は落とす。"""
    d = str(item.get("date", ""))
    return d.startswith(ym)


def build_draft(ym, items, names):
    """月次まとめの下書き本文を組み立てる。

    ここで作るのは完成品ではなく叩き台。
    「■ ここを埋める」の箇所を人が書いて初めて商品になる。
    """
    y, m = ym.split("-")
    title = f"【{y}年{int(m)}月】食品接触材料 規制アップデートまとめ — どの容器に効くか"

    # 容器ごとに、関係する更新をまとめ直す
    by_container = defaultdict(list)
    cross_items = []
    unrelated = []

    for it in items:
        hits, cross = screen(it)
        if cross:
            cross_items.append(it)
        if hits:
            for no in hits:
                by_container[no].append(it)
        elif not cross:
            unrelated.append(it)

    touched = sorted(by_container.keys())
    untouched = [no for no in sorted(names.keys()) if no not in touched]

    lines = []
    lines.append(f"{y}年{int(m)}月に出た食品接触材料の規制アップデートを、"
                 f"容器の種類ごとに整理しました。")
    lines.append("")
    lines.append("この記事は「今月の更新が自分の製品に関係あるか」を"
                 "判断するためのものです。関係ない容器については"
                 "「関係ありません」とはっきり書きます。"
                 "全部の条文を読む時間を省くのが目的です。")
    lines.append("")

    # --- 無料パート：今月の全体像 ---
    lines.append("今月のサマリー")
    lines.append("")
    lines.append(f"・検知した更新：{len(items)}件")
    if touched:
        touched_names = "、".join(f"#{no} {names.get(no, '')}" for no in touched)
        lines.append(f"・影響の可能性がある容器：{touched_names}")
    else:
        lines.append("・影響の可能性がある容器：なし（今月は該当なし）")
    if untouched:
        untouched_names = "、".join(f"#{no} {names.get(no, '')}"
                                   for no in untouched)
        lines.append(f"・今月の更新と直接関係しない容器：{untouched_names}")
    if cross_items:
        lines.append(f"・容器を問わず確認が要る横断的な変更：{len(cross_items)}件")
    lines.append("")
    lines.append("■ ここを埋める：上の一覧を見て、今月の要点を2〜3行で。"
                 "「今月は動かなくていい」ならそう書く。")
    lines.append("")
    lines.append("── ここから下が有料パートです ──")
    lines.append("")

    # --- 有料パート：中身 ---
    if cross_items:
        lines.append("【全容器共通】横断的な変更")
        lines.append("")
        for it in cross_items:
            lines.append(f"◆ {it.get('regionLabel', '')} / {it.get('date', '')}")
            lines.append(f"{it.get('title', '')}")
            lines.append(f"{it.get('body', '')}")
            if it.get("link"):
                lines.append(f"一次情報：{it['link']}")
            lines.append("")
            lines.append("■ ここを埋める：規則番号／発効日／移行期限、"
                         "旧→新の数値、今やること、まだやらなくていいこと")
            lines.append("")

    for no in touched:
        name = names.get(no, "")
        lines.append(f"【#{no} {name}】")
        lines.append("")
        for it in by_container[no]:
            lines.append(f"◆ {it.get('regionLabel', '')} / {it.get('date', '')}")
            lines.append(f"{it.get('title', '')}")
            lines.append(f"{it.get('body', '')}")
            if it.get("link"):
                lines.append(f"一次情報：{it['link']}")
            lines.append("")
        lines.append("■ ここを埋める：この容器に本当に効くのか（効かないなら"
                     "「キーワードは一致したが対象外」と書いて消す）。"
                     "効くなら、旧→新の数値と、取引先に投げる質問文まで。")
        prem = has_premium(no)
        if prem:
            lines.append(f"（背景は詳細版に：{prem['url']}）")
        lines.append("")

    if untouched:
        lines.append("【今月は関係のない容器】")
        lines.append("")
        for no in untouched:
            lines.append(f"・#{no} {names.get(no, '')}：今月の更新に該当なし")
        lines.append("")
        lines.append("■ ここを埋める：本当に関係ないか一応確認。"
                     "「なぜ関係ないか」を一言添えると価値が上がる"
                     "（例：今回の改正はプラスチック規則の話なので、"
                     "ガラス瓶本体には及ばない）。")
        lines.append("")

    if unrelated:
        lines.append("【キーワードに引っかからなかった更新】")
        lines.append("")
        for it in unrelated:
            lines.append(f"・{it.get('regionLabel', '')} {it.get('title', '')}")
        lines.append("")
        lines.append("■ ここを埋める：自動判定から漏れた分。"
                     "読んで、関係あれば上のセクションに移す。")
        lines.append("")

    lines.append("──")
    lines.append("")
    lines.append(f"容器別の記事一覧・更新履歴は {ARTICLES_URL} に、"
                 f"規制アップデートの元データは {HP_URL} で毎日自動更新しています。")
    lines.append(f"X： {X_URL}")
    lines.append("")
    lines.append("本記事は一般的な情報提供を目的としたものであり、"
                 "法的助言ではありません。個別の輸出案件については、"
                 "最新の一次情報および専門家への確認をお願いします。")

    return title, "\n".join(lines)


def main():
    ym = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y-%m")

    if not os.environ.get("NOTE_SESSION_COOKIE"):
        print("[warn] NOTE_SESSION_COOKIE が未設定のため、下書き作成をスキップします")
        return

    updates = load_json(UPDATES_FILE, [])
    items = [u for u in updates if in_month(u, ym)]
    if not items:
        print(f"[info] {ym} の更新が0件のため、下書きは作りません")
        return

    drafted = load_json(DRAFTED_FILE, [])
    if ym in drafted:
        print(f"[info] {ym} の下書きは作成済みです（重複作成を防止）")
        return

    names = container_names()
    title, body = build_draft(ym, items, names)

    try:
        client = NoteClient()
        note_id, note_key = client.create_empty_draft()
        client.save_draft(note_id, title, body)
    except NoteError as e:
        print(f"[error] 下書き作成に失敗: {e}")
        return

    drafted.append(ym)
    save_json(DRAFTED_FILE, drafted)

    print(f"[ok] {ym} の下書きを作成しました（{len(items)}件を整理）")
    print(f"     https://editor.note.com/notes/{note_key}/edit")
    print("     内容を確認・肉付けしてから手動で公開してください")


if __name__ == "__main__":
    main()
