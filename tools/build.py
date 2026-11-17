"""店舗データを index.html に同梱して、配信用フォルダを作る。

    python -I tools/build.py                      # LAN 版: public/（Service Worker のスコープ ./）
    python -I tools/build.py --out ../oishii-map-public --scope /oishii-map/   # 公開版

入力:
  data/stores.txt   店名｜エリア・最寄り駅｜ジャンル｜看板メニュー｜根拠｜食べログURL（1行1店）
  data/coords.json  tools/resolve.py が作る座標（出所 osm/geocode・最終確認日つき）
座標が確定していない店（coords.json の pending）は地図に載せない。
外部への通信はしない。
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ジャンルのチップ（表示順）。データの「ジャンル」をこのどれかにまとめる。詳細カードには元のジャンル名を出す。
GENRE_GROUPS = [
    ("寿司", ["寿司", "立ち食い寿司"]),
    ("和食", ["日本料理", "郷土料理", "かつ丼", "天ぷら", "海鮮・魚料理"]),
    ("うなぎ", ["うなぎ"]),
    ("そば・うどん", ["そば", "うどん"]),
    ("鍋・もんじゃ・お好み焼き", ["どじょう", "ちゃんこ鍋", "牛鍋", "もんじゃ焼き", "お好み焼き"]),
    ("ラーメン", ["ラーメン", "つけ麺", "担々麺", "まぜそば"]),  # 「ラーメン（醤油）」などもここ
    ("焼肉", ["焼肉"]),
    ("居酒屋・焼き鳥", ["居酒屋", "もつ焼き", "もつ焼き・居酒屋", "焼き鳥"]),
    ("中華", ["町中華", "中華料理", "四川料理", "餃子", "餃子・町中華"]),
    ("定食", ["定食", "弁当・惣菜"]),
    ("とんかつ", ["とんかつ"]),
    ("洋食", ["洋食", "洋食・ステーキ", "ステーキ", "ハンバーグ", "ハンバーガー"]),
    ("カレー", ["カレー", "スパイスカレー"]),
    ("イタリアン・フレンチ", ["イタリアン", "フレンチ", "ビストロ", "ピザ"]),
    ("アジア・エスニック", ["アジア・エスニック", "インド・ネパール料理", "韓国料理"]),
    ("喫茶・カフェ", ["喫茶店", "カフェ"]),
    ("パン", ["パン"]),
    ("甘味", ["和菓子", "スイーツ", "たい焼き"]),
]

# 根拠タグ（表示順）と、「根拠」文から付ける規則
TAGS = ["百名店", "ミシュラン", "Tabelog Award", "老舗", "TV紹介", "地元名物・ご当地", "メディア紹介"]
OLD_YEARS = 50  # 創業・開店から50年以上を「老舗」とする（2026年基準で1976年以前）


def tags_of(basis):
    t = []
    if "百名店" in basis:
        t.append("百名店")
    if "ミシュラン" in basis:
        t.append("ミシュラン")
    if "Tabelog Award" in basis:
        t.append("Tabelog Award")
    years = [int(y) for y in re.findall(r"(\d{4})年(?:創業|開店|オープン|開業)", basis)]
    # 「創業50年」「60年続く」「70年の歴史」のような年数表現
    spans = [int(x or y) for x, y in re.findall(r"創業(?:約)?(\d{2,3})年|(\d{2,3})年(?:以上)?(?:続く|の歴史|超)", basis)]
    if ("老舗" in basis or "最古" in basis or "明治" in basis or "昭和" in basis
            or any(y <= 2026 - OLD_YEARS for y in years) or any(n >= OLD_YEARS for n in spans)):
        t.append("老舗")
    if "TV紹介" in basis:
        t.append("TV紹介")
    if re.search(r"公式|観光協会|発祥|元祖|名物|ご当地|代表店|表彰|お土産100選|いちおしグルメ|しながわみやげ", basis):
        t.append("地元名物・ご当地")
    if re.search(r"メディア紹介|『[^』]+』|Hanako|Retty|おーたふる|TRY", basis):
        t.append("メディア紹介")
    return t


def group_of(genre):
    for g, members in GENRE_GROUPS:
        if genre in members or (g == "ラーメン" and genre.startswith("ラーメン")):
            return g
    raise SystemExit(f"ジャンル「{genre}」のチップが未定義です。tools/build.py の GENRE_GROUPS に追加してください。")


def load_stores():
    out = []
    for i, line in enumerate(open(os.path.join(ROOT, "data/stores.txt"), encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("｜")
        if len(f) != 6:
            raise SystemExit(f"data/stores.txt {i}行目: 区切り「｜」で6項目になっていません: {line}")
        name, area, genre, menu, basis, url = (x.strip() for x in f)
        if not re.match(r"^https://tabelog\.com/[a-z]+/A\d+/A\d+/\d+/$", url):
            raise SystemExit(f"data/stores.txt {i}行目: 食べログURLの形式が違います: {url}")
        out.append({"name": name, "area": area, "genre": genre, "menu": menu, "basis": basis, "url": url})
    names = [s["name"] for s in out]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise SystemExit(f"店名が重複しています: {dup}")
    return out


def sha256_b64(text):
    return "sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "public"))
    ap.add_argument("--scope", default="./")
    a = ap.parse_args()

    coords = json.load(open(os.path.join(ROOT, "data/coords.json"), encoding="utf-8"))
    stores, skipped = [], []
    for s in load_stores():
        c = coords["coords"].get(s["name"])
        if not c:
            skipped.append(s["name"])
            continue
        stores.append({
            **s,
            "group": group_of(s["genre"]),
            "tags": tags_of(s["basis"]),
            "lat": c["lat"],
            "lon": c["lon"],
            "src": c["source"],  # 座標の出所 osm / geocode
            "checked": c["checked"],
        })
    used_groups = [g for g, _ in GENRE_GROUPS if any(s["group"] == g for s in stores)]
    data = {"checked": coords["checked"], "genres": used_groups, "tags": TAGS, "stores": stores}
    # </script> を含まないよう「<」をエスケープして埋め込む
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")

    src = os.path.join(ROOT, "src")
    style = open(os.path.join(src, "style.css"), encoding="utf-8").read()
    script = open(os.path.join(src, "app.js"), encoding="utf-8").read().replace("{{SW_SCOPE}}", a.scope)
    csp = "; ".join([
        "default-src 'self'",
        f"script-src 'self' '{sha256_b64(script)}'",
        f"style-src 'self' '{sha256_b64(style)}'",
        "img-src 'self' data: https://tile.openstreetmap.org",
        "connect-src 'self'",
        "worker-src 'self'",
        "manifest-src 'self'",
        "base-uri 'self'",
        "form-action 'none'",
        "object-src 'none'",
    ])
    y, m, d = coords["checked"].split("-")
    html = (open(os.path.join(src, "index.template.html"), encoding="utf-8").read()
            .replace("{{CSP}}", csp)
            .replace("{{STYLE}}", style)
            .replace("{{SCRIPT}}", script)
            .replace("{{DATA}}", data_json)
            .replace("{{CHECKED_JA}}", f"{int(y)}年{int(m)}月{int(d)}日"))

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    for name in ("sw.js", "manifest.webmanifest"):
        shutil.copyfile(os.path.join(src, name), os.path.join(a.out, name))
    pub = os.path.join(ROOT, "public")
    if os.path.isdir(pub) and os.path.abspath(a.out) != os.path.abspath(pub):
        for d in ("icons", "vendor"):
            shutil.copytree(os.path.join(pub, d), os.path.join(a.out, d), dirs_exist_ok=True)

    print(f"掲載 {len(stores)}店 → {a.out}（SW スコープ {a.scope}）")
    for g in used_groups:
        print(f"  {g}: {sum(1 for s in stores if s['group'] == g)}")
    for t in TAGS:
        print(f"  #{t}: {sum(1 for s in stores if t in s['tags'])}")
    untagged = [s["name"] for s in stores if not s["tags"]]
    if untagged:
        print("  根拠タグなし:", "、".join(untagged))
    if skipped:
        print("  座標未確定で除外:", "、".join(skipped))


if __name__ == "__main__":
    main()
