"""Sleeper data: leagues, rosters, player universe, weekly projections and actual stats."""
from urllib.parse import quote

from .http import get_json

API = "https://api.sleeper.app/v1"
POS = "&".join(f"position[]={p}" for p in ("QB", "RB", "WR", "TE", "K", "DEF"))


def state():
    return get_json(f"{API}/state/nfl", ttl=300)


def players():
    return get_json(f"{API}/players/nfl", ttl=6 * 3600)


def user(username):
    return get_json(f"{API}/user/{quote(username)}", ttl=86400)


def trending(kind="add"):
    rows = get_json(f"{API}/players/nfl/trending/{kind}?lookback_hours=48&limit=100", ttl=900)
    return {r["player_id"]: r["count"] for r in rows}


def week_rows(kind, season, week):
    """kind = 'projections' (Rotowire) or 'stats' (actuals). Returns {player_id: stats}."""
    rows = get_json(f"https://api.sleeper.app/{kind}/nfl/{season}/{week}?season_type=regular&{POS}",
                    ttl=900 if kind == "projections" else 3600)
    out = {}
    for r in rows:
        if r.get("stats"):
            out[r["player_id"]] = {"stats": r["stats"], "opp": r.get("opponent"), "team": r.get("team")}
    return out


def load_league(league_id, my_user_id, week):
    lg = get_json(f"{API}/league/{league_id}", ttl=600)
    users = {u["user_id"]: u for u in get_json(f"{API}/league/{league_id}/users", ttl=600)}
    rosters = get_json(f"{API}/league/{league_id}/rosters", ttl=300)
    matchups = get_json(f"{API}/league/{league_id}/matchups/{week}", ttl=300) or []
    s = lg.get("settings", {})
    teams, my_id = [], None
    for r in rosters:
        u = users.get(r.get("owner_id") or "", {})
        name = (u.get("metadata") or {}).get("team_name") or u.get("display_name") or f"Team {r['roster_id']}"
        rs = r.get("settings") or {}
        mine = r.get("owner_id") == my_user_id or my_user_id in (r.get("co_owners") or [])
        if mine:
            my_id = r["roster_id"]
        teams.append({
            "id": r["roster_id"], "name": name, "owner": u.get("display_name", "?"),
            "players": [p for p in (r.get("players") or [])],
            "reserve": r.get("reserve") or [],
            "wins": rs.get("wins", 0), "losses": rs.get("losses", 0),
            "pf": rs.get("fpts", 0) + rs.get("fpts_decimal", 0) / 100,
            "faab_left": (s.get("waiver_budget") or 0) - rs.get("waiver_budget_used", 0),
        })
    def pairs(rows):
        by_mid = {}
        for m in rows or []:
            if m.get("matchup_id") is not None:
                by_mid.setdefault(m["matchup_id"], []).append(m)
        return [p for p in by_mid.values() if len(p) == 2]

    opp = {}
    for a, b in pairs(matchups):
        opp[a["roster_id"]], opp[b["roster_id"]] = b["roster_id"], a["roster_id"]
    playoff_start = s.get("playoff_week_start") or 15
    schedule = {week: [(a["roster_id"], b["roster_id"]) for a, b in pairs(matchups)]}
    for w in range(week + 1, playoff_start):
        schedule[w] = [(a["roster_id"], b["roster_id"]) for a, b in
                       pairs(get_json(f"{API}/league/{league_id}/matchups/{w}", ttl=3600))]
    history = []  # completed weeks: [(roster_a, pts_a, roster_b, pts_b)]
    for w in range(1, week):
        history.append([(a["roster_id"], a.get("points") or 0, b["roster_id"], b.get("points") or 0)
                        for a, b in pairs(get_json(f"{API}/league/{league_id}/matchups/{w}", ttl=86400))])
    return {
        "platform": "Sleeper", "id": str(league_id), "name": lg.get("name"),
        "scoring": lg.get("scoring_settings") or {},
        "slots": [p for p in lg.get("roster_positions", []) if p not in ("BN", "IR", "TAXI")],
        "bench": sum(1 for p in lg.get("roster_positions", []) if p == "BN"),
        "teams": teams, "my_team": my_id, "opponents": opp, "schedule": schedule, "history": history,
        "faab": s.get("waiver_type") == 2, "faab_budget": s.get("waiver_budget") or 0,
        "trade_deadline": s.get("trade_deadline"), "playoff_start": s.get("playoff_week_start") or 15,
        "playoff_teams": s.get("playoff_teams") or 6,
    }
