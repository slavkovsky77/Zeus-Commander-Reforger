#!/bin/bash
# Drone storms in the game window (24 Oct, the infantry sub-lab with drones; Martin: "will this sub-lab be reproducible?"): DCO on both sides, drone operators for the attacker, the defender, both; farm then
# village; 3x, each ends when decided. ORDER = "scenario[:variant] ..." (variant dco when left out).
# Stop: touch .runtime/watch_stop (after the current storm). Run: ORDER="farm-drones-both village-drones-both:game" ONCE=1 bash lab/drone_storms.sh
# Each storm: lab/watch_test.py records the window to videos/, the result goes into the infantry sub-lab and .runtime/drone_playlist.log.
# Needs the FPV AI Drones build with Soviet stations without soldiers (fpv-ai-reforger 41084aa, staged by tools/stage_release.py --local).
cd /d/work/reforger-commander
while true; do
  for item in ${ORDER:-farm-drones-att farm-drones-def farm-drones-both village-drones-att village-drones-def village-drones-both}; do
    [ -f .runtime/watch_stop ] && { rm -f .runtime/watch_stop; exit 0; }
    sc=${item%%:*}; v=dco; [ "$item" != "$sc" ] && v=${item#*:}
    python -u lab/watch_test.py inftest $sc --variant $v --minutes 12 >> .runtime/drone_playlist.log 2>&1
    python -c "
import sys, pathlib; sys.path.insert(0,'lab'); import inftest, sublab
d = sorted(pathlib.Path('.runtime/runs').glob('inftest-$sc-$v-watch-*'))[-1]
r = inftest.summarize(d, '$sc', '$v'); r['watched'] = True; sublab.record('infantry', r)
print('DRONES $sc $v', {k: r.get(k) for k in ('ended_why','ended_s','us_lost','ussr_lost','us_drones_at','ussr_drones_at','us_drone_lost','ussr_drone_lost','us_ff','ussr_ff','us_held_friend','ussr_held_friend','us_shot_down','ussr_shot_down','us_drone_dead_covered','ussr_drone_dead_covered','us_shelter_runs','us_shelter_in','ussr_shelter_runs','ussr_shelter_in','us_near_drone_covered','ussr_near_drone_covered','shelter_searches','shelter_inside_points','shelter_off_navmesh','shelter_crowded','shelter_found','sorties','sortie_launches','resupplies')})" >> .runtime/drone_playlist.log 2>&1
  done
  [ -n "$ONCE" ] && exit 0
done
