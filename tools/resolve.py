"""OSM 候補（data/raw/osm_candidates.json）と住所の座標（data/raw/geocode.json）を照合して
data/coords.json を作る。

    python -I tools/resolve.py

規則（推測で座標を置かない）:
  - OSM 候補 = 店名の検索語に一致し、飲食・食品系の地点。
  - OSM と geocode の両方がある店: 距離 200m 以内なら OSM の座標（source=osm）。
    200m を超える／近くに OSM 候補がない店は geocode の座標（source=geocode）。
  - geocode が無い店（番地まで引けない）: OSM 候補の addr:* タグが公開情報の住所と一致する場合だけ OSM を使う。
  - 最後に Nominatim の逆ジオコーディングで市区町村を取り、住所の市区町村と一致しない店は外す（座標未確定）。
"""
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match_terms import TERMS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "OishiiMap/1.0 (unofficial personal map)"}
CHECKED = "2026-11-13"
FOOD_AMENITY = {"restaurant", "cafe", "fast_food", "bar", "pub", "food_court", "ice_cream"}
FOOD_SHOP = {"bakery", "confectionery", "pastry", "deli", "coffee", "tea"}
MAX_PAIR_M = 200
REV_CACHE = "data/raw/reverse.json"
# 手作業で確認した結果、店名は一致するが別の店（支店・旧店舗など）と分かった OSM 地点
MANUAL_OSM = json.load(open("data/osm_manual.json", encoding="utf-8")) if os.path.exists("data/osm_manual.json") else {}
EXCLUDE_OSM = json.load(open("data/osm_exclude.json", encoding="utf-8")) if os.path.exists("data/osm_exclude.json") else {}


def hav(a, b):
    r = math.radians
    h = math.sin(r(b[0] - a[0]) / 2) ** 2 + math.cos(r(a[0])) * math.cos(r(b[0])) * math.sin(r(b[1] - a[1]) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def norm(s):
    return unicodedata.normalize("NFKC", s or "")


def municipality(addr):
    a = norm(addr)
    m = re.match(r"^(.+?[都道府県])(.+?市.+?区|.+?郡.+?[町村]|.+?[市区町村])", a)
    return m.group(2) if m else None


def reverse(lat, lon, cache):
    key = f"{lat:.6f},{lon:.6f}"
    if key in cache:
        return cache[key]
    url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
        {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 1, "accept-language": "ja"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as res:
                r = json.loads(res.read().decode("utf-8"))
            break
        except Exception:  # noqa: BLE001
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
    time.sleep(1.2)
    cache[key] = r
    with open(REV_CACHE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cache, f, ensure_ascii=False)
    return r


# 自動照合で店名から外す一般語（「〇〇店」「本店」やジャンル名だけでは同じ店とみなさない）
GENERIC = re.compile(
    r"(総本店|本店|本舗|支店|らーめん|ラーメン|らぁ麺|拉麺|中華そば|中華ソバ|中華料理|中国料理|中華|"
    r"そば処|手打ちそば|手打ち|蕎麦|そば|うどん|寿司|鮨|すし|とんかつ|洋食|食堂|喫茶|珈琲|コーヒー|カフェ|cafe|"
    r"レストラン|restaurant|居酒屋|酒場|焼肉|焼き鳥|焼鳥|やきとり|天ぷら|天麩羅|うなぎ|鰻|ベーカリー|bakery|"
    r"パン|菓子|お菓子|御菓子司|洋菓子|和菓子|餃子|麺屋|麺処|麺や|つけ麺|定食|キッチン|kitchen|グリル|ビストロ|bistro|"
    r"トラットリア|trattoria|カレー|curry)", re.I)


def norm_key(s):
    s = norm(s).lower()
    return re.sub(r"[\s・･'’\-‐()（）「」『』〜~!！.。、,]", "", s)


def core_of(name):
    s = re.sub(r"[（(][^）)]*[）)]", "", norm(name)).strip()  # 「（よみがな）」「（エリア）」は比べない
    s = re.sub(r"[\s　]+\S{0,8}店$", "", s)  # 「〇〇 上大岡店」の支店名部分
    return GENERIC.sub("", norm_key(s))


def auto_match(name, txts):
    """手作業の検索語が無い店用の自動照合: 一般語を除いた店名の中核が、OSM 名の中核と一致・包含するか"""
    c = core_of(name)
    if len(c) < 2:
        c = norm_key(name)  # 中核が短すぎる店名（例「とんかつ〇」）は店名全体で比べる
        return any(c and c == norm_key(t) for t in txts)
    for t in txts:
        o = core_of(t)
        if len(o) >= 2 and (c in o or o in c):
            return True
    return False


def candidates(name, els):
    pat = re.compile("|".join(TERMS[name]), re.I) if name in TERMS else None
    out = []
    seen = set()
    for e in els:
        t = e.get("tags", {})
        if t.get("amenity") not in FOOD_AMENITY and t.get("shop") not in FOOD_SHOP:
            continue
        oid0 = e["type"][0] + str(e["id"])
        if oid0 in seen:
            continue
        txts = [t.get(k, "") for k in ("name", "name:ja", "name:en", "alt_name", "brand", "old_name") if t.get(k)]
        if pat is not None:
            if not pat.search(" ".join(txts)):
                continue
        elif not auto_match(name, txts):
            continue
        seen.add(oid0)
        oid = e["type"][0] + str(e["id"])
        if oid in EXCLUDE_OSM.get(name, {}):
            continue
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        addr = " ".join(v for k, v in sorted(t.items()) if k.startswith("addr:"))
        out.append({"osm": oid, "lat": lat, "lon": lon, "name": t.get("name") or t.get("name:en") or "", "addr": addr})
    return out


def addr_matches(osm_addr, addr):
    """geocode が無い店用: OSM の addr タグに、公開情報の市区町村・大字・番地が全部含まれるか"""
    a = norm(addr)
    m = re.match(r"^(.+?[都道府県])(.+?郡)?(.+?[市町村])(.+?)(\d+)(?:-\d+)*$", a)
    if not m:
        return False
    _, _, city, town, num = m.groups()
    o = norm(osm_addr)
    return city in o and town in o and re.search(rf"(^|\D){num}(\D|$)", o) is not None


def main():
    els = json.load(open("data/raw/osm_candidates.json", encoding="utf-8"))["elements"]
    if os.path.exists("data/raw/osm_area.json"):  # 品川区・大田区の飲食店（自動照合用）
        els = els + json.load(open("data/raw/osm_area.json", encoding="utf-8"))["elements"]
    geo = json.load(open("data/raw/geocode.json", encoding="utf-8"))
    cache = json.load(open(REV_CACHE, encoding="utf-8")) if os.path.exists(REV_CACHE) else {}
    names = [l.split("｜")[0] for l in open("data/stores.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
    coords, pending, log = {}, [], []
    for name in names:
        g = geo[name]
        cands = candidates(name, els)
        gpt = (g["lat"], g["lon"]) if g.get("geocoder") else None
        rec = None
        note = ""
        if gpt:
            near = sorted(((hav(gpt, (c["lat"], c["lon"])), c) for c in cands), key=lambda x: x[0])
            if near and near[0][0] <= MAX_PAIR_M:
                d, c = near[0]
                rec = {"lat": round(c["lat"], 6), "lon": round(c["lon"], 6), "source": "osm", "osm": c["osm"],
                       "pair_distance_m": round(d)}
                note = f"OSM {c['osm']}「{c['name']}」と geocode の距離 {d:.0f}m"
            else:
                rec = {"lat": round(gpt[0], 6), "lon": round(gpt[1], 6), "source": "geocode"}
                nd = f"{near[0][0]:.0f}m 先の「{near[0][1]['name']}」" if near else "なし"
                note = f"200m 以内の OSM 候補なし（最寄りの同名候補: {nd}）"
            rec["geocoder"] = g["geocoder"]
            rec["geocode_matched"] = g["matched"]
        else:
            ok = [c for c in cands if addr_matches(c["addr"], g["address"])]
            if name in MANUAL_OSM:  # 手作業で同じ店と確認した OSM 地点（data/osm_manual.json に理由つき）
                ok = [c for c in cands if c["osm"] == MANUAL_OSM[name]["osm"]]
                for c in ok:
                    c["addr"] = c["addr"] or MANUAL_OSM[name]["reason"]
            if len(ok) == 1:
                c = ok[0]
                rec = {"lat": round(c["lat"], 6), "lon": round(c["lon"], 6), "source": "osm", "osm": c["osm"],
                       "osm_addr": c["addr"]}
                note = f"geocode は大字止まり（{g.get('best')}）。OSM {c['osm']}「{c['name']}」の住所タグ「{c['addr']}」が公開情報と一致"
                if name in MANUAL_OSM:
                    note = f"手作業で確認: {MANUAL_OSM[name]['reason']}"
                    rec["osm_manual"] = MANUAL_OSM[name]["reason"]
            else:
                pending.append({"name": name, "reason": f"番地まで座標化できず（{g.get('best')}）、住所の一致する OSM 地点もなし"})
                log.append(f"✗ {name}: 未確定")
                continue
        # 市区町村の確認
        rv = reverse(rec["lat"], rec["lon"], cache)
        ra = rv.get("address", {})
        rev_city = " ".join(ra.get(k, "") for k in ("province", "state", "county", "city", "municipality", "administrative", "town", "village", "city_district", "suburb", "quarter", "neighbourhood"))
        want = municipality(g["address"])
        parts = re.findall(r".+?(?:市|区|郡|町|村)", want or "")
        if not want or not all(p in norm(rev_city) for p in parts):
            pending.append({"name": name, "reason": f"逆ジオコーディングの市区町村（{rev_city.strip()}）が住所（{want}）と一致しない"})
            log.append(f"✗ {name}: 市区町村不一致 {rev_city} / {want}")
            continue
        rec["reverse"] = rv.get("display_name", "")
        rec["address"] = g["address"]
        rec["checked"] = CHECKED
        coords[name] = rec
        log.append(f"○ {name}: {rec['source']} {rec['lat']},{rec['lon']} | {note} | 逆: {rec['reverse'][:60]}")
    # 1つの OSM 地点を2店以上が使った（同名の支店など）→ 取り違えを避けるため、その店は住所の座標にする
    used = {}
    for name, rec in coords.items():
        if rec.get("source") == "osm":
            used.setdefault(rec["osm"], []).append(name)
    for oid, shared in used.items():
        if len(shared) < 2:
            continue
        for name in shared:
            g = geo[name]
            if not g.get("geocoder"):
                coords.pop(name)
                pending.append({"name": name, "reason": f"同名の別店と同じ OSM 地点 {oid} に当たり、住所も番地まで座標化できない"})
                continue
            rec = coords[name]
            rec.update({"lat": round(g["lat"], 6), "lon": round(g["lon"], 6), "source": "geocode",
                        "note": f"同名の別店と同じ OSM 地点 {oid} に当たったため住所の座標を使用"})
            rec.pop("osm", None)
            rec.pop("pair_distance_m", None)
            log.append(f"△ {name}: OSM {oid} を {len(shared)}店が共有 → geocode に変更")
    with open("data/coords.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"checked": CHECKED, "coords": coords, "pending": pending}, f, ensure_ascii=False, indent=1)
    print("\n".join(log))
    print(f"\n確定 {len(coords)} / 未確定 {len(pending)}")
    for p in pending:
        print(" -", p["name"], p["reason"])


if __name__ == "__main__":
    main()
