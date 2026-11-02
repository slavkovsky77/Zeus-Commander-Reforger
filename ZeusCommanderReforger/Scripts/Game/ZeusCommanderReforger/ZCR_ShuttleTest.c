// The transport integration test (31 Oct, Martin: "points is now to optimize manpower reinforcement supplies, catch problems
// ... i noticed soldier are not being transported properly"; review note 474). -zcrShuttleTest, with -zcrAllBasesTo US and
// -aicfNoForces USSR: one side holds the whole map and nobody fights. Each of its teams is sent to one of its bases, and on
// arrival to the next - teams cross the map again and again the way AI Conflict moves them (a ride or on foot), and every
// trip is logged for lab/transporttest.py:
//   [ZCR][SHUTTLE] t=.. side=US slot=N event=assign trip=K base=Name dist=M from=x,z
//   [ZCR][SHUTTLE] t=.. side=US slot=N event=arrive trip=K base=Name dist=M trip_s=S rode=0|1 men=K
// The next base: the slot's own walk through the side's bases (spread over the teams), skipping one closer than 400 m.
class ZCR_ShuttleTest
{
	static const float ARRIVE_M = 120;
	static const float MIN_TRIP_M = 400;
	protected static ref map<int, int> s_mTarget = new map<int, int>();       // slot -> graph node
	protected static ref map<int, int> s_mSince = new map<int, int>();        // slot -> when the trip began
	protected static ref map<int, vector> s_mFrom = new map<int, vector>();   // slot -> where it began
	protected static ref map<int, bool> s_mRode = new map<int, bool>();       // slot -> seen in a vehicle on this trip
	protected static ref map<int, int> s_mTrips = new map<int, int>();        // slot -> trips assigned
	protected static ref map<int, int> s_mNoneAt = new map<int, int>();       // slot -> when "no trip" was last logged

	static bool On()
	{
		return System.IsCLIParam("zcrShuttleTest");
	}

	// Called last in the commander's candidate list for a team (ZCR_AdaptiveCommanderPolicy): only the team's base of the
	// moment stays on (switched on even when AI Conflict keeps a quiet friendly base off an attack team's list).
	static void Filter(SCR_CampaignFaction faction, AICF_GroupSlot slot, array<ref AICF_AdaptiveCandidate> candidates)
	{
		if (!On() || !faction || !slot || !candidates || candidates.IsEmpty() || !slot.GetGroup())
			return;
		IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(slot.GetGroup());
		if (!leader)
			return;
		string side = faction.GetFactionKey();
		vector at = leader.GetOrigin();
		int id = slot.GetSlotId();
		int now = ZCR_LossLog.Seconds();
		ChimeraCharacter lc = ChimeraCharacter.Cast(leader);
		if (lc && lc.IsInVehicle())
			s_mRode.Set(id, true);
		int target = -1;
		if (!s_mTarget.Find(id, target))
			target = -1;
		AICF_AdaptiveCandidate current;
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && c.m_iNodeId == target)
				current = c;
		}
		bool there = current && vector.DistanceXZ(at, current.m_vPosition) <= ARRIVE_M;
		// A defend team holds a forward spot short of the base (FORWARD_DEFEND) and waited there for minutes, never counted
		// (31 Oct, note 480: 12% of a defend team's time, up to 7 min a stop): standing at its own order's spot, when that
		// spot is within 400 m of the base, is arriving.
		// 2 Nov (note 508): in Martin's watched Soviet run team D1 stood 72 game minutes at its forward-defend spot - the spot
		// 420 m from Airport Base, the team stopped 80 m short of it - never counted, never given its next trip: a third of
		// the run's late standing. Now the order's spot within 600 m of the base and the team within 100 m of it.
		AIWaypoint order = slot.GetWaypoint();
		if (current && !there && order && !(lc && lc.IsInVehicle()) &&
			vector.DistanceXZ(order.GetOrigin(), current.m_vPosition) <= 600 && vector.DistanceXZ(at, order.GetOrigin()) <= 100)
			there = true;
		if (there)
		{
			vector from = s_mFrom.Get(id);
			int rode;
			if (s_mRode.Get(id))
				rode = 1;
			Print(string.Format("[ZCR][SHUTTLE] t=%1 side=%2 slot=%3 event=arrive trip=%4 base=%5 dist=%6 trip_s=%7 rode=%8 men=%9",
				now, side, id, s_mTrips.Get(id), ZCR_LiveMap.Name(ZCR_Strategist.BaseName(current.m_Base)),
				Math.Round(vector.DistanceXZ(from, current.m_vPosition)), now - s_mSince.Get(id), rode,
				AICF_GroupRuntime.CountAliveAgents(slot.GetGroup())), LogLevel.NORMAL);
			current = null;
			s_mTarget.Set(id, -1);   // logged once, even if no next base is found this time
		}
		if (!current)
		{
			current = Next(faction, id, at, candidates);
			if (!current)
			{
				// Why no trip (once a minute a team): what the commander's list held.
				int said;
				if (!s_mNoneAt.Find(id, said) || now - said >= 60)
				{
					s_mNoneAt.Set(id, now);
					string seen;
					foreach (AICF_AdaptiveCandidate c : candidates)
					{
						if (c)
						{
							string owner = "-";
							if (c.m_Base && c.m_Base.GetFaction())
								owner = c.m_Base.GetFaction().GetFactionKey();
							seen += string.Format(" %1:%2:%3:%4:att%5:av%6:held%7", c.m_iNodeId, ZCR_LiveMap.Name(ZCR_Strategist.BaseName(c.m_Base)),
								Math.Round(vector.DistanceXZ(at, c.m_vPosition)), owner, c.m_bAttack, c.m_bAvailable, c.m_bZcrHeld);
						}
					}
					Print(string.Format("[ZCR][SHUTTLE] t=%1 side=%2 slot=%3 event=none candidates=%4%5", now, side, id, candidates.Count(), seen), LogLevel.NORMAL);
				}
				return;
			}
			int trips = s_mTrips.Get(id) + 1;
			s_mTrips.Set(id, trips);
			s_mTarget.Set(id, current.m_iNodeId);
			s_mSince.Set(id, now);
			s_mFrom.Set(id, at);
			s_mRode.Set(id, false);
			Print(string.Format("[ZCR][SHUTTLE] t=%1 side=%2 slot=%3 event=assign trip=%4 base=%5 dist=%6 from=%7,%8",
				now, side, id, trips, ZCR_LiveMap.Name(ZCR_Strategist.BaseName(current.m_Base)),
				Math.Round(vector.DistanceXZ(at, current.m_vPosition)), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
		}
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (!c)
				continue;
			c.m_bAvailable = c == current;
			if (c == current)
				c.m_bZcrHeld = false;
		}
	}

	// The slot's next base: its own walk through the side's bases (by graph node), 400 m or more from where it stands.
	protected static AICF_AdaptiveCandidate Next(SCR_CampaignFaction faction, int id, vector at, array<ref AICF_AdaptiveCandidate> candidates)
	{
		array<int> nodes = {};
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && c.m_Base && c.m_Base.GetFaction() == faction && !nodes.Contains(c.m_iNodeId))
				nodes.Insert(c.m_iNodeId);
		}
		if (nodes.IsEmpty())
			return null;
		nodes.Sort();
		int start = id * 3 + s_mTrips.Get(id);
		for (int k; k < nodes.Count(); k++)
		{
			int node = nodes[(start + k) % nodes.Count()];
			foreach (AICF_AdaptiveCandidate c : candidates)
			{
				if (c && c.m_iNodeId == node && vector.DistanceXZ(at, c.m_vPosition) >= MIN_TRIP_M)
					return c;
			}
		}
		return null;
	}
}
