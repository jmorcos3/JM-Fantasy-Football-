#!/usr/bin/env python3
"""Fantasy football advisor. Usage: python3 run.py  ->  writes site/index.html and site/data.json"""
import json
import os
import sys
from datetime import datetime, timezone

from advisor import advice, espn, headshots, markets, report, sim, sleeper
from advisor.http import get_json
from advisor.model import Model

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    cfg = json.load(open(os.path.join(ROOT, "config.json")))
    st = sleeper.state()
    season, week = st["season"], max(1, int(st["week"]))
    last = cfg["last_week_of_season"]
    if st.get("season_type") != "regular" or week > last:
        print("NFL regular season not in progress; nothing to project.")
        week = min(week, last)
    print(f"Season {season}, week {week}")
    data = {"week": week, "players": sleeper.players(),
            "proj": {w: sleeper.week_rows("projections", season, w) for w in range(week, last + 1)},
            "stats": {w: sleeper.week_rows("stats", season, w) for w in range(1, week)}}
    data["photo"] = headshots.build(data["players"])
    notes = []
    try:
        data["lines"] = markets.game_lines(season, week)
    except Exception as e:
        data["lines"] = {}
        notes.append(f"Sportsbook lines unavailable ({e}).")
    try:
        data["props"] = markets.kalshi_props()
    except Exception as e:
        data["props"] = {}
        notes.append(f"Prediction-market props unavailable ({e}).")
    key = os.environ.get("ODDS_API_KEY")
    if key and (datetime.now(timezone.utc).strftime("%a") in cfg.get("odds_api_days", []) or os.environ.get("ODDS_API_FORCE")):
        try:
            books = markets.sportsbook_props(key)
            data["props"] = markets.merge_props(data["props"], books)
            print(f"Sportsbook props: {len(books)} players")
        except Exception as e:
            notes.append(f"Sportsbook props unavailable ({e}).")
    trending = sleeper.trending("add")

    leagues, uid = [], None
    for c in cfg["leagues"]:  # listed in priority order
        lid = c["league_id"]
        try:
            if c["platform"] == "sleeper":
                uid = uid or sleeper.user(cfg["sleeper_username"])["user_id"]
                lg = sleeper.load_league(lid, uid, week)
                starters = next((r.get("starters") for r in get_json(f"{sleeper.API}/league/{lid}/rosters", ttl=300)
                                 if r["roster_id"] == lg["my_team"]), None)
            else:
                lg = espn.load_league(c, season, week, data["players"])
                starters = lg["my_starters"]
                if lg["unmapped"]:
                    notes.append(f"{lg['name']}: could not match {len(lg['unmapped'])} ESPN players ({', '.join(lg['unmapped'][:5])}).")
                if lg["ignored_slots"]:
                    notes.append(f"{lg['name']}: the {', '.join(lg['ignored_slots'])} slot is not modelled; set it yourself.")
            lg["rules"] = c
            leagues.append((lg, starters))
        except Exception as ex:
            why = "it is private: add the ESPN_S2 and ESPN_SWID secrets (see README)" if "401" in str(ex) or "403" in str(ex) else str(ex)
            notes.append(f"{c['platform'].upper()} league {lid} not loaded: {why}.")

    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "season": season, "week": week,
           "repo": cfg.get("repo"), "notes": notes, "games": data["lines"], "leagues": []}
    for lg, starters in leagues:
        m = Model(lg, data, cfg)
        season_sim = sim.run(m, cfg)
        p_playoffs = season_sim["odds"].get(lg["my_team"], 0)
        if cfg.get("playoff_weighting"):
            for w in m.weeks:  # playoff weeks count for more the likelier you are to be playing in them
                if w >= lg["playoff_start"]:
                    m.week_w[w] = 0.5 + 1.5 * p_playoffs
        res = advice.build(m, trending, starters, season_sim)
        out["leagues"].append(res)
        print(f"  {lg['name']}: {len(res.get('waivers', []))} waiver ideas, {len(res.get('trades', []))} trade ideas, "
              f"{res.get('market_players', 0)} market-priced players")
    os.makedirs(os.path.join(ROOT, "site"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "site", "data.json"), "w"), indent=1)
    open(os.path.join(ROOT, "site", "index.html"), "w").write(report.render(out))
    frag = report.fragment(out)
    if "--embed" in sys.argv:  # for hosts that block external images
        frag = headshots.embed(frag)
    open(os.path.join(ROOT, "site", "artifact.html"), "w").write(frag)
    print("Wrote site/index.html")


if __name__ == "__main__":
    sys.exit(main())
