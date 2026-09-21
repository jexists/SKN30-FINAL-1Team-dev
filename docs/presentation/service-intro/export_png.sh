#!/bin/sh
# out/SalesLuv_서비스소개서@2x.pptx → out/png/*.png (1920×1080)
#
#   DECK_SCALE=2 /usr/local/bin/python3.12 build_pptx.py && ./export_png.sh
#
# soffice 가 없어 Keynote 가 유일한 렌더 경로다. Keynote 창이 잠깐 떴다 닫힌다.
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
rm -rf out/png && mkdir -p out/png

osascript <<AS
tell application "Keynote"
	set d to open POSIX file "$DIR/out/SalesLuv_서비스소개서@2x.pptx"
	delay 4
	export d to POSIX file "$DIR/out/png" as slide images ¬
		with properties {image format:PNG, skipped slides:false}
	close d saving no
end tell
AS

# Keynote 는 png.001.png 로 뱉는다. pages.json 순서대로 slug 를 붙인다.
/usr/local/bin/python3.12 - <<'PY'
import json, pathlib, re
here = pathlib.Path("out/png")
slugs = [p["slug"] for p in json.loads(pathlib.Path("pages.json").read_text(encoding="utf-8"))]
for f in sorted(here.glob("*.png")):
    m = re.search(r"\.(\d+)\.png$", f.name)
    if m:
        f.rename(here / f"{slugs[int(m.group(1)) - 1]}.png")
print(f"  → out/png/ ({len(slugs)}장, 1920×1080)")
PY
