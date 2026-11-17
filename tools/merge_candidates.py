"""調査担当が data/candidates/*.txt に書いた候補を検査し、掲載リストへ追記する。

    python -I tools/merge_candidates.py          # 検査結果を表示するだけ
    python -I tools/merge_candidates.py --apply  # data/stores.txt・addresses.txt・sources.txt に追記

候補の形式（全角「｜」区切り8項目）:
  店名｜エリア・最寄り駅｜ジャンル｜看板メニュー｜根拠｜食べログURL｜住所｜出典URL
検査: 項目数、食べログURLの形式、住所が対象の区（品川区・大田区）か、評点らしき数字が根拠に無いか、
既存の掲載店・保留リストとの重複、候補どうしの重複（食べログURL・店名）。
外部への通信はしない。
"""
import glob
import os
import re
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_WARDS = ("東京都品川区", "東京都大田区")
HOLD_FILE = os.path.join(ROOT, "保留リスト.txt")  # 内部ファイル（公開リポジトリには置かない）


def load_hold():
    """保留リスト.txt の「店名（補足）」行から店名を読む。ファイルが無ければ空。"""
    if not os.path.exists(HOLD_FILE):
        return []
    names = []
    for line in open(HOLD_FILE, encoding="utf-8"):
        m = re.match(r"^(.+?)（.*）\s*$", line.strip())
        if m and "保留リスト" not in line:
            names.append(m.group(1))
    return names


HOLD = load_hold()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import GENRE_GROUPS  # noqa: E402

GENRES = {g for _, members in GENRE_GROUPS for g in members}
URL_RE = re.compile(r"^https://tabelog\.com/tokyo/A\d{4}/A\d{6}/\d{8}/$")


def key(name):
    s = unicodedata.normalize("NFKC", name).lower()
    return re.sub(r"[\s・･'’\-‐（）()「」『』]", "", s)


def lines(path):
    for i, line in enumerate(open(path, encoding="utf-8-sig"), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            yield i, line


def main(apply):
    existing = {}
    for _, l in lines(os.path.join(ROOT, "data/stores.txt")):
        f = l.split("｜")
        existing[key(f[0])] = f[5]
    existing_urls = set(existing.values())
    hold = {key(h) for h in HOLD}

    accepted, rejected = [], []
    seen_url, seen_name = {}, {}
    for path in sorted(glob.glob(os.path.join(ROOT, "data/candidates/*.txt"))):
        src = os.path.basename(path)
        for i, l in lines(path):
            f = [x.strip() for x in l.split("｜")]
            why = None
            if len(f) != 8:
                why = f"項目数 {len(f)}"
            else:
                name, area, genre, menu, basis, url, addr, cite = f
                url = re.sub(r"^https://tabelog\.com/(en|cn|tw|kr)/", "https://tabelog.com/", url)
                if not url.endswith("/"):
                    url += "/"
                addr = re.sub(r"(?<=\d)[−‐ー―–](?=\d)", "-", unicodedata.normalize("NFKC", addr))
                addr = re.sub(r"(\d+)丁目(\d)", r"\1-\2", addr).replace("番地", "-").replace("番", "-").replace("号", "").rstrip("-")
                f[5], f[6] = url, addr
                k = key(name)
                if not all([name, area, genre, menu, basis, url, addr]):
                    why = "空の項目あり"
                elif genre not in GENRES and not genre.startswith("ラーメン"):
                    why = f"ジャンル未定義 {genre}"
                elif not URL_RE.match(url):
                    why = f"食べログURLの形式 {url}"
                elif not addr.startswith(TARGET_WARDS):
                    why = f"対象外の住所 {addr}"
                elif not re.search(r"\d", addr):
                    why = f"番地なしの住所 {addr}"
                elif re.search(r"[0-9]\.[0-9]{2}|点|★|口コミ|評価", basis):
                    why = f"根拠に評点・口コミらしき表現 {basis}"
                elif re.fullmatch(r"メディア紹介（『品川経済新聞』\d{4}年）", basis):
                    why = "根拠が開店ニュース記事だけ（評判の根拠にならない）"
                elif url in existing_urls:
                    why = "既存の掲載店と重複"
                elif k in hold or any(h in k for h in hold):
                    why = "保留リストの店"
            if why:
                rejected.append((src, i, f[0] if f else l, why))
                continue
            if f[5] in seen_url:
                # 同じ店（同じ食べログURL）を複数の担当が出した: 根拠の多い方を残す
                j = seen_url[f[5]]
                old = accepted[j]
                keep, drop = (f, old) if len(f[4]) > len(old[4]) else (old, f)
                accepted[j] = keep
                rejected.append((src, i, drop[0], f"同じ店の重複（根拠の多い方を採用: {keep[4]}）"))
                continue
            seen_url[f[5]] = len(accepted)
            accepted.append(f)

    # 店名だけが同じ別の店（食べログURL・住所が別）は「店名（エリア）」にして区別する
    names = {}
    for f in accepted:
        names.setdefault(key(f[0]), []).append(f)
    for k, group in names.items():
        if len(group) > 1 or k in existing:
            for f in group:
                f[0] = f"{f[0]}（{f[1].split('・')[0]}）"

    print(f"採用候補 {len(accepted)}件 / 除外 {len(rejected)}件")
    for r in rejected:
        print("  除外", *r)
    if not apply:
        return
    with open(os.path.join(ROOT, "data/stores.txt"), "a", encoding="utf-8", newline="\n") as fs, \
            open(os.path.join(ROOT, "data/addresses.txt"), "a", encoding="utf-8", newline="\n") as fa, \
            open(os.path.join(ROOT, "data/sources.txt"), "a", encoding="utf-8", newline="\n") as fc:
        for f in accepted:
            fs.write("｜".join(f[:6]) + "\n")
            fa.write(f"{f[0]}｜{f[6]}\n")
            fc.write(f"{f[0]}｜{f[7]}\n")
    print("追記しました")


if __name__ == "__main__":
    main("--apply" in sys.argv)
