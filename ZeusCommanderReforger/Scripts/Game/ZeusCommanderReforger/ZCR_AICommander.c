// Runs our strategist on AI Conflict's commander tick, before AI Conflict assigns its squads, and
// commits or releases DEFEND squads as the plan says (ZCR_Commit.c).
modded class AICF_AICommander
{
	override bool Tick(AICF_MatchController matchController, string reason)
	{
		if (Replication.IsServer() && IsEnabled() && m_Faction)
		{
			ZCR_Strategist.Get(m_sFactionKey).Tick(m_FactionState, m_Faction, m_ObjectiveGraph, m_TargetSelector);
			if (matchController)
				matchController.ZCR_CommitDefenders(m_Faction, m_FactionState, ZCR_StrategicPlan.Get(m_sFactionKey).GetCommit(), ZCR_UnderCapture());
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
}
