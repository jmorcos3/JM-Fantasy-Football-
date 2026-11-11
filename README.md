# Fantasy War Room

Pulls your Sleeper and ESPN leagues, projects every player under each league's own scoring, and writes one
page of decisions: optimal lineup, waiver targets with FAAB bids, trade offers, buy-low / sell-high, power rankings.

## Run it

    python3 run.py        # no installs needed; writes site/index.html

## How the numbers are built

| Layer | Source |
|---|---|
| Rosters, scoring, matchups | Sleeper API, ESPN fantasy API |
| Baseline stat projections (this week through week 17) | Rotowire, via Sleeper |
| Player props | Kalshi prediction markets (yardage, receptions, TDs), converted to expected stat lines |
| Game environment | DraftKings spread and total, converted to implied team totals |
| Recent form | Last four weeks of actual points |

- **This week** = 50% baseline + 50% market-implied, where a liquid market exists (`market_weight`).
- **Future weeks** = 70% baseline + 30% recent form (`recent_form_weight`).
- **Waiver / trade gain** = change in your optimal-lineup points over the rest of the season, net of what a
  free streamer would score in that slot. Trades must also help the other team and be close on player value.

## Settings: `config.json`

Leagues are listed in priority order. For ESPN, `my_team` is any part of your team name.

## Private ESPN leagues

Add two repository secrets (Settings → Secrets and variables → Actions): `ESPN_S2` and `ESPN_SWID`.
Both are cookies on espn.com once you are logged in (browser dev tools → Application → Cookies).

## Auto-refresh

`.github/workflows/update.yml` rebuilds the page six times a week and publishes it with GitHub Pages
(Settings → Pages → Source: GitHub Actions). Pages sites are public even when the repo is private.

## Known gaps

- Individual defensive player (IDP) slots are not modelled.
- Injured-reserve players get a flat 50% haircut on future weeks; return dates are not modelled.
- FAAB bids are a heuristic sized to lineup gain, not a model of what league-mates will bid.
