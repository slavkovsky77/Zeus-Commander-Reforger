// The Lab app's live map (25 Oct - Martin: "the map could also show the individual supply missions", "also live teams and
// that kind of thing - that can be done in the Commander Lab"): every LIVE_S seconds one line per team, AI Conflict supply
// truck and drive-test van, read by lab/app/server.py (/api/map/live) and drawn on the Map tab. Names last, spaces as _.
//   [ZCR][LIVE] t= kind=team side= id= role= men= ride= x= z= to=
//   [ZCR][LIVE] t= kind=truck side= id= phase= cargo= cap= kmh= x= z= from= to=
//   [ZCR][LIVE] t= kind=van id= phase= cargo= kmh= route= x= z= to=
// -zcrNoLiveMap off.
class ZCR_LiveMap
{
	static const int LIVE_S = 5;
	protected static bool s_bStarted;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoLiveMap"))
			return;
		s_bStarted = true;
		GetGame().GetCallqueue().CallLater(Tick, LIVE_S * 1000, true);
	}

	static string Name(string s)
	{
		string named = s;
		named.Replace(" ", "_");
		if (named.IsEmpty())
			named = "-";
		return named;
	}

	protected static void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		foreach (FactionKey faction, AICF_FactionState state : ZCR_Strategist.s_mStates)
		{
			for (int s; state && s < state.GetSlotCount(); s++)
			{
				AICF_GroupSlot slot = state.GetSlot(s);
				if (!slot || !slot.GetGroup())
					continue;
				IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(slot.GetGroup());
				if (!leader)
					continue;
				vector at = leader.GetOrigin();
				ChimeraCharacter lc = ChimeraCharacter.Cast(leader);
				int ride = lc && lc.IsInVehicle();
				string to = "-";
				if (slot.GetTargetBase())
					to = Name(ZCR_Strategist.BaseName(slot.GetTargetBase()));
				Print(string.Format("[ZCR][LIVE] t=%1 kind=team side=%2 id=%3 role=%4 men=%5 ride=%6 x=%7 z=%8 to=%9", now, faction, slot.GetSlotId(),
					typename.EnumToString(AICF_EGroupRole, slot.GetRole()), AICF_GroupRuntime.CountAliveAgents(slot.GetGroup()), ride, Math.Round(at[0]),
					Math.Round(at[2]), to), LogLevel.NORMAL);
			}
		}
		array<AICF_LogisticsWorker> workers = {};
		AICF_LogisticsLookup.All(workers);
		foreach (AICF_LogisticsWorker w : workers)
		{
			if (!w || !w.m_Vehicle)
				continue;
			vector p = w.m_Vehicle.GetOrigin();
			string from = "-";
			string to = "-";
			if (w.m_Job && !w.m_Job.m_bCancelled)
			{
				if (w.m_Job.m_Source)
					from = Name(ZCR_Strategist.BaseName(w.m_Job.m_Source.m_Base));
				if (w.m_Job.m_Destination)
					to = Name(ZCR_Strategist.BaseName(w.m_Job.m_Destination.m_Base));
			}
			float cargo = -1;
			float cap = -1;
			if (w.m_CargoPool && w.m_CargoPool.Valid())
			{
				cargo = w.m_CargoPool.Value();
				cap = w.m_CargoPool.Capacity();
			}
			float kmh;
			if (w.m_Vehicle.GetPhysics())
				kmh = w.m_Vehicle.GetPhysics().GetVelocity().Length() * 3.6;
			string side = "?";
			if (w.m_Faction)
				side = w.m_Faction.GetFactionKey();
			Print(string.Format("[ZCR][LIVE] t=%1 kind=truck side=%2 id=%3 phase=%4 cargo=%5 cap=%6 kmh=%7 x=%8 z=%9", now, side, w.m_iSlot,
				typename.EnumToString(AICF_ELogisticsPhase, w.m_ePhase), Math.Round(cargo), Math.Round(cap), Math.Round(kmh), Math.Round(p[0]), Math.Round(p[2]))
				+ string.Format(" from=%1 to=%2", from, to), LogLevel.NORMAL);
		}
		ZCR_DriveTest.LiveLines(now);
	}
}
