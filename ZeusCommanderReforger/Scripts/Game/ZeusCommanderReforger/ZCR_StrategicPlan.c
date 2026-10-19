// One side's strategic plan, on top of AI Conflict's own commander (AICF_AdaptiveCommanderPolicy).
// Our doctrine or the LLM strategist fills it; an empty plan leaves AI Conflict deciding alone.
//   priority  extra score for a base (graph node id): the main effort high, bases to leave negative.
//             AI Conflict adds it to the candidate's front value, so its route, readiness and
//             threat rules still decide which squad can go.
//   demand    the least force a base calls for: more squads converge on it (our doctrine: go in
//             with 2x the known enemy, 3x against a trench line).
//   commit    how many of AI Conflict's DEFEND squads join the attack (0-2): Arma 3's doctrine keeps
//             a minimal garrison while nothing threatens us (ZCR_CommitDefenders).
//   storm     a base the squads sent there go into without stopping to fight at range (ZCR_Storm).
// Server only. Every change is logged as [ZCR][PLAN] for the lab.
class ZCR_StrategicPlan
{
	protected static ref map<FactionKey, ref ZCR_StrategicPlan> s_mPlans;

	protected FactionKey m_sFaction;
	protected ref map<int, float> m_mPriority = new map<int, float>();
	protected ref map<int, float> m_mDemand = new map<int, float>();
	protected string m_sIntent;
	protected string m_sSource;
	protected int m_iRevision;
	protected int m_iMainEffort = -1;
	protected int m_iChangedAt;
	protected int m_iCommit;
	protected int m_iStorm = -1;

	static ZCR_StrategicPlan Get(FactionKey faction)
	{
		if (!s_mPlans)
			s_mPlans = new map<FactionKey, ref ZCR_StrategicPlan>();
		ZCR_StrategicPlan plan;
		if (!s_mPlans.Find(faction, plan) || !plan)
		{
			plan = new ZCR_StrategicPlan();
			plan.m_sFaction = faction;
			s_mPlans.Set(faction, plan);
		}
		return plan;
	}

	bool IsEmpty()
	{
		return m_mPriority.IsEmpty() && m_mDemand.IsEmpty();
	}

	float GetPriority(int nodeId)
	{
		float value;
		if (m_mPriority.Find(nodeId, value))
			return value;
		return 0;
	}

	float GetDemand(int nodeId)
	{
		float value;
		if (m_mDemand.Find(nodeId, value))
			return value;
		return 0;
	}

	int GetCommit()
	{
		return m_iCommit;
	}

	void SetCommit(int commit)
	{
		m_iCommit = Math.ClampInt(commit, 0, 2);
	}

	int GetStorm()
	{
		return m_iStorm;
	}

	void SetStorm(int nodeId)
	{
		m_iStorm = nodeId;
	}

	string GetIntent()
	{
		return m_sIntent;
	}

	int GetRevision()
	{
		return m_iRevision;
	}

	// The base with the highest priority (the main effort), -1 for none.
	int GetMainEffort()
	{
		return m_iMainEffort;
	}

	string GetSource()
	{
		return m_sSource;
	}

	// Game seconds when the plan last changed.
	int GetChangedAt()
	{
		return m_iChangedAt;
	}

	array<int> GetPriorityBases()
	{
		array<int> bases = {};
		foreach (int node, float value : m_mPriority)
		{
			if (value > 0)
				bases.Insert(node);
		}
		return bases;
	}

	// Replace the whole plan at once. source: "doctrine", "llm" or "lab".
	void Apply(map<int, float> priority, map<int, float> demand, string intent, string source)
	{
		if (!Replication.IsServer())
			return;
		m_mPriority.Clear();
		m_mDemand.Clear();
		if (priority)
		{
			foreach (int node, float value : priority)
				m_mPriority.Set(node, value);
		}
		if (demand)
		{
			foreach (int node, float value : demand)
				m_mDemand.Set(node, value);
		}
		m_sIntent = intent;
		m_sSource = source;
		m_iRevision++;
		m_iChangedAt = ZCR_LossLog.Seconds();
		m_iMainEffort = -1;
		float best = 0;
		foreach (int node, float value : m_mPriority)
		{
			if (value > best)
			{
				best = value;
				m_iMainEffort = node;
			}
		}
		Print(string.Format("[ZCR][PLAN] faction=%1 revision=%2 source=%3 priorities=%4 demands=%5 commit=%7 storm=%8 intent=%6",
			m_sFaction, m_iRevision, m_sSource, m_mPriority.Count(), m_mDemand.Count(), m_sIntent, m_iCommit, m_iStorm), LogLevel.NORMAL);
	}

	void Clear(string source)
	{
		m_iCommit = 0;
		m_iStorm = -1;
		Apply(null, null, "", source);
	}
}
