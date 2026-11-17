"""data/addresses.txt の住所を座標にする（結果は data/raw/geocode.json に保存）。

    python -I tools/geocode.py

1) Nominatim（OpenStreetMap）を先に試し、結果は nominatim_ref に参考として残す。
   2026-11-13 の調査で、日本の住所は町名止まりか、街区番号と建物番号を取り違えた地点
   （例: 銀座4-11-7 → 銀座4-5-11 の建物）を返すことが分かったため、座標には使わない。
2) 座標は国土地理院「住所検索」API の結果を使う。返ってきた住所が「〜番」「〜号」「〜番地」まで
   一致した場合だけ採用する（大字・町名止まりは不採用 = geocode なし）。
問い合わせは1秒以上あけ、外部へ送るのは住所文字列だけ。
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "OishiiMap/1.0 (unofficial personal map)"}
OUT = "data/raw/geocode.json"
KANJI = "〇一二三四五六七八九"


def get(url):
    for attempt in range(5):  # 一時的な 503 などは待って再試行
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))


def kanji_num(n):
    n = int(n)
    if n < 10:
        return KANJI[n]
    t, o = divmod(n, 10)
    return ("" if t == 1 else KANJI[t]) + "十" + (KANJI[o] if o else "")


def parse(addr):
    """'東京都中央区銀座8-3-1' → 町名部分 '銀座', 丁目 8, 残り ['3','1']"""
    a = unicodedata.normalize("NFKC", addr)
    m = re.match(r"^(.+?[都道府県])(.+?(?:市.+?区|郡.+?[町村]|[市区町村]))(.+?)(\d+(?:-\d+)*)$", a)
    if not m:
        return None
    pref, city, town, nums = m.groups()
    parts = nums.split("-")
    return {"pref": pref, "city": city, "town": town, "nums": parts}


def has_chome(p):
    """先頭の数字が丁目か（2つ以上の数字があり、先頭が1〜9）。'白井久保296-8' のような番地は丁目なし"""
    return len(p["nums"]) >= 2 and int(p["nums"][0]) <= 9


def block_of(p):
    """街区番号（丁目ありなら2つ目、なしなら先頭）"""
    if not p:
        return None
    return p["nums"][1] if has_chome(p) else p["nums"][0]


def nominatim(addr, p):
    queries = [addr]
    block = block_of(p)
    if p and has_chome(p):
        chome = f"{p['town']}{kanji_num(p['nums'][0])}丁目"
        queries.append(f"{p['nums'][1]}, {chome}, {p['city']}, {p['pref']}")
    for q in queries:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": q, "format": "jsonv2", "addressdetails": 1, "limit": 5, "countrycodes": "jp"})
        res = get(url)
        time.sleep(1.2)
        for r in res:
            ad = r.get("address", {})
            if r.get("addresstype") in ("suburb", "quarter", "neighbourhood", "city", "town", "village", "city_district", "province", "state", "road", "hamlet"):
                continue
            hn = unicodedata.normalize("NFKC", ad.get("house_number", ""))
            # 番地（2つ目の数字）か、住所全体の番地列が一致するものだけ
            if p and hn and hn.split("-")[0] == block:
                town_ok = p["town"] in r.get("display_name", "")
                if town_ok:
                    return {"geocoder": "nominatim", "lat": float(r["lat"]), "lon": float(r["lon"]),
                            "matched": r["display_name"], "query": q}
    return None


def gsi(addr, p):
    url = "https://msearch.gsi.go.jp/address-search/AddressSearch?" + urllib.parse.urlencode({"q": addr})
    res = get(url)
    time.sleep(0.6)
    for r in res:
        title = unicodedata.normalize("NFKC", r["properties"]["title"])
        if not re.search(r"\d+(番|号|番地)", title):
            continue  # 大字・町名止まり
        # 問い合わせの町名と番地の頭が一致すること
        if p and p["town"] not in title:
            continue
        lon, lat = r["geometry"]["coordinates"]
        return {"geocoder": "gsi", "lat": lat, "lon": lon, "matched": r["properties"]["title"], "query": addr}
    return {"geocoder": None, "best": res[0]["properties"]["title"] if res else None, "query": addr}


def main():
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    for line in open("data/addresses.txt", encoding="utf-8"):
        if not line.strip() or line.startswith("#"):
            continue
        name, addr = line.rstrip("\n").split("｜")
        if name in done and done[name].get("address") == addr:
            continue
        p = parse(addr)
        nom = nominatim(addr, p)
        r = gsi(addr, p)
        # Nominatim は日本の住所の番地を正しく引けない（街区番号と建物番号の取り違えを確認）ため参考記録のみ。
        r["nominatim_ref"] = nom
        r["address"] = addr
        done[name] = r
        print(name, "→", r.get("geocoder"), r.get("lat"), r.get("lon"), r.get("matched") or r.get("best"))
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            json.dump(done, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
