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
		Bind(slot, plan, candidates);
	}

	// -zcrBindMainEffort (the assault sub-lab, 28 Oct; review note 433): the plan's main effort binds the attack teams. The
	// bonus alone (+80) lost to AI Conflict's own scores - of 12 Soviet attack teams in an assault on Military Training
	// Area, 5 were sent to Farm and Signal Hill instead. With the switch, while the main effort is an enemy base an attack
	// team may go for, every other enemy base is off its list (its own bases stay: a threatened base still calls).
	protected void Bind(AICF_GroupSlot slot, ZCR_StrategicPlan plan, array<ref AICF_AdaptiveCandidate> candidates)
	{
		if (!System.IsCLIParam("zcrBindMainEffort") || !slot || slot.GetRole() != AICF_EGroupRole.ATTACK)
			return;
		int main = plan.GetMainEffort();
		if (main < 0)
			return;
		bool reachable;
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && c.m_iNodeId == main && c.m_bAvailable && c.m_bAttack)
				reachable = true;
		}
		if (!reachable)
			return;
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && c.m_bAttack && c.m_iNodeId != main)
				c.m_bAvailable = false;
		}
	}
}
