// The seam into AI Conflict's commander: after it builds the candidate bases for a squad, our
// side's plan (ZCR_StrategicPlan) raises or lowers each base's score and its demand. AI Conflict
// then scores and assigns as usual, with all its own checks (route, readiness, threat, player
// orders). With an empty plan nothing changes.
modded class AICF_AdaptiveCommanderPolicy
{
	override protected void BuildCandidates(AICF_GroupSlot slot, int now, array<ref AICF_AdaptiveCandidate> candidates)
	{
		super.BuildCandidates(slot, now, candidates);
		if (!m_Faction || !candidates)
			return;
		ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(m_Faction.GetFactionKey());
		if (!plan || plan.IsEmpty())
			return;
		foreach (AICF_AdaptiveCandidate candidate : candidates)
		{
			if (!candidate)
				continue;
			candidate.m_fFrontValue += plan.GetPriority(candidate.m_iNodeId);
			candidate.m_fDemand = Math.Max(candidate.m_fDemand, plan.GetDemand(candidate.m_iNodeId));
		}
	}
}
