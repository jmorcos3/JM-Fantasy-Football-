"""Player headshots from nflverse (official NFL photos), with Sleeper's thumbnails as a fallback.

nflverse links point at multi-megabyte originals, so every URL is rewritten to a small face crop.
"""
import base64
import csv
import io
import os
import urllib.request

from .http import CACHE_DIR, UA
from .markets import norm_name

SRC = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
SIZE = "w_96,h_96,c_fill,g_face,f_jpg,q_70"


def _fetch(url, name, ttl):
    import time
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, name)
    if not (os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl):
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "rb") as f:
        return f.read()


def _small(url):
    return url.replace("/image/upload/f_auto,q_auto/", f"/image/upload/{SIZE}/") if "/image/upload/" in url else url


def build(players):
    """Returns a function pid -> image URL (or None)."""
    by_gsis, by_espn, by_name = {}, {}, {}
    try:
        rows = csv.DictReader(io.StringIO(_fetch(SRC, "nflverse_players.csv", 86400).decode("utf-8")))
        for x in sorted(rows, key=lambda x: x.get("last_season") or ""):  # newest season wins name clashes
            if not x.get("headshot"):
                continue
            url = _small(x["headshot"])
            by_gsis[x["gsis_id"]] = url
            if x.get("espn_id"):
                by_espn[x["espn_id"]] = url
            by_name[(norm_name(x.get("display_name") or ""), x.get("position"))] = url
    except Exception as e:  # photos are cosmetic: never fail the run over them
        print(f"nflverse headshots unavailable ({e}); using Sleeper thumbnails")

    def url(pid):
        p = players.get(pid) or {}
        if p.get("position") == "DEF" or (pid.isalpha() and len(pid) <= 3):
            return f"https://sleepercdn.com/images/team_logos/nfl/{pid.lower()}.png"
        if not p:
            return None
        pos = "K" if p.get("position") == "K" else p.get("position")
        return (by_gsis.get((p.get("gsis_id") or "").strip()) or by_espn.get(str(p.get("espn_id")))
                or by_name.get((norm_name(p.get("full_name") or ""), pos))
                or f"https://sleepercdn.com/content/nfl/players/thumb/{pid}.jpg")

    return url


def embed(html):
    """Inline every headshot as a data URI, for hosts that block external images."""
    import re
    cache = {}

    def sub(m):
        u = m.group(1)
        if u not in cache:
            try:
                raw = _fetch(u, "img_" + base64.urlsafe_b64encode(u.encode()).decode()[-80:], 7 * 86400)
                kind = "png" if raw[:4] == b"\x89PNG" else "jpeg"
                cache[u] = f"data:image/{kind};base64,{base64.b64encode(raw).decode()}" if len(raw) < 60000 else ""
            except Exception:
                cache[u] = ""
        return f'<img class="hs" src="{cache[u]}"' if cache[u] else '<img class="hs" hidden src=""'

    return re.sub(r'<img class="hs" src="([^"]+)"', sub, html)
