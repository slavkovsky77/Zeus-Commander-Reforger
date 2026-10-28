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

	// The point itself (null outside the sub-lab).
	static SCR_CampaignMilitaryBaseComponent Base()
	{
		if (Name().IsEmpty())
			return null;
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return null;
		array<SCR_MilitaryBaseComponent> all = {};
		system.GetBases(all);
		foreach (SCR_MilitaryBaseComponent b : all)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (Is(base) && base.GetOwner())
				return base;
		}
		return null;
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

// The game counts a base as a target only inside the side's radio network; with every other base neutral the point
// (Beauregard: linked only to Signal Hill) is outside both (29 Oct 00:48: both plans fell back, both sides stayed home).
// In the one-point sub-lab the point is a target for both sides whatever their radio reaches.
modded class SCR_CampaignMilitaryBaseComponent
{
	override bool IsValidTarget(notnull SCR_CampaignFaction faction)
	{
		if (ZCR_OnePoint.Is(this) && GetFaction() != faction)
			return true;
		return super.IsValidTarget(faction);
	}
}
