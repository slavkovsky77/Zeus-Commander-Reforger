// Runs our strategist on AI Conflict's commander tick, before AI Conflict assigns its squads;
// commits or releases DEFEND squads (ZCR_Commit.c) and storms a base (ZCR_Storm.c) as the plan says.
modded class AICF_AICommander
{
	override bool Tick(AICF_MatchController matchController, string reason)
	{
		if (Replication.IsServer() && IsEnabled() && m_Faction)
		{
			ZCR_Strategist.Get(m_sFactionKey).Tick(m_FactionState, m_Faction, m_ObjectiveGraph, m_TargetSelector);
			ZCR_Sampler.Start();
			ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(m_sFactionKey);
			if (matchController)
			{
				matchController.ZCR_CommitDefenders(m_Faction, m_FactionState, plan.GetCommit(), ZCR_UnderCapture());
				// Only a side whose strategist has spoken: AI Conflict alone keeps its own squads.
				if (!plan.IsEmpty())
					matchController.ZCR_Motorize(m_Faction, m_FactionState, plan.GetMotorize());
			}
			ZCR_ApplyStorm(plan.GetStorm());
			// The soldier layer (cover in a firefight) for the side with our strategist.
			if (!plan.IsEmpty())
				ZCR_CoverLayer.Tick(m_sFactionKey, m_FactionState);
			// A side on AI Conflict alone uses drones too (a baseline; ZCR_Drones).
			if (plan.IsEmpty())
				ZCR_Drones.Baseline(m_sFactionKey, m_FactionState, m_ObjectiveGraph);
		}
		return super.Tick(matchController, reason);
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
				squads++;
				men += AICF_GroupRuntime.CountAliveAgents(slot.GetGroup());
			}
		}
		Print(string.Format("[ZCR][STORM] t=%1 faction=%2 base=%3 squads=%4 men=%5 priority=%6 normal=%7",
			ZCR_LossLog.Seconds(), m_sFactionKey, ZCR_Strategist.BaseName(base), squads, men, ZCR_Storm.Priority(),
			SCR_AIActionBase.PRIORITY_LEVEL_NORMAL), LogLevel.NORMAL);
		ZCR_Director.Note(string.Format("%1 STORMS %2 with %3 soldiers", m_sFactionKey, ZCR_Strategist.BaseName(base), men));
		ZCR_Storm.Event(string.Format("%1 STORMS %2 - %3 squads, %4 soldiers go in without stopping to fight at range",
			m_sFactionKey, ZCR_Strategist.BaseName(base), squads, men), base.GetOwner().GetOrigin());
	}
}
