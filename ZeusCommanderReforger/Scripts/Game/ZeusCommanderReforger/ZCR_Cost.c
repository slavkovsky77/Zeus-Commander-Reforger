// Our scripts' cost (24 Oct, Martin: "pretty low FPS - it would be good to find out why"): each recurring system times
// its tick with the game's millisecond clock (as DCO's own profiler does); every 60 game s the minute's totals:
//   [ZCR][COST] t= wall_ms= ours_ms= ours_pct= top=name:ms/max,name:ms/max,...      (the 8 dearest systems)
// A tick opens a scope at its top: ZCR_CostScope cost = new ZCR_CostScope("junction"); its destructor records the time
// when the tick returns, whichever return it takes.
class ZCR_Cost
{
	protected static ref map<string, int> s_mMs = new map<string, int>();
	protected static ref map<string, int> s_mMax = new map<string, int>();
	protected static int s_iNextAt = 60;
	protected static int s_iWallStart = -1;

	static void Add(string name, int ms)
	{
		if (ms < 0)
			ms = 0;
		s_mMs.Set(name, s_mMs.Get(name) + ms);
		if (ms > s_mMax.Get(name))
			s_mMax.Set(name, ms);
		Flush();
	}

	// Who the game's AI characters are (24 Oct: 152 AI characters with 83 squad soldiers sampled): per side on foot / in a
	// vehicle (drones included), and the rest.
	//   [ZCR][POP] t= us_foot= us_veh= ussr_foot= ussr_veh= fia= other= total=
	protected static void Population(int now)
	{
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		int usFoot, usVeh, ussrFoot, ussrVeh, fia, other, total;
		foreach (AIAgent a : agents)
		{
			ChimeraCharacter c = null;
			if (a)
				c = ChimeraCharacter.Cast(a.GetControlledEntity());
			if (!c)
				continue;
			CharacterControllerComponent ctl = c.GetCharacterController();
			if (ctl && ctl.GetLifeState() == ECharacterLifeState.DEAD)
				continue;
			total++;
			string side = ZCR_LossLog.SideOf(c);
			bool veh = c.IsInVehicle();
			if (side == "US" && veh)
				usVeh++;
			else if (side == "US")
				usFoot++;
			else if (side == "USSR" && veh)
				ussrVeh++;
			else if (side == "USSR")
				ussrFoot++;
			else if (side == "FIA")
				fia++;
			else
				other++;
		}
		Print(string.Format("[ZCR][POP] t=%1 us_foot=%2 us_veh=%3 ussr_foot=%4 ussr_veh=%5 fia=%6 other=%7 total=%8", now, usFoot, usVeh, ussrFoot, ussrVeh, fia,
			other, total), LogLevel.NORMAL);
	}

	protected static void Flush()
	{
		int now = ZCR_LossLog.Seconds();
		int tick = System.GetTickCount();
		if (s_iWallStart < 0)
			s_iWallStart = tick;
		if (now < s_iNextAt)
			return;
		s_iNextAt = now + 60;
		int wall = Math.Max(1, tick - s_iWallStart);
		s_iWallStart = tick;
		int ours;
		array<string> names = {};
		foreach (string n, int ms : s_mMs)
		{
			ours += ms;
			names.Insert(n);
		}
		// The dearest first.
		for (int i = 1; i < names.Count(); i++)
		{
			string key = names[i];
			int j = i - 1;
			while (j >= 0 && s_mMs.Get(names[j]) < s_mMs.Get(key))
			{
				names[j + 1] = names[j];
				j--;
			}
			names[j + 1] = key;
		}
		string top;
		for (int k; k < names.Count() && k < 8; k++)
		{
			if (k > 0)
				top += ",";
			top += string.Format("%1:%2/%3", names[k], s_mMs.Get(names[k]), s_mMax.Get(names[k]));
		}
		Print(string.Format("[ZCR][COST] t=%1 wall_ms=%2 ours_ms=%3 ours_pct=%4 top=%5", now, wall, ours, Math.Round(1000.0 * ours / wall) / 10, top), LogLevel.NORMAL);
		Population(now);
		s_mMs.Clear();
		s_mMax.Clear();
	}
}

class ZCR_CostScope
{
	protected string m_sName;
	protected int m_iStart;

	void ZCR_CostScope(string name)
	{
		m_sName = name;
		m_iStart = System.GetTickCount();
	}

	void ~ZCR_CostScope()
	{
		ZCR_Cost.Add(m_sName, System.GetTickCount() - m_iStart);
	}
}
