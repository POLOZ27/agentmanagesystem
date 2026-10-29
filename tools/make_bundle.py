"""把资料打成加密收件箱的包：python tools/make_bundle.py <inbox.pub> <输出目录> <包名> --workbook X.xlsx --contracts 目录 [--tracker Y.xlsx]

输出 <包名>.json + <包名>.part001…（每份不超过 --chunk MB），拷到服务器 <数据目录>/inbox/ 即可。
"""
import argparse
import hashlib
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inbox  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("pub"), ap.add_argument("out"), ap.add_argument("name")
ap.add_argument("--workbook"), ap.add_argument("--contracts"), ap.add_argument("--tracker")
ap.add_argument("--chunk", type=int, default=25)
a = ap.parse_args()

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
    if a.workbook:
        z.write(a.workbook, "workbook.xlsx")
    if a.tracker:
        z.write(a.tracker, "tracker.xlsx")
    if a.contracts:
        for f in sorted(os.listdir(a.contracts)):
            p = os.path.join(a.contracts, f)
            if os.path.isfile(p) and f.lower().endswith((".pdf", ".doc", ".docx")):
                z.write(p, "contracts/" + f)
blob = inbox.seal(open(a.pub).read().strip(), buf.getvalue())
os.makedirs(a.out, exist_ok=True)
size = a.chunk * 1024 * 1024
parts = [blob[i:i + size] for i in range(0, len(blob), size)]
for i, part in enumerate(parts, 1):
    with open(os.path.join(a.out, f"{a.name}.part{i:03d}"), "wb") as f:
        f.write(part)
with open(os.path.join(a.out, a.name + ".json"), "w") as f:
    json.dump({"parts": len(parts), "sha256": hashlib.sha256(blob).hexdigest()}, f)
print(f"{len(parts)} 份，共 {len(blob) / 1e6:.1f} MB")
