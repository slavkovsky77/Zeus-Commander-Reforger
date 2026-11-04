// Farm's houses first (4 Nov, note 536 - Martin, watching farm-brains: "I would expect at farm ai to hide and clear house as
// priority as it is withing capture ratio right? and it provides defense?", "they use it to be honest but not as quickly").
// The one-point battle's point (-zcrOnePoint): the houses inside its capture core (ZCR_PointSeize.POINT_M) are searched once
// for interior spots on the navmesh (a low roof and walls on 5 of 8 sides - ZCR_DroneThreat.IsInside), 3 m apart. Every 3 s
// a man on foot within the core who is not inside a house gets the nearest free spot and runs there (at the drone shelter
// run's priority, so the squad's own moves don't stop him), and is sent back - every 8 s at most - when the squad pulls him
// out; the spot is his while he lives and stays near the point. Both sides: the attackers take the houses on the way in,
// the holders fight from them (the capture counts every man within the core, inside or not).
// [ZCR][HOUSE] every 30 s: spots, men in the core and inside a house per side, runs. -zcrNoFarmHouses turns it off.
// 4 Nov night: they didn't stay - in the town battles only 14-34% of the men at the point were inside, with 704 runs in one
// battle (the move ends on arrival and the squad takes them out again). Now the run is a move-and-hold (the game's
// move-and-investigate behaviour: to the spot, then HOLD_S there within 2 m), renewed every RENEW_S while the man is at his
// spot - at the point only; the stops on the way keep the plain move. -zcrHouseHoldStay 0: the plain move as before.
class ZCR_HouseHold
{
	static const float SPOT_STEP = 3;
	static const int AGAIN_S = 8;
	static const float HOLD_S = 40;
	static const int RENEW_S = 30;
	protected ref map<IEntity, int> m_mHoldUntil = new map<IEntity, int>();
	protected int m_iRenews;
	protected static bool s_bStarted;
	protected static ref ZCR_HouseHold s_Instance;
	protected ref array<vector> m_aSpots;
	protected ref map<IEntity, int> m_mSpotOf = new map<IEntity, int>();
	protected ref map<int, IEntity> m_mManAt = new map<int, IEntity>();
	protected ref map<IEntity, int> m_mNextAt = new map<IEntity, int>();
	protected int m_iRuns;
	protected int m_iLogAt;
	// Stops on the way (4 Nov, note 540 - Martin: "those waypoints dont have type like ... clear building, enter building"):
	// an attack team on a defend leg outside the core (a live route's 'e' point, the hold line) with houses within STOP_M
	// of it - its men go inside them, a spot each. Spots per stop point (10-m key), searched once.
	static const float STOP_M = 25;
	protected ref map<string, ref array<vector>> m_mStopSpots = new map<string, ref array<vector>>();
	protected int m_iStopRuns;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || ZCR_OnePoint.Name().IsEmpty() || System.IsCLIParam("zcrNoFarmHouses"))
			return;
		s_bStarted = true;
		s_Instance = new ZCR_HouseHold();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 3000, true);
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("household");
		SCR_CampaignMilitaryBaseComponent base = ZCR_OnePoint.Base();
		if (!base || !base.GetOwner())
			return;
		vector at = base.GetOwner().GetOrigin();
		float radius = ZCR_PointSeize.POINT_M;
		if (base.GetRadius() > 0)
			radius = Math.Min(radius, base.GetRadius());
		int now = ZCR_LossLog.Seconds();
		// Spots of the dead and of those gone off the point are free again.
		array<IEntity> gone = {};
		foreach (IEntity held, int heldSpot : m_mSpotOf)
		{
			if (!held || !Alive(held) || vector.DistanceXZ(held.GetOrigin(), at) > radius + 30)
				gone.Insert(held);
		}
		foreach (IEntity leaver : gone)
		{
			int freed = m_mSpotOf.Get(leaver);
			m_mSpotOf.Remove(leaver);
			m_mManAt.Remove(freed);
			m_mNextAt.Remove(leaver);
			m_mHoldUntil.Remove(leaver);
		}
		map<string, int> inCore = new map<string, int>();
		map<string, int> inHouse = new map<string, int>();
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		foreach (AIAgent agent : agents)
		{
			if (!agent)
				continue;
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (!c || !Alive(c) || c.IsInVehicle() || vector.DistanceXZ(c.GetOrigin(), at) > radius)
				continue;
			string side = ZCR_LossLog.SideOf(c);
			if (side != "US" && side != "USSR")
				continue;
			inCore.Set(side, inCore.Get(side) + 1);
			if (!m_aSpots)
				FindSpots(c, at, radius);
			int mine = -1;
			bool has = m_mSpotOf.Find(c, mine);
			if ((has && vector.Distance(c.GetOrigin(), m_aSpots[mine]) <= 2.5) || (!has && ZCR_DroneThreat.IsInside(c.GetOrigin(), c)))
			{
				inHouse.Set(side, inHouse.Get(side) + 1);
				// At his spot: the hold renewed before it runs out.
				if (has && Stay() && now >= m_mHoldUntil.Get(c))
				{
					SCR_AIUtilityComponent holder = ZCR_DroneThreat.UtilityOf(c);
					if (holder)
					{
						ZCR_Reserved.Add(holder, Run(holder, m_aSpots[mine]));
						m_mHoldUntil.Set(c, now + RENEW_S);
						m_iRenews++;
					}
				}
				continue;
			}
			if (now < m_mNextAt.Get(c))
				continue;
			if (!has)
			{
				mine = NearestFree(c.GetOrigin());
				if (mine < 0)
					continue;
				m_mSpotOf.Set(c, mine);
				m_mManAt.Set(mine, c);
			}
			SCR_AIUtilityComponent utility = ZCR_DroneThreat.UtilityOf(c);
			if (!utility)
				continue;
			ZCR_Reserved.Add(utility, Run(utility, m_aSpots[mine]));
			m_mNextAt.Set(c, now + AGAIN_S);
			m_mHoldUntil.Set(c, now + RENEW_S);
			m_iRuns++;
		}
		Stops(at, radius, now);
		if (now < m_iLogAt || (inCore.Get("US") + inCore.Get("USSR")) == 0)
			return;
		m_iLogAt = now + 30;
		int spots;
		if (m_aSpots)
			spots = m_aSpots.Count();
		Print(string.Format("[ZCR][HOUSE] t=%1 spots=%2 taken=%3 us_core=%4 us_inside=%5 ussr_core=%6 ussr_inside=%7 runs=%8", now, spots,
			m_mManAt.Count(), inCore.Get("US"), inHouse.Get("US"), inCore.Get("USSR"), inHouse.Get("USSR"), m_iRuns) + string.Format(" stop_runs=%1 renews=%2", m_iStopRuns, m_iRenews), LogLevel.NORMAL);
	}

	// Interior spots of the houses within the core, on the navmesh (found with this man's pathfinding), SPOT_STEP apart.
	protected void FindSpots(ChimeraCharacter c, vector at, float radius)
	{
		m_aSpots = SearchSpots(c, at, radius);
		Print(string.Format("[ZCR][HOUSE] t=%1 event=spots found=%2 radius_m=%3", ZCR_LossLog.Seconds(), m_aSpots.Count(), Math.Round(radius)), LogLevel.NORMAL);
	}

	// A team stopped on its way near houses: its men inside them (see STOP_M).
	protected void Stops(vector core, float coreRadius, int now)
	{
		foreach (FactionKey faction, AICF_FactionState state : ZCR_Strategist.s_mStates)
		{
			for (int s; state && s < state.GetSlotCount(); s++)
			{
				AICF_GroupSlot slot = state.GetSlot(s);
				if (!slot || !slot.GetGroup() || slot.GetRole() != AICF_EGroupRole.ATTACK)
					continue;
				SCR_DefendWaypoint stop = SCR_DefendWaypoint.Cast(slot.GetGroup().GetCurrentWaypoint());
				if (!stop)
					continue;
				vector sp = stop.GetOrigin();
				if (vector.DistanceXZ(sp, core) <= coreRadius + 20)
					continue;
				array<AIAgent> members = {};
				slot.GetGroup().GetAgents(members);
				int k;
				foreach (AIAgent member : members)
				{
					ChimeraCharacter mc;
					if (member)
						mc = ChimeraCharacter.Cast(member.GetControlledEntity());
					if (!mc || !Alive(mc) || mc.IsInVehicle() || vector.DistanceXZ(mc.GetOrigin(), sp) > 60)
						continue;
					string key = string.Format("%1_%2", Math.Round(sp[0] / 10), Math.Round(sp[2] / 10));
					array<vector> spots;
					if (!m_mStopSpots.Find(key, spots))
					{
						spots = SearchSpots(mc, sp, STOP_M);
						m_mStopSpots.Set(key, spots);
					}
					if (spots.IsEmpty())
						break;
					vector mine = spots[k % spots.Count()];
					k++;
					if (vector.Distance(mc.GetOrigin(), mine) <= 2.5 || now < m_mNextAt.Get(mc))
						continue;
					SCR_AIUtilityComponent utility = ZCR_DroneThreat.UtilityOf(mc);
					if (!utility)
						continue;
					// A stop on the way: the plain move, no hold (4 Nov night - a 40-s hold kept men in the houses after their team
					// moved on; the first night battle had nobody in Beauregard in 30 minutes).
					ZCR_Reserved.Add(utility, new SCR_AIMoveIndividuallyBehavior(utility, null, mine,
						SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_FROM_DANGER + 2, SCR_AIActionBase.PRIORITY_LEVEL_NORMAL, null, 1.0));
					m_mNextAt.Set(mc, now + AGAIN_S);
					m_iStopRuns++;
				}
			}
		}
	}

	// Interior spots of the houses within 'radius' of 'at', on the navmesh (with this man's pathfinding), SPOT_STEP apart.
	protected array<vector> SearchSpots(ChimeraCharacter c, vector at, float radius)
	{
		array<vector> found = {};
		AIControlComponent control = AIControlComponent.Cast(c.FindComponent(AIControlComponent));
		AIPathfindingComponent pathfinding;
		if (control && control.GetControlAIAgent())
			pathfinding = AIPathfindingComponent.Cast(control.GetControlAIAgent().FindComponent(AIPathfindingComponent));
		BaseWorld world = GetGame().GetWorld();
		for (float gx = -radius; gx <= radius; gx += SPOT_STEP)
		{
			for (float gz = -radius; gz <= radius; gz += SPOT_STEP)
			{
				vector p = at + Vector(gx, 0, gz);
				if (vector.DistanceXZ(p, at) > radius)
					continue;
				p[1] = world.GetSurfaceY(p[0], p[2]);
				if (!ZCR_DroneThreat.IsInside(p, c))
					continue;
				vector nav = p;
				if (pathfinding && (!pathfinding.GetClosestPositionOnNavmesh(p, "2 3 2", nav) || vector.DistanceXZ(nav, p) > 2))
					continue;
				if (!ZCR_DroneThreat.IsInside(nav + Vector(0, 0.2, 0), c))
					continue;
				bool near;
				foreach (vector q : found)
				{
					if (vector.DistanceXZ(q, nav) < SPOT_STEP - 0.5)
						near = true;
				}
				if (!near)
					found.Insert(nav);
			}
		}
		return found;
	}

	protected int NearestFree(vector from)
	{
		int best = -1;
		float bestM = 1e9;
		for (int k; k < m_aSpots.Count(); k++)
		{
			if (m_mManAt.Contains(k))
				continue;
			float d = vector.DistanceXZ(from, m_aSpots[k]);
			if (d < bestM)
			{
				bestM = d;
				best = k;
			}
		}
		return best;
	}

	protected static bool Stay()
	{
		string value;
		return !(System.GetCLIParam("zcrHouseHoldStay", value) && value == "0");
	}

	// The run to a spot: to it and a hold there (HOLD_S within 2 m), or the plain move (-zcrHouseHoldStay 0).
	protected static SCR_AIActionBase Run(SCR_AIUtilityComponent utility, vector spot)
	{
		float priority = SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_FROM_DANGER + 2;
		if (!Stay())
			return new SCR_AIMoveIndividuallyBehavior(utility, null, spot, priority, SCR_AIActionBase.PRIORITY_LEVEL_NORMAL, null, 1.0);
		return new SCR_AIMoveAndInvestigateBehavior(utility, null, spot, priority, SCR_AIActionBase.PRIORITY_LEVEL_NORMAL, 2.0, true,
			EAIUnitType.UnitType_Infantry, HOLD_S);
	}

	protected static bool Alive(IEntity e)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(e);
		return c && c.GetCharacterController() && !c.GetCharacterController().IsDead();
	}
}
