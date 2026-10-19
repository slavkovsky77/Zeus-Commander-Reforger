// Supplies and logistics on the screen (Martin, 19 Oct 22:30: "a supply chain and logistics overview
// for the factions, maybe over the points - important to see for debugging"). Per side, for its panel:
// the supplies at its bases, the main base's stock, the change over the last minute, and AI Conflict's
// supply trucks on the road (its logistics ledger: from where to where, how much). Per base, for its
// label on the map: its stock. Server side (the director builds the panels).
class ZCR_Logistics
{
	protected static ref map<string, float> s_mLast = new map<string, float>();
	protected static ref map<string, int> s_mLastAt = new map<string, int>();
	protected static ref map<string, int> s_mRate = new map<string, int>();

	static int Stock(SCR_CampaignMilitaryBaseComponent base)
	{
		if (!base)
			return 0;
		return Math.Round(base.GetSupplies());
	}

	// "SUPPLIES 1840 at 5 bases (main 1000/1000), +40 a min" and the trucks on the road.
	static string Text(string side, int now, map<SCR_CampaignMilitaryBaseComponent, string> owners)
	{
		float total;
		int bases;
		foreach (SCR_CampaignMilitaryBaseComponent base, string owner : owners)
		{
			if (!base || owner != side)
				continue;
			total += base.GetSupplies();
			bases++;
		}
		string main = "";
		SCR_CampaignFaction faction = SCR_CampaignFaction.Cast(GetGame().GetFactionManager().GetFactionByKey(side));
		if (faction && faction.GetMainBase())
			main = string.Format(" (main %1/%2)", Math.Round(faction.GetMainBase().GetSupplies()), Math.Round(faction.GetMainBase().GetSuppliesMax()));
		// The change per minute, measured over a minute or more.
		if (!s_mLastAt.Contains(side))
		{
			s_mLast.Set(side, total);
			s_mLastAt.Set(side, now);
		}
		else if (now - s_mLastAt.Get(side) >= 60)
		{
			s_mRate.Set(side, Math.Round((total - s_mLast.Get(side)) * 60 / (now - s_mLastAt.Get(side))));
			s_mLast.Set(side, total);
			s_mLastAt.Set(side, now);
		}
		string rate = "";
		if (s_mRate.Contains(side))
		{
			int r = s_mRate.Get(side);
			if (r >= 0)
				rate = string.Format(", +%1 a min", r);
			else
				rate = string.Format(", %1 a min", r);
		}
		string text = string.Format("  %1 at %2 bases%3%4", Math.Round(total), bases, main, rate);
		return text + "<br/>  " + Trucks(side);
	}

	// AI Conflict's supply trucks of this side with a delivery: how many, and the first two routes.
	protected static string Trucks(string side)
	{
		AICF_LogisticsLedger ledger = AICF_LogisticsLedger.s_Current;
		if (!ledger)
			return "trucks: -";
		int tick = System.GetTickCount();
		int n;
		string routes;
		foreach (AICF_LogisticsJob job : ledger.m_aJobs)
		{
			if (!job || job.m_bCancelled || tick >= job.m_iExpiresAtMs || !job.m_Destination || !job.m_Destination.m_Owner)
				continue;
			if (job.m_Destination.m_Owner.GetFactionKey() != side)
				continue;
			n++;
			if (n <= 2)
			{
				string from = "depot";
				if (job.m_Source && job.m_Source.m_Base)
					from = ZCR_Strategist.BaseName(job.m_Source.m_Base);
				string to = "?";
				if (job.m_Destination.m_Base)
					to = ZCR_Strategist.BaseName(job.m_Destination.m_Base);
				routes += string.Format(", %1 > %2 %3", from, to, Math.Round(job.m_fReservedIncoming));
			}
		}
		if (n == 0)
			return "trucks: none on the road";
		return string.Format("trucks: %1 on the road%2", n, routes);
	}
}
