// The attack plan's hold line (29 Oct night - Martin, review note 449: "coordination of teams where they would actually
// attack, maybe some timing"; with -zcrAttackPlan, AICF_ZcrAttackPlan / lab/attackplan.py): a team of the side whose
// leader reaches its lane's hold point (~150 m from the objective) gets a Defend waypoint there ahead of AI Conflict's
// own - it takes positions and AI Conflict's approach legs wait (they advance only on their own current waypoint). When
// GO_TEAMS teams hold, or HOLD_MAX_S game seconds after the first got there, every hold of the side is lifted at once and
// the teams go in together. A hold AI Conflict removed is put back (at most 3 times). -zcrNoAttackHold off.
//   [ZCR][HOLD] t= side= slot= event=hold|readd|go holding= waited_s= x= z=
class ZCR_AttackHold
{
	static const float HOLD_M = 35;
	static const int GO_TEAMS = 3;
	static const int HOLD_MAX_S = 90;
	protected static bool s_bStarted;
	protected static ref map<string, ref map<int, AIWaypoint>> s_mHolds = new map<string, ref map<int, AIWaypoint>>();
	protected static ref map<string, int> s_mFirstAt = new map<string, int>();
	protected static ref map<string, bool> s_mGone = new map<string, bool>();
	protected static ref map<string, int> s_mReadded = new map<string, int>();

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || !AICF_ZcrAttackPlan.On() || System.IsCLIParam("zcrNoAttackHold"))
			return;
		s_bStarted = true;
		GetGame().GetCallqueue().CallLater(Tick, 2000, true);
	}

	protected static void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		foreach (FactionKey faction, AICF_FactionState state : ZCR_Strategist.s_mStates)
		{
			AICF_ZcrPlan plan = AICF_ZcrAttackPlan.Of(faction);
			if (!state || !plan || plan.m_aLanes.IsEmpty() || s_mGone.Get(faction))
				continue;
			map<int, AIWaypoint> holds = s_mHolds.Get(faction);
			if (!holds)
			{
				holds = new map<int, AIWaypoint>();
				s_mHolds.Set(faction, holds);
			}
			for (int s; s < state.GetSlotCount(); s++)
			{
				AICF_GroupSlot slot = state.GetSlot(s);
				if (!slot || !slot.GetGroup() || slot.GetRole() != AICF_EGroupRole.ATTACK || !slot.GetTargetBase() || !slot.GetTargetBase().GetOwner())
					continue;
				if (vector.DistanceXZ(slot.GetTargetBase().GetOwner().GetOrigin(), plan.m_vObjective) > 150)
					continue;
				IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(slot.GetGroup());
				if (!leader)
					continue;
				AICF_ZcrPlanLane lane = plan.m_aLanes[slot.GetSlotId() % plan.m_aLanes.Count()];
				AIWaypoint held;
				if (holds.Find(slot.GetSlotId(), held))
				{
					// Still holding: AI Conflict may have put its own waypoint first - ours back on top.
					if (held && slot.GetGroup().GetCurrentWaypoint() != held && s_mReadded.Get(faction + ":" + slot.GetSlotId()) < 3)
					{
						slot.GetGroup().AddWaypointAt(held, 0);
						s_mReadded.Set(faction + ":" + slot.GetSlotId(), s_mReadded.Get(faction + ":" + slot.GetSlotId()) + 1);
						Log(faction, slot.GetSlotId(), "readd", holds.Count(), now, lane.m_vHold);
					}
					continue;
				}
				if (vector.DistanceXZ(leader.GetOrigin(), lane.m_vHold) > HOLD_M)
					continue;
				vector p = lane.m_vHold;
				p[1] = GetGame().GetWorld().GetSurfaceY(p[0], p[2]);
				EntitySpawnParams params = new EntitySpawnParams();
				params.TransformMode = ETransformMode.WORLD;
				params.Transform[3] = p;
				AIWaypoint w = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{93291E72AC23930F}Prefabs/AI/Waypoints/AIWaypoint_Defend.et", false, params: params));
				if (!w)
					continue;
				w.SetCompletionRadius(30);
				slot.GetGroup().AddWaypointAt(w, 0);
				holds.Set(slot.GetSlotId(), w);
				if (!s_mFirstAt.Contains(faction))
					s_mFirstAt.Set(faction, now);
				Log(faction, slot.GetSlotId(), "hold", holds.Count(), now, p);
				ZCR_Feed.Note(faction, string.Format("team %1 at the hold line, waiting for the others", slot.GetSlotId()));
			}
			if (holds.IsEmpty())
				continue;
			if (holds.Count() >= GO_TEAMS || now - s_mFirstAt.Get(faction) >= HOLD_MAX_S)
				Go(faction, holds, now);
		}
	}

	protected static void Go(string faction, map<int, AIWaypoint> holds, int now)
	{
		s_mGone.Set(faction, true);
		Log(faction, -1, "go", holds.Count(), now, vector.Zero);
		ZCR_Feed.Note(faction, string.Format("%1 teams at the hold line - all go in together", holds.Count()));
		AICF_FactionState state = ZCR_Strategist.s_mStates.Get(faction);
		for (int s; state && s < state.GetSlotCount(); s++)
		{
			AICF_GroupSlot slot = state.GetSlot(s);
			AIWaypoint w;
			if (slot && slot.GetGroup() && holds.Find(slot.GetSlotId(), w) && w)
				slot.GetGroup().RemoveWaypoint(w);
		}
		foreach (int slotId, AIWaypoint w : holds)
		{
			if (w)
				RplComponent.DeleteRplEntity(w, false);
		}
	}

	protected static void Log(string faction, int slot, string what, int holding, int now, vector at)
	{
		int waited;
		if (s_mFirstAt.Contains(faction))
			waited = now - s_mFirstAt.Get(faction);
		Print(string.Format("[ZCR][HOLD] t=%1 side=%2 slot=%3 event=%4 holding=%5 waited_s=%6 x=%7 z=%8", now, faction, slot, what, holding, waited,
			Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
	}
}
