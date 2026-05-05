#!/usr/bin/env python3
"""
Download a curated set of real ACiD Productions .ANS files from 16colo.rs.
Raw file URL pattern: https://16colo.rs/pack/{pack}/raw/{FILE.ANS}
"""
import os
import time
import urllib.request
import urllib.error

BASE = "https://16colo.rs"
OUT  = "assets/ansi/acid"

# Curated picks: mix of logos, info screens, art pieces
DOWNLOADS = [
    # acid-56  (1997, issue 56)
    ("acid-56", "GS-ACID.ANS"),    # Ghengis' Final ANSI
    ("acid-56", "KT-ABRAX.ANS"),   # Abraxas by KT
    ("acid-56", "MD-SKULL.ANS"),   # Skull by MD
    ("acid-56", "NEWS-56.ANS"),    # Newsfile

    # acid-50a (1996, 50th issue A-side)
    ("acid-50a", "ANS-50A.ANS"),   # 50th issue title
    ("acid-50a", "KM-FIFTY.ANS"),  # KM's 50th piece
    ("acid-50a", "RA-FIFTY.ANS"),  # RA's 50th piece
    ("acid-50a", "SE-JELLO.ANS"),  # SE Jello
    ("acid-50a", "SE-LIME.ANS"),   # SE Lime
    ("acid-50a", "NI-SKULL.ANS"),  # Skull by NI
    ("acid-50a", "GS-SHAD1.ANS"),  # Ghengis shade
    ("acid-50a", "PH-MOOSE.ANS"),  # Moose

    # acid-100 (milestone 100th issue)
    ("acid-100", "ANSI-100.ANS"),  # 100th issue ANSI board
    ("acid-100", "ANSC-100.ANS"),  # 100th credits
    ("acid-100", "DA-ANIME.ANS"),  # Anime art
    ("acid-100", "MAY-ACID.ANS"),  # May ACiD
    ("acid-100", "OS-HAZ01.ANS"),  # Hazard 01
    ("acid-100", "GO-EAST.ANS"),   # Go East
]


def download(pack: str, filename: str) -> bool:
    url = f"{BASE}/pack/{pack}/raw/{filename}"
    os.makedirs(OUT, exist_ok=True)
    dest = os.path.join(OUT, f"{pack}_{filename}")
    if os.path.exists(dest):
        print(f"  skip (exists): {dest}")
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "unicorn-viz/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 10:
            print(f"  SKIP (empty): {dest}")
            return False
        with open(dest, "wb") as f:
            f.write(data)
        print(f"  OK  {dest}  ({len(data)} bytes)")
        return True
    except Exception as e:
        print(f"  ERR {url}: {e}")
        return False


def main() -> None:
    ok = fail = 0
    for pack, fname in DOWNLOADS:
        if download(pack, fname):
            ok += 1
        else:
            fail += 1
        time.sleep(0.3)   # be polite
    print(f"\nDone: {ok} OK, {fail} failed → {OUT}/")


if __name__ == "__main__":
    main()
