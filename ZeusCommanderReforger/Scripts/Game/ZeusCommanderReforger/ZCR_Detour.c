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

// Lab: what stands at a spot, and its trees taken away (24 Oct, the Farm's wall corner: the depot's vans stuck in the gap
// between the wall's end and a tree - is it the tree?). -zcrProbeAt "x,z,r": every entity within r m logged 5 s after the
// start; with -zcrClearTrees its trees are deleted.
//   [ZCR][PROBEAT] t= class= prefab= m= x= z= deleted=0|1      then [ZCR][PROBEAT] t= entities= trees_cleared=
class ZCR_ProbeAt
{
	protected static ref array<IEntity> s_aFound = {};

	static void Start()
	{
		if (!Replication.IsServer() || !System.IsCLIParam("zcrProbeAt"))
			return;
		GetGame().GetCallqueue().CallLater(Run, 5000, false);
	}

	protected static bool Add(IEntity e)
	{
		if (e)
			s_aFound.Insert(e);
		return true;
	}

	protected static void Run()
	{
		string spec;
		System.GetCLIParam("zcrProbeAt", spec);
		array<string> v = {};
		spec.Split(",", v, true);
		if (v.Count() < 3)
			return;
		vector at = Vector(v[0].ToFloat(), 0, v[1].ToFloat());
		at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]);
		float r = v[2].ToFloat();
		s_aFound.Clear();
		GetGame().GetWorld().QueryEntitiesBySphere(at, r, Add, null, EQueryEntitiesFlags.ALL);
		bool clear = System.IsCLIParam("zcrClearTrees");
		int n, cleared;
		foreach (IEntity e : s_aFound)
		{
			if (!e || e.GetRootParent() != e || ChimeraCharacter.Cast(e) || Vehicle.Cast(e))
				continue;
			n++;
			string prefab = "-";
			if (e.GetPrefabData())
				prefab = FilePath.StripPath(e.GetPrefabData().GetPrefabName());
			bool tree = BaseTree.Cast(e) != null;
			vector p = e.GetOrigin();
			Print(string.Format("[ZCR][PROBEAT] t=%1 class=%2 prefab=%3 m=%4 x=%5 z=%6 tree=%7 deleted=%8", ZCR_LossLog.Seconds(), e.ClassName(), prefab,
				Math.Round(vector.DistanceXZ(p, at) * 10) / 10, Math.Round(p[0]), Math.Round(p[2]), tree, clear && tree), LogLevel.NORMAL);
			if (clear && tree)
			{
				SCR_EntityHelper.DeleteEntityAndChildren(e);
				cleared++;
			}
		}
		Print(string.Format("[ZCR][PROBEAT] t=%1 entities=%2 trees_cleared=%3", ZCR_LossLog.Seconds(), n, cleared), LogLevel.NORMAL);
	}
}

// Lab: the roads around a spot (24 Oct, Martin: "they should use the road when coming to the base!!!" - which road runs
// through the Farm's corner gap, and which one leads out). -zcrRoadsAt "x,z,r": every road within r m (a grid every 15 m,
// the closest road within 10 m of each point), with its width and its points every ~25 m.
//   [ZCR][ROADS] t= road= width= points= length_m= path=x,z x,z ...
class ZCR_RoadsAt
{
	static void Start()
	{
		if (!Replication.IsServer() || !System.IsCLIParam("zcrRoadsAt"))
			return;
		GetGame().GetCallqueue().CallLater(Run, 6000, false);
	}

	protected static void Run()
	{
		string spec;
		System.GetCLIParam("zcrRoadsAt", spec);
		array<string> v = {};
		spec.Split(",", v, true);
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (v.Count() < 3 || !aiWorld || !aiWorld.GetRoadNetworkManager())
			return;
		vector at = Vector(v[0].ToFloat(), 0, v[1].ToFloat());
		float r = v[2].ToFloat();
		array<BaseRoad> roads = {};
		for (float dx = -r; dx <= r; dx += 15)
		{
			for (float dz = -r; dz <= r; dz += 15)
			{
				vector p = at + Vector(dx, 0, dz);
				BaseRoad road;
				float dist;
				aiWorld.GetRoadNetworkManager().GetClosestRoad(p, road, dist, true);
				if (road && dist <= 10 && !roads.Contains(road))
					roads.Insert(road);
			}
		}
		foreach (int i, BaseRoad road : roads)
		{
			array<vector> points = {};
			road.GetPoints(points);
			float length;
			string path;
			vector last;
			foreach (int k, vector q : points)
			{
				if (k > 0)
					length += vector.DistanceXZ(q, points[k - 1]);
				if (k == 0 || k == points.Count() - 1 || vector.DistanceXZ(q, last) >= 25)
				{
					path += string.Format(" %1,%2", Math.Round(q[0]), Math.Round(q[2]));
					last = q;
				}
			}
			Print(string.Format("[ZCR][ROADS] t=%1 road=%2 width=%3 points=%4 length_m=%5 path=%6", ZCR_LossLog.Seconds(), i, Math.Round(road.GetWidth() * 10) / 10,
				points.Count(), Math.Round(length), path), LogLevel.NORMAL);
		}
	}
}

// Road first (24 Oct, Martin: "they should fucking use the road when coming to the base!!!"; the Farm: no road runs through
// the wall corner's gap - the depot's vans drove straight across the field into it, while vans starting on the road went
// round by the roads and arrived): a driven vehicle more than OFFROAD_M off any road with its current waypoint more than
// FAR_M away first drives to the nearest proper road (MIN_WIDTH m wide or more) within 150 m - its own route goes on from
// there along the roads. Once per waypoint a vehicle, every 2 s. -zcrNoRoadFirst off.
//   [ZCR][ROADFIRST] t= side= vehicle= road_m= width= goal_m= x= z= road_x= road_z=
class ZCR_RoadFirst
{
	static const float OFFROAD_M = 15;
	static const float FAR_M = 250;
	static const float MIN_WIDTH = 4;
	protected static ref ZCR_RoadFirst s_Instance;
	protected ref map<IEntity, AIWaypoint> m_mDone = new map<IEntity, AIWaypoint>();
	protected ref map<IEntity, AIWaypoint> m_mOurs = new map<IEntity, AIWaypoint>();

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || System.IsCLIParam("zcrNoRoadFirst"))
			return;
		s_Instance = new ZCR_RoadFirst();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 2000, true);
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("roadfirst");
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (!aiWorld || !aiWorld.GetRoadNetworkManager())
			return;
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		foreach (IEntity v : cars)
		{
			if (!v || ZCR_Armour.IsUnit(v))
				continue;
			SCR_AIGroup group = DriverGroupOf(v);
			if (!group)
				continue;
			AIWaypoint w = group.GetCurrentWaypoint();
			if (!w || w == m_mDone.Get(v) || w == m_mOurs.Get(v))
				continue;
			m_mDone.Set(v, w);
			vector at = v.GetOrigin();
			vector goal = w.GetOrigin();
			if (vector.DistanceXZ(at, goal) < FAR_M)
				continue;
			BaseRoad road;
			float off;
			aiWorld.GetRoadNetworkManager().GetClosestRoad(at, road, off, true);
			if (road && off <= OFFROAD_M)
				continue;                      // on a road already
			vector q;
			float width;
			if (!NearestProperRoad(aiWorld, at, q, width))
				continue;
			EntitySpawnParams params = new EntitySpawnParams();
			params.TransformMode = ETransformMode.WORLD;
			params.Transform[3] = q;
			AIWaypoint first = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", false, params: params));
			if (!first)
				continue;
			first.SetCompletionRadius(10);
			group.AddWaypointAt(first, 0);
			m_mOurs.Set(v, first);
			Print(string.Format("[ZCR][ROADFIRST] t=%1 side=%2 vehicle=%3 road_m=%4 width=%5 goal_m=%6 x=%7 z=%8 road_x=%9", ZCR_LossLog.Seconds(),
				ZCR_Driving.DrivenSide(v), ZCR_LossLog.ShortName(v), Math.Round(vector.DistanceXZ(at, q)), Math.Round(width * 10) / 10,
				Math.Round(vector.DistanceXZ(at, goal)), Math.Round(at[0]), Math.Round(at[2]), Math.Round(q[0])) + string.Format(" road_z=%1", Math.Round(q[2])),
				LogLevel.NORMAL);
		}
	}

	// The nearest point of a road at least MIN_WIDTH wide within 150 m (a ring search; the closest road of each point).
	protected static bool NearestProperRoad(SCR_AIWorld aiWorld, vector at, out vector best, out float bestWidth)
	{
		float bestM = 1e9;
		array<float> rings = {0, 20, 40, 60, 90, 120, 150};
		foreach (float r : rings)
		{
			int steps = 12;
			if (r == 0)
				steps = 1;
			for (int k; k < steps; k++)
			{
				float a = k * (360 / steps) * Math.DEG2RAD;
				vector p = at + Vector(Math.Cos(a), 0, Math.Sin(a)) * r;
				BaseRoad road;
				float dist;
				aiWorld.GetRoadNetworkManager().GetClosestRoad(p, road, dist, true);
				if (!road || road.GetWidth() < MIN_WIDTH)
					continue;
				array<vector> points = {};
				road.GetPoints(points);
				foreach (vector q : points)
				{
					float m = vector.DistanceXZ(q, at);
					if (m < bestM && !AICF_BadRoadPoints.IsBad(q, 20))
					{
						bestM = m;
						best = q;
						bestWidth = road.GetWidth();
					}
				}
			}
			if (bestM < r)
				break;                         // nothing nearer is left in the rings further out
		}
		return bestM <= 150;
	}

	protected static SCR_AIGroup DriverGroupOf(IEntity vehicle)
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

// Lab: -zcrRenavAt "x1,z1,x2,z2" - the navmesh of that area regenerated at the start (24 Oct, the Farm: vans from 3 of the
// 4 depot spots drove to two places where the planner sees a way and a van doesn't fit - 2197,2928 and 2357,2969 - and the
// crews got out; is the baked vehicle navmesh stale round the farm's fences?). Logs which navmeshes have a tile there, the
// request, and when no tile is waiting any more: [ZCR][RENAV] t= navmeshes= requested= / t= done=1 waited_s=
class ZCR_RenavAt
{
	protected static vector s_vMin;
	protected static vector s_vMax;
	protected static int s_iAt;

	static void Start()
	{
		if (!Replication.IsServer() || !System.IsCLIParam("zcrRenavAt"))
			return;
		GetGame().GetCallqueue().CallLater(Run, 3000, false);
	}

	protected static void Run()
	{
		string spec;
		System.GetCLIParam("zcrRenavAt", spec);
		array<string> v = {};
		spec.Split(",", v, true);
		AIWorld aiWorld = GetGame().GetAIWorld();
		if (v.Count() < 4 || !aiWorld)
			return;
		s_vMin = Vector(v[0].ToFloat(), -100, v[1].ToFloat());
		s_vMax = Vector(v[2].ToFloat(), 1000, v[3].ToFloat());
		vector mid = (s_vMin + s_vMax) * 0.5;
		mid[1] = GetGame().GetWorld().GetSurfaceY(mid[0], mid[2]);
		string names;
		array<string> kinds = {"Soldiers", "BTRlike", "LowRes", "Vehicles", "Cars"};
		foreach (string k : kinds)
		{
			NavmeshWorldComponent nav = aiWorld.GetNavmeshWorldComponent(k);
			if (nav)
				names += string.Format("%1:%2 ", k, nav.IsTileValid(mid));
		}
		aiWorld.RequestNavmeshRebuild(s_vMin, s_vMax);
		s_iAt = ZCR_LossLog.Seconds();
		Print(string.Format("[ZCR][RENAV] t=%1 navmeshes=%2requested=%3,%4..%5,%6", s_iAt, names, Math.Round(s_vMin[0]), Math.Round(s_vMin[2]),
			Math.Round(s_vMax[0]), Math.Round(s_vMax[2])), LogLevel.NORMAL);
		GetGame().GetCallqueue().CallLater(Wait, 1000, true);
	}

	protected static void Wait()
	{
		AIWorld aiWorld = GetGame().GetAIWorld();
		if (!aiWorld)
			return;
		int waiting;
		array<string> kinds = {"Soldiers", "BTRlike", "LowRes", "Vehicles", "Cars"};
		foreach (string k : kinds)
		{
			NavmeshWorldComponent nav = aiWorld.GetNavmeshWorldComponent(k);
			if (!nav)
				continue;
			for (float x = s_vMin[0]; x <= s_vMax[0]; x += 50)
			{
				for (float z = s_vMin[2]; z <= s_vMax[2]; z += 50)
				{
					vector p = Vector(x, GetGame().GetWorld().GetSurfaceY(x, z), z);
					if (nav.IsTileRequested(p))
						waiting++;
				}
			}
		}
		int now = ZCR_LossLog.Seconds();
		if (waiting > 0 && now - s_iAt < 120)
			return;
		GetGame().GetCallqueue().Remove(Wait);
		Print(string.Format("[ZCR][RENAV] t=%1 done=%2 waited_s=%3", now, waiting == 0, now - s_iAt), LogLevel.NORMAL);
	}
}
