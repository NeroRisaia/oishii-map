"""品川区・大田区の名前つき飲食・食品系の地点を OpenStreetMap（Overpass API）から一括取得する。

    python -I tools/fetch_osm_area.py data/raw/osm_area.json

店名の自動照合（tools/resolve.py）に使う。データは © OpenStreetMap contributors（ODbL 1.0）。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
USER_AGENT = "OishiiMap/1.0 (unofficial personal map; OSM data consumer)"
QUERY = """[out:json][timeout:300];
(area["name"="品川区"]["admin_level"="7"];area["name"="大田区"]["admin_level"="7"];)->.w;
(
  nwr["name"]["amenity"~"^(restaurant|cafe|fast_food|bar|pub|food_court|ice_cream)$"](area.w);
  nwr["name"]["shop"~"^(bakery|confectionery|pastry|deli|coffee|tea)$"](area.w);
);
out center tags;"""


def main(out):
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    last = None
    for ep in ENDPOINTS:
        try:
            req = urllib.request.Request(ep, data=body, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=330) as res:
                data = json.loads(res.read().decode("utf-8"))
            if data.get("elements"):
                print(f"ok {ep} elements={len(data['elements'])} osm_base={data.get('osm3s', {}).get('timestamp_osm_base')}")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                json.dump(data, open(out, "w", encoding="utf-8", newline="\n"), ensure_ascii=False)
                return
            last = data.get("remark")
        except Exception as exc:  # noqa: BLE001
            last = f"{ep}: {exc}"
        print("retry:", last)
        time.sleep(5)
    raise SystemExit(f"Overpass 取得失敗: {last}")


if __name__ == "__main__":
    main(sys.argv[1])
