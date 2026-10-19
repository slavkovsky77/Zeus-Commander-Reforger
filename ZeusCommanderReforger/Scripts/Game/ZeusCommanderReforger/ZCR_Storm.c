// Arma 3's storm: once the assault force is at the objective, its squads go in and keep moving
// under fire instead of trading shots at range. AI Conflict stages them 400-500 m out, and each
// 220 m approach step ends when a Reforger group under fire stops to fight (Arland, Moss Hill:
// 40-65 soldiers held 270-600 m out for 23 minutes). The strategist names the base (storm <id>);
// the attack waypoints AI Conflict creates for it get a player-order priority level, like a Game
// Master's forced move, and the squads already on their way are re-ordered once.
// Logs [ZCR][STORM] for the lab. Server only.
class ZCR_Storm
{
	protected static ref map<string, vector> s_mTarget;   // faction -> position of the base stormed

	static float Priority()
	{
		return SCR_AIActionBase.PRIORITY_LEVEL_PLAYER;
	}

	static bool IsStormed(string faction, SCR_CampaignMilitaryBaseComponent base)
	{
		if (!s_mTarget || !base || !base.GetOwner())
			return false;
		vector at;
		return s_mTarget.Find(faction, at) && vector.DistanceXZ(at, base.GetOwner().GetOrigin()) < 1;
	}

	// True when the stormed base changed.
	static bool Set(string faction, SCR_CampaignMilitaryBaseComponent base)
	{
		if (!s_mTarget)
			s_mTarget = new map<string, vector>();
		bool had = s_mTarget.Contains(faction);
		if (!base || !base.GetOwner())
		{
			s_mTarget.Remove(faction);
			return had;
		}
		if (IsStormed(faction, base))
			return false;
		s_mTarget.Set(faction, base.GetOwner().GetOrigin());
		return true;
	}
}

modded class AICF_OrderPlanner
{
	override protected AIWaypoint CreateWaypoint(
		SCR_CampaignMilitaryBaseComponent target,
		AICF_EGroupRole role,
		SCR_AIGroup group,
		int endpointRevision,
		AICF_GroupSlot slot,
		out bool approachRoute)
	{
		AIWaypoint waypoint = super.CreateWaypoint(target, role, group, endpointRevision, slot, approachRoute);
		if (!waypoint || role != AICF_EGroupRole.ATTACK || !group || !group.GetFaction())
			return waypoint;
		if (!ZCR_Storm.IsStormed(group.GetFaction().GetFactionKey(), target))
			return waypoint;
		SCR_AIWaypoint scripted = SCR_AIWaypoint.Cast(waypoint);
		if (scripted)
			scripted.SetPriorityLevel(ZCR_Storm.Priority());
		return waypoint;
	}
}
