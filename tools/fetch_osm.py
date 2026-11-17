"""掲載店の候補地点を OpenStreetMap（Overpass API）から一括取得する。

    python -I tools/fetch_osm.py data/raw/osm_candidates.json

data/stores.txt の店名から作った検索語（tools/match_terms.py の TERMS）を
首都圏（1都3県＋周辺）の範囲で、飲食・食品系の地点に限って探す。
データは © OpenStreetMap contributors（ODbL 1.0）。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match_terms import TERMS  # noqa: E402

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
BBOX = "34.85,138.70,36.35,140.95"  # 東京・神奈川・千葉・埼玉
USER_AGENT = "OishiiMap/1.0 (unofficial personal map; OSM data consumer)"


def query():
    pat = "|".join(sorted({t for terms in TERMS.values() for t in terms}))
    sel = []
    for key in ("name", "name:ja", "name:en", "alt_name", "brand", "old_name"):
        sel.append(f'nwr["{key}"~"{pat}",i]["amenity"]({BBOX});')
        sel.append(f'nwr["{key}"~"{pat}",i]["shop"]({BBOX});')
    return f"[out:json][timeout:300];\n(\n" + "\n".join(sel) + "\n);\nout center tags;"


def main(out):
    body = urllib.parse.urlencode({"data": query()}).encode()
    last = None
    for ep in ENDPOINTS:
        try:
            req = urllib.request.Request(ep, data=body, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=330) as res:
                data = json.loads(res.read().decode("utf-8"))
            if "elements" in data:
                print(f"ok endpoint={ep} elements={len(data['elements'])} osm_base={data.get('osm3s', {}).get('timestamp_osm_base')}")
                os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
                with open(out, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(data, f, ensure_ascii=False)
                return
            last = data.get("remark")
        except Exception as exc:  # noqa: BLE001
            last = f"{ep}: {exc}"
        print("retry:", last)
        time.sleep(5)
    raise SystemExit(f"Overpass 取得失敗: {last}")


if __name__ == "__main__":
    main(sys.argv[1])
