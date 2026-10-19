// Covered dismount (Martin, 19 Oct: "modern combat is a lot about driving to a point where they have
// cover, then clearing the position"; Arma 3: they dismount 100-300 m out). AI Conflict drives a
// squad's vehicle to the road nearest its objective and lets it out 150 m short, in the open. For the
// side with our strategist the vehicle instead stops 200-400 m short of the objective, toward where it
// comes from, at the nearest road point the objective can't see (a crest, a treeline or buildings
// between them), and the squad goes on from there on foot. No such point: AI Conflict's own.
// Logs [ZCR][DISMOUNT] per route (chosen point, distance, hidden) and per covered dismount.
// -zcrNoCoveredDismount turns it off.
class ZCR_Dismount
{
	static string s_sFaction;                                  // the trip being routed (set around it)
	protected static ref array<vector> s_aPoints = {};         // covered points chosen
	protected static ref TraceParam s_Trace;
	static const float NEAR = 200;
	static const float FAR = 400;

	static bool Active()
	{
		if (System.IsCLIParam("zcrNoCoveredDismount") || s_sFaction.IsEmpty())
			return false;
		return !ZCR_StrategicPlan.Get(s_sFaction).IsEmpty();
	}

	// A covered point chosen within 'radius' of p (the vehicle has arrived), or false.
	static bool NearChosen(vector p, float radius, out vector point)
	{
		foreach (vector q : s_aPoints)
		{
			if (vector.DistanceXZ(p, q) < radius)
			{
				point = q;
				return true;
			}
		}
		return false;
	}

	// The covered point for a route from 'from' to 'target', or false.
	static bool Find(vector from, vector target, out vector point)
	{
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		RoadNetworkManager roads;
		if (aiWorld)
			roads = aiWorld.GetRoadNetworkManager();
		if (!roads)
			return false;
		vector toward = from - target;
		toward[1] = 0;
		if (toward.Length() < NEAR + 50)
			return false;                                       // already close: AI Conflict's own
		toward.Normalize();
		BaseWorld world = GetGame().GetWorld();
		array<float> rings = {200, 250, 300, 350, 400};
		array<float> angles = {0, 20, -20, 40, -40, 60, -60};
		int queries;
		foreach (float d : rings)
		{
			foreach (float a : angles)
			{
				float r = a * Math.DEG2RAD;
				vector dir = Vector(toward[0] * Math.Cos(r) - toward[2] * Math.Sin(r), 0, toward[0] * Math.Sin(r) + toward[2] * Math.Cos(r));
				vector p = target + dir * d;
				p[1] = world.GetSurfaceY(p[0], p[2]);
				if (!Hidden(world, target, p))
					continue;
				queries++;
				if (queries > 8)
					return false;
				vector road;
				if (!roads.GetReachableWaypointInRoad(from, p, 40, road))
					continue;
				road[1] = world.GetSurfaceY(road[0], road[2]);
				float dr = vector.DistanceXZ(road, target);
				if (dr < NEAR - 30 || dr > FAR + 40 || !Hidden(world, target, road))
					continue;
				point = road;
				s_aPoints.Insert(road);
				return true;
			}
		}
		return false;
	}

	// The objective can't see the point: from its centre and from its edge toward the point (3 m up -
	// a rooftop, a window), something solid or a treeline is in between (at a soldier's height there).
	protected static bool Hidden(BaseWorld world, vector target, vector p)
	{
		vector eye = p + Vector(0, 1.6, 0);
		vector dir = p - target;
		dir[1] = 0;
		dir.Normalize();
		array<vector> watchers = {target, target + dir * 50};
		foreach (vector w : watchers)
		{
			w[1] = world.GetSurfaceY(w[0], w[2]) + 3;
			if (!Blocked(world, w, eye))
				return false;
		}
		return true;
	}

	protected static bool Blocked(BaseWorld world, vector a, vector b)
	{
		if (!s_Trace)
			s_Trace = new TraceParam();
		s_Trace.Flags = TraceFlags.WORLD | TraceFlags.ENTS;
		s_Trace.TargetLayers = EPhysicsLayerDefs.Terrain | EPhysicsLayerDefs.ViewGeometry | EPhysicsLayerDefs.Foliage | EPhysicsLayerDefs.FireGeometry;
		s_Trace.Exclude = null;
		s_Trace.Start = a;
		s_Trace.End = b;
		return world.TraceMove(s_Trace, null) < 0.98;
	}
}

// The route: our side's trips get the covered point instead of the road nearest the objective.
modded class AICF_VehicleWaypointFactory
{
	override AIWaypoint CreateMoveWaypoint(vector fromPosition, vector targetPosition, float targetRangeMeters, out vector resolvedPosition, out string routeMode)
	{
		vector point;
		if (ZCR_Dismount.Active() && ZCR_Dismount.Find(fromPosition, targetPosition, point))
		{
			AIWaypoint waypoint = SpawnWaypoint(MOVE_WAYPOINT_PREFAB, point);
			if (waypoint)
			{
				waypoint.SetCompletionRadius(15);
				resolvedPosition = point;
				routeMode = "ROAD_REACHABLE";
				Print(string.Format("[ZCR][DISMOUNT] t=%1 faction=%2 route point=%3 %4 from_objective=%5 from_start=%6", ZCR_LossLog.Seconds(),
					ZCR_Dismount.s_sFaction, Math.Round(point[0]), Math.Round(point[2]), Math.Round(vector.DistanceXZ(point, targetPosition)),
					Math.Round(vector.DistanceXZ(point, fromPosition))), LogLevel.NORMAL);
				return waypoint;
			}
		}
		return super.CreateMoveWaypoint(fromPosition, targetPosition, targetRangeMeters, resolvedPosition, routeMode);
	}
}

modded class AICF_VehicleTransitFlow
{
	// Which side the route is for.
	protected override AICF_TripOutcome CreateAndStageRoute(AICF_TransportTrip trip, string causationId, bool safeReuseRetarget, bool recovery,
		string recoveryReason, bool requireRouteProgress, bool unstuckRelocated)
	{
		ZCR_Dismount.s_sFaction = "";
		if (trip && trip.GetAssignment())
			ZCR_Dismount.s_sFaction = trip.GetAssignment().GetFactionKey();
		AICF_TripOutcome outcome = super.CreateAndStageRoute(trip, causationId, safeReuseRetarget, recovery, recoveryReason, requireRouteProgress, unstuckRelocated);
		ZCR_Dismount.s_sFaction = "";
		return outcome;
	}

	// At the covered point: everyone out (AI Conflict lets them out only within 150 m of the objective).
	// The vehicle's waypoint completes as it arrives, so this checks where the vehicle is, not the
	// waypoint (19 Oct probe: it arrived, the route was made again to the same point, three times).
	override AICF_TripOutcome Tick(AICF_TransportTrip trip, string causationId)
	{
		if (trip && trip.GetLease() && trip.GetLease().GetVehicle() && trip.GetAssignment())
		{
			AICF_VehicleMovementState state = trip.GetMovementState();
			vector at = trip.GetLease().GetVehicle().GetOrigin();
			vector point;
			if (state && ZCR_Dismount.NearChosen(at, 25, point) && vector.DistanceXZ(at, state.GetTacticalTarget()) < ZCR_Dismount.FAR + 60)
			{
				Print(string.Format("[ZCR][DISMOUNT] t=%1 faction=%2 out at=%3 %4 from_objective=%5", ZCR_LossLog.Seconds(), trip.GetAssignment().GetFactionKey(),
					Math.Round(point[0]), Math.Round(point[2]), Math.Round(vector.DistanceXZ(at, state.GetTacticalTarget()))), LogLevel.NORMAL);
				AbortOwnedActions(trip);
				return AICF_TripOutcome.StartDismount("ZCR_COVERED_DISMOUNT", causationId);
			}
		}
		return super.Tick(trip, causationId);
	}
}
