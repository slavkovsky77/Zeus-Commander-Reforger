# Two unattended days, 21-23 Oct: the day's complaints, by severity

Martin (21 Oct 22:40): "rate them on severity ... next cycle you will focus on these issues ... improve the commander
lab in order to watch if they got resolved ... prepare everything for the next round of night testing; I will be
gone for two days". Each issue has a goal in goals.toml - the lab app's **Goals** tab judges it on every watched
match (pass/fail per match, the last matches as a strip); the **Live** tab lists jams, stuck vehicles, run-overs and
give-ways as they happen; **Crashes** keeps every crash.

| Severity | Issue (review notes) | Goal | Measure, target | State 21 Oct 22:45 |
|---|---|---|---|---|
| 1 | Crashes and freezes (246, 269, 271) | no-crash | ended_early == 0, 10 of 10 matches | cause found: the mods' tanks; off since 21:50 |
| 1 | Vehicles jam, ram, run over their own (275, 277, 282, 286) | traffic | jams <= 2, runovers <= 1, armour_still <= 2 a match | guard counts vehicles (fixed); give-way written |
| 2 | Building: sites slow, searches give up, depots missing (265, 266, 268, 272, 284) | building-fast | site_search_s <= 60, search_gave_up_pct <= 25, depots >= 1 a side | search 3x faster (fixed); roadside depot spots, no wasted tries, slot lanes written |
| 2 | Teams exposed - waiting for a ride, marching (276, 285) | cover | field_overhead >= 30% a side | covered march legs and staging written |
| 2 | The Bradley drives badly (283) | traffic (armour_still) | as above | Martin's call: mod IFVs or the game's LAV/BTR |
| 3 | Lag / FPS (273) | smooth | fps >= 35 | the stress servers; idle priority |
| - | Progress GUI, phase times, crash reporting (267, 270, 272, 274) | - | - | done |

Baseline (w19-w21, before the night's changes): no-crash 8 of 10; armour_still 3-9; site searches 18-25 game s but
34-40% give up; field_overhead 7-27%; fps 19-32 (stress servers alongside).

## How the two days run

1. Wait until Age of Empires IV (RelicCardinal) has been closed 10 minutes - nothing is started while Martin plays.
2. Compile-check the written changes (ZCR: ZCR_Driving jam watch, run-overs, armour give-way; the fork: roadside depot
   spots, candidates inside the radius, slot lanes, covered march legs, covered staging); one focused headless test
   each where a log shows it (site searches: gave-up %, CONSTRUCTION_ROAD_SEEDS); commit.
3. keepawake for 50 h; the watched loop (Arland, 3x, IFVs, no mod tanks) with the recordings; the remark waiter; a
   self-waking check every <= 25 min.
4. Every few matches: lab/goals.py; the first failing goal by severity -> evidence (frames, logs) -> a fix ->
   compile-check -> commit -> verify on the next matches (one change at a time, no repeat runs). Review notes,
   PLAN.md, the pages and the app kept current.
5. A morning report each day (what was tried, what moved on the goals, what didn't), in the app and the changelog.
