// The strategic layer for one side. Every -zcrPlanSeconds (default 90) of game time it writes a
// situation report: only what this side can know (every base's owner and links, its own bases'
// supplies and threats, its own squads). The report goes to $profile:zcr/snapshots.jsonl for the
// lab and, with -zcrBridge=http://127.0.0.1:8765, to the bridge (lab/bridge.py), which asks the
// LLM or our doctrine and answers with a plan in plain lines:
//   ok source=llm
//   intent Pin Morton with fire, main effort on the radio relay to the west
//   priority 12 80
//   demand 12 30
// The plan goes into ZCR_StrategicPlan, which steers AI Conflict's commander. No answer for three
// rounds: the plan is cleared and AI Conflict decides alone again. Server only.
class ZCR_Strategist
{
	protected static ref map<FactionKey, ref ZCR_Strategist> s_mStrategists;

	protected FactionKey m_sFaction;
	protected int m_iIntervalMs = 90000;
	protected string m_sBridge;
	protected float m_fNextAt = -1;
	protected int m_iRound;
	protected int m_iMissed;
	protected bool m_bWaiting;
	protected ref RestCallback m_Callback;

	static ZCR_Strategist Get(FactionKey faction)
	{
		if (!s_mStrategists)
			s_mStrategists = new map<FactionKey, ref ZCR_Strategist>();
		ZCR_Strategist strategist;
		if (!s_mStrategists.Find(faction, strategist) || !strategist)
		{
			strategist = new ZCR_Strategist(faction);
			s_mStrategists.Set(faction, strategist);
		}
		return strategist;
	}

	void ZCR_Strategist(FactionKey faction)
	{
		m_sFaction = faction;
		string value;
		if (System.GetCLIParam("zcrPlanSeconds", value) && value.ToInt() >= 20)
			m_iIntervalMs = value.ToInt() * 1000;
		if (System.GetCLIParam("zcrBridge", value))
			m_sBridge = value;
		ZCR_LossLog.Register();
		Print(string.Format("[ZCR][STRATEGIST] faction=%1 interval_s=%2 bridge=%3", m_sFaction, m_iIntervalMs / 1000, m_sBridge), LogLevel.NORMAL);
	}

	// Called from AI Conflict's commander tick (every 15 s); runs a round when one is due.
	void Tick(AICF_FactionState state, SCR_CampaignFaction faction, AICF_ObjectiveGraph graph)
	{
		if (!Replication.IsServer() || !state || !faction || !graph)
			return;
		BaseWorld world = GetGame().GetWorld();
		if (!world)
			return;
		float now = world.GetWorldTime();
		if (m_fNextAt < 0)
			m_fNextAt = now + m_iIntervalMs / 3;   // first round after the opening deployment
		if (now < m_fNextAt)
			return;
		m_fNextAt = now + m_iIntervalMs;
		m_iRound++;

		if (m_bWaiting)
			OnNoAnswer("BUSY");
		string report = BuildReport(state, faction, graph);
		SaveReport(report);
		if (m_sBridge.IsEmpty())
			return;
		RestContext context = GetGame().GetRestApi().GetContext(m_sBridge);
		if (!context)
		{
			OnNoAnswer("NO_CONTEXT");
			return;
		}
		context.SetTimeout(30);
		m_Callback = new RestCallback();
		m_Callback.SetOnSuccess(OnAnswer);
		m_Callback.SetOnError(OnError);
		m_bWaiting = true;
		context.POST(m_Callback, "/plan", report);
	}

	protected static string Clean(string text)
	{
		string clean = text;
		clean.Replace("\\", "/");
		clean.Replace("\"", "'");
		return clean;
	}

	protected static string Num(float value)
	{
		return Math.Round(value).ToString();
	}

	protected string BuildReport(AICF_FactionState state, SCR_CampaignFaction faction, AICF_ObjectiveGraph graph)
	{
		string bases;
		for (int i; i < graph.GetNodeCount(); i++)
		{
			AICF_ObjectiveNode node = graph.GetNode(i);
			if (!node || !node.GetBase())
				continue;
			SCR_CampaignMilitaryBaseComponent base = node.GetBase();
			string owner;
			if (base.GetFaction())
				owner = base.GetFaction().GetFactionKey();
			bool ours = base.GetFaction() == faction;
			string links;
			foreach (int next : node.GetOutgoingNodeIds())
			{
				if (!links.IsEmpty())
					links += ",";
				links += next.ToString();
			}
			vector at = base.GetOwner().GetOrigin();
			string entry = string.Format("{\"id\":%1,\"name\":\"%2\",\"owner\":\"%3\",\"hq\":%4,\"objective\":%5,\"links\":[%6],\"x\":%7,\"z\":%8",
				node.GetId(), Clean(base.GetBaseName()), owner, base.IsHQ(), node.IsObjective(), links, Num(at[0]), Num(at[2]));
			if (ours)
				entry += string.Format(",\"supplies\":%1,\"threatened\":%2", Num(base.GetSupplies()), base.IsBeingCaptured() || base.AreEnemiesPresent());
			entry += "}";
			if (!bases.IsEmpty())
				bases += ",";
			bases += entry;
		}

		string squads;
		for (int s; s < state.GetSlotCount(); s++)
		{
			AICF_GroupSlot slot = state.GetSlot(s);
			if (!slot)
				continue;
			SCR_AIGroup group = slot.GetGroup();
			int alive = AICF_GroupRuntime.CountAliveAgents(group);
			IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(group);
			int target = -1;
			if (slot.GetTargetBase())
				target = graph.FindNodeId(slot.GetTargetBase());
			string entry = string.Format("{\"slot\":%1,\"role\":\"%2\",\"alive\":%3,\"size\":%4,\"ready\":%5,\"target\":%6",
				slot.GetSlotId(), typename.EnumToString(AICF_EGroupRole, slot.GetRole()), alive, slot.GetDesiredSize(),
				slot.IsCombatReady(), target);
			if (leader)
			{
				vector at = leader.GetOrigin();
				entry += string.Format(",\"x\":%1,\"z\":%2", Num(at[0]), Num(at[2]));
			}
			entry += "}";
			if (!squads.IsEmpty())
				squads += ",";
			squads += entry;
		}

		ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(m_sFaction);
		return string.Format("{\"faction\":\"%1\",\"t\":%2,\"round\":%3,\"plan_revision\":%4,\"intent\":\"%5\",\"bases\":[%6],\"squads\":[%7]}",
			m_sFaction, ZCR_LossLog.Seconds(), m_iRound, plan.GetRevision(), Clean(plan.GetIntent()), bases, squads);
	}

	protected void SaveReport(string report)
	{
		FileIO.MakeDirectory("$profile:zcr");
		FileHandle file = FileIO.OpenFile("$profile:zcr/snapshots.jsonl", FileMode.APPEND);
		if (file)
		{
			file.WriteLine(report);
			file.Close();
		}
		Print(string.Format("[ZCR][SNAPSHOT] faction=%1 t=%2 round=%3 bytes=%4", m_sFaction, ZCR_LossLog.Seconds(), m_iRound, report.Length()), LogLevel.NORMAL);
	}

	protected void OnAnswer(RestCallback callback)
	{
		m_bWaiting = false;
		array<string> lines = {};
		callback.GetData().Split("\n", lines, true);
		if (lines.IsEmpty() || !lines[0].StartsWith("ok"))
		{
			OnNoAnswer("BAD_ANSWER");
			return;
		}
		string source = "bridge";
		array<string> head = {};
		lines[0].Split(" ", head, true);
		foreach (string part : head)
		{
			if (part.StartsWith("source="))
				source = part.Substring(7, part.Length() - 7);
		}
		map<int, float> priority = new map<int, float>();
		map<int, float> demand = new map<int, float>();
		string intent;
		for (int i = 1; i < lines.Count(); i++)
		{
			string line = lines[i].Trim();
			if (line.StartsWith("intent "))
			{
				intent = line.Substring(7, line.Length() - 7);
				continue;
			}
			array<string> parts = {};
			line.Split(" ", parts, true);
			if (parts.Count() != 3)
				continue;
			if (parts[0] == "priority")
				priority.Set(parts[1].ToInt(), parts[2].ToFloat());
			else if (parts[0] == "demand")
				demand.Set(parts[1].ToInt(), parts[2].ToFloat());
		}
		m_iMissed = 0;
		ZCR_StrategicPlan.Get(m_sFaction).Apply(priority, demand, intent, source);
	}

	protected void OnError(RestCallback callback)
	{
		m_bWaiting = false;
		OnNoAnswer(typename.EnumToString(ERestResult, callback.GetRestResult()));
	}

	protected void OnNoAnswer(string reason)
	{
		m_bWaiting = false;
		m_iMissed++;
		Print(string.Format("[ZCR][BRIDGE_MISS] faction=%1 round=%2 missed=%3 reason=%4", m_sFaction, m_iRound, m_iMissed, reason), LogLevel.WARNING);
		ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(m_sFaction);
		if (m_iMissed >= 3 && !plan.IsEmpty())
			plan.Clear("no_answer");
	}
}
