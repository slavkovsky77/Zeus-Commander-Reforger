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
// 22 Oct 03:00: stuck alone (no vehicle near) lasted a median 88 game s, 27 of 96 spells 2 min+ - an AI driver hung on
// rocks, trees, a gate or a slope. Stuck alone UNSTICK_S: it backs off the same way (the way it came is drivable)
// and plans again.
// Following (22 Oct 03:40, Everon: 16 jams in one match at a farm by the US route - a queue of rides squeezing past each
// other into the field): a vehicle with one of its side's vehicles within FOLLOW_M ahead going under 5 km/h creeps at
// 4 km/h behind it; the way clear, the game's own cruise speed again. Not our armour (its guard does it). [ZCR][DRIVE]
// following=. Off: -zcrNoFollow.
// Onto the road (22 Oct 04:10, Arland w8: one Soviet ride stuck 4 times at the same granite stones 10-15 m off an 8-m
// road - backed off 8 m, it drove the same line again, and after the third back-off sat there 10 minutes until its crew
// left; supply trucks bunched at their depot's exit): stuck alone UNSTICK_S (60), a vehicle is put on the nearest road
// at least ROAD_MIN_W wide within ROAD_M, a few metres on toward its waypoint, facing along the road - if the spot is
// clear of anything solid; else it backs off. Up to 4 times a vehicle. [ZCR][UNJAM] action=road m= (how far it moved).
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
	// 22 Oct 22:10 (Martin: "is there any way to make those jams better?"): with moves now a gentle push, a pair standing
	// nose to nose is unjammed after 20 s instead of waiting the 45 s that make it a jam. -zcrNoEarlyUnjam turns it off.
	static const int EARLY_S = 20;
	static const float JAM_M = 10;
	static const float GOAL_M = 30;
	static const float BACK_M = 8;
	static const int UNSTICK_S = 60;
	static const float ROAD_M = 40;
	static const float ROAD_MIN_W = 3;
	protected static ref map<IEntity, int> s_mRoads = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mMoveFailAt = new map<IEntity, int>();
	static const float FOLLOW_M = 14;
	static const int MOVED_S = 10;
	protected static ref map<IEntity, int> s_mMovedAt = new map<IEntity, int>();
	protected static ref map<IEntity, bool> s_mFollowing = new map<IEntity, bool>();
	protected static ref map<IEntity, int> s_mBackAt = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mBacks = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mParked = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mEarly = new map<IEntity, int>();     // still-spell (its start) unjammed early     // when it was last parked aside
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
		ZCR_VehicleGuns.Start();   // [ZCR][VEHGUNS]: shots from vehicle turrets
		ZCR_DriveTest.Start();     // lab: the driving test track (-zcrDriveTest)
		ZCR_TrafficSim.Start();    // lab: the traffic simulation (-zcrTrafficSim)
		ZCR_Oncoming.Start();      // both slow to 15 km/h for a car coming the other way (-zcrNoOncoming off)
		ZCR_Traffic.Start();       // the speed arbiter and the spacing rule (-zcrNoTraffic / -zcrNoSpacing off)
		ZCR_Risk.Start();          // collision forecast: the fastest speed with under 10% risk (-zcrRisk on)
		ZCR_NavProbe.Start();      // lab: is the vehicle navmesh loaded where the cars drive (-zcrNavProbe)
		ZCR_DoorProbe.Start();     // lab: doors and gates near given points, how open (-zcrDoorProbe)
		ZCR_OpenGates.Start();     // lab: every gate on the map open, checked each minute (-zcrOpenGates)
		ZCR_GateNudge.Start();     // a car waiting at a closed gate gets the game's open-the-gate goal (-zcrNoGateNudge off)
	}

	// [ZCR][OFFROAD] t= side= moving= offroad= pct= every 30 s (22 Oct: 220 of 310 trapped vehicles were 30-80 m off
	// the road in fenced fields, the route planner cutting across): AI-driven vehicles moving over 3 km/h, and how many
	// of them are more than 8 m outside the nearest road's edge.
	protected static void OffRoadLog(int now, string side)
	{
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (!aiWorld || !aiWorld.GetRoadNetworkManager())
			return;
		RoadNetworkManager roads = aiWorld.GetRoadNetworkManager();
		int moving, off;
		foreach (IEntity v, float kmh : s_mSpeed)
		{
			if (!v || kmh <= 3 || s_mSide.Get(v) != side || s_mSeen.Get(v) != now)
				continue;
			moving++;
			BaseRoad road;
			float distance;
			roads.GetClosestRoad(v.GetOrigin(), road, distance, true);
			float edge = 0;
			if (road)
				edge = road.GetWidth() / 2;
			if (!road || distance - edge > 8)
				off++;
		}
		int pct = -1;
		if (moving > 0)
			pct = Math.Round(100.0 * off / moving);
		Print(string.Format("[ZCR][OFFROAD] t=%1 side=%2 moving=%3 offroad=%4 pct=%5", now, side, moving, off, pct), LogLevel.NORMAL);
	}

	// The lab's speed cap (-zcrCruiseSpeed), 0 when none.
	static float CruiseLimit()
	{
		if (!s_Instance)
			return 0;
		return s_Instance.m_fLimit;
	}

	// The side of a vehicle seen driven (its driver's faction), "" when unknown.
	static string DrivenSide(IEntity v)
	{
		return s_mSide.Get(v);
	}

	// The AI-driven vehicles seen this tick or the last one (for ZCR_Oncoming and ZCR_Traffic).
	static void DrivenNow(notnull array<IEntity> cars)
	{
		int now = ZCR_LossLog.Seconds();
		foreach (IEntity v, int at : s_mSeen)
		{
			if (v && now - at <= 3)
				cars.Insert(v);
		}
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
			if (m_fLimit > 0 && !ZCR_Traffic.Active())   // with the traffic manager the cap is its "lab" rule
			{
				AICarMovementComponent car = AICarMovementComponent.Cast(v.FindComponent(AICarMovementComponent));
				if (car)
					car.SetCruiseSpeed(m_fLimit);
			}
			string side = ZCR_LossLog.SideOf(c);
			s_mSide.Set(v, side);
			Watch(v, side, now, agent);
			Follow(v, side);
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
				OffRoadLog(now, side);
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
				int followN;
				foreach (IEntity fv, bool following : s_mFollowing)
				{
					if (fv && following && s_mSide.Get(fv) == side)
						followN++;
				}
				Print(string.Format("[ZCR][DRIVE] t=%1 side=%2 driven=%3 median_kmh=%4 max_kmh=%5 over60=%6 limit=%7",
					now, side, s.Count(), Math.Round(s[s.Count() / 2]), Math.Round(s[s.Count() - 1]), over, m_fLimit) +
					string.Format(" stuck=%1 jammed=%2 moving_kmh=%3 following=%4", stuckN, jamN, movingKmh, followN), LogLevel.NORMAL);
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
		int stillS = now - s_mMarkAt.Get(v);
		if (stillS >= EARLY_S && stillS < STUCK_S && s_mStuck.Get(v).IsEmpty() && s_mEarly.Get(v) != s_mMarkAt.Get(v)
			&& !System.IsCLIParam("zcrNoEarlyUnjam") && !System.IsCLIParam("zcrNoUnjam"))
		{
			IEntity early = OtherVehicleNear(v, JAM_M);
			if (early)
			{
				s_mEarly.Set(v, s_mMarkAt.Get(v));
				Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 action=early still_s=%4 other=%5 x=%6 z=%7", now, side, ZCR_LossLog.ShortName(v), stillS,
					ZCR_LossLog.ShortName(early), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
				Unjam(v, early, side, now, driver);
			}
		}
		if (stillS < STUCK_S)
			return;
		if (!s_mStuck.Get(v).IsEmpty())
		{
			// Still jammed: another back-off when allowed.
			if (s_mStuck.Get(v) == "JAM")
			{
				IEntity still = OtherVehicleNear(v, JAM_M);
				if (still)
					Unjam(v, still, side, now, driver);
			}
			else if (now - s_mMarkAt.Get(v) >= UNSTICK_S && !System.IsCLIParam("zcrNoUnjam"))
			{
				if (!OntoRoad(v, driver, side, now))
					BackOff(v, side, now, v, null);
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
			Unjam(v, other, side, now, driver);
		}
		else
		{
			s_mStuck.Set(v, "STUCK");
			Print(string.Format("[ZCR][STUCKVEH] t=%1 side=%2 vehicle=%3 x=%4 z=%5", now, side, ZCR_LossLog.ShortName(v), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
		}
	}

	// Creep behind a slow vehicle of the side right ahead instead of squeezing past it.
	protected void Follow(IEntity v, string side)
	{
		// 22 Oct 08:20: OFF unless -zcrFollow. With the hand moves and following both on, 6 of 18 watched matches
		// crashed; moves without following 6 of 6 clean (100 moves), following without moves 4 of 4 clean - and no
		// clear gain in jams to set against the risk.
		if (m_fLimit > 0 || !System.IsCLIParam("zcrFollow") || System.IsCLIParam("zcrNoFollow") || ZCR_Armour.IsUnit(v))
			return;
		// 22 Oct 07:35: the watched matches crashed with hand moves and following both on (6 of 18), not with either
		// alone - Watch can move a vehicle and Follow then change its cruise speed in the same frame. Not within
		// MOVED_S of a hand move.
		int moved;
		if (s_mMovedAt.Find(v, moved) && ZCR_LossLog.Seconds() - moved < MOVED_S)
			return;
		AICarMovementComponent car = AICarMovementComponent.Cast(v.FindComponent(AICarMovementComponent));
		if (!car)
			return;
		bool behind = SlowFriendAhead(v, side);
		bool was = s_mFollowing.Get(v);
		if (behind && !was)
			car.SetCruiseSpeed(4);
		else if (!behind && was)
			car.ResetCruiseSpeed();
		s_mFollowing.Set(v, behind);
	}

	protected static bool SlowFriendAhead(IEntity v, string side)
	{
		vector mat[4];
		v.GetWorldTransform(mat);
		vector forward = mat[2];
		forward[1] = 0;
		forward.Normalize();
		s_aNear = {};
		GetGame().GetWorld().QueryEntitiesBySphere(mat[3] + forward * (FOLLOW_M * 0.5), FOLLOW_M * 0.6, CollectVehicle, null, EQueryEntitiesFlags.DYNAMIC);
		foreach (IEntity e : s_aNear)
		{
			if (e == v || e.GetRootParent() == v)
				continue;
			string owner = s_mSide.Get(e);
			if (owner != side)
				continue;
			vector rel = e.GetOrigin() - mat[3];
			rel[1] = 0;
			float ahead = vector.Dot(rel, forward);
			if (ahead <= 0 || ahead > FOLLOW_M || (rel - forward * ahead).Length() > 4)
				continue;
			float kmh;
			if (!s_mSpeed.Find(e, kmh) || kmh < 5)
				return true;
		}
		return false;
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
	protected static void Unjam(IEntity v, IEntity other, string side, int now, AIAgent driver)
	{
		if (System.IsCLIParam("zcrNoUnjam"))
			return;
		IEntity yielder = v;
		bool otherDriven = s_mSeen.Contains(other) && now - s_mSeen.Get(other) < 10;
		// The front one of a queue (the other behind, facing it; nothing in its own way): it is hung on something of its
		// own - a boulder by a sunken track (Arland w12: 10 jams of US rides in one 4-m lane at 1515,1020) - and the
		// ones behind only wait. Onto the road ahead; backing the one behind off frees nothing.
		if (otherDriven && InFront(other, v) && !InFront(v, other) && OntoRoad(v, driver, side, now))
			return;
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
		if (BackOff(yielder, side, now, v, other) || !otherDriven)
			return;
		// It can't be moved (a turret aboard, someone getting in or out, its back-offs used up): the other one - on
		// along the road if it has room, else back (never onto a vehicle: both check the spot).
		IEntity alt = v;
		if (yielder == v)
			alt = other;
		if (!OntoRoad(alt, null, side, now))
			BackOff(alt, side, now, v, other);
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
		if (!vehicle || s_mBacks.Get(yielder) >= 4 || now - s_mBackAt.Get(yielder) < 30)
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
			if (!SafeMove(vehicle, mat[2], spot + "0 0.3 0", "unjam_back"))
				return false;
			s_mBackAt.Set(yielder, now);
			s_mBacks.Set(yielder, s_mBacks.Get(yielder) + 1);
			IEntity partner = a;
			if (yielder == a)
				partner = b;
			string partnerName = "none";
			if (partner)
				partnerName = ZCR_LossLog.ShortName(partner);
			Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 action=back m=%4 other=%5 count=%6 x=%7 z=%8", now, side, ZCR_LossLog.ShortName(yielder),
				dist, partnerName, s_mBacks.Get(yielder), Math.Round(spot[0]), Math.Round(spot[2])), LogLevel.NORMAL);
			return true;
		}
		return false;
	}

	// The game gave up a group's move in a vehicle (stuck, unreachable...) - it then takes the whole group out to go on
	// foot, supply truck drivers included (AI Conflict: LOGISTICS_DRIVER_INTERACTION_STARTED EXIT_CAUSE_UNRECOGNIZED, 22
	// in w8). [ZCR][MOVEFAIL] t= side= vehicle= error= x= z= to_m= - once in 20 s a vehicle.
	static void MoveFailed(int result, IEntity vehicle, vector location)
	{
		if (!vehicle || result == EMoveError.WAITING_ON_NAVLINK)
			return;
		// The point itself, for AI Conflict's ride routing: avoided by later rides this match.
		if (result == EMoveError.UNREACHABLE)
			AICF_BadRoadPoints.Add(location);
		int now = ZCR_LossLog.Seconds();
		int last;
		if (s_mMoveFailAt.Find(vehicle, last) && now - last < 20)
			return;
		s_mMoveFailAt.Set(vehicle, now);
		vector at = vehicle.GetOrigin();
		string side = ZCR_LossLog.SideOf(vehicle);
		if (side.IsEmpty())
			side = "none";
		Print(string.Format("[ZCR][MOVEFAIL] t=%1 side=%2 vehicle=%3 error=%4 x=%5 z=%6 to_m=%7", now, side, ZCR_LossLog.ShortName(vehicle),
			typename.EnumToString(EMoveError, result), Math.Round(at[0]), Math.Round(at[2]), Math.Round(vector.DistanceXZ(at, location)))
			+ string.Format(" to_x=%1 to_z=%2", Math.Round(location[0]), Math.Round(location[2])), LogLevel.NORMAL);
	}

	protected static ref map<string, int> s_mCollisionAt = new map<string, int>();

	static void Collision(IEntity vehicle, IEntity source, float damage, float kmh)
	{
		if (!vehicle)
			return;
		IEntity other = source;
		if (other)
			other = other.GetRootParent();
		// The game gives no source for many vehicle-on-vehicle hits (22 Oct test track: two UAZs met head-on at 1947,1185,
		// both drivers dead, both logged "object"): with none, a vehicle within 7 m is the other one.
		if (!other)
			other = OtherVehicleNear(vehicle, 7);
		bool withVehicle = Vehicle.Cast(other) != null && other != vehicle;
		string otherName = "object";
		if (withVehicle)
			otherName = ZCR_LossLog.ShortName(other);
		string key = vehicle.GetID().ToString() + "/" + otherName;
		int now = ZCR_LossLog.Seconds();
		int last;
		if (s_mCollisionAt.Find(key, last) && now - last < 10)
			return;
		s_mCollisionAt.Set(key, now);
		string side = ZCR_LossLog.SideOf(vehicle);
		if (side.IsEmpty())
			side = "none";
		string otherSide = "none";
		if (withVehicle && !ZCR_LossLog.SideOf(other).IsEmpty())
			otherSide = ZCR_LossLog.SideOf(other);
		bool driven = s_mSeen.Contains(vehicle) && now - s_mSeen.Get(vehicle) < 10;
		vector at = vehicle.GetOrigin();
		string otherId = "0";
		if (withVehicle)
			otherId = other.GetID().ToString();
		Print(string.Format("[ZCR][COLLISION] t=%1 side=%2 vehicle=%3 other=%4 other_side=%5 kmh=%6 damage=%7 driven=%8 x=%9", now, side,
			ZCR_LossLog.ShortName(vehicle), otherName, otherSide, Math.Round(kmh), Math.Round(damage), driven, Math.Round(at[0])) +
			string.Format(" z=%1 id=%2 other_id=%3", Math.Round(at[2]), vehicle.GetID(), otherId), LogLevel.NORMAL);
	}

	// Stuck alone: onto the nearest proper road, a few metres on toward the waypoint, facing along it.
	protected static bool OntoRoad(IEntity v, AIAgent driver, string side, int now)
	{
		// 22 Oct 05:31: OFF - w14, w16 and w19 crashed 7 s, 1.6 s and 0.6 s after a road recovery (LAV-25, LAV-25, an
		// unarmed UAZ-452 moved 28 m); back-off and park-aside ran for hours without one. -zcrRoadRecovery: on (to test).
		if (!System.IsCLIParam("zcrRoadRecovery"))
			return false;
		Vehicle vehicle = Vehicle.Cast(v);
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (!vehicle || !aiWorld || !aiWorld.GetRoadNetworkManager() || s_mRoads.Get(v) >= 4 || now - s_mBackAt.Get(v) < 30)
			return false;
		BaseWorld world = GetGame().GetWorld();
		vector mat[4];
		vehicle.GetWorldTransform(mat);
		vector at = mat[3];
		vector goal = at + mat[2] * 100;
		if (driver && driver.GetParentGroup() && driver.GetParentGroup().GetCurrentWaypoint())
			goal = driver.GetParentGroup().GetCurrentWaypoint().GetOrigin();
		array<BaseRoad> roads = {};
		aiWorld.GetRoadNetworkManager().GetRoadsInAABB(at - Vector(ROAD_M, 50, ROAD_M), at + Vector(ROAD_M, 50, ROAD_M), roads);
		float best = ROAD_M;
		vector bestA;
		vector bestB;
		vector bestQ;
		bool any;
		array<vector> points = {};
		foreach (BaseRoad road : roads)
		{
			if (!road || road.GetWidth() < ROAD_MIN_W)
				continue;
			points.Clear();
			road.GetPoints(points);
			for (int i = 0; i + 1 < points.Count(); i++)
			{
				vector a = points[i];
				vector b = points[i + 1];
				vector ab = b - a;
				ab[1] = 0;
				float len2 = ab[0] * ab[0] + ab[2] * ab[2];
				if (len2 < 0.01)
					continue;
				float f = Math.Clamp(((at[0] - a[0]) * ab[0] + (at[2] - a[2]) * ab[2]) / len2, 0, 1);
				vector q = a + (b - a) * f;
				float d = vector.DistanceXZ(q, at);
				if (d < best)
				{
					best = d;
					bestA = a;
					bestB = b;
					bestQ = q;
					any = true;
				}
			}
		}
		if (!any)
			return false;
		vector dir = bestB - bestA;
		dir[1] = 0;
		dir.Normalize();
		if (vector.DistanceXZ(bestQ - dir * 5, goal) < vector.DistanceXZ(bestQ + dir * 5, goal))
			dir = -dir;
		vector mins;
		vector maxs;
		vehicle.GetBounds(mins, maxs);
		array<float> steps = {4.0, 0.0, 9.0};
		foreach (float step : steps)
		{
			vector spot = bestQ + dir * step;
			// The road's own height - a bridge deck, not the gorge under it (Everon w11: a LAV-25 by a bridge).
			spot[1] = Math.Max(bestQ[1], world.GetSurfaceY(spot[0], spot[2]));
			if (VehicleAt(spot, 5, v) || ChimeraWorldUtils.TryGetWaterSurfaceSimple(world, spot - "0 0.5 0"))
				continue;
			vector pose[4];
			Math3D.DirectionAndUpMatrix(dir, "0 1 0", pose);
			pose[3] = spot + "0 0.6 0";
			// Nothing solid where the body would stand (rocks, walls, trees, other vehicles).
			TraceOBB body = new TraceOBB();
			for (int axis; axis < 3; axis++)
				body.Mat[axis] = pose[axis];
			body.Start = pose[3];
			body.Mins = Vector(mins[0], mins[1] + 0.5, mins[2]);
			body.Maxs = maxs;
			body.Flags = TraceFlags.ENTS;
			body.LayerMask = EPhysicsLayerPresets.Vehicle;
			body.Exclude = vehicle;
			if (world.TracePosition(body, null) < 0)
				continue;
			if (!SafeMove(vehicle, dir, pose[3], "unstick_road"))
				return false;
			s_mBackAt.Set(v, now);
			s_mRoads.Set(v, s_mRoads.Get(v) + 1);
			Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 action=road m=%4 count=%5 x=%6 z=%7", now, side, ZCR_LossLog.ShortName(v),
				Math.Round(vector.DistanceXZ(at, spot)), s_mRoads.Get(v), Math.Round(spot[0]), Math.Round(spot[2])), LogLevel.NORMAL);
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
		if (across.Length() < 0.1)
			return false;
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
			if (!SafeMove(vehicle, mat[2], spot, "unjam_park"))
				return false;
			Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 action=park m=%4 for=%5 x=%6 z=%7", now, side, ZCR_LossLog.ShortName(blocker),
				Math.AbsFloat(off), ZCR_LossLog.ShortName(jammed), Math.Round(spot[0]), Math.Round(spot[2])), LogLevel.NORMAL);
			return true;
		}
		return false;
	}

	// Every move by hand goes here (22 Oct: w7's park-aside and w14's road recovery were each followed by the engine
	// asserting on a bad matrix - in w14 a crash 7 s later): an upright pose from a flat heading, not a tipped-over
	// vehicle, nobody in or round it half through a door (a soldier getting in or out is attached to the vehicle mid
	// animation), and no NaN.
	protected static bool SafeMove(Vehicle vehicle, vector forward, vector at, string why)
	{
		vector mat[4];
		vehicle.GetWorldTransform(mat);
		if (mat[1][1] < 0.5 || Boarding(vehicle) || HasTurret(vehicle))
			return false;
		forward[1] = 0;
		if (forward.Length() < 0.1)
			return false;
		forward.Normalize();
		vector pose[4];
		Math3D.DirectionAndUpMatrix(forward, "0 1 0", pose);
		pose[3] = at;
		for (int row; row < 4; row++)
		{
			for (int col; col < 3; col++)
			{
				float value = pose[row][col];
				if (value != value || Math.AbsFloat(value) > 100000)
					return false;
			}
		}
		// The way the game's own Game Master moves a vehicle (SCR_EditableEntityComponent.SetTransformOwner): Teleport,
		// not a bare SetWorldTransform, then tell replication the node jumped - in the watched game (a listen server)
		// every vehicle is also interpolated for the local client; the headless stress server, with none, moved APCs
		// 35 times in 24 minutes without a crash where the watched matches crashed three times.
		vector previous = vehicle.GetOrigin();
		// 22 Oct evening: a physics push (ZCR_Push, JMVehicleAI's way) instead of the teleport; -zcrTeleportMoves for the old way.
		if (!System.IsCLIParam("zcrTeleportMoves"))
		{
			if (!ZCR_Push.Start(vehicle, at, why))
				return false;
			s_mMovedAt.Set(vehicle, ZCR_LossLog.Seconds());
			ZCR_Trace.Ent("push", vehicle, why);
			return true;
		}
		s_mMovedAt.Set(vehicle, ZCR_LossLog.Seconds());
		ZCR_Trace.Ent("move", vehicle, why);
		BaseGameEntity game = BaseGameEntity.Cast(vehicle);
		if (game)
			game.Teleport(pose);
		else if (!vehicle.SetWorldTransform(pose))
			return false;
		Physics physics = vehicle.GetPhysics();
		if (physics)
		{
			physics.SetVelocity(vector.Zero);
			physics.SetAngularVelocity(vector.Zero);
		}
		RplComponent rpl = RplComponent.Cast(vehicle.FindComponent(RplComponent));
		if (rpl)
			rpl.ForceNodeMovement(previous);
		return true;
	}

	// 22 Oct 05:06: vehicles with a turret were kept from hand moves after crashes that turned out to need the following
	// rule as well (now off). 10:30, experiment 4: with turret vehicles moved, 1 freeze in 6 matches (not seconds after a
	// move) and half the long stops and jams (2.8 and 2.0 a match against 5.9 and 5.3). Moved again by default;
	// -zcrNoMoveTurrets keeps them out.
	// 11:00: back to kept out - with turret vehicles moved, 2 of 8 matches failed (w42 froze, w50 crashed 7 s after a
	// BTR-70 back-off); with them kept out 0 of 13. -zcrMoveTurrets moves them (to test).
	protected static bool HasTurret(Vehicle vehicle)
	{
		if (System.IsCLIParam("zcrMoveTurrets"))
			return false;
		BaseCompartmentManagerComponent manager = BaseCompartmentManagerComponent.Cast(vehicle.FindComponent(BaseCompartmentManagerComponent));
		if (!manager)
			return false;
		array<BaseCompartmentSlot> slots = {};
		manager.GetCompartments(slots);
		foreach (BaseCompartmentSlot slot : slots)
		{
			if (TurretCompartmentSlot.Cast(slot))
				return true;
		}
		return false;
	}

	// Someone getting in or out of it: an occupant, or any soldier within 8 m.
	protected static bool Boarding(Vehicle vehicle)
	{
		BaseCompartmentManagerComponent manager = BaseCompartmentManagerComponent.Cast(vehicle.FindComponent(BaseCompartmentManagerComponent));
		if (manager)
		{
			array<BaseCompartmentSlot> slots = {};
			manager.GetCompartments(slots);
			foreach (BaseCompartmentSlot slot : slots)
			{
				if (slot && Transferring(slot.GetOccupant()))
					return true;
			}
		}
		s_aMen = {};
		GetGame().GetWorld().QueryEntitiesBySphere(vehicle.GetOrigin(), 8, CollectMan, null, EQueryEntitiesFlags.DYNAMIC);
		foreach (IEntity man : s_aMen)
		{
			if (Transferring(man))
				return true;
		}
		return false;
	}

	protected static bool Transferring(IEntity man)
	{
		if (!man)
			return false;
		CompartmentAccessComponent access = CompartmentAccessComponent.Cast(man.FindComponent(CompartmentAccessComponent));
		return access && (access.IsGettingIn() || access.IsGettingOut());
	}

	protected static ref array<IEntity> s_aMen;

	protected static bool CollectMan(IEntity e)
	{
		if (ChimeraCharacter.Cast(e))
			s_aMen.Insert(e);
		return true;
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

// [ZCR][COLLISION] (22 Oct, Martin: "they crash and block each other - is that trackable?"): a vehicle damaged in a
// collision - with another vehicle (other=, other_side=) or with something else (other=object). Once per vehicle and
// what it hit in 10 game s.
modded class SCR_VehicleDamageManagerComponent
{
	override protected void OnDamage(notnull BaseDamageContext damageContext)
	{
		super.OnDamage(damageContext);
		if (damageContext.damageType == EDamageType.COLLISION && Replication.IsServer())
			ZCR_Driving.Collision(GetOwner(), damageContext.damageSource, damageContext.damageValue, damageContext.impactVelocity.Length() * 3.6);
	}
}

// [ZCR][MOVEFAIL]: every failed group move in a vehicle (ZCR_Driving.MoveFailed).
modded class SCR_AIGroupUtilityComponent
{
	override void OnMoveFailed(int moveResult, IEntity vehicleUsed, bool isWaypointRelated, vector moveLocation)
	{
		ZCR_Driving.MoveFailed(moveResult, vehicleUsed, moveLocation);
		super.OnMoveFailed(moveResult, vehicleUsed, isWaypointRelated, moveLocation);
	}
}
