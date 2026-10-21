// Soldiers AI Conflict is using for a job of its own - supply truck drivers and base builders - get no
// orders from our soldier layers (cover, drone reaction, dispersal, anti-drone fire, bounding, work crews).
// 21 Oct: 99 of 128 of the game's own gate-opening chains for supply trucks were lost ("native chain lost")
// - the driver, standing at the gate, was sent to cover or picked to shoot at a drone (Martin: "improve
// the driving"). Every layer adds its actions through Add().
class ZCR_Reserved
{
	static bool Is(IEntity soldier)
	{
		return soldier && (AICF_LogisticsDepotRegistry.AICF_IsTruckCrew(soldier) || AICF_BaseBuilderService.AICF_IsBuilder(soldier));
	}

	static void Add(SCR_AIUtilityComponent utility, AIActionBase action)
	{
		if (!utility || !action)
			return;
		AIAgent agent = AIAgent.Cast(utility.GetOwner());
		if (agent && Is(agent.GetControlledEntity()))
			return;
		utility.AddAction(action);
	}
}
