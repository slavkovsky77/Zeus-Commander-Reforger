// A detour when the game gives up a vehicle's route as unreachable (24 Oct, the Farm: the supply vans' route from the depot
// led along the farm wall into a gap too narrow for them; at the corner the game declared the source base unreachable and
// the drivers got out - Martin: "why didn't the trucks use the correct road to the farm?", "let's try to make it work"):
// the driver's group gets a waypoint on a road 35-160 m off and not ahead of the vehicle (the dead end is ahead), the one
// nearest the goal, before its own; the route goes on from there. A minute between detours of a vehicle, 3 at most.
// -zcrNoDetour off.
//   [ZCR][DETOUR] t= side= vehicle= via_m= via_goal_m= goal_m= x= z= via_x= via_z=      (none found: why=no_road)
class ZCR_Detour
{
	protected static ref map<IEntity, int> s_mAt = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mCount = new map<IEntity, int>();

	static void Unreachable(IEntity vehicle, vector goal)
	{
		if (!vehicle || !Replication.IsServer() || System.IsCLIParam("zcrNoDetour") || ZCR_Armour.IsUnit(vehicle))
			return;
		int now = ZCR_LossLog.Seconds();
		if (s_mCount.Get(vehicle) >= 3 || (s_mAt.Contains(vehicle) && now - s_mAt.Get(vehicle) < 60))
			return;
		SCR_AIGroup group = DriverGroup(vehicle);
		if (!group)
			return;
		s_mAt.Set(vehicle, now);
		vector at = vehicle.GetOrigin();
		string side = ZCR_LossLog.SideOf(vehicle);
		vector via;
		if (!RoadAway(vehicle, goal, via))
		{
			Print(string.Format("[ZCR][DETOUR] t=%1 side=%2 vehicle=%3 why=no_road x=%4 z=%5", now, side, ZCR_LossLog.ShortName(vehicle), Math.Round(at[0]),
				Math.Round(at[2])), LogLevel.NORMAL);
			return;
		}
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = via;
		AIWaypoint w = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", false, params: params));
		if (!w)
			return;
		w.SetCompletionRadius(12);
		group.AddWaypointAt(w, 0);
		s_mCount.Set(vehicle, s_mCount.Get(vehicle) + 1);
		Print(string.Format("[ZCR][DETOUR] t=%1 side=%2 vehicle=%3 via_m=%4 via_goal_m=%5 goal_m=%6 x=%7 z=%8 via_x=%9", now, side, ZCR_LossLog.ShortName(vehicle),
			Math.Round(vector.DistanceXZ(at, via)), Math.Round(vector.DistanceXZ(via, goal)), Math.Round(vector.DistanceXZ(at, goal)), Math.Round(at[0]),
			Math.Round(at[2]), Math.Round(via[0])) + string.Format(" via_z=%1", Math.Round(via[2])), LogLevel.NORMAL);
	}

	// A road point 35-160 m off, not ahead of the vehicle, not a known dead end, the nearest to the goal.
	protected static bool RoadAway(IEntity vehicle, vector goal, out vector via)
	{
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (!aiWorld || !aiWorld.GetRoadNetworkManager())
			return false;
		vector at = vehicle.GetOrigin();
		vector fwd = vehicle.GetTransformAxis(2);
		fwd[1] = 0;
		fwd.Normalize();
		float best = 1e9;
		bool found;
		array<float> rings = {40, 70, 100, 140};
		foreach (float r : rings)
		{
			for (int k; k < 12; k++)
			{
				float a = k * 30 * Math.DEG2RAD;
				vector p = at + Vector(Math.Cos(a), 0, Math.Sin(a)) * r;
				BaseRoad road;
				float dist;
				aiWorld.GetRoadNetworkManager().GetClosestRoad(p, road, dist, true);
				if (!road || dist > 25)
					continue;
				array<vector> points = {};
				road.GetPoints(points);
				vector q;
				float nearest = 1e9;
				foreach (vector pt : points)
				{
					float dq = vector.DistanceXZ(pt, p);
					if (dq < nearest)
					{
						nearest = dq;
						q = pt;
					}
				}
				vector d = q - at;
				d[1] = 0;
				float m = d.Length();
				if (m < 35 || m > 160)
					continue;
				d.Normalize();
				if (vector.Dot(fwd, d) > 0.2)
					continue;                      // ahead: where the dead end is
				if (AICF_BadRoadPoints.IsBad(q, 30))
					continue;
				float score = vector.DistanceXZ(q, goal);
				if (score < best)
				{
					best = score;
					via = q;
					found = true;
				}
			}
		}
		return found;
	}

	// The group of the man in the driver's seat.
	protected static SCR_AIGroup DriverGroup(IEntity vehicle)
	{
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(vehicle, seats);
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (!seat || seat.GetType() != ECompartmentType.PILOT || !seat.GetOccupant())
				continue;
			AIControlComponent control = AIControlComponent.Cast(seat.GetOccupant().FindComponent(AIControlComponent));
			if (!control || !control.GetControlAIAgent())
				return null;
			return SCR_AIGroup.Cast(control.GetControlAIAgent().GetParentGroup());
		}
		return null;
	}
}

// Gates and barriers open as our vehicles come (24 Oct, Martin at the Farm test: "they even got stuck on a barrier"; "let's
// try to make it work"). The lab showed only a gate open before a car arrives works - once cars wait at it the queue never
// recovers (review note 316). Every 2 s: a closed door whose prefab names a gate, barrier or boom within 60 m ahead of a
// moving driven vehicle (within 35 degrees of its heading) is opened. Gates stay on the map (21 Oct) - they open for the
// traffic. -zcrNoGateAhead off.
//   [ZCR][GATEAHEAD] t= side= vehicle= gate= m= x= z=        and every 60 s: t= opened=
class ZCR_GateAhead
{
	static const float AHEAD_M = 60;
	protected static ref ZCR_GateAhead s_Instance;
	protected ref array<IEntity> m_aFound = {};
	protected ref map<IEntity, int> m_mOpenedAt = new map<IEntity, int>();
	protected int m_iOpened;
	protected int m_iNextLog = 60;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || System.IsCLIParam("zcrNoGateAhead"))
			return;
		s_Instance = new ZCR_GateAhead();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 2000, true);
	}

	protected bool Add(IEntity e)
	{
		if (e && e.FindComponent(DoorComponent))
			m_aFound.Insert(e);
		return true;
	}

	protected static bool GateLike(IEntity e)
	{
		IEntity named = e;
		while (named)
		{
			if (named.GetPrefabData())
			{
				string name = named.GetPrefabData().GetPrefabName();
				name.ToLower();
				if (name.Contains("gate") || name.Contains("barrier") || name.Contains("boom") || name.Contains("roadblock"))
					return true;
			}
			named = named.GetParent();
		}
		return false;
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("gateahead");
		int now = ZCR_LossLog.Seconds();
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		BaseWorld world = GetGame().GetWorld();
		foreach (IEntity v : cars)
		{
			if (!v || !v.GetPhysics() || v.GetPhysics().GetVelocity().Length() < 0.5)
				continue;
			vector at = v.GetOrigin();
			vector fwd = v.GetTransformAxis(2);
			fwd[1] = 0;
			fwd.Normalize();
			m_aFound.Clear();
			world.QueryEntitiesBySphere(at + fwd * (AHEAD_M * 0.5), AHEAD_M * 0.6, Add, null, EQueryEntitiesFlags.ALL);
			foreach (IEntity e : m_aFound)
			{
				DoorComponent door = DoorComponent.Cast(e.FindComponent(DoorComponent));
				if (!door || Math.AbsFloat(door.GetNormalizedDoorState()) > 0.5 || door.IsOpening())
					continue;
				vector d = e.GetOrigin() - at;
				d[1] = 0;
				float m = d.Length();
				if (m > AHEAD_M || m < 1)
					continue;
				d.Normalize();
				if (vector.Dot(fwd, d) < 0.82)
					continue;                      // not within 35 degrees ahead
				if (!GateLike(e))
					continue;
				door.SetControlValue(1, RplId.Invalid());
				m_iOpened++;
				if (now - m_mOpenedAt.Get(e) > 30)
				{
					m_mOpenedAt.Set(e, now);
					vector g = e.GetOrigin();
					Print(string.Format("[ZCR][GATEAHEAD] t=%1 side=%2 vehicle=%3 gate=%4 m=%5 x=%6 z=%7", now, ZCR_Driving.DrivenSide(v), ZCR_LossLog.ShortName(v),
						ZCR_LossLog.ShortName(e), Math.Round(m), Math.Round(g[0]), Math.Round(g[2])), LogLevel.NORMAL);
				}
			}
		}
		if (now >= m_iNextLog)
		{
			m_iNextLog = now + 60;
			if (m_iOpened > 0)
				Print(string.Format("[ZCR][GATEAHEAD] t=%1 opened=%2", now, m_iOpened), LogLevel.NORMAL);
			m_iOpened = 0;
		}
	}
}
