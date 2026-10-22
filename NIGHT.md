# Two unattended days, 21-23 Oct: the day's complaints, by severity

Martin (21 Oct 22:40): "rate them on severity ... next cycle you will focus on these issues ... improve the commander
lab in order to watch if they got resolved ... prepare everything for the next round of night testing; I will be
gone for two days". Each issue has a goal in goals.toml - the lab app's **Goals** tab judges it on every watched
match (pass/fail per match, the last matches as a strip); the **Live** tab lists jams, stuck vehicles, run-overs and
give-ways as they happen; **Crashes** keeps every crash.

| Severity | Issue (review notes) | Goal | Measure, target | State 21 Oct 22:45 |
|---|---|---|---|---|
| 1 | Crashes and freezes (246, 269, 271) | no-crash | ended_early == 0, 10 of 10 matches | cause found: the mods' tanks; off since 21:50 |
| 1 | Vehicles drive badly - jam, ram, get stuck, run over their own; all vehicles, the Bradley was one example (275, 277, 282, 283, 286) | traffic | jams <= 2, runovers <= 1, armour_still <= 2, stuck_vehicles <= 5, drive_kmh >= 18 a match | guard counts vehicles (fixed); give-way written; jam watch written |
| 2 | Building: sites slow, searches give up, depots missing (265, 266, 268, 272, 284) | building-fast | site_search_s <= 60, search_gave_up_pct <= 25, depots >= 1 a side | search 3x faster (fixed); roadside depot spots, no wasted tries, slot lanes written |
| 2 | Teams exposed - waiting for a ride, marching (276, 285) | cover | field_overhead >= 30% a side | covered march legs and staging written |
| 3 | Lag / FPS (273) | smooth | fps >= 35 | the stress servers; idle priority |
| - | Progress GUI, phase times, crash reporting (267, 270, 272, 274) | - | - | done |

Baseline (w19-w21, before the night's changes): no-crash 8 of 10; armour_still 3-9; site searches 18-25 game s but
34-40% give up; field_overhead 7-27%; fps 19-32 (stress servers alongside).

## How the two days run

1. Wait until Age of Empires IV (RelicCardinal) has been closed 10 minutes - nothing is started while Martin plays.
2. Compile-check the written changes (ZCR: ZCR_Driving jam watch, run-overs, armour give-way; the fork: roadside depot
   spots, candidates inside the radius, slot lanes, covered march legs, covered staging); one focused headless test
   each where a log shows it (site searches: gave-up %, CONSTRUCTION_ROAD_SEEDS); commit.
3. keepawake for 52 h; the watched loop (Arland and Everon in turn - Martin: 'test it on at least two scenarios'; 3x,
   IFVs, no mod tanks) with the recordings, started 22 Oct 00:20; the remark waiter; a self-waking check every <= 30 min.
4. Every few matches: lab/goals.py; the first failing goal by severity -> evidence (frames, logs) -> a fix ->
   compile-check -> commit -> verify on the next matches (one change at a time, no repeat runs). Review notes,
   PLAN.md, the pages and the app kept current.
5. A morning report each day (what was tried, what moved on the goals, what didn't), in the app and the changelog.

## Morning report, 22 Oct (night 02:20-06:30, matches w1-w26, Arland and Everon in turn, all game vehicles)

**Crashes - worse, cause narrowed down, a test running.** Six watched matches crashed (w7, w14, w16, w19, w21, w24 -
6 of 18 from 03:27; none in the 13 before). Every crash came seconds after one of our scripts moved a vehicle by hand
(back off 8 m, park aside, or the new "back onto the road"), 4 of 6 within 4 s. The same moves on a headless server
(no game window) ran 30 minutes and 35 moves without a crash, so it is something in the watched game itself. Moving
vehicles the way the game's Game Master does (Teleport) didn't help (w24). Since 06:23 (w26) every hand move is off in
the watched matches; if the crashes stop, that was it. The other suspect is the new following rule (on since w7).

**Cars blocking each other - the night's main work, mixed result.** Fixed causes found in the logs and on the map:
- rides squeezing past a slow one of their side into the field (Everon farm, 16 jams in one match): a vehicle now
  creeps behind a slow one ahead;
- supply trucks of one depot all driving to the one road point of a base and meeting head-on (7 of ~30 Arland jams):
  their load/unload points are spread along the roads;
- spots where drivers hang on rocks: Arland's north base bend, a sunken 4-m track with boulders south of the US base
  (10 jams in one match), a bridge on Everon - handled by moving the vehicle, which is now off (see crashes).
Jams a match: Arland 1-16 (typically 6), Everon 0-16; with the moves off, long stops (2 min+) rise (w26: 10).
Next: a way to free a stuck vehicle without moving it by hand (a short reverse order, as the armour already does).

**Supply trucks on Everon - fixed.** Not one truck had driven on Everon in eleven matches: the trucks' route search
never finished on a map with 39 bases. Now 18-34 trucks a match, the first deliveries on Everon (w15), at most 8 of a
side out at once.

**Lag on Everon - a big cause found and fixed.** AI Conflict's commander took 60-94 ms on nearly every tick on Everon
(Arland under 20) - a stutter every few seconds: for every squad it recomputed a network calculation over all 39
bases. Now once per tick: under 20 ms on 80 of 84 ticks (headless). In the watched matches from w26.

**Building - no progress.** Everon's searches take 60-100 game s and 40-50% give up. Tried: three times the search
budget (no faster, twice the CPU - reverted), without the base access lanes (the same). The spots fail on rocks, slope
and roads; next idea: use the map's own flat building slots first.

**Not started:** teams exposed on the march (cover), armour standing still in the assault.
