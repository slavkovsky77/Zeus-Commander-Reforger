// AI drivers' speed (Martin, 20 Oct: "cars are weirdly wiggling - goes left, right"; the logs of 20 Oct:
// 230 of 342 vehicles lost were crashes - the killer their own driver at 1 m - 191 of them at two places on
// the main bases' exit roads, ~500 m east of the US base and ~300 m north-east of the USSR base).
// The game's own cruise-speed limit for an AI driver (AICarMovementComponent.SetCruiseSpeed - its scenario
// framework's "set vehicle cruise speed" action) on every vehicle an AI drives: -zcrCruiseSpeed (km/h;
// default 0 = the game's own speed). A/B 20 Oct, 0 v 50 km/h: AI drivers run a median 12 km/h, at most 62,
// and the vehicles still blew up at the same places - the world's minefields across the exit roads (removed
// by our AI Conflict, AICF_RoadMines), not speed.
// Measured every 30 s: [ZCR][DRIVE] t= side= driven= median_kmh= max_kmh= over60= limit= stuck= jammed=, and a
// vehicle's last speed on its [ZCR][LOSS] line (kmh=).
// Stuck and jammed vehicles (Martin, 21 Oct: "AI crashed into vehicles, they crash and crash, they deadlock
// themselves" - a T-72 and a supply truck nose to nose in a rock gap 2 min, cars bumping at the main base): a
// driven vehicle that hasn't moved 3 m for STUCK_S game seconds is stuck; with another vehicle within JAM_M it is
// jammed (a deadlock). Logged once when it starts and when it ends:
//   [ZCR][JAM] t= side= vehicle= other= other_side= x= z= (jammed) / [ZCR][STUCKVEH] t= side= vehicle= x= z=
//   [ZCR][UNJAM] t= side= vehicle= stuck_s= (moving again or gone)
// A soldier killed with no killer next to a moving vehicle of his side (6 m, over 2 km/h) gets runover=<vehicle> on
// his [ZCR][LOSS] line (Martin's /bad 21:03: the T-72 ran over its medic and machine gunner).
// 22 Oct 00:35 (Martin: "one of the biggest issues is cars blocking each other ... the biggest one"): only a vehicle
// that wants to go somewhere counts - its driver's group has a waypoint over GOAL_M away (a truck loading at its
// depot, a ride waiting for its team, a parked car aren't stuck). A jammed one backs off: of the two, the one driving
// into the other (the other within 15 m in its front cone); head-on or side by side, the lighter one; a vehicle
// nobody drives never moves, so the driven one backs. BACK_M back along its own track (5 m if that spot is taken),
// at most every 30 game s and 3 times a vehicle - then the AI drivers find their way round each other. Logs
// [ZCR][UNJAM] ... action=back. Off: -zcrNoUnjam.
// 22 Oct 00:55, the first night's Everon match: the jams were rides against an abandoned UAZ (nobody aboard, no
// side) on their way out - backing off 8 m brought them back against it 45 s later. A blocker nobody drives and
// nobody sits in is parked off the road instead: 10-14 m to its side, a spot free of vehicles ([ZCR][UNJAM]
// action=park), once a vehicle.
// 22 Oct 01:40, Arland: the rides leaving the harbour main base jammed against the next ride waiting at the pad (its
// driver aboard, its team on the way) and backed off three times for nothing. A blocker that is driven but waiting
// (its goal within GOAL_M) is parked aside too; a vehicle can be parked again after 120 game s.
class ZCR_Driving
{
	protected static ref ZCR_Driving s_Instance;
	protected static ref map<IEntity, float> s_mSpeed = new map<IEntity, float>();
	protected static ref map<IEntity, int> s_mSeen = new map<IEntity, int>();
	protected static ref map<IEntity, vector> s_mMark = new map<IEntity, vector>();
	protected static ref map<IEntity, int> s_mMarkAt = new map<IEntity, int>();
	protected static ref map<IEntity, string> s_mStuck = new map<IEntity, string>();     // "" not stuck, "STUCK", "JAM"
	protected static ref map<IEntity, string> s_mSide = new map<IEntity, string>();
	protected static ref array<IEntity> s_aNear;
	static const int STUCK_S = 45;
	static const float JAM_M = 10;
	static const float GOAL_M = 30;
	static const float BACK_M = 8;
	protected static ref map<IEntity, int> s_mBackAt = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mBacks = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mParked = new map<IEntity, int>();     // when it was last parked aside
	protected static ref map<IEntity, bool> s_mWaiting = new map<IEntity, bool>();  // driven, but its goal is near
	protected float m_fLimit = 0;
	protected int m_iNextLog;
	protected int m_iNextClean;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer())
			return;
		s_Instance = new ZCR_Driving();
		string value;
		if (System.GetCLIParam("zcrCruiseSpeed", value) && !value.IsEmpty())
			s_Instance.m_fLimit = value.ToFloat();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 2000, true);
	}

	// " runover=<vehicle>" for a soldier killed with no killer next to a moving vehicle of his side, else "".
	static string RunOver(IEntity victim, IEntity killer)
	{
		ChimeraCharacter man = ChimeraCharacter.Cast(victim);
		if (!man || (killer && killer != victim))
			return "";
		// Killed aboard (a drone hit on his vehicle has no killer either) - not run over.
		if (man.IsInVehicle() || Vehicle.Cast(victim.GetRootParent()))
			return "";
		string side = ZCR_LossLog.SideOf(victim);
		foreach (IEntity v, float kmh : s_mSpeed)
		{
			if (!v || kmh < 2 || s_mSide.Get(v) != side)
				continue;
			if (vector.DistanceXZ(v.GetOrigin(), victim.GetOrigin()) <= 6)
				return " runover=" + ZCR_LossLog.ShortName(v);
		}
		return "";
	}

	// " kmh=NN" for a vehicle seen driven in the last minute, else "".
	static string Note(IEntity victim)
	{
		float kmh;
		if (!Vehicle.Cast(victim) || !s_mSpeed.Find(victim, kmh))
			return "";
		return string.Format(" kmh=%1", Math.Round(kmh));
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		map<string, ref array<float>> speeds = new map<string, ref array<float>>();
		foreach (AIAgent agent : agents)
		{
			if (!agent)
				continue;
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (!c || !c.IsInVehicle())
				continue;
			CompartmentAccessComponent access = c.GetCompartmentAccessComponent();
			if (!access)
				continue;
			PilotCompartmentSlot seat = PilotCompartmentSlot.Cast(access.GetCompartment());
			if (!seat)
				continue;
			IEntity v = seat.GetVehicle();
			if (!v || !v.GetPhysics())
				continue;
			float kmh = v.GetPhysics().GetVelocity().Length() * 3.6;
			s_mSpeed.Set(v, kmh);
			s_mSeen.Set(v, now);
			if (m_fLimit > 0)
			{
				AICarMovementComponent car = AICarMovementComponent.Cast(v.FindComponent(AICarMovementComponent));
				if (car)
					car.SetCruiseSpeed(m_fLimit);
			}
			string side = ZCR_LossLog.SideOf(c);
			s_mSide.Set(v, side);
			Watch(v, side, now, agent);
			if (!speeds.Contains(side))
				speeds.Set(side, {});
			speeds.Get(side).Insert(kmh);
		}
		if (now >= m_iNextLog)
		{
			m_iNextLog = now + 30;
			array<string> sides = {"US", "USSR"};
			foreach (string side : sides)
			{
				array<float> s = speeds.Get(side);
				if (!s || s.IsEmpty())
				{
					Print(string.Format("[ZCR][DRIVE] t=%1 side=%2 driven=0 limit=%3", now, side, m_fLimit), LogLevel.NORMAL);
					continue;
				}
				s.Sort();
				int over;
				foreach (float k : s)
				{
					if (k > 60)
						over++;
				}
				int stuckN, jamN;
				foreach (IEntity sv, string state : s_mStuck)
				{
					if (!sv || s_mSide.Get(sv) != side)
						continue;
					if (state == "STUCK")
						stuckN++;
					else if (state == "JAM")
						jamN++;
				}
				// The moving ones (over 3 km/h): how fast the AI drives when it drives - waiting at a pad or loading isn't driving.
				array<float> moving = {};
				foreach (float mk : s)
				{
					if (mk > 3)
						moving.Insert(mk);
				}
				int movingKmh = -1;
				if (!moving.IsEmpty())
					movingKmh = Math.Round(moving[moving.Count() / 2]);
				Print(string.Format("[ZCR][DRIVE] t=%1 side=%2 driven=%3 median_kmh=%4 max_kmh=%5 over60=%6 limit=%7",
					now, side, s.Count(), Math.Round(s[s.Count() / 2]), Math.Round(s[s.Count() - 1]), over, m_fLimit) +
					string.Format(" stuck=%1 jammed=%2 moving_kmh=%3", stuckN, jamN, movingKmh), LogLevel.NORMAL);
			}
		}
		if (now >= m_iNextClean)
		{
			m_iNextClean = now + 60;
			map<IEntity, float> speed = new map<IEntity, float>();
			map<IEntity, int> seen = new map<IEntity, int>();
			foreach (IEntity e, int at : s_mSeen)
			{
				if (e && now - at < 60)
				{
					speed.Set(e, s_mSpeed.Get(e));
					seen.Set(e, at);
				}
			}
			s_mSpeed = speed;
			s_mSeen = seen;
			// Vehicles no longer driven (driver out or dead, wreck gone): a stuck one ends there.
			array<IEntity> gone = {};
			foreach (IEntity sv, string state : s_mStuck)
			{
				if (!sv || !seen.Contains(sv))
					gone.Insert(sv);
			}
			foreach (IEntity g : gone)
			{
				if (g && !s_mStuck.Get(g).IsEmpty())
					Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 stuck_s=%4 ended=not_driven", now, s_mSide.Get(g), ZCR_LossLog.ShortName(g),
						now - s_mMarkAt.Get(g)), LogLevel.NORMAL);
				s_mStuck.Remove(g);
				s_mMark.Remove(g);
				s_mMarkAt.Remove(g);
			}
		}
	}

	// Stuck / jammed bookkeeping for one driven vehicle (every 2 s).
	protected static void Watch(IEntity v, string side, int now, AIAgent driver)
	{
		vector at = v.GetOrigin();
		vector mark;
		// Not trying to go anywhere (no waypoint, or it is within GOAL_M): waiting, not stuck.
		float goal = GoalDistance(driver, v);
		bool waiting = goal < GOAL_M;
		s_mWaiting.Set(v, waiting);
		if (!s_mMark.Find(v, mark) || vector.DistanceXZ(at, mark) > 3 || waiting)
		{
			string was = s_mStuck.Get(v);
			string ended = "moving";
			if (waiting)
				ended = "arrived";
			if (!was.IsEmpty())
				Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 stuck_s=%4 ended=%5", now, side, ZCR_LossLog.ShortName(v), now - s_mMarkAt.Get(v), ended), LogLevel.NORMAL);
			s_mMark.Set(v, at);
			s_mMarkAt.Set(v, now);
			s_mStuck.Set(v, "");
			return;
		}
		if (now - s_mMarkAt.Get(v) < STUCK_S)
			return;
		if (!s_mStuck.Get(v).IsEmpty())
		{
			// Still jammed: another back-off when allowed.
			if (s_mStuck.Get(v) == "JAM")
			{
				IEntity still = OtherVehicleNear(v, JAM_M);
				if (still)
					Unjam(v, still, side, now);
			}
			return;
		}
		IEntity other = OtherVehicleNear(v, JAM_M);
		if (other)
		{
			s_mStuck.Set(v, "JAM");
			string otherSide = ZCR_LossLog.SideOf(other);
			if (otherSide.IsEmpty())
				otherSide = "none";
			Print(string.Format("[ZCR][JAM] t=%1 side=%2 vehicle=%3 other=%4 other_side=%5 x=%6 z=%7 goal_m=%8", now, side, ZCR_LossLog.ShortName(v),
				ZCR_LossLog.ShortName(other), otherSide, Math.Round(at[0]), Math.Round(at[2]), Math.Round(goal)), LogLevel.NORMAL);
			Unjam(v, other, side, now);
		}
		else
		{
			s_mStuck.Set(v, "STUCK");
			Print(string.Format("[ZCR][STUCKVEH] t=%1 side=%2 vehicle=%3 x=%4 z=%5", now, side, ZCR_LossLog.ShortName(v), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
		}
	}

	// Metres from the vehicle to where its driver's group's current waypoint counts as reached (its centre less its
	// completion radius - armour in an assault holds a firing spot inside a 60-m one); -1 with none.
	protected static float GoalDistance(AIAgent driver, IEntity v)
	{
		if (!driver)
			return -1;
		AIGroup group = driver.GetParentGroup();
		if (!group)
			return -1;
		AIWaypoint waypoint = group.GetCurrentWaypoint();
		if (!waypoint)
			return -1;
		return Math.Max(0, vector.DistanceXZ(waypoint.GetOrigin(), v.GetOrigin()) - waypoint.GetCompletionRadius());
	}

	// The jammed pair: which one backs off, then back it.
	protected static void Unjam(IEntity v, IEntity other, string side, int now)
	{
		if (System.IsCLIParam("zcrNoUnjam"))
			return;
		IEntity yielder = v;
		bool otherDriven = s_mSeen.Contains(other) && now - s_mSeen.Get(other) < 10;
		bool otherWaiting = otherDriven && s_mWaiting.Get(other);
		bool mayPark = !s_mParked.Contains(other) || now - s_mParked.Get(other) >= 120;
		// An abandoned vehicle in the way, or one waiting there for its team: park it aside, the driven one goes on.
		if (mayPark && ((!otherDriven && !ZCR_Wrecks.Occupied(other)) || otherWaiting) && ParkAside(other, side, now, v))
			return;
		if (otherDriven)
		{
			// Both driven: the one with the other in its front cone; head-on or neither, the lighter.
			bool vInto = InFront(v, other);
			bool oInto = InFront(other, v);
			if (oInto && !vInto)
				yielder = other;
			else if (vInto == oInto && Mass(other) < Mass(v))
				yielder = other;
		}
		BackOff(yielder, side, now, v, other);
	}

	protected static bool InFront(IEntity a, IEntity b)
	{
		vector mat[4];
		a.GetWorldTransform(mat);
		vector forward = mat[2];
		forward[1] = 0;
		forward.Normalize();
		vector rel = b.GetOrigin() - mat[3];
		rel[1] = 0;
		float d = rel.Length();
		return d < 15 && vector.Dot(rel, forward) > 0.5 * d;
	}

	protected static float Mass(IEntity e)
	{
		if (!e || !e.GetPhysics())
			return 0;
		return e.GetPhysics().GetMass();
	}

	protected static bool BackOff(IEntity yielder, string side, int now, IEntity a, IEntity b)
	{
		Vehicle vehicle = Vehicle.Cast(yielder);
		if (!vehicle || s_mBacks.Get(yielder) >= 3 || now - s_mBackAt.Get(yielder) < 30)
			return false;
		BaseWorld world = GetGame().GetWorld();
		vector mat[4];
		vehicle.GetWorldTransform(mat);
		vector back = mat[2];
		back[1] = 0;
		back.Normalize();
		float lift = mat[3][1] - world.GetSurfaceY(mat[3][0], mat[3][2]);
		if (lift < 0)
			lift = 0;
		array<float> distances = {BACK_M, 5.0};
		foreach (float dist : distances)
		{
			vector spot = mat[3] - back * dist;
			spot[1] = world.GetSurfaceY(spot[0], spot[2]) + lift;
			if (VehicleAt(spot, 4, yielder))
				continue;
			mat[3] = spot;
			Physics physics = vehicle.GetPhysics();
			if (physics)
			{
				physics.SetVelocity(vector.Zero);
				physics.SetAngularVelocity(vector.Zero);
			}
			ZCR_Trace.Ent("move", vehicle, "unjam_back");
			if (!vehicle.SetWorldTransform(mat))
				return false;
			s_mBackAt.Set(yielder, now);
			s_mBacks.Set(yielder, s_mBacks.Get(yielder) + 1);
			IEntity partner = a;
			if (yielder == a)
				partner = b;
			Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 action=back m=%4 other=%5 count=%6 x=%7 z=%8", now, side, ZCR_LossLog.ShortName(yielder),
				dist, ZCR_LossLog.ShortName(partner), s_mBacks.Get(yielder), Math.Round(spot[0]), Math.Round(spot[2])), LogLevel.NORMAL);
			return true;
		}
		return false;
	}

	protected static bool ParkAside(IEntity blocker, string side, int now, IEntity jammed)
	{
		Vehicle vehicle = Vehicle.Cast(blocker);
		if (!vehicle)
			return false;
		s_mParked.Set(blocker, now);
		BaseWorld world = GetGame().GetWorld();
		vector mat[4];
		vehicle.GetWorldTransform(mat);
		vector across = mat[0];
		across[1] = 0;
		across.Normalize();
		// The side away from the jammed vehicle first.
		vector away = jammed.GetOrigin() - mat[3];
		float first = 1;
		if (vector.Dot(away, across) > 0)
			first = -1;
		array<float> offsets = {10 * first, 14 * first, -10 * first, -14 * first};
		foreach (float off : offsets)
		{
			vector spot = mat[3] + across * off;
			spot[1] = world.GetSurfaceY(spot[0], spot[2]) + 0.3;
			if (VehicleAt(spot, 5, blocker) || ChimeraWorldUtils.TryGetWaterSurfaceSimple(world, spot - "0 0.5 0"))
				continue;
			mat[3] = spot;
			Physics physics = vehicle.GetPhysics();
			if (physics)
			{
				physics.SetVelocity(vector.Zero);
				physics.SetAngularVelocity(vector.Zero);
			}
			ZCR_Trace.Ent("move", vehicle, "unjam_park");
			if (!vehicle.SetWorldTransform(mat))
				return false;
			Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 action=park m=%4 for=%5 x=%6 z=%7", now, side, ZCR_LossLog.ShortName(blocker),
				Math.AbsFloat(off), ZCR_LossLog.ShortName(jammed), Math.Round(spot[0]), Math.Round(spot[2])), LogLevel.NORMAL);
			return true;
		}
		return false;
	}

	protected static bool VehicleAt(vector spot, float radius, IEntity except)
	{
		s_aNear = {};
		GetGame().GetWorld().QueryEntitiesBySphere(spot, radius, CollectVehicle, null, EQueryEntitiesFlags.DYNAMIC);
		foreach (IEntity e : s_aNear)
		{
			if (e != except && e.GetRootParent() != except)
				return true;
		}
		return false;
	}

	protected static IEntity OtherVehicleNear(IEntity v, float radius)
	{
		s_aNear = {};
		GetGame().GetWorld().QueryEntitiesBySphere(v.GetOrigin(), radius, CollectVehicle, null, EQueryEntitiesFlags.DYNAMIC);
		foreach (IEntity e : s_aNear)
		{
			if (e != v && e.GetRootParent() != v)
				return e;
		}
		return null;
	}

	protected static bool CollectVehicle(IEntity e)
	{
		if (Vehicle.Cast(e))
			s_aNear.Insert(e);
		return true;
	}
}
