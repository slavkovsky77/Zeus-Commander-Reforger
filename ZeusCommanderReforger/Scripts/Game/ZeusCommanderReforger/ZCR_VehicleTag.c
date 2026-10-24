// What a vehicle is doing, for the watched game's vehicle tags (25 Oct - Martin: "why don't vehicles have tags with their
// mission and supplies? I would expect to see this"): a drive test's van - its goal, planned route or not, distance left;
// an AI Conflict supply truck - its phase, from where to where, its cargo. Empty for anything else.
class ZCR_VehicleTag
{
	static string Mission(IEntity v)
	{
		if (!v)
			return "";
		string test = ZCR_DriveTest.TagFor(v);
		if (!test.IsEmpty())
			return test;
		AICF_LogisticsWorker w = AICF_LogisticsLookup.Get(v);
		if (!w)
			return "";
		string from, to;
		if (w.m_Job && !w.m_Job.m_bCancelled)
		{
			if (w.m_Job.m_Source)
				from = ZCR_Strategist.BaseName(w.m_Job.m_Source.m_Base);
			if (w.m_Job.m_Destination)
				to = ZCR_Strategist.BaseName(w.m_Job.m_Destination.m_Base);
		}
		string what;
		switch (w.m_ePhase)
		{
			case AICF_ELogisticsPhase.TO_SOURCE: what = "SUPPLY RUN: to load at " + from; break;
			case AICF_ELogisticsPhase.LOADING: what = "SUPPLY RUN: loading at " + from; break;
			case AICF_ELogisticsPhase.TO_DESTINATION: what = "SUPPLY RUN: delivering " + from + " -> " + to; break;
			case AICF_ELogisticsPhase.UNLOADING: what = "SUPPLY RUN: unloading at " + to; break;
			case AICF_ELogisticsPhase.RETURN_HOME: what = "SUPPLY TRUCK: returning to " + ZCR_Strategist.BaseName(w.m_Home); break;
			case AICF_ELogisticsPhase.WAIT_RETRY: what = "SUPPLY TRUCK: waiting to retry"; break;
			case AICF_ELogisticsPhase.SPAWN_PENDING: what = "SUPPLY TRUCK: getting ready"; break;
			case AICF_ELogisticsPhase.DRIVER_READY: what = "SUPPLY TRUCK: ready"; break;
			default: what = "SUPPLY TRUCK: waiting for a job";
		}
		if (w.m_CargoPool && w.m_CargoPool.Valid())
			what += string.Format("  |  %1/%2 supplies", Math.Round(w.m_CargoPool.Value()), Math.Round(w.m_CargoPool.Capacity()));
		return what;
	}

	// The name of the base nearest to a point ("Farm"), within 'within' metres; else "".
	static string NearestBase(vector p, float within = 400)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return "";
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		string best;
		float bestM = within;
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || !base.GetOwner())
				continue;
			float d = vector.DistanceXZ(base.GetOwner().GetOrigin(), p);
			if (d < bestM)
			{
				bestM = d;
				best = ZCR_Strategist.BaseName(base);
			}
		}
		return best;
	}
}
