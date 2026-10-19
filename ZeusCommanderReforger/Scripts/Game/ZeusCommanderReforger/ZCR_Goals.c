// Each side's goals in its panel (Martin, 19 Oct 23:59: "engineering goals in the overview - we should
// probably have a set of goals for the agent"): what it attacks, which of its bases it has to hold
// (enemies known within 400 m), which need supplies (under 40%), what its engineers build now and
// what they have built. Built from the plan, the side's knowledge, the bases' stock and AI Conflict's
// construction planner. Server side (the director builds the panels).
class ZCR_Goals
{
	static string Text(string side, map<SCR_CampaignMilitaryBaseComponent, string> owners)
	{
		string br = "<br/>";
		string text;
		// Attack: the plan's main effort.
		ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(side);
		int effort = plan.GetMainEffort();
		if (effort >= 0 && ZCR_Strategist.s_mNodeName.Contains(effort))
			text += "  attack " + ZCR_Strategist.s_mNodeName.Get(effort) + br;
		// Hold and resupply: own bases with enemies near, or low on supplies.
		string hold, supply;
		foreach (SCR_CampaignMilitaryBaseComponent base, string owner : owners)
		{
			if (!base || owner != side || !base.GetOwner())
				continue;
			vector at = base.GetOwner().GetOrigin();
			int near = ZCR_Sampler.KnownEnemiesNear(side, at, 400);
			if (near > 0)
				hold += string.Format(", %1 (%2 enemies)", ZCR_Strategist.BaseName(base), near);
			float max = base.GetSuppliesMax();
			if (max > 0 && base.GetSupplies() < 0.4 * max)
				supply += string.Format(", %1 %2/%3", ZCR_Strategist.BaseName(base), Math.Round(base.GetSupplies()), Math.Round(max));
		}
		if (!hold.IsEmpty())
			text += "  hold" + hold.Substring(1, hold.Length() - 1) + br;
		if (!supply.IsEmpty())
			text += "  resupply" + supply.Substring(1, supply.Length() - 1) + br;
		// Engineers: AI Conflict's construction orders now, and what stands at the side's bases.
		array<SCR_CampaignMilitaryBaseComponent> bases = {};
		array<string> what = {};
		array<bool> building = {};
		AICF_ConstructionPlanner.AICF_Orders(side, bases, what, building);
		string build;
		for (int i; i < bases.Count(); i++)
		{
			string stage = "choosing a site";
			if (building[i])
				stage = "building";
			build += string.Format(", %1 at %2 (%3)", what[i], ZCR_Strategist.BaseName(bases[i]), stage);
		}
		if (!build.IsEmpty())
			text += "  engineers: " + build.Substring(2, build.Length() - 2) + br;
		text += "  built: " + Built(side, owners);
		return text;
	}

	// "2 barracks, 3 vehicle depots, 1 armory" - the services standing at the side's bases.
	protected static string Built(string side, map<SCR_CampaignMilitaryBaseComponent, string> owners)
	{
		map<string, int> count = new map<string, int>();
		foreach (SCR_CampaignMilitaryBaseComponent base, string owner : owners)
		{
			if (!base || owner != side)
				continue;
			array<SCR_ServicePointComponent> services = {};
			base.GetServices(services);
			foreach (SCR_ServicePointComponent service : services)
			{
				if (!service)
					continue;
				string kind = typename.EnumToString(SCR_EServicePointType, service.GetType());
				kind.ToLower();
				kind.Replace("_", " ");
				count.Set(kind, count.Get(kind) + 1);
			}
		}
		string text;
		foreach (string kind, int n : count)
		{
			if (!text.IsEmpty())
				text += ", ";
			text += string.Format("%1 %2", n, kind);
		}
		if (text.IsEmpty())
			return "nothing yet";
		return text;
	}
}
