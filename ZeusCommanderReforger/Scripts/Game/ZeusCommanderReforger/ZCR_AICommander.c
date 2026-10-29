// Runs our strategist on AI Conflict's commander tick, before AI Conflict assigns its squads;
// commits or releases DEFEND squads (ZCR_Commit.c) and storms a base (ZCR_Storm.c) as the plan says.
modded class AICF_AICommander
{
	override bool Tick(AICF_MatchController matchController, string reason)
	{
		ZCR_CostScope cost = new ZCR_CostScope("commander");
		if (Replication.IsServer() && IsEnabled() && m_Faction)
		{
			ZCR_Trace.Begin(m_sFactionKey);   // [ZCR][STEP] / [ZCR][SLOW] (crash hunting)
			ZCR_Setup.NoFIA();          // -zcrNoFIA: only the two armies (once, at the first tick)
			ZCR_FortList.Tick();        // -zcrListFortifications (lab: what the builders could put up)
			ZCR_SpotProbe.Tick();       // -zcrProbeSpots x,z;x,z (lab: what is at a map spot)
			ZCR_SpotProbe.Roads();      // -zcrProbeRoads (lab: each base's nearest road)
			ZCR_Trace.Step("efforts");
			ZCR_Efforts.Tick(); // [ZCR][EFFORTS] each side's efforts every 30 s (the lab app's Live tab)
			ZCR_SpotProbe.SupplyProbe(); // -zcrSupplyProbe (lab: what refills the front bases)
			ZCR_SpotProbe.DepotProbe(); // -zcrDepotProbe (lab: which vehicle depots exist)
			ZCR_SpotProbe.DryPathProbe(); // -zcrDryPathProbe (lab: drones' way over land)
			ZCR_Trace.Step("setup");
			ZCR_Setup.StartSupplies();  // starting stock so the builders can afford defenses
			ZCR_Setup.Income();         // lab supply income (-zcrSupplyIncome)
			if (m_FactionState)
				ZCR_Strategist.s_mStates.Set(m_sFactionKey, m_FactionState);
			ZCR_Trace.Step("strategist");
			ZCR_Strategist.Get(m_sFactionKey).Tick(m_FactionState, m_Faction, m_ObjectiveGraph, m_TargetSelector);
			ZCR_Trace.Step("loops");
			ZCR_Sampler.Start();
			ZCR_Tactical.Get().Tend(m_sFactionKey, m_FactionState);   // the tactical layer's squad detail (ZCR_DCO)
			ZCR_DroneThreat.Start();     // soldiers react to enemy drones (both sides)
			ZCR_Danger.Start();       // danger awareness: no standing in danger (-zcrNoDanger)
			ZCR_AntiDrone.Start();    // small-arms fire at enemy drones (-zcrNoAntiDrone)
			ZCR_Driving.Start();      // AI drivers' cruise speed (-zcrCruiseSpeed, km/h) and [ZCR][DRIVE]
			ZCR_Logistics.Log();      // [ZCR][SUPPLY] each base's stock and storage, every minute
			ZCR_WorkCrew.Start();     // idle soldiers near a building site join the builder (-zcrNoWorkCrew)
			ZCR_Trace.Step("feed");
			ZCR_Feed.Now(m_sFactionKey, m_FactionState);
			ZCR_Trace.Step("drones");
			ZCR_Drones.Tend(m_sFactionKey);
			ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(m_sFactionKey);
			// Drone sites: the front is the plan's main effort, or AI Conflict's main target.
			vector front = ZCR_Feed.s_mMainTargetPos.Get(m_sFactionKey);
			if (!plan.IsEmpty() && plan.GetMainEffort() >= 0 && ZCR_Strategist.s_mNodePos.Contains(plan.GetMainEffort()))
				front = ZCR_Strategist.s_mNodePos.Get(plan.GetMainEffort());
			ZCR_Trace.Step("drone_sites");
			// The drone sites follow where the drones fly - the plan's drone target - not the main effort: while the force
			// gathers (phased) or shapes and pulls back (modern) the main effort is the staging base, and a side got its
			// forward crew only once the objective changed (26 Oct night, modern match 2: the US at minute 27).
			vector droneFront = front;
			array<int> droneTargets = plan.GetDroneTargets();
			if (!plan.IsEmpty() && droneTargets && !droneTargets.IsEmpty() && ZCR_Strategist.s_mNodePos.Contains(droneTargets[0]))
				droneFront = ZCR_Strategist.s_mNodePos.Get(droneTargets[0]);
			ZCR_DroneSites.Tick(m_sFactionKey, droneFront);
			ZCR_Trace.Step("armour");
			ZCR_Armour.Tick(m_sFactionKey, m_Faction, front);   // crewed tanks/IFVs to the front (-zcrNoArmour)
			ZCR_Trace.Step("commit");
			if (matchController)
			{
				matchController.ZCR_CommitDefenders(m_Faction, m_FactionState, plan.GetCommit(), ZCR_UnderCapture());
				// Only a side whose strategist has spoken: AI Conflict alone keeps its own squads.
				if (!plan.IsEmpty())
					matchController.ZCR_Motorize(m_Faction, m_FactionState, plan.GetMotorize());
			}
			ZCR_Trace.Step("storm");
			ZCR_ApplyStorm(plan.GetStorm());
			// The soldier layer (cover in a firefight) for the side with our strategist.
			ZCR_Trace.Step("cover");
			if (!plan.IsEmpty())
				ZCR_CoverLayer.Tick(m_sFactionKey, m_FactionState);
			// A side on AI Conflict alone uses drones too (a baseline; ZCR_Drones).
			if (plan.IsEmpty())
				ZCR_Drones.Baseline(m_sFactionKey, m_FactionState, m_ObjectiveGraph);
			ZCR_Trace.Step("aicf");
		}
		bool result = super.Tick(matchController, reason);
		ZCR_Trace.Step("idle");
		return result;
	}

	// One of our bases is being captured: every squad's place is AI Conflict's to decide again.
	protected bool ZCR_UnderCapture()
	{
		if (!m_ObjectiveGraph)
			return false;
		for (int i = 0; i < m_ObjectiveGraph.GetNodeCount(); i++)
		{
			AICF_ObjectiveNode node = m_ObjectiveGraph.GetNode(i);
			if (!node || !node.GetBase())
				continue;
			SCR_CampaignMilitaryBaseComponent base = node.GetBase();
			if (base.GetFaction() == m_Faction && base.IsBeingCaptured())
				return true;
		}
		return false;
	}

	// The plan's storm target (a graph node, -1 for none): when it changes, the squads already sent
	// there get new orders, whose waypoints carry the storm priority.
	protected void ZCR_ApplyStorm(int nodeId)
	{
		SCR_CampaignMilitaryBaseComponent base;
		if (nodeId >= 0 && m_ObjectiveGraph && nodeId < m_ObjectiveGraph.GetNodeCount())
		{
			AICF_ObjectiveNode node = m_ObjectiveGraph.GetNode(nodeId);
			if (node)
				base = node.GetBase();
		}
		if (base && base.GetFaction() == m_Faction)
			base = null;
		if (!ZCR_Storm.Set(m_sFactionKey, base))
			return;
		ZCR_Tactical.EndStorm(m_sFactionKey);   // the previous storm's squads fight normally again
		if (!base)
		{
			Print(string.Format("[ZCR][STORM] t=%1 faction=%2 end", ZCR_LossLog.Seconds(), m_sFactionKey), LogLevel.NORMAL);
			return;
		}
		int squads;
		int men;
		for (int i = 0; i < m_FactionState.GetSlotCount(); i++)
		{
			AICF_GroupSlot slot = m_FactionState.GetSlot(i);
			if (!slot || slot.GetRole() != AICF_EGroupRole.ATTACK || slot.GetTargetBase() != base || !slot.IsCombatReady())
				continue;
			if (m_OrderPlanner && m_OrderPlanner.RebuildCurrentOrder(slot, m_Faction, "ZCR_STORM"))
			{
				// The tactical layer: the squad pushes in (with DCO: its contact drills and overmatch off - ZCR_DCO).
				ZCR_Tactical.Storming(slot.GetGroup(), true, m_sFactionKey);
				squads++;
				men += AICF_GroupRuntime.CountAliveAgents(slot.GetGroup());
			}
		}
		Print(string.Format("[ZCR][STORM] t=%1 faction=%2 base=%3 squads=%4 men=%5 priority=%6 normal=%7",
			ZCR_LossLog.Seconds(), m_sFactionKey, ZCR_Strategist.BaseName(base), squads, men, ZCR_Storm.Priority(),
			SCR_AIActionBase.PRIORITY_LEVEL_NORMAL), LogLevel.NORMAL);
		ZCR_Feed.Note(m_sFactionKey, string.Format("STORM on %1: %2 squads, %3 soldiers go in", ZCR_Strategist.BaseName(base), squads, men));
		ZCR_Storm.Event(string.Format("%1 STORMS %2 - %3 squads, %4 soldiers go in without stopping to fight at range",
			m_sFactionKey, ZCR_Strategist.BaseName(base), squads, men), base.GetOwner().GetOrigin());
	}
}
