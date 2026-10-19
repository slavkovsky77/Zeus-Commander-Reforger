"""The strategic plan: what the strategist decides, how it's checked, and how it reaches the game.

A decision names bases by their graph id from the situation report (ZCR_Strategist.BuildReport):
    {"intent": "...", "main_effort": 12, "supporting": [7], "hold": [3], "avoid": [20],
     "concentration": "normal" | "heavy"}
validate() drops anything the report doesn't support; to_lines() turns it into the plain lines the
game reads (ZCR_Strategist.OnAnswer): a score bonus and a force demand per base, on top of AI
Conflict's own commander. One full squad counts 10 in AI Conflict's units.
"""

# Score bonus and minimum demand per role. AI Conflict's own scale: an objective base is worth 60,
# 100 m of approach costs 1.5, a threat to a base 120.
WEIGHTS = {
    "main_effort": (80.0, 25.0),
    "main_effort_heavy": (80.0, 35.0),
    "supporting": (30.0, 12.0),
    "hold": (40.0, 12.0),
    "avoid": (-60.0, 0.0),
}
MAX_INTENT = 200


def bases_by_id(report: dict) -> dict:
    return {b["id"]: b for b in report.get("bases", [])}


def own_bases(report: dict) -> list:
    return [b for b in report.get("bases", []) if b.get("owner") == report.get("faction")]


def validate(decision: dict, report: dict) -> tuple:
    """(clean decision, list of problems). Unknown ids are dropped; hold must be our own base;
    a main effort is required."""
    problems = []
    known = bases_by_id(report)
    faction = report.get("faction")

    def ids(value, field):
        out = []
        for v in value if isinstance(value, list) else ([value] if value is not None else []):
            try:
                i = int(v)
            except (TypeError, ValueError):
                problems.append(f"{field}: not an id: {v!r}")
                continue
            if i not in known:
                problems.append(f"{field}: no base {i}")
            elif i not in out:
                out.append(i)
        return out

    main = ids(decision.get("main_effort"), "main_effort")
    # AI Conflict attacks only bases its radio network reaches: a main effort elsewhere does nothing.
    if any("attackable" in b for b in known.values()):
        def usable(i):
            return known[i].get("owner") == faction or bool(known[i].get("attackable"))
        for i in [i for i in main if not usable(i)]:
            problems.append(f"main_effort: base {i} can't be attacked yet (not reached by our radio network)")
        main = [i for i in main if usable(i)]
    clean = {
        "intent": " ".join(str(decision.get("intent", "")).split())[:MAX_INTENT],
        "main_effort": main[0] if main else None,
        "supporting": [i for i in ids(decision.get("supporting", []), "supporting") if i not in main
                       and (known[i].get("attackable", True) or known[i].get("owner") == faction)][:2],
        "hold": [],
        "avoid": ids(decision.get("avoid", []), "avoid"),
        "concentration": "heavy" if decision.get("concentration") == "heavy" else "normal",
    }
    for i in ids(decision.get("hold", []), "hold"):
        if known[i].get("owner") == faction:
            clean["hold"].append(i)
        else:
            problems.append(f"hold: base {i} is not ours")
    clean["hold"] = clean["hold"][:3]
    if clean["main_effort"] is None:
        problems.append("main_effort: missing")
    taken = {clean["main_effort"], *clean["supporting"], *clean["hold"]}
    clean["avoid"] = [i for i in clean["avoid"] if i not in taken][:4]
    return clean, problems


def to_lines(decision: dict, source: str) -> str:
    """The game's plain-line answer."""
    priority, demand = {}, {}

    def put(i, role):
        p, d = WEIGHTS[role]
        priority[i] = priority.get(i, 0.0) + p
        if d:
            demand[i] = max(demand.get(i, 0.0), d)

    if decision.get("main_effort") is not None:
        put(decision["main_effort"], "main_effort_heavy" if decision.get("concentration") == "heavy" else "main_effort")
    for i in decision.get("supporting", []):
        put(i, "supporting")
    for i in decision.get("hold", []):
        put(i, "hold")
    for i in decision.get("avoid", []):
        put(i, "avoid")
    out = [f"ok source={source}"]
    if decision.get("intent"):
        out.append("intent " + decision["intent"])
    out += [f"priority {i} {v:g}" for i, v in sorted(priority.items())]
    out += [f"demand {i} {v:g}" for i, v in sorted(demand.items())]
    return "\n".join(out) + "\n"
