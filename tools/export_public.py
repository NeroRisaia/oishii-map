"""公開リポジトリへ data/ を書き出す（内部専用の情報は含めない）。

    python -I tools/export_public.py ../oishii-map-public

含めないもの: 座標未確定などで地図に載せていない店（coords.json の pending）とその理由、
OSM 除外リスト（data/osm_exclude.json）、調査の原票（data/candidates/）、保留リスト、data/raw/。
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.abspath(sys.argv[1])
src = os.path.join(ROOT, "data")
dst = os.path.join(out, "data")
os.makedirs(dst, exist_ok=True)

coords = json.load(open(os.path.join(src, "coords.json"), encoding="utf-8"))
hidden = {p["name"] for p in coords.get("pending", [])}
coords.pop("pending", None)
with open(os.path.join(dst, "coords.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(coords, f, ensure_ascii=False, indent=1)
    f.write("\n")

for name in ("stores.txt", "addresses.txt", "sources.txt"):
    lines = open(os.path.join(src, name), encoding="utf-8").read().split("\n")
    kept = [l for l in lines if l.startswith("#") or l.split("｜", 1)[0] not in hidden]
    open(os.path.join(dst, name), "w", encoding="utf-8", newline="").write("\n".join(kept))

shutil.copy(os.path.join(src, "osm_manual.json"), dst)
for name in ("osm_exclude.json",):
    p = os.path.join(dst, name)
    if os.path.exists(p):
        os.remove(p)
print(f"data/ → {dst}（非掲載 {len(hidden)} 店を除外）")
