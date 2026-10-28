// The one-point sub-lab (Martin, 28 Oct evening, after an assault test full of rides that went wrong: "a sublab where
// there will be only main base and one point they will fight for ... just one point!"). -zcrOnePoint <base name,
// underscores for spaces>: the two main bases and that base are the whole war. With -zcrNoFIA the point stays neutral
// (FIA's, without soldiers - the fork spawns no FIA garrison then) while the other bases are dealt to the sides as usual
// (they still give vehicles and supplies); every base but the point and a team's own main base is off every team's list.
class ZCR_OnePoint
{
	static string Name()
	{
		string v;
		if (!System.GetCLIParam("zcrOnePoint", v) || v.IsEmpty())
			return string.Empty;
		v.Replace("_", " ");
		return v;
	}

	static bool Is(SCR_CampaignMilitaryBaseComponent base)
	{
		string n = Name();
		return !n.IsEmpty() && base && ZCR_Strategist.BaseName(base) == n;
	}

	// Off the list: every base but the point and the team's own main base.
	static void Filter(SCR_CampaignFaction faction, array<ref AICF_AdaptiveCandidate> candidates)
	{
		if (Name().IsEmpty() || !faction || !candidates)
			return;
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && !Is(c.m_Base) && !(c.m_Base && c.m_Base == faction.GetMainBase()))
				c.m_bAvailable = false;
		}
	}
}
