// Arma 3's storm: once the assault force is at the objective, its squads go in and keep moving
// under fire instead of trading shots at range. AI Conflict stages them 400-500 m out, and each
// 220 m approach step ends when a Reforger group under fire stops to fight (Arland, Moss Hill:
// 40-65 soldiers held 270-600 m out for 23 minutes). The strategist names the base (storm <id>);
// the attack waypoints AI Conflict creates for it get a higher priority level (careful by default,
// see Priority), and the squads already on their way are re-ordered once.
// Logs [ZCR][STORM] for the lab. Server only.
class ZCR_Storm
{
	protected static ref map<string, vector> s_mTarget;   // faction -> position of the base stormed
	// Storms for the director's camera: what, where, when (-1000 once shown).
	static ref array<string> s_aEventText = {};
	static ref array<vector> s_aEventPos = {};
	static ref array<int> s_aEventAt = {};

	static void Event(string text, vector at)
	{
		s_aEventText.Insert(text);
		s_aEventPos.Insert(at);
		s_aEventAt.Insert(ZCR_LossLog.Seconds());
	}

	// A storm from the last 40 s not yet shown, or -1.
	static int PendingEvent(int now)
	{
		for (int i = s_aEventAt.Count() - 1; i >= 0; i--)
		{
			if (now - s_aEventAt[i] <= 40)
				return i;
		}
		return -1;
	}

	// A careful storm by default: at 25 the squad's move (50 + 25) beats stopping to fight a spotted
	// group (70), but a soldier's formation movement (30 + 25) still loses to taking a fire position
	// (60) or shooting a chosen target (90) - they keep advancing and still use cover. Moss Hill
	// probes: taken as fast as at 1000 (a player order's) with 15 soldiers lost instead of 39.
	// -zcrStormPriority <n> for the lab.
	static const float CAREFUL = 25;

	static float Priority()
	{
		string value;
		if (System.GetCLIParam("zcrStormPriority", value) && !value.IsEmpty())
			return value.ToFloat();
		return CAREFUL;
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
