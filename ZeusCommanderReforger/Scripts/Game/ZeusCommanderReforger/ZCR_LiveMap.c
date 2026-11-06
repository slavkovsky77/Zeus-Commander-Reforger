// The Lab app's live map (25 Oct - Martin: "the map could also show the individual supply missions", "also live teams and
// that kind of thing - that can be done in the Commander Lab"): every LIVE_S seconds one line per team, AI Conflict supply
// truck and drive-test van, read by lab/app/server.py (/api/map/live) and drawn on the Map tab. Names last, spaces as _.
//   [ZCR][LIVE] t= kind=team side= id= role= men= ride= x= z= to=
//   [ZCR][LIVE] t= kind=truck side= id= phase= cargo= cap= kmh= x= z= wps=x,z;x,z from= to=
//   [ZCR][LIVE] t= kind=van id= phase= cargo= kmh= route= x= z= to=
//   [ZCR][LIVE] t= kind=builder side= id= doing= progress= x= z= sx= sz= what= base=   (AI Conflict's base builders)
// -zcrNoLiveMap off.
class ZCR_LiveMap
{
	static const int LIVE_S = 5;
	protected static bool s_bStarted;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || AICF_Launch.Has("zcrNoLiveMap"))
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
				// to= is the team's ASSIGNED target; what it really does and where it really goes (28 Oct, note 433: all 12
				// Soviet attack teams read 'to Military Training Area' while 3 walked home as lone survivors and 5 had orders
				// for other bases): AI Conflict's posture and the team's current waypoint.
				string posture = slot.GetOperationalPosture();
				if (slot.IsLoneSurvivorRetreat())
					posture = "LONE_SURVIVOR_RETREAT";
				if (posture.IsEmpty())
					posture = "-";
				string wp = "-";
				// The current waypoint's priority level: above 0 the team keeps moving under fire (a storm, ZCR_Storm).
				float wpLevel;
				AIWaypoint current = slot.GetGroup().GetCurrentWaypoint();
				if (current)
				{
					vector w = current.GetOrigin();
					wp = string.Format("%1,%2", Math.Round(w[0]), Math.Round(w[2]));
					SCR_AIWaypoint currentScripted = SCR_AIWaypoint.Cast(current);
					if (currentScripted)
						wpLevel = currentScripted.GetPriorityLevel();
				}
				string head = string.Format("[ZCR][LIVE] t=%1 kind=team side=%2 id=%3 role=%4 men=%5 ride=%6 x=%7 z=%8 to=%9", now, faction, slot.GetSlotId(),
					typename.EnumToString(AICF_EGroupRole, slot.GetRole()), AICF_GroupRuntime.CountAliveAgents(slot.GetGroup()), ride, Math.Round(at[0]),
					Math.Round(at[2]), to);
				// The group's whole waypoint queue (3 Nov, Martin: "in commander lab map when i click unit I should see its way
				// points !!"), for the map's click-a-team view.
				string teamWps;
				// ... and what each is (4 Nov, Martin: "we could have type of waypoint and status maybe like next or whatever like
				// more details when I click on them"): kind/storm level/completion radius m, e.g. move/25/20;search/0/20.
				string teamWpKinds;
				array<AIWaypoint> teamQueue = {};
				slot.GetGroup().GetWaypoints(teamQueue);
				foreach (AIWaypoint qw : teamQueue)
				{
					if (!qw || teamWps.Length() >= 400)
						continue;
					teamWps += string.Format("%1,%2;", Math.Round(qw.GetOrigin()[0]), Math.Round(qw.GetOrigin()[2]));
					string qwKind = "move";
					if (SCR_SearchAndDestroyWaypoint.Cast(qw))
						qwKind = "search";
					else if (SCR_DefendWaypoint.Cast(qw))
						qwKind = "defend";
					else if (SCR_SmartActionWaypoint.Cast(qw))
						qwKind = "action";
					else if (SCR_TimedWaypoint.Cast(qw))
						qwKind = "hold";
					float qwLevel;
					SCR_AIWaypoint qwScripted = SCR_AIWaypoint.Cast(qw);
					if (qwScripted)
						qwLevel = qwScripted.GetPriorityLevel();
					teamWpKinds += string.Format("%1/%2/%3;", qwKind, Math.Round(qwLevel), Math.Round(qw.GetCompletionRadius()));
				}
				if (teamWps.IsEmpty())
					teamWps = "-";
				if (teamWpKinds.IsEmpty())
					teamWpKinds = "-";
				// Each living member (4 Nov, Martin: "map should show individual units maybe no?"): x,z,stance - s stand,
				// c crouch, p prone, v in a vehicle, u unconscious (5 Nov - Martin: "maybe some soldiers are unconscious?") - e.g.
				// mp=2210,2905,p;2214,2901,s; and what each one's AI is doing now (Martin: "i see soviet soldier inside building why
				// dont they push close to point now?"): acts=<behaviour>:<men>,... (its class, SCR_AI / Behavior cut).
				string members;
				map<string, int> acts = new map<string, int>();
				array<AIAgent> memberAgents = {};
				slot.GetGroup().GetAgents(memberAgents);
				foreach (AIAgent memberAgent : memberAgents)
				{
					if (!memberAgent || members.Length() >= 300)
						continue;
					ChimeraCharacter mc = ChimeraCharacter.Cast(memberAgent.GetControlledEntity());
					if (!mc || !AICF_GroupRuntime.IsAliveCharacter(mc))
						continue;
					string stance = "s";
					SCR_AIUtilityComponent memberUtility = ZCR_DroneThreat.UtilityOf(mc);
					if (memberUtility && memberUtility.GetCurrentAction())
					{
						string actName = memberUtility.GetCurrentAction().ClassName();
						actName.Replace("SCR_AI", "");
						actName.Replace("Behavior", "");
						acts.Set(actName, acts.Get(actName) + 1);
					}
					if (mc.GetCharacterController() && mc.GetCharacterController().IsUnconscious())
						stance = "u";
					else if (mc.IsInVehicle())
						stance = "v";
					else if (mc.GetCharacterController())
					{
						ECharacterStance cs = mc.GetCharacterController().GetStance();
						if (cs == ECharacterStance.PRONE)
							stance = "p";
						else if (cs == ECharacterStance.CROUCH)
							stance = "c";
					}
					vector mp = mc.GetOrigin();
					members += string.Format("%1,%2,%3;", Math.Round(mp[0]), Math.Round(mp[2]), stance);
				}
				if (members.IsEmpty())
					members = "-";
				string actText;
				foreach (string actKey, int actMen : acts)
					actText += string.Format("%1:%2,", actKey, actMen);
				if (actText.IsEmpty())
					actText = "-";
				string tail = string.Format(" posture=%1 wp=%2 wps=%3 wplevel=%4 wpk=%5 mp=%6", posture, wp, teamWps, Math.Round(wpLevel), teamWpKinds, members) +
					string.Format(" acts=%1", actText);
				// Print of a plain variable writes "string line = '...'" (28 Oct); a Format call prints the text alone.
				Print(string.Format("%1%2", head, tail), LogLevel.NORMAL);
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
			// The road route still ahead (AICF_RoadGraph's waypoints, then the job's own), for the map's click-a-truck view.
			string wps;
			foreach (AIWaypoint rw : w.m_aRouteWaypoints)
			{
				if (rw)
					wps += string.Format("%1,%2;", Math.Round(rw.GetOrigin()[0]), Math.Round(rw.GetOrigin()[2]));
			}
			if (w.m_Waypoint)
				wps += string.Format("%1,%2", Math.Round(w.m_Waypoint.GetOrigin()[0]), Math.Round(w.m_Waypoint.GetOrigin()[2]));
			if (wps.IsEmpty())
				wps = "-";
			Print(string.Format("[ZCR][LIVE] t=%1 kind=truck side=%2 id=%3 phase=%4 cargo=%5 cap=%6 kmh=%7 x=%8 z=%9", now, side, w.m_iSlot,
				typename.EnumToString(AICF_ELogisticsPhase, w.m_ePhase), Math.Round(cargo), Math.Round(cap), Math.Round(kmh), Math.Round(p[0]), Math.Round(p[2]))
				+ string.Format(" wps=%1 from=%2 to=%3", wps, from, to), LogLevel.NORMAL);
		}
		// AI Conflict's base builders (25 Oct, the base-building sub-lab): what each does, his site and its progress.
		array<AICF_BaseBuilder> builders = {};
		AICF_BaseBuilderService.ZCR_Builders(builders);
		foreach (AICF_BaseBuilder b : builders)
		{
			if (!b.m_Character)
				continue;
			vector bp = b.m_Character.GetOrigin();
			string bside = "?";
			if (b.m_Faction)
				bside = b.m_Faction.GetFactionKey();
			string bbase = "-";
			if (b.m_Base)
				bbase = Name(ZCR_Strategist.BaseName(b.m_Base));
			string progress = ZCR_BuildTest.Progress(b);
			if (progress.IsEmpty())
				progress = "-";
			vector site = b.m_vWorkPosition;
			if (!b.m_Target)
				site = bp;
			Print(string.Format("[ZCR][LIVE] t=%1 kind=builder side=%2 id=%3 doing=%4 progress=%5 x=%6 z=%7 sx=%8 sz=%9", now, bside, b.m_iSlotId,
				ZCR_BuildTest.Doing(b), progress, Math.Round(bp[0]), Math.Round(bp[2]), Math.Round(site[0]), Math.Round(site[2]))
				+ string.Format(" what=%1 base=%2", Name(ZCR_BuildTest.What(b)), bbase), LogLevel.NORMAL);
		}
		ZCR_DriveTest.LiveLines(now);
	}
}
