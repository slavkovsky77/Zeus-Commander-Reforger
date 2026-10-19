// Runs our strategist on AI Conflict's commander tick, before AI Conflict assigns its squads.
modded class AICF_AICommander
{
	override bool Tick(AICF_MatchController matchController, string reason)
	{
		if (Replication.IsServer() && IsEnabled() && m_Faction)
			ZCR_Strategist.Get(m_sFactionKey).Tick(m_FactionState, m_Faction, m_ObjectiveGraph, m_TargetSelector);
		return super.Tick(matchController, reason);
	}
}
