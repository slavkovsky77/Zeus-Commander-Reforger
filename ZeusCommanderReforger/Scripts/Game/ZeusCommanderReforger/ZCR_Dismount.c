// Covered dismount (Martin, 19 Oct: "modern combat is a lot about driving to a point where they have
// cover, then clearing the position"; Arma 3: they dismount 100-300 m out). AI Conflict drives a
// squad's vehicle along the road toward its objective and lets it out 150 m short, in the open. For
// the side with our strategist, everyone gets out earlier: at the first place on that same drive,
// 180-450 m from the objective, that the objective can't see (a crest, a treeline or buildings in
// between) - and goes on from there on foot. No such place on the way: AI Conflict's own 150 m.
// (First version routed the vehicle to a hidden road point beside the objective: the road network's
// way there went the long way round and the trucks drove away from the objective.)
// Logs [ZCR][DISMOUNT] per covered dismount. -zcrNoCoveredDismount turns it off.
class ZCR_Dismount
{
	protected static ref TraceParam s_Trace;
	static const float NEAR = 180;
	static const float FAR = 450;

	static bool ActiveFor(string faction)
	{
		if (System.IsCLIParam("zcrNoCoveredDismount") || faction.IsEmpty())
			return false;
		return !ZCR_StrategicPlan.Get(faction).IsEmpty();
	}

	// The objective can't see the point: from its centre and from its edge toward the point (3 m up -
	// a rooftop, a window), something solid or a treeline is in between (at a soldier's height there).
	static bool Hidden(vector target, vector p)
	{
		BaseWorld world = GetGame().GetWorld();
		vector eye = p;
		eye[1] = world.GetSurfaceY(p[0], p[2]) + 1.6;
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

modded class AICF_VehicleTransitFlow
{
	// On the way, 180-450 m from the objective and out of its sight: everyone out.
	override AICF_TripOutcome Tick(AICF_TransportTrip trip, string causationId)
	{
		if (trip && trip.GetLease() && trip.GetLease().GetVehicle() && trip.GetAssignment()
			&& ZCR_Dismount.ActiveFor(trip.GetAssignment().GetFactionKey()))
		{
			AICF_VehicleMovementState state = trip.GetMovementState();
			if (state && state.GetRouteWaypoint())
			{
				vector at = trip.GetLease().GetVehicle().GetOrigin();
				vector target = state.GetTacticalTarget();
				float d = vector.DistanceXZ(at, target);
				if (d >= ZCR_Dismount.NEAR && d <= ZCR_Dismount.FAR && ZCR_Dismount.Hidden(target, at))
				{
					Print(string.Format("[ZCR][DISMOUNT] t=%1 faction=%2 out at=%3 %4 from_objective=%5", ZCR_LossLog.Seconds(),
						trip.GetAssignment().GetFactionKey(), Math.Round(at[0]), Math.Round(at[2]), Math.Round(d)), LogLevel.NORMAL);
					AbortOwnedActions(trip);
					return AICF_TripOutcome.StartDismount("ZCR_COVERED_DISMOUNT", causationId);
				}
			}
		}
		return super.Tick(trip, causationId);
	}
}
