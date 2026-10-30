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
		ZCR_OnePoint.Filter(m_Faction, candidates);   // -zcrOnePoint: the point and the own main base only
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
	// team may go for, every other base is off its list. Its own bases too (the assault test, 28 Oct: the holding US side
	// raided Military Training Area anyway, and every Soviet attack team left the assault on Signal Hill to guard it, came
	// back, and left again to retake it) - the DEFEND teams guard. And a base the plan avoids (priority below 0) is off
	// every team's list while the team has something else to do.
	protected void Bind(AICF_GroupSlot slot, ZCR_StrategicPlan plan, array<ref AICF_AdaptiveCandidate> candidates)
	{
		if (!System.IsCLIParam("zcrBindMainEffort") || !slot)
			return;
		int left;
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && c.m_bAvailable && plan.GetPriority(c.m_iNodeId) >= 0)
				left++;
		}
		if (left > 0)
		{
			foreach (AICF_AdaptiveCandidate c : candidates)
			{
				if (c && c.m_bAttack && plan.GetPriority(c.m_iNodeId) < 0)
					c.m_bAvailable = false;
			}
		}
		if (slot.GetRole() != AICF_EGroupRole.ATTACK)
			return;
		int main = plan.GetMainEffort();
		if (main < 0)
			return;
		// The main effort taken: the attack teams hold it (28 Oct: with the objective captured the plan had nothing more, and
		// every attack team was sent home to guard the main base - its riders drove back 1.5 km). 30 Oct: AI Conflict leaves a
		// held base off an attack team's list (m_bZcrHeld) - put back here, or the rule never fired (both watched Farm battles:
		// 7 US attack teams sent back to the harbour HQ right after taking Farm).
		bool reachable;
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && c.m_iNodeId == main && c.m_bZcrHeld && !c.m_bAvailable)
			{
				c.m_bAvailable = true;
				c.m_bZcrHeld = false;
			}
			if (c && c.m_iNodeId == main && c.m_bAvailable)
				reachable = true;
		}
		if (!reachable)
			return;
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && c.m_iNodeId != main)
				c.m_bAvailable = false;
		}
	}
}
