// The tactical layer under our commander (24 Oct 2026, Martin: "DCO will be used as the tactical AI mod and Zeus
// Commander as strategic"). Our code tells the tactical layer what a squad is doing; with DCO_AI loaded the bridge addon
// ZCR_DCO (ZCR_DCO/Scripts/Game/ZCR_DCO/ZCR_DCOBridge.c) turns it into DCO's own per-group switches; without DCO nothing
// happens. In the lab: -zcrStormPush makes the guns test's attacking squads storm from the start.
//   [ZCR][TACTICAL] t= group= storming=0|1 layer=dco|none
class ZCR_Tactical
{
	protected static ref ZCR_Tactical s_Instance;

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

	// A squad starts (true) or stops storming its objective: the tactical layer lets it push instead of breaking contact.
	void SetStorming(SCR_AIGroup group, bool storming)
	{
	}

	static void Storming(SCR_AIGroup group, bool storming)
	{
		if (!group)
			return;
		Get().SetStorming(group, storming);
		Print(string.Format("[ZCR][TACTICAL] t=%1 group=%2 storming=%3 layer=%4", ZCR_LossLog.Seconds(), group.GetID(), storming, Get().Layer()), LogLevel.NORMAL);
	}
}
