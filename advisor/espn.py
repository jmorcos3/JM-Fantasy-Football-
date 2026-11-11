"""Optional ESPN league loader. Players are mapped onto Sleeper ids via Sleeper's espn_id field
so the rest of the engine is platform-agnostic.

Public leagues need only the league id. Private leagues need the ESPN_S2 and ESPN_SWID
environment variables (browser cookies), stored as GitHub secrets.
"""
import os
import time

from .http import get_json
from .markets import norm_name

HOST = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"
SLOT = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DEF", 17: "K", 23: "FLEX", 3: "WRRB_FLEX", 5: "REC_FLEX"}
# ESPN stat id -> Sleeper stat keys. Offence / kicking use the base points value.
STAT = {3: ["pass_yd"], 4: ["pass_td"], 19: ["pass_2pt"], 20: ["pass_int"], 24: ["rush_yd"], 25: ["rush_td"],
        26: ["rush_2pt"], 42: ["rec_yd"], 43: ["rec_td"], 44: ["rec_2pt"], 53: ["rec"], 72: ["fum_lost"],
        80: ["fgm_0_19", "fgm_20_29", "fgm_30_39"], 77: ["fgm_40_49"], 74: ["fgm_50p"], 198: ["fgm_50p"],
        85: ["fgmiss"], 86: ["xpm"], 88: ["xpmiss"]}
# Team defence items use ESPN's D/ST-slot override ("16") when present.
DST = {99: "sack", 95: "int", 96: "fum_rec", 97: "blk_kick", 98: "safe", 103: "def_td", 106: "ff",
       89: "pts_allow_0", 90: "pts_allow_1_6", 91: "pts_allow_7_13", 92: "pts_allow_14_20", 123: "pts_allow_28_34",
       124: "pts_allow_35p", 128: "yds_allow_0_100", 129: "yds_allow_100_199", 130: "yds_allow_200_299",
       132: "yds_allow_350_399", 133: "yds_allow_400_449", 134: "yds_allow_450_499", 135: "yds_allow_500_549",
       136: "yds_allow_550p"}
PRO = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN", 11: "IND",
       12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI",
       22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU"}


def load_league(cfg, season, week, players):
    lid = cfg["league_id"]
    headers = {}
    if os.environ.get("ESPN_S2") and os.environ.get("ESPN_SWID"):
        headers["Cookie"] = f"espn_s2={os.environ['ESPN_S2']}; SWID={os.environ['ESPN_SWID']}"
    views = "&".join(f"view={v}" for v in ("mTeam", "mRoster", "mSettings", "mMatchup"))
    d = get_json(f"{HOST}/{season}/segments/0/leagues/{lid}?{views}", ttl=300, headers=headers)
    by_espn = {str(p["espn_id"]): pid for pid, p in players.items() if p.get("espn_id")}
    by_name = {}
    for pid, p in players.items():
        if p.get("full_name") and p.get("team") and p.get("position") in ("QB", "RB", "WR", "TE", "K"):
            by_name[(norm_name(p["full_name"]), p["position"])] = pid
    pos_of = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K"}
    unmapped = []
    st = d["settings"]
    scoring = {}
    for it in st["scoringSettings"]["scoringItems"]:
        for key in STAT.get(it["statId"], []):
            scoring[key] = it["points"]
        if it["statId"] in DST:
            scoring[DST[it["statId"]]] = (it.get("pointsOverrides") or {}).get("16", it["points"])
    slots, bench = [], 0
    for sid, n in st["rosterSettings"]["lineupSlotCounts"].items():
        if int(sid) == 20:
            bench = n
        elif int(sid) in SLOT:
            slots += [SLOT[int(sid)]] * n
        elif int(sid) != 21:
            bench += n  # unmodelled slots (e.g. IDP) still take up roster spots
    teams, my_id, starters = [], None, {}
    me = str(cfg.get("my_team", "")).lower()
    for t in d["teams"]:
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
        ids, reserve = [], []
        for e in t.get("roster", {}).get("entries", []):
            pl = e["playerPoolEntry"]["player"]
            if pl.get("defaultPositionId") == 16:
                pid = PRO.get(pl.get("proTeamId"))
            else:
                pid = by_espn.get(str(pl["id"])) or by_name.get(
                    (norm_name(pl.get("fullName", "")), pos_of.get(pl.get("defaultPositionId"))))
                if not pid:
                    if pl.get("defaultPositionId") in pos_of:
                        unmapped.append(pl.get("fullName"))
                    pid = f"{pl.get('fullName')} (not modelled)"
            if pid:
                if e.get("lineupSlotId") not in (20, 21) and t["id"] not in starters:
                    starters[t["id"]] = []
                if e.get("lineupSlotId") not in (20, 21):
                    starters[t["id"]].append(pid)
                ids.append(pid)
                if e.get("lineupSlotId") == 21:
                    reserve.append(pid)
        rec = t.get("record", {}).get("overall", {})
        if me and (me == str(t["id"]) or me in name.lower() or me == (t.get("abbrev") or "").lower()):
            my_id = t["id"]
        teams.append({"id": t["id"], "name": name, "owner": name, "players": ids, "reserve": reserve,
                      "wins": rec.get("wins", 0), "losses": rec.get("losses", 0), "pf": rec.get("pointsFor", 0),
                      "faab_left": st["acquisitionSettings"].get("acquisitionBudget", 0)
                      - t.get("transactionCounter", {}).get("acquisitionBudgetSpent", 0)})
    opp = {}
    for m in d.get("schedule", []):
        if m.get("matchupPeriodId") == week and m.get("home") and m.get("away"):
            a, b = m["home"]["teamId"], m["away"]["teamId"]
            opp[a], opp[b] = b, a
    dl = (st.get("tradeSettings") or {}).get("deadlineDate")
    closed = bool(dl) and time.time() * 1000 > dl
    ignored = sorted({n for sid, n in ((15, "DP (individual defender)"), (7, "OP"), (18, "P"), (19, "HC"))
                      if st["rosterSettings"]["lineupSlotCounts"].get(str(sid))})
    return {
        "unmapped": unmapped, "my_starters": starters.get(my_id), "ignored_slots": ignored,
        "platform": "ESPN", "id": str(lid), "name": st.get("name"), "scoring": scoring, "slots": slots, "bench": bench,
        "teams": teams, "my_team": my_id, "opponents": opp,
        "faab": bool(st["acquisitionSettings"].get("isUsingAcquisitionBudget")),
        "faab_budget": st["acquisitionSettings"].get("acquisitionBudget", 0),
        "trade_deadline": week - 1 if closed else None, "playoff_start": st["scheduleSettings"].get("matchupPeriodCount", 14) + 1,
        "playoff_teams": st["scheduleSettings"].get("playoffTeamCount", 6),
    }
