// The tactical layer under our commander (24 Oct 2026, Martin: "DCO will be used as the tactical AI mod and Zeus
// Commander as strategic"). Our code tells the tactical layer what a squad is doing; with DCO_AI loaded the bridge addon
// ZCR_DCO (ZCR_DCO/Scripts/Game/ZCR_DCO/ZCR_DCOBridge.c) turns it into DCO's own per-group switches; without DCO nothing
// happens. In the lab: -zcrStormPush makes the guns test's attacking squads storm from the start.
//   [ZCR][TACTICAL] t= group= storming=0|1 layer=dco|none
class ZCR_Tactical
{
	protected static ref ZCR_Tactical s_Instance;
	protected ref map<SCR_AIGroup, string> m_mStorming = new map<SCR_AIGroup, string>();   // squad -> its faction

	static ZCR_Tactical Get()
	{
		if (!s_Instance)
			s_Instance = new ZCR_Tactical();
		return s_Instance;
	}

	// "dco" with the bridge loaded.
	string Layer()
	{
		return "none";
	}

	// Every commander tick for a side: the tactical layer can adjust its squads (DCO: detail by distance to known enemies).
	void Tend(string faction, AICF_FactionState state)
	{
	}

	// A squad starts (true) or stops storming its objective: the tactical layer lets it push instead of breaking contact.
	void SetStorming(SCR_AIGroup group, bool storming)
	{
	}

	// A team that must stay where it is (the drone operators, ZCR_DroneOperator): the tactical layer's own squad moves off.
	void HoldStill(SCR_AIGroup group)
	{
	}

	static void Storming(SCR_AIGroup group, bool storming, string faction = "")
	{
		if (!group)
			return;
		Get().SetStorming(group, storming);
		if (storming)
			Get().m_mStorming.Set(group, faction);
		else
			Get().m_mStorming.Remove(group);
		Print(string.Format("[ZCR][TACTICAL] t=%1 group=%2 storming=%3 layer=%4 faction=%5", ZCR_LossLog.Seconds(), group.GetID(), storming, Get().Layer(), faction), LogLevel.NORMAL);
	}

	// A faction's storm is over (or moves to another base): its storming squads fight normally again.
	static void EndStorm(string faction)
	{
		array<SCR_AIGroup> done = {};
		foreach (SCR_AIGroup g, string f : Get().m_mStorming)
		{
			if (f == faction)
				done.Insert(g);
		}
		foreach (SCR_AIGroup g : done)
		{
			if (g)
				Storming(g, false, faction);
			else
				Get().m_mStorming.Remove(g);
		}
	}
}
