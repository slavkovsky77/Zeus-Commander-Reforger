// What each side is doing, for the watch panels (Martin, 19 Oct: "left and right side for BLUFOR and
// OPFOR like it was in Arma 3 - we saw what is happening, like live logs"; Arma 3: ZC_fnc_feed and
// ZC_fnc_debugPanel). Server: per side its latest decisions in plain words with the game time (the
// last 8, newest first), what its squads are doing now (from AI Conflict's own assignments), and the
// lab's measures for the bottom bar. ZCR_Director sends them to the screen.
class ZCR_Feed
{
	protected static ref map<string, ref array<string>> s_mLines = new map<string, ref array<string>>();
	protected static ref map<string, ref array<string>> s_mNow = new map<string, ref array<string>>();
	protected static ref map<string, string> s_mPlanKey = new map<string, string>();
	protected static ref map<string, string> s_mMainTarget = new map<string, string>();
	static ref map<string, vector> s_mMainTargetPos = new map<string, vector>();   // where the side's main attack goes
	static ref map<string, int> s_mCover = new map<string, int>();      // % in the game's cover (last sample)
	static ref map<string, int> s_mStacked = new map<string, int>();    // % stacked in the field (last sample)
	static ref map<string, int> s_mAtBase = new map<string, int>();     // % within 200 m of the main base (last sample)
	static ref map<string, int> s_mLostFire = new map<string, int>();   // soldiers lost to a killer
	static ref map<string, int> s_mLostOther = new map<string, int>();  // lost with no killer (drones, explosions)

	static void Note(string side, string text)
	{
		if (side != "US" && side != "USSR")
			return;
		array<string> lines;
		if (!s_mLines.Find(side, lines))
		{
			lines = {};
			s_mLines.Set(side, lines);
		}
		// The same line again moves to the top instead.
		for (int i = lines.Count() - 1; i >= 0; i--)
		{
			string l = lines[i].Trim();
			int sp = l.IndexOf(" ");
			if (sp > 0 && l.Substring(sp + 1, l.Length() - sp - 1) == text)
				lines.Remove(i);
		}
		lines.InsertAt("  " + Clock(ZCR_LossLog.Seconds()) + " " + text, 0);
		while (lines.Count() > 8)
			lines.Remove(8);
	}

	// Arma 3's colours (ZC_fnc_feed / ZC_fnc_debugPanel).
	static const string GREEN = "155,224,138,255";
	static const string RED = "255,138,112,255";
	static const string YELLOW = "255,208,96,255";
	static const string GREY = "154,154,154,255";
	static const string LIGHT = "200,200,200,255";
	static const string BLUE = "122,168,255,255";
	static const string OPFOR_RED = "255,112,112,255";

	static string Col(string rgba, string text)
	{
		return "<color rgba='" + rgba + "'>" + text + "</color>";
	}

	static string SideCol(string side, string text)
	{
		if (side == "US")
			return Col(BLUE, text);
		if (side == "USSR")
			return Col(OPFOR_RED, text);
		return text;
	}

	// A decision's colour by what it is: captures green, losses red, attacks and plans yellow.
	protected static string Tint(string text)
	{
		if (text.StartsWith("TOOK"))
			return Col(GREEN, text);
		if (text.StartsWith("LOST") || text.StartsWith("no clear"))
			return Col(RED, text);
		if (text.StartsWith("STORM") || text.StartsWith("PLAN") || text.StartsWith("main attack"))
			return Col(YELLOW, text);
		if (text.Contains("drone team"))
			return Col("255,180,120,255", text);
		if (text.Contains("vehicle") || text.Contains("joins the attack"))
			return Col("160,210,255,255", text);
		return text;
	}

	static string Latest(string side)
	{
		array<string> lines;
		if (!s_mLines.Find(side, lines) || lines.IsEmpty())
			return "  -";
		string joined;
		foreach (int i, string l : lines)
		{
			if (i > 0)
				joined += "<br/>";
			string t = l.Trim();
			int sp = t.IndexOf(" ");
			if (sp > 0)
				joined += "  " + Col(LIGHT, t.Substring(0, sp)) + " " + Tint(t.Substring(sp + 1, t.Length() - sp - 1));
			else
				joined += "  " + t;
		}
		return joined;
	}

	// A new plan worth a line: its phase and objective changed (not just the head count).
	static void Plan(string side, string intent)
	{
		string key = intent;
		int cut = key.IndexOf(":");
		if (cut > 0)
			key = key.Substring(0, cut);
		cut = key.IndexOf(" with ");
		if (cut > 0)
			key = key.Substring(0, cut);
		if (key.IsEmpty() || s_mPlanKey.Get(side) == key)
			return;
		s_mPlanKey.Set(side, key);
		Note(side, "PLAN: " + key);
	}

	static void Lost(string side, bool byFire)
	{
		if (byFire)
			s_mLostFire.Set(side, s_mLostFire.Get(side) + 1);
		else
			s_mLostOther.Set(side, s_mLostOther.Get(side) + 1);
	}

	// What the side's squads do now, from AI Conflict's own assignments: per role and objective, how
	// many squads and soldiers (and how many ride); squads still forming. Notes when the side's main
	// attack moves to another base (AI Conflict's own decisions show too).
	static void Now(string side, AICF_FactionState state)
	{
		if (!state)
			return;
		map<string, int> squads = new map<string, int>();
		map<string, int> men = new map<string, int>();
		map<string, int> riding = new map<string, int>();
		int forming;
		string top;
		int topMen;
		for (int s; s < state.GetSlotCount(); s++)
		{
			AICF_GroupSlot slot = state.GetSlot(s);
			if (!slot || !slot.GetGroup())
				continue;
			int alive = AICF_GroupRuntime.CountAliveAgents(slot.GetGroup());
			if (!slot.IsCombatReady() || alive == 0)
			{
				forming++;
				continue;
			}
			string role = "ATTACK";
			if (slot.GetRole() != AICF_EGroupRole.ATTACK)
				role = "DEFEND";
			string where = "-";
			if (slot.GetTargetBase())
				where = ZCR_Strategist.BaseName(slot.GetTargetBase());
			string key = role + " " + where;
			squads.Set(key, squads.Get(key) + 1);
			men.Set(key, men.Get(key) + alive);
			IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(slot.GetGroup());
			ChimeraCharacter lc = ChimeraCharacter.Cast(leader);
			if (lc && lc.IsInVehicle())
				riding.Set(key, riding.Get(key) + alive);
			if (role == "ATTACK" && men.Get(key) > topMen && slot.GetTargetBase() && slot.GetTargetBase().GetOwner())
			{
				topMen = men.Get(key);
				top = where;
				s_mMainTargetPos.Set(side, slot.GetTargetBase().GetOwner().GetOrigin());
			}
		}
		array<string> lines = {};
		foreach (string key, int n : squads)
		{
			string line = string.Format("  %1: %2 teams, %3 men", key, n, men.Get(key));
			if (riding.Get(key) > 0)
				line += string.Format(" (%1 riding)", riding.Get(key));
			lines.Insert(line);
		}
		lines.Sort();
		if (forming > 0)
			lines.Insert(string.Format("  forming at the main base: %1 teams", forming));
		s_mNow.Set(side, lines);
		if (!top.IsEmpty() && top != "-" && s_mMainTarget.Get(side) != top)
		{
			if (s_mMainTarget.Contains(side))
				Note(side, string.Format("main attack now on %1 (%2 men)", top, topMen));
			s_mMainTarget.Set(side, top);
		}
	}

	static string NowText(string side)
	{
		array<string> lines;
		if (!s_mNow.Find(side, lines) || lines.IsEmpty())
			return "  nothing yet - teams forming";
		string joined;
		foreach (int i, string l : lines)
		{
			if (i > 0)
				joined += "<br/>";
			joined += l;
		}
		return joined;
	}

	static string Clock(int seconds)
	{
		int m = seconds / 60;
		int s = seconds % 60;
		if (s < 10)
			return string.Format("%1:0%2", m, s);
		return string.Format("%1:%2", m, s);
	}
}
