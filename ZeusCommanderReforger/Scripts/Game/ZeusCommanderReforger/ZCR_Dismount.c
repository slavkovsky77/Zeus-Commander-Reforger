// Covered dismount (Martin, 19 Oct: "modern combat is a lot about driving to a point where they have
// cover, then clearing the position"; Arma 3: they dismount 100-300 m out). AI Conflict drives a
// squad's vehicle along the road toward its objective and lets it out 150 m short, in the open. For
// the side with our strategist, everyone gets out earlier: at the first place on that same drive,
// 180-300 m from the objective, that the objective can't see (a crest, a treeline or buildings in
// between) - and goes on from there on foot. No such place on the way: AI Conflict's own 150 m.
// (First version routed the vehicle to a hidden road point beside the objective: the road network's
// way there went the long way round and the trucks drove away from the objective.)
// Logs [ZCR][DISMOUNT] per covered dismount. -zcrNoCoveredDismount turns it off.
class ZCR_Dismount
{
	protected static ref TraceParam s_Trace;
	static const float NEAR = 180;
	// 450 until 26 Oct night: the first hidden spot inside 450 m was always at its edge - 440-450 m out in 5 headless
	// matches, the team then walked half a kilometre (Martin, note 420: "quick dismounts near positions").
	static const float FAR = 300;

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

	// The plan's ride: its driver's group gets a waypoint at the assembly point ahead of its own, once per vehicle.
	// 2 Nov night (note 515): per vehicle, the team (slot) it was steered for and the drop point - a live plan
	// (lab/liveplan.py) may name another drop point while it drives; the ride still lets its team out where it was sent.
	// A vehicle that later carries another team is steered again.
	protected static ref map<IEntity, int> s_mSteered = new map<IEntity, int>();
	protected static ref map<IEntity, vector> s_mSteeredTo = new map<IEntity, vector>();

	static vector AssemblyFor(IEntity vehicle, AICF_ZcrPlan plan, int slot)
	{
		vector p;
		if (vehicle && s_mSteered.Contains(vehicle) && s_mSteered.Get(vehicle) == slot && s_mSteeredTo.Find(vehicle, p))
			return p;
		return plan.m_vAssembly;
	}

	static void Steer(IEntity vehicle, AICF_ZcrPlan plan, int slot)
	{
		if (!vehicle || (s_mSteered.Contains(vehicle) && s_mSteered.Get(vehicle) == slot))
			return;
		SCR_AIGroup group = ZCR_Detour.DriverGroup(vehicle);
		if (!group)
			return;
		s_mSteered.Set(vehicle, slot);
		s_mSteeredTo.Set(vehicle, plan.m_vAssembly);
		vector p = plan.m_vAssembly;
		p[1] = GetGame().GetWorld().GetSurfaceY(p[0], p[2]);
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = p;
		AIWaypoint w = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", false, params: params));
		if (!w)
			return;
		w.SetCompletionRadius(15);
		group.AddWaypointAt(w, 0);
		ZCR_Detour.Track(group, w);
		vector at = vehicle.GetOrigin();
		Print(string.Format("[ZCR][PLANRIDE] t=%1 side=%2 vehicle=%3 plan=%4 to_assembly_m=%5 x=%6 z=%7", ZCR_LossLog.Seconds(), ZCR_LossLog.SideOf(vehicle),
			ZCR_LossLog.ShortName(vehicle), plan.m_sId, Math.Round(vector.DistanceXZ(at, p)), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
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
				// 29 Oct: the team's attack plan read from the map (AICF_ZcrAttackPlan, lab/attackplan.py): the ride goes to the
				// plan's assembly point - hidden from the objective, where the lanes start - and everyone gets out there. The
				// plan from the origin nearest the ride's first tick (latched per team, shared with its approach legs).
				AICF_ZcrPlan plan = AICF_ZcrAttackPlan.ForTeam(trip.GetAssignment().GetFactionKey(), trip.GetAssignment().GetSlotId(), target, at);
				// A live plan's team on foot has no drop point (0 0): the covered dismount below as without a plan.
				vector assembly;
				if (plan)
					assembly = ZCR_Dismount.AssemblyFor(trip.GetLease().GetVehicle(), plan, trip.GetAssignment().GetSlotId());
				if (plan && assembly != vector.Zero && d > vector.DistanceXZ(assembly, target) - 30)
				{
					float toAssembly = vector.DistanceXZ(at, assembly);
					if (toAssembly <= 60)
					{
						Print(string.Format("[ZCR][DISMOUNT] t=%1 faction=%2 out at=%3 %4 from_objective=%5 plan=%6 assembly", ZCR_LossLog.Seconds(),
							trip.GetAssignment().GetFactionKey(), Math.Round(at[0]), Math.Round(at[2]), Math.Round(d), plan.m_sId), LogLevel.NORMAL);
						ZCR_Feed.Note(trip.GetAssignment().GetFactionKey(), string.Format("squad out at plan %1's assembly point, %2 m out, hidden", plan.m_sId, Math.Round(d)));
						AbortOwnedActions(trip);
						return AICF_TripOutcome.StartDismount("ZCR_PLAN_ASSEMBLY", causationId);
					}
					ZCR_Dismount.Steer(trip.GetLease().GetVehicle(), plan, trip.GetAssignment().GetSlotId());
					return super.Tick(trip, causationId);
				}
				if (d >= ZCR_Dismount.NEAR && d <= ZCR_Dismount.FAR && ZCR_Dismount.Hidden(target, at))
				{
					Print(string.Format("[ZCR][DISMOUNT] t=%1 faction=%2 out at=%3 %4 from_objective=%5", ZCR_LossLog.Seconds(),
						trip.GetAssignment().GetFactionKey(), Math.Round(at[0]), Math.Round(at[2]), Math.Round(d)), LogLevel.NORMAL);
					ZCR_Feed.Note(trip.GetAssignment().GetFactionKey(), string.Format("squad out of its vehicle %1 m short, out of the objective's sight", Math.Round(d)));
					AbortOwnedActions(trip);
					return AICF_TripOutcome.StartDismount("ZCR_COVERED_DISMOUNT", causationId);
				}
			}
		}
		return super.Tick(trip, causationId);
	}
}
