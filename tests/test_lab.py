"""Offline checks of the lab's Python side: plan validation, the rules doctrine, the plain-line
answer, the LLM answer parsing, the bridge over HTTP, and the log metrics.

    python -m unittest discover -s tests -v
"""
import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lab"))

import bridge  # noqa: E402
import doctrine  # noqa: E402
import metrics  # noqa: E402
import providers  # noqa: E402
from plan import to_lines, validate  # noqa: E402

REPORT = json.loads((ROOT / "tests" / "fixtures" / "report_small.json").read_text(encoding="utf-8"))


class PlanTests(unittest.TestCase):
    def test_unknown_ids_and_foreign_holds_are_dropped(self):
        clean, problems = validate({"intent": "go\nnow", "main_effort": 99, "supporting": [3, "x"],
                                    "hold": [1, 3], "avoid": [4, 3]}, REPORT)
        self.assertIsNone(clean["main_effort"])
        self.assertEqual(clean["supporting"], [3])
        self.assertEqual(clean["hold"], [1])
        self.assertEqual(clean["avoid"], [4])
        self.assertEqual(clean["intent"], "go now")
        self.assertTrue(any("no base 99" in p for p in problems))
        self.assertTrue(any("not ours" in p for p in problems))

    def test_lines(self):
        clean, _ = validate({"intent": "Main effort Town", "main_effort": 3, "hold": [1], "avoid": [5],
                             "concentration": "heavy"}, REPORT)
        lines = to_lines(clean, "llm").splitlines()
        self.assertEqual(lines[0], "ok source=llm")
        self.assertIn("intent Main effort Town", lines)
        self.assertIn("priority 3 80", lines)
        self.assertIn("demand 3 35", lines)
        self.assertIn("priority 1 40", lines)
        self.assertIn("priority 5 -60", lines)


class DoctrineTests(unittest.TestCase):
    def test_reachable(self):
        self.assertEqual(sorted(b["id"] for b in doctrine.reachable_targets(REPORT)), [2, 3])

    def test_decide(self):
        d = doctrine.decide(REPORT)
        self.assertEqual(d["main_effort"], 3)          # the enemy-held objective next to our squads
        self.assertEqual(d["concentration"], "heavy")
        self.assertEqual(d["hold"][:2], [1, 0])          # the threatened farm first, then the HQ
        clean, problems = validate(d, REPORT)
        self.assertEqual(problems, [])


class ProviderTests(unittest.TestCase):
    def test_extract_json_from_fenced_answer(self):
        self.assertEqual(providers.extract_json('Sure:\n```json\n{"main_effort": 3}\n```')["main_effort"], 3)

    def test_report_text_has_every_base_and_squad(self):
        text = providers.report_text(REPORT)
        for name in ("USSR HQ", "Farm", "Relay hill", "Town", "Crossroads", "US HQ"):
            self.assertIn(name, text)
        self.assertIn("UNDER THREAT", text)
        self.assertIn("7/10", text)

    def test_openrouter_request_and_answer(self):
        seen = {}

        def fake_post(url, body, headers, timeout):
            seen.update(url=url, body=body, headers=headers)
            return {"choices": [{"message": {"content": '{"intent": "Take Town", "main_effort": 3, "hold": [1]}'}}]}

        old = providers._post
        providers._post = fake_post
        try:
            import os
            os.environ["ZCR_TEST_OPENROUTER_KEY"] = "test-key"
            p = providers.make({"provider": "openrouter", "model": "google/gemini-3.8-flash",
                                "api_key_env": "ZCR_TEST_OPENROUTER_KEY"})
            decision, raw, _ = providers.timed(p, REPORT, "Mass on one axis.")
        finally:
            providers._post = old
            os.environ.pop("ZCR_TEST_OPENROUTER_KEY", None)
        self.assertEqual(seen["url"], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(seen["headers"]["authorization"], "Bearer test-key")
        self.assertEqual(seen["body"]["model"], "google/gemini-3.8-flash")
        self.assertIn("Mass on one axis.", seen["body"]["messages"][0]["content"])
        self.assertIn("Town", seen["body"]["messages"][1]["content"])
        self.assertEqual(decision["main_effort"], 3)

    def test_llm_needs_a_key(self):
        with self.assertRaises(ValueError):
            providers.make({"provider": "gemini", "model": "x", "api_key_env": "ZCR_TEST_NO_SUCH_VAR"})


class BridgeTests(unittest.TestCase):
    def test_round_trip(self):
        cfg = {"port": 0, "provider": "doctrine", "log_dir": ".runtime/test-bridge"}
        server = bridge.serve(cfg)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/plan"
            req = urllib.request.Request(url, data=json.dumps(REPORT).encode(), method="POST")
            answer = urllib.request.urlopen(req, timeout=10).read().decode()
        finally:
            server.shutdown()
            server.server_close()
        self.assertTrue(answer.startswith("ok source=doctrine\n"))
        self.assertIn("priority 3 80", answer)

    def test_failed_model_falls_back_to_doctrine(self):
        s = bridge.Strategist({"provider": "doctrine", "log_dir": ".runtime/test-bridge"})

        class Broken:
            name = "gemini"

            def decide(self, report, text):
                raise TimeoutError("model too slow")

        s.provider = Broken()
        self.assertTrue(s.plan(REPORT).startswith("ok source=doctrine-fallback"))


class MetricsTests(unittest.TestCase):
    def test_measure(self):
        log = [
            "12:00:01 SCRIPT : [ZCR][SNAPSHOT] faction=USSR t=60 round=1 bytes=900",
            "12:00:02 SCRIPT : [ZCR][LOSS] t=95 victim=Character_US_Rifleman side=US kind=man killer_side=USSR killer_kind=man relation=KILLED_BY_ENEMY_AI distance=210 x=10 z=20",
            "12:00:03 SCRIPT : [ZCR][LOSS] t=120 victim=BTR70 side=USSR kind=vehicle killer_side=US killer_kind=man relation=KILLED_BY_ENEMY_AI distance=90 x=11 z=21",
            "12:00:04 SCRIPT : [AICF][STAGE1][INFO][BASE_OWNER_CHANGED] base=Town#3 old_owner=US new_owner=USSR",
            "12:00:05 SCRIPT : [ZCR][PLAN] faction=USSR revision=3 source=llm priorities=3 demands=1 intent=Main effort Town",
            "12:00:06 SCRIPT (W): [ZCR][BRIDGE_MISS] faction=US round=2 missed=1 reason=EREST_ERROR_TIMEOUT",
        ]
        m = metrics.measure(log)
        self.assertEqual(m["lost"], {"US": {"man": 1}, "USSR": {"vehicle": 1}})
        self.assertEqual(m["captures"], {"USSR": 1})
        self.assertEqual(m["plans"], {"llm": 1})
        self.assertEqual(m["bridge_misses"], 1)
        self.assertEqual(m["minutes"], 2.0)


if __name__ == "__main__":
    unittest.main()


class PhasedTests(unittest.TestCase):
    def report(self, t, weak=False, **changes):
        r = json.loads(json.dumps(REPORT))
        r["t"] = t
        if weak:
            r["squads"][0]["alive"] = 3                  # 20 near the Farm: not yet enough for Town
        for bid, owner in changes.items():
            for b in r["bases"]:
                if b["id"] == int(bid[1:]):
                    b["owner"] = owner
        return r

    def test_gather_then_assault_then_next(self):
        import phased
        p = phased.Phased()
        d, _ = p.decide(self.report(100, weak=True))
        self.assertEqual(d["main_effort"], 1)            # gather at the Farm, our base nearest Town
        self.assertIn(3, d["avoid"])                     # nobody walks into Town alone
        d, _ = p.decide(self.report(190))
        self.assertEqual(d["main_effort"], 3)            # 27 soldiers near the Farm >= 25: assault Town
        d, _ = p.decide(self.report(400, b3="USSR"))     # Town taken
        self.assertNotEqual(d["main_effort"], 3)
        self.assertIn(d["main_effort"], (2, 4, 5))

    def test_bled_out_assault_falls_back(self):
        import phased
        p = phased.Phased()
        p.decide(self.report(100))
        p.decide(self.report(190))                       # assault Town
        r = self.report(190 + 400)
        for s in r["squads"]:
            s["alive"] = 1                               # the attack bled out
        d, _ = p.decide(r)
        self.assertEqual(d["main_effort"], 1)            # back to the Farm
        self.assertEqual(p.state["USSR"]["fails"][3], 1)

    def test_stalled_assault_picks_another_objective(self):
        import phased
        p = phased.Phased()
        p.decide(self.report(100))
        p.decide(self.report(190))                       # assault Town, plenty of force
        d, _ = p.decide(self.report(190 + 620))          # 10 min, Town still US: called off
        self.assertEqual(p.state["USSR"]["fails"][3], 1)
        self.assertNotEqual(p.state["USSR"]["target"], 3)   # an untried objective now

    def test_assault_commits_defenders_only_when_safe(self):
        import phased
        p = phased.Phased()
        p.decide(self.report(100))
        d, _ = p.decide(self.report(190))                # assault Town - but the Farm is threatened
        self.assertEqual(d["main_effort"], 3)
        self.assertEqual(d["commit"], 0)
        r = self.report(280)
        for b in r["bases"]:
            b["threatened"] = False
        d, _ = p.decide(r)
        self.assertEqual(d["commit"], 2)                 # nothing threatened: two DEFEND squads join
        clean, _ = validate(d, r)
        self.assertIn("commit 2", to_lines(clean, "phased").splitlines())
        clean, problems = validate({"main_effort": 3, "commit": 9}, r)
        self.assertEqual(clean["commit"], 2)

    def test_force_at_objective_skips_staging_garrison(self):
        import phased
        r = self.report(100)
        farm = next(b for b in r["bases"] if b["id"] == 1)
        farm["x"], farm["z"] = 2200, 1300                # staging base 447 m from Town
        r["squads"] = [{"alive": 10, "x": 2200, "z": 1300, "target": 1},   # the staging garrison
                       {"alive": 8, "x": 2500, "z": 1450, "target": 3},    # at Town
                       {"alive": 9, "x": 2000, "z": 1100, "target": 3},    # sent to Town, 640 m out
                       {"alive": 7, "x": 2580, "z": 1480, "target": 4}]    # in Town, other orders
        town = next(b for b in r["bases"] if b["id"] == 3)
        self.assertEqual(phased.force_at(r, town, 900), 24.0)
        self.assertEqual(phased.force_near(r, town, 450), 25.0)

    def test_assault_on_the_objective_gets_longer(self):
        import phased
        p = phased.Phased()
        p.decide(self.report(100))
        p.decide(self.report(190))                       # assault Town
        r = self.report(190 + 620)
        r["squads"][0].update(x=2550, z=1450)            # 10 soldiers on Town: still gaining
        p.decide(r)
        self.assertEqual(p.state["USSR"]["target"], 3)
        self.assertNotIn(3, p.state["USSR"]["fails"])
        r = self.report(190 + 920)
        r["squads"][0].update(x=2550, z=1450)
        p.decide(r)                                      # 15 min: called off all the same
        self.assertEqual(p.state["USSR"]["fails"][3], 1)

    def test_assault_goes_on_while_seizing(self):
        import phased
        p = phased.Phased()
        p.decide(self.report(100))
        p.decide(self.report(190))                       # assault Town
        r = self.report(190 + 1000)
        next(b for b in r["bases"] if b["id"] == 3)["seizing"] = 1
        p.decide(r)                                      # 16 min, but Town is being taken
        self.assertEqual(p.state["USSR"]["target"], 3)
        self.assertNotIn(3, p.state["USSR"]["fails"])

    def test_storm_after_four_minutes_with_the_force_there(self):
        import phased
        p = phased.Phased()
        p.decide(self.report(100))
        d, _ = p.decide(self.report(190))                # assault Town
        self.assertIsNone(d["storm"])
        d, _ = p.decide(self.report(190 + 250))          # 17 soldiers sent to Town >= 0.6 x 25
        self.assertEqual(d["storm"], 3)
        clean, _ = validate(d, self.report(440))
        self.assertIn("storm 3", to_lines(clean, "phased").splitlines())
        clean, problems = validate({"main_effort": 3, "storm": 4}, self.report(440))
        self.assertIsNone(clean["storm"])                # only the main effort is stormed

    def test_commit_stays_with_enemies_near_but_no_capture(self):
        import phased
        p = phased.Phased()
        p.decide(self.report(100))
        r = self.report(190)
        for b in r["bases"]:
            b["seizing"] = 0                             # the Farm is "threatened" but nobody takes it
        d, _ = p.decide(r)
        self.assertEqual(d["commit"], 2)
        next(b for b in r["bases"] if b["id"] == 1)["seizing"] = 1
        d, _ = p.decide(r)
        self.assertEqual(d["commit"], 0)                 # being captured: defenders go back

    def test_two_matches_at_once_keep_their_own_memory(self):
        import phased
        p = phased.Phased()
        a = lambda t: dict(self.report(t), match="watched")
        b = lambda t: dict(self.report(t), match="headless")
        p.decide(a(600))
        p.decide(a(690))                                 # watched: assault on Town since 600
        p.decide(b(100))                                 # headless starts, earlier in its match
        d, _ = p.decide(a(780))
        self.assertEqual(p.state["watched:USSR"]["phase"], "assault")
        self.assertEqual(p.state["watched:USSR"]["since"], 600)   # its assault, not reset by the other match
        self.assertEqual(p.state["headless:USSR"]["since"], 100)

    def test_far_objective_is_not_bled_out_or_stalled_while_marching(self):
        import phased
        p = phased.Phased()

        def far(t, arrived=False):
            r = self.report(t)
            for b in r["bases"]:
                if b["id"] == 1:
                    b["x"] -= 1000                       # the staging base 1.8 km from Town
            for s_ in r["squads"]:
                if "x" in s_ and not arrived:
                    s_["x"] -= 1000                      # gathered there, then marching
            return r
        p.decide(far(100))                               # gathered: assault Town at once
        self.assertEqual(p.state["USSR"]["phase"], "assault")
        p.decide(far(590))                               # 8 min marching, nobody within 900 m yet
        self.assertEqual(p.state["USSR"]["phase"], "assault")
        self.assertNotIn(3, p.state["USSR"]["fails"])
        p.decide(far(890, arrived=True))                 # arrived (within 900 m)
        p.decide(far(1190, arrived=True))                # 5 min there, nobody on it: not yet stalled
        self.assertNotIn(3, p.state["USSR"]["fails"])
        p.decide(far(1500, arrived=True))                # 10 min there, nobody on it: called off
        self.assertEqual(p.state["USSR"]["fails"].get(3), 1)

    def test_motorize_goes_through_every_decision(self):
        import phased
        p = phased.Phased(motorize=True)
        d, _ = p.decide(self.report(100, weak=True))     # gathering
        self.assertTrue(d["motorize"])
        clean, _ = validate(d, self.report(100))
        self.assertIn("motorize 1", to_lines(clean, "phased").splitlines())
        d, _ = phased.Phased().decide(self.report(100))
        self.assertFalse(d["motorize"])

    def test_drones_on_the_objective_while_gathering_and_assaulting(self):
        import phased
        p = phased.Phased()
        d, _ = p.decide(self.report(100, weak=True))     # gathering at the Farm for Town
        self.assertEqual(d["drones"], [3])
        clean, _ = validate(d, self.report(100))
        self.assertIn("drone 3", to_lines(clean, "phased").splitlines())
        d, _ = p.decide(self.report(190))                # assault Town
        self.assertEqual(d["drones"], [3])
        clean, _ = validate({"main_effort": 3, "drones": [1, 3]}, self.report(190))
        self.assertEqual(clean["drones"], [3])           # never our own base

    def test_need_follows_known_defenders_and_storm_when_few_left(self):
        import phased
        p = phased.Phased()
        r = self.report(100, weak=True)
        next(b for b in r["bases"] if b["id"] == 3)["enemies"] = 14
        p.decide(r)
        self.assertEqual(p.state["USSR"]["need"], 32)    # 2 x 14 + 4
        r = self.report(190)
        r["squads"][0].update(x=2550, z=1450)
        r["squads"][1].update(x=2560, z=1460)            # our soldiers at Town
        r["squads"][0]["alive"] = r["squads"][1]["alive"] = 12
        town = next(b for b in r["bases"] if b["id"] == 3)
        town["enemies"] = 2                             # and they see 2 defenders left
        p.state["USSR"].update(phase="assault", since=150, need=32)
        d, _ = p.decide(r)                               # 40 s into the assault: storm now
        self.assertEqual(d["storm"], 3)

    def test_new_match_resets(self):
        import phased
        p = phased.Phased()
        p.decide(self.report(500))
        p.decide(self.report(600))
        d, _ = p.decide(self.report(45, weak=True))      # t went back: a new match
        self.assertEqual(p.state["USSR"]["phase"], "gather")
        self.assertEqual(d["main_effort"], 1)

    def test_llm_picks_only_when_due(self):
        import phased
        calls = []

        def pick(report, text):
            calls.append(report["t"])
            return 4, "Take the crossroads", ""

        p = phased.Phased(pick, "llm-phased")
        p.decide(self.report(100))
        p.decide(self.report(190))
        p.decide(self.report(280))
        self.assertEqual(len(calls), 1)
        self.assertEqual(p.state["USSR"]["target"], 4)


class AttackableTests(unittest.TestCase):
    def report(self):
        r = json.loads(json.dumps(REPORT))
        for b in r["bases"]:
            b["attackable"] = b["id"] == 2      # only Relay hill is reached by our radio network
        return r

    def test_only_attackable_targets(self):
        r = self.report()
        self.assertEqual([b["id"] for b in doctrine.reachable_targets(r)], [2])
        self.assertEqual(doctrine.decide(r)["main_effort"], 2)

    def test_unreachable_main_effort_is_dropped(self):
        clean, problems = validate({"main_effort": 3, "supporting": [4, 2]}, self.report())
        self.assertIsNone(clean["main_effort"])
        self.assertEqual(clean["supporting"], [2])
        self.assertTrue(any("radio" in p for p in problems))

    def test_phased_picks_attackable(self):
        import phased
        d, _ = phased.Phased().decide(self.report())
        self.assertIn(2, (d["main_effort"], *d["avoid"]))
