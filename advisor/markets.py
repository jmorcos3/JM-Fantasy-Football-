"""Market signals.

1. Sportsbook game lines (DraftKings, via ESPN's public scoreboard) -> implied team totals.
2. Kalshi prediction-market player props (yardage / reception / TD ladders) -> market-implied
   expected stat lines, which are then re-scored with each league's own scoring rules.
"""
import math
import re
import time
from datetime import datetime, timedelta, timezone

from .http import get_json

ESPN_ABBR = {"WSH": "WAS"}
KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets"
# series -> (sleeper stat key, is_count_stat)
SERIES = {
    "KXNFLPASSYDS": ("pass_yd", False), "KXNFLRSHYDS": ("rush_yd", False), "KXNFLRECYDS": ("rec_yd", False),
    "KXNFLREC": ("rec", True), "KXNFLPASSTDS": ("pass_td", True), "KXNFLTD": ("td", True),
}


def game_lines(season, week):
    d = get_json("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
                 f"?week={week}&seasontype=2&dates={season}", ttl=900)
    out = {}
    for e in d.get("events", []):
        c = e["competitions"][0]
        teams = {t["homeAway"]: ESPN_ABBR.get(t["team"]["abbreviation"], t["team"]["abbreviation"]) for t in c["competitors"]}
        odds = (c.get("odds") or [None])[0] or {}
        total, spread = odds.get("overUnder"), odds.get("spread")
        for side, other in (("home", "away"), ("away", "home")):
            row = {"opp": teams[other], "home": side == "home", "kickoff": e["date"], "total": total, "spread": None,
                   "implied": None, "done": e["status"]["type"].get("completed", False)}
            if total is not None and spread is not None:
                line = spread if side == "home" else -spread  # negative = favourite
                row["spread"] = line
                row["implied"] = round(total / 2 - line / 2, 1)
            out[teams[side]] = row
    return out


def norm_name(n):
    n = re.sub(r"[^a-z ]", "", n.lower().replace("-", " "))
    return " ".join(w for w in n.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def _mid(m):
    try:
        bid, ask = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
    except ValueError:
        return None
    if ask <= 0 or ask - bid > 0.2:  # no real two-sided market
        return None
    return (bid + ask) / 2


def _ladder_mean(points, count):
    """points: [(threshold, P(X >= threshold))]. Expected value = area under the survival curve."""
    pts = sorted(points)
    run, clean = 1.0, []
    for t, p in pts:  # enforce a non-increasing survival curve
        run = min(run, p)
        clean.append((t, run))
    if count:
        ks = [(int(math.ceil(t)), p) for t, p in clean]
        if len(ks) == 1:
            k, p = ks[0]
            return -math.log(max(1 - p, 1e-6)) if k == 1 else None  # Poisson mean from P(X>=1)
        ev, prev_k, prev_p = 0.0, 0, 1.0
        for k, p in ks:
            for j in range(prev_k + 1, k + 1):  # fill unlisted rungs linearly
                ev += prev_p + (p - prev_p) * (j - prev_k) / (k - prev_k)
            prev_k, prev_p = k, p
        ratio = min(0.8, ks[-1][1] / ks[-2][1]) if ks[-2][1] > 0 else 0
        return ev + (ks[-1][1] * ratio / (1 - ratio) if ratio else 0)
    if len(clean) < 3 or clean[0][1] < 0.45 or clean[-1][1] > 0.3:
        return None  # ladder does not bracket the middle of the distribution
    ev, prev_t, prev_p = 0.0, 0.0, 1.0
    for t, p in clean:
        ev += (prev_p + p) / 2 * (t - prev_t)
        prev_t, prev_p = t, p
    step = clean[-1][0] - clean[-2][0]
    if 0 < clean[-1][1] < clean[-2][1]:
        ev += min(clean[-1][1] * step / math.log(clean[-2][1] / clean[-1][1]), 3 * step * clean[-1][1])
    return ev


def kalshi_props(days_ahead=7):
    """Returns {normalised player name: {stat: market-implied mean}} for games in the coming week."""
    horizon = datetime.now(timezone.utc) + timedelta(days=days_ahead + 1)
    ladders = {}
    for series, (stat, _) in SERIES.items():
        cursor = ""
        for _ in range(10):
            try:
                d = get_json(f"{KALSHI}?series_ticker={series}&status=open&limit=1000" + (f"&cursor={cursor}" if cursor else ""), ttl=900)
            except Exception:
                break
            for m in d.get("markets", []):
                exp = m.get("expected_expiration_time") or m.get("close_time") or ""
                try:
                    if datetime.fromisoformat(exp.replace("Z", "+00:00")) > horizon:
                        continue
                except ValueError:
                    continue
                p, strike = _mid(m), m.get("floor_strike")
                if p is None or strike is None or ":" not in m.get("title", ""):
                    continue
                name = norm_name(m["title"].split(":")[0])
                ladders.setdefault(name, {}).setdefault(stat, []).append((float(strike), p))
            cursor = d.get("cursor") or ""
            time.sleep(0.4)  # Kalshi rate limit
            if not cursor:
                break
    out = {}
    for name, stats in ladders.items():
        for stat, pts in stats.items():
            mean = _ladder_mean(pts, SERIES[[s for s, v in SERIES.items() if v[0] == stat][0]][1])
            if mean is not None:
                out.setdefault(name, {})[stat] = mean
    return out


def apply_market(base_stats, mkt):
    """Overlay market-implied means on a baseline projected stat line. Returns (stats, n_signals)."""
    s, n = dict(base_stats), 0
    for k in ("pass_yd", "rush_yd", "rec_yd", "rec", "pass_td"):
        if k in mkt and base_stats.get(k):
            ratio = mkt[k] / base_stats[k]
            if 0.4 <= ratio <= 2.5:  # discard broken/illiquid ladders
                s[k] = mkt[k]
                n += 1
    base_td = (base_stats.get("rush_td") or 0) + (base_stats.get("rec_td") or 0)
    if "td" in mkt and base_td > 0 and 0.4 <= mkt["td"] / base_td <= 2.5:
        for k in ("rush_td", "rec_td"):
            if base_stats.get(k):
                s[k] = base_stats[k] * mkt["td"] / base_td
        n += 1
    return s, n
