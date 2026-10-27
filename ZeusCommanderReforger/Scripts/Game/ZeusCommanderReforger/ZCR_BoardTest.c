// The crash sub-lab's mass-boarding scenario (26 Oct - Martin, note 421: "short tests doing the same thing all over again
// we suspect is causing the crashes"; "mass board ... can be easily simulated"). The bad-matrix crash (enf_entity.cpp
// asserts, then bad memory) came ~40 s into a match while 5-6 rides boarded at once at the main bases, and only with the
// AI Conflict fork whose free pads let every ride spawn at the same moment (5 of 72 runs v 0 of 54). Here nothing else
// happens: count vehicles spawn in the same tick on pads 16 m apart, a team beside each, and every soldier is put into a
// seat at the same moment the way AI Conflict does it (AICF_VehicleBoardingFlow: the seat reserved, the game's
// SCR_AIGetInVehicle action), then they get out the way AI Conflict drops a team (AICF_VehicleWatchdog.
// ResetGroupVehicleActions + a get-out order), and again. Lab only, on a test map: -zcrBoardTest "x,z;count;mode[;kinds[;delay]]"
//   mode spawnboard  every cycle the vehicles are deleted and spawned anew, boarded at once - the first ride wave
//        board       the same vehicles, boarded and emptied at once, again and again
//        calm        as board, but the get-out without the release/interrupt
//        spawnboard_kill  as spawnboard, and a soldier killed while he climbs in, up to 3 a cycle
//        spawnboard_oneby as spawnboard, but per vehicle one soldier at a time (the next when the one before is in)
//        ..._crew / ..._cargo  only the driver and turret seats / only the back seats
//        ..._tpin / ..._tpout  in / out without the animation (the engine's teleport into and out of the seat)
//   kinds all (default) | cars | apc - US only (see Kinds) | apc_fight (LAV-25 + US squads beside BTR-70 + Soviet ones)
//   [ZCR][BOARDTEST] t= cycle= event=SPAWN|BOARD|ABOARD|DROP|OUT vehicles= soldiers= n= mode=
//   [ZCR][BOARDTEST_SUM] t= cycles= issued= seated= timeouts= mode=   (every 60 s)
//   [ZCR][BOARDTILT] t= cycle= i= x= z= pitch= roll=   (each vehicle when the board order goes out)
// The tilt sweep (27 Oct 03:50 - at what tilt does it start?): the first field may be a list of spots "x,z/x,z/..." (the
// vehicles go there instead of the pads), and mode "scan" lists even, clear spots by slope instead of a test:
//   [ZCR][SLOPESCAN] bin= x= z= slope= pitch= roll=   (bin = 3-deg steps; pitch/roll for a vehicle heading north)
class ZCR_BoardTest
{
	static const string GET_OUT = "{C40316EE26846CAB}Prefabs/AI/Waypoints/AIWaypoint_GetOut.et";
	protected static ref ZCR_BoardTest s_Instance;
	protected ref array<Vehicle> m_aVehicles = {};
	protected ref array<SCR_AIGroup> m_aTeams = {};
	protected ref array<string> m_aCars = {};
	protected ref array<string> m_aTeamPrefabs = {};
	protected vector m_vAt;
	protected int m_iCount;
	protected string m_sMode;
	protected int m_iBoardDelay = 3;   // s from the spawn to the board order (fifth field)
	protected int m_iPhase;        // 0 waiting to board, 1 boarding, 2 aboard -> drop, 3 getting out, 4 rest
	protected int m_iPhaseAt;
	protected int m_iCycle;
	protected int m_iIssued, m_iSeated, m_iTimeouts, m_iNextSum;
	protected int m_iKills, m_iKilledThisCycle, m_iNextKillAt;
	protected int m_iOffered = 1000;
	// "oneby" (Martin, 27 Oct: "they get stuck and run bumping into each other - they should go slowly one by one"): per
	// vehicle the next soldier's order only when the one before is in, or after 6 s.
	protected ref map<int, IEntity> m_mLast = new map<int, IEntity>();
	protected ref map<int, int> m_mLastAt = new map<int, int>();
	protected ref array<IEntity> m_aOrdered = {};
	protected ref array<BaseCompartmentSlot> m_aTaken = {};
	protected ref array<vector> m_aSpots = {};
	protected int m_iNear;

	static void Start()
	{
		string spec;
		if (s_Instance || !Replication.IsServer() || !System.GetCLIParam("zcrBoardTest", spec) || spec.IsEmpty())
			return;
		array<string> f = {};
		spec.Split(";", f, true);
		if (f.Count() < 3)
			return;
		s_Instance = new ZCR_BoardTest();
		array<string> spots = {};
		f[0].Split("/", spots, true);
		foreach (string spot : spots)
		{
			array<string> xz = {};
			spot.Split(",", xz, true);
			if (xz.Count() == 2)
				s_Instance.m_aSpots.Insert(Vector(xz[0].ToFloat(), 0, xz[1].ToFloat()));
		}
		if (s_Instance.m_aSpots.IsEmpty())
			return;
		s_Instance.m_vAt = s_Instance.m_aSpots[0];
		if (s_Instance.m_aSpots.Count() == 1)
			s_Instance.m_aSpots.Clear();        // one point: the pads beside it, as before
		s_Instance.m_iCount = f[1].ToInt();
		s_Instance.m_sMode = f[2];
		if (s_Instance.m_sMode == "scan")
		{
			GetGame().GetCallqueue().CallLater(s_Instance.Scan, 3000, false);
			return;
		}
		string kinds = "all";
		if (f.Count() > 3)
			kinds = f[3];
		s_Instance.Kinds(kinds);
		// Fifth field: seconds from the spawn to the board order (27 Oct: 60 of 60 runs crashed 4-6 s after the order given
		// 3 s after the spawn - is it climbing into a vehicle that just appeared?).
		if (f.Count() > 4)
			s_Instance.m_iBoardDelay = f[4].ToInt();
		s_Instance.m_iPhase = -1;
		GetGame().GetCallqueue().CallLater(s_Instance.Begin, 3000, false);
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 500, true);
		Print(string.Format("[ZCR][BOARDTEST] start vehicles=%1 mode=%2 kinds=%3", s_Instance.m_iCount, s_Instance.m_sMode, kinds), LogLevel.NORMAL);
	}

	// One side only (27 Oct, Martin watching the first window run: "they now fight each other" - the US and Soviet teams
	// side by side shot each other, so soldiers died mid-boarding). US vehicles and US teams, as one base's first ride wave:
	//   all  M998, M1025 M2, LAV-25   cars  M998, M1025 M2   apc  LAV-25 only
	protected void Kinds(string kinds)
	{
		// Cars only for "all" and "cars" (04:05: "!= apc" put US cars and teams beside the BTR-70s' Soviet squads - they fought).
		if (kinds == "all" || kinds == "cars")
		{
			Add("{9B1BF9644E0378D6}Prefabs/Vehicles/Wheeled/M998/M998_covered_long.et", "{3BF36BDEEB33AEC9}Prefabs/Groups/BLUFOR/Group_US_SentryTeam.et");
			Add("{428B2BC55F1628E0}Prefabs/Vehicles/Wheeled/Conflict_Variants/M1025_armed_M2HB_Conflict.et", "{3BF36BDEEB33AEC9}Prefabs/Groups/BLUFOR/Group_US_SentryTeam.et");
		}
		// "apc_fight": the one setup the first runs crashed in (27 Oct 23:58) - LAV-25s with US squads beside BTR-70s with
		// Soviet ones, so the squads shot each other while they boarded (Martin: "try to make it the way it crashed").
		// 03:30 which part of the APC (the battle fix run crashed after a LAV-25 on flat ground): the Conflict LAV-25 v the
		// plain one, and the BTR-70 (Conflict and plain) - one side each, so no fighting.
		if (kinds == "lav_plain")
		{
			Add("{0FBF8F010F81A4E5}Prefabs/Vehicles/Wheeled/LAV25/LAV25.et", "{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et");
			return;
		}
		if (kinds == "btr")
		{
			Add("{BD75A18920BD1278}Prefabs/Vehicles/Wheeled/Conflict_Variants/BTR70_Conflict.et", "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et");
			return;
		}
		// The vehicle or the soldiers? Each APC with the other side's squad (one side per test, so no fighting).
		if (kinds == "lav_ussr")
		{
			Add("{590E677BBCD1D26E}Prefabs/Vehicles/Wheeled/Conflict_Variants/LAV25_Conflict.et", "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et");
			return;
		}
		if (kinds == "btr_us")
		{
			Add("{BD75A18920BD1278}Prefabs/Vehicles/Wheeled/Conflict_Variants/BTR70_Conflict.et", "{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et");
			return;
		}
		if (kinds == "btr_plain")
		{
			Add("{C012BB3488BEA0C2}Prefabs/Vehicles/Wheeled/BTR70/BTR70.et", "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et");
			return;
		}
		if (kinds == "apc_fight")
		{
			Add("{590E677BBCD1D26E}Prefabs/Vehicles/Wheeled/Conflict_Variants/LAV25_Conflict.et", "{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et");
			Add("{BD75A18920BD1278}Prefabs/Vehicles/Wheeled/Conflict_Variants/BTR70_Conflict.et", "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et");
			return;
		}
		if (kinds != "cars")
			Add("{590E677BBCD1D26E}Prefabs/Vehicles/Wheeled/Conflict_Variants/LAV25_Conflict.et", "{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et");
	}

	protected void Add(string car, string team)
	{
		m_aCars.Insert(car);
		m_aTeamPrefabs.Insert(team);
	}

	// The pads: rows of four, 16 m apart (AI Conflict's free pads kept 20 m from a reserved one; its spawns came 16-28 m apart).
	protected vector Pad(int i)
	{
		if (!m_aSpots.IsEmpty())
		{
			vector q = m_aSpots[i % m_aSpots.Count()];
			q[1] = GetGame().GetWorld().GetSurfaceY(q[0], q[2]);
			return q;
		}
		int col = i % 4;
		int row = i / 4;
		float x = 16 * col;
		float z = 18 * row;
		vector p = m_vAt + Vector(x, 0, z);
		p[1] = GetGame().GetWorld().GetSurfaceY(p[0], p[2]);
		return p;
	}

	protected void Begin()
	{
		for (int i; i < m_iCount; i++)
		{
			vector at = Pad(i) + Vector(-7, 0, 0);
			at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]);
			EntitySpawnParams params = new EntitySpawnParams();
			params.TransformMode = ETransformMode.WORLD;
			params.Transform[3] = at;
			SCR_AIGroup team = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(Resource.Load(m_aTeamPrefabs[i % m_aTeamPrefabs.Count()]), GetGame().GetWorld(), params));
			m_aTeams.Insert(team);
		}
		SpawnVehicles();
	}

	// All in the same tick, as a base's free pads did at the start of a match.
	protected void SpawnVehicles()
	{
		int now = ZCR_LossLog.Seconds();
		m_aVehicles.Clear();
		for (int i; i < m_iCount; i++)
		{
			vector pose[4];
			Math3D.DirectionAndUpMatrix(Vector(0, 0, 1), "0 1 0", pose);
			pose[3] = Pad(i) + Vector(0, 0.5, 0);
			EntitySpawnParams params = new EntitySpawnParams();
			params.TransformMode = ETransformMode.WORLD;
			for (int axis; axis < 4; axis++)
				params.Transform[axis] = pose[axis];
			Vehicle v = Vehicle.Cast(GetGame().SpawnEntityPrefab(Resource.Load(m_aCars[i % m_aCars.Count()]), GetGame().GetWorld(), params));
			m_aVehicles.Insert(v);
		}
		m_iPhase = 0;
		m_iPhaseAt = now;
		Print(string.Format("[ZCR][BOARDTEST] t=%1 cycle=%2 event=SPAWN vehicles=%3", now, m_iCycle, m_aVehicles.Count()), LogLevel.NORMAL);
	}

	protected void Tick()
	{
		if (m_iPhase < 0)
			return;
		int now = ZCR_LossLog.Seconds();
		int since = now - m_iPhaseAt;
		int soldiers, aboard;
		Count(soldiers, aboard);
		if (m_iPhase == 0)
		{
			if (since >= m_iBoardDelay && soldiers > 0)
				Board(now, soldiers);
		}
		else if (m_iPhase == 1)
		{
			// "..._kill": a soldier killed while he climbs in, up to 3 a cycle (the crashed run's squads shot each other mid-boarding).
			if (m_sMode.Contains("kill") && m_iKilledThisCycle < 3 && now >= m_iNextKillAt && since >= 1)
				KillOneGettingIn(now);
			if (m_sMode.Contains("oneby"))
			{
				for (int k; k < m_aVehicles.Count(); k++)
				{
					IEntity last = m_mLast.Get(k);
					if (!last || CompartmentAccessComponent.GetVehicleIn(last) || !AICF_GroupRuntime.IsAliveCharacter(last) || now - m_mLastAt.Get(k) >= 6)
						m_iIssued += IssueNext(k, now);
				}
			}
			if (aboard >= Math.Min(soldiers, m_iOffered) || since >= BoardTimeout())
			{
				if (aboard < soldiers)
					m_iTimeouts++;
				m_iSeated += aboard;
				Log(now, "ABOARD", soldiers, aboard);
				m_iPhase = 2;
				m_iPhaseAt = now;
			}
		}
		else if (m_iPhase == 2)
		{
			if (since >= 4)
				Drop(now, soldiers, aboard);
		}
		else if (m_iPhase == 3)
		{
			if (aboard == 0 || since >= 30)
			{
				if (aboard > 0)
					m_iTimeouts++;
				Log(now, "OUT", soldiers, aboard);
				m_iPhase = 4;
				m_iPhaseAt = now;
			}
		}
		else if (m_iPhase == 4)
		{
			if (since >= 4)
			{
				m_iCycle++;
				m_iKilledThisCycle = 0;
				Refill();
				if (m_sMode.StartsWith("spawnboard") && aboard == 0)
				{
					foreach (Vehicle v : m_aVehicles)
					{
						if (v)
							RplComponent.DeleteRplEntity(v, false);
					}
					m_iPhase = -1;
					GetGame().GetCallqueue().CallLater(SpawnVehicles, 1500, false);
				}
				else
					Board(now, soldiers);
			}
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 60;
			Print(string.Format("[ZCR][BOARDTEST_SUM] t=%1 cycles=%2 issued=%3 seated=%4 timeouts=%5 mode=%6", now, m_iCycle, m_iIssued, m_iSeated,
				m_iTimeouts, m_sMode), LogLevel.NORMAL);
		}
	}

	protected void Count(out int soldiers, out int aboard)
	{
		soldiers = 0;
		aboard = 0;
		foreach (SCR_AIGroup team : m_aTeams)
		{
			if (!team)
				continue;
			array<AIAgent> agents = {};
			team.GetAgents(agents);
			foreach (AIAgent agent : agents)
			{
				IEntity man = agent.GetControlledEntity();
				if (!AICF_GroupRuntime.IsAliveCharacter(man))
					continue;
				soldiers++;
				if (CompartmentAccessComponent.GetVehicleIn(man))
					aboard++;
			}
		}
	}

	// Every soldier of every team at the same moment: a free seat reserved for him (driver, then gunner, then the back),
	// and the game's get-in action - AICF_VehicleBoardingFlow's two calls.
	protected void Board(int now, int soldiers)
	{
		LogTilt(now);
		if (m_sMode.Contains("oneby"))
		{
			m_mLast.Clear();
			m_mLastAt.Clear();
			m_aOrdered.Clear();
			m_aTaken.Clear();
			int first;
			for (int k; k < m_aVehicles.Count(); k++)
				first += IssueNext(k, now);
			m_iIssued += first;
			m_iPhase = 1;
			m_iPhaseAt = now;
			Log(now, "BOARD", soldiers, first);
			return;
		}
		int issued;
		for (int i; i < m_aTeams.Count() && i < m_aVehicles.Count(); i++)
		{
			SCR_AIGroup team = m_aTeams[i];
			Vehicle v = m_aVehicles[i];
			if (!team || !v)
				continue;
			SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(v.FindComponent(SCR_AIVehicleUsageComponent));
			if (usage && team.GetGroupUtilityComponent())
				team.GetGroupUtilityComponent().AddUsableVehicle(usage);
			BaseCompartmentManagerComponent seatsOf = BaseCompartmentManagerComponent.Cast(v.FindComponent(BaseCompartmentManagerComponent));
			if (!seatsOf)
				continue;
			array<BaseCompartmentSlot> seats = {};
			seatsOf.GetCompartments(seats);
			array<BaseCompartmentSlot> order = {};
			// "_crew" modes: only the driver's and turret seats; "_cargo": only the back.
			foreach (BaseCompartmentSlot s : seats)
			{
				if (s && s.GetType() == ECompartmentType.PILOT && !m_sMode.Contains("_cargo"))
					order.Insert(s);
			}
			foreach (BaseCompartmentSlot s : seats)
			{
				if (s && s.GetType() == ECompartmentType.TURRET && !m_sMode.Contains("_cargo"))
					order.Insert(s);
			}
			foreach (BaseCompartmentSlot s : seats)
			{
				if (s && s.GetType() == ECompartmentType.CARGO && !m_sMode.Contains("_crew"))
					order.Insert(s);
			}
			array<AIAgent> agents = {};
			team.GetAgents(agents);
			int next;
			foreach (AIAgent agent : agents)
			{
				IEntity man = agent.GetControlledEntity();
				if (!AICF_GroupRuntime.IsAliveCharacter(man) || CompartmentAccessComponent.GetVehicleIn(man))
					continue;
				while (next < order.Count() && order[next].GetOccupant())
					next++;
				if (next >= order.Count())
					break;
				BaseCompartmentSlot seat = order[next];
				next++;
				// "_tpin": straight into the seat, no walk to the door and no climbing animation (27 Oct 03:40: the crash
				// comes 2.5-9 s into the get-in, or in the get-out - is it the animation on a tilted APC?).
				if (m_sMode.Contains("_tpin"))
				{
					ChimeraCharacter who = ChimeraCharacter.Cast(man);
					if (who && who.GetCompartmentAccessComponent() && who.GetCompartmentAccessComponent().GetInVehicle(v, seat, true, -1, ECloseDoorAfterActions.INVALID, false))
						issued++;
					continue;
				}
				SCR_AIUtilityComponent utility = SCR_AIUtilityComponent.Cast(agent.FindComponent(SCR_AIUtilityComponent));
				if (!utility)
					continue;
				seat.SetReserved(man);
				EAICompartmentType role = EAICompartmentType.Cargo;
				if (seat.GetType() == ECompartmentType.PILOT)
					role = EAICompartmentType.Pilot;
				else if (seat.GetType() == ECompartmentType.TURRET)
					role = EAICompartmentType.Turret;
				SCR_AIGetInVehicle action = new SCR_AIGetInVehicle(utility, null, v, seat, role, SCR_AIActionBase.PRIORITY_BEHAVIOR_GET_IN_VEHICLE,
					SCR_AIActionBase.PRIORITY_LEVEL_NORMAL);
				utility.AddAction(action);
				issued++;
			}
		}
		m_iIssued += issued;
		m_iOffered = issued + Math.Max(0, AlreadyAboard());
		m_iPhase = 1;
		m_iPhaseAt = now;
		Log(now, "BOARD", soldiers, issued);
	}

	// AI Conflict's drop (AICF_VehicleDismountFlow.Begin -> AICF_VehicleWatchdog.ResetGroupVehicleActions, then a get-out).
	protected void Drop(int now, int soldiers, int aboard)
	{
		for (int i; i < m_aTeams.Count() && i < m_aVehicles.Count(); i++)
		{
			SCR_AIGroup team = m_aTeams[i];
			Vehicle v = m_aVehicles[i];
			if (!team || !v)
				continue;
			array<AIWaypoint> old = {};
			team.GetWaypoints(old);
			foreach (AIWaypoint w : old)
				team.RemoveWaypoint(w);
			if (m_sMode != "calm")
			{
				team.ReleaseCompartments();
				array<AIAgent> agents = {};
				team.GetAgents(agents);
				foreach (AIAgent agent : agents)
				{
					ChimeraCharacter man = ChimeraCharacter.Cast(agent.GetControlledEntity());
					if (!man || !man.GetCharacterController() || man.GetCharacterController().GetLifeState() == ECharacterLifeState.DEAD)
						continue;
					CompartmentAccessComponent access = man.GetCompartmentAccessComponent();
					if (access)
						access.InterruptVehicleActionQueue(true, true, true);
					// "_tpout": out of the seat without the animation, beside the vehicle.
					if (access && m_sMode.Contains("_tpout") && CompartmentAccessComponent.GetVehicleIn(man))
						access.GetOutVehicle(EGetOutType.TELEPORT, -1, ECloseDoorAfterActions.INVALID, false);
				}
			}
			EntitySpawnParams params = new EntitySpawnParams();
			params.TransformMode = ETransformMode.WORLD;
			params.Transform[3] = v.GetOrigin();
			SCR_BoardingWaypoint getOut = SCR_BoardingWaypoint.Cast(GetGame().SpawnEntityPrefabEx(GET_OUT, false, params: params));
			if (getOut)
			{
				getOut.SetAllowance(true, true, true);
				getOut.SetCompletionRadius(25);
				team.AddWaypoint(getOut);
			}
		}
		m_iPhase = 3;
		m_iPhaseAt = now;
		Log(now, "DROP", soldiers, aboard);
	}

	// The vehicles' tilt when the board order goes out (27 Oct: the crash comes in the get-in or the get-out of an APC on
	// Moss Hill's 17-21 deg hillside, never on the flat airport apron). Pitch: nose up +; roll: right side up +.
	protected void LogTilt(int now)
	{
		for (int i; i < m_aVehicles.Count(); i++)
		{
			Vehicle v = m_aVehicles[i];
			if (!v)
				continue;
			vector mat[4];
			v.GetWorldTransform(mat);
			vector right = mat[0];
			vector fwd = mat[2];
			vector pos = mat[3];
			float pitch = Math.Asin(Math.Clamp(fwd[1], -1, 1)) * Math.RAD2DEG;
			float roll = Math.Asin(Math.Clamp(right[1], -1, 1)) * Math.RAD2DEG;
			Print(string.Format("[ZCR][BOARDTILT] t=%1 cycle=%2 i=%3 x=%4 z=%5 pitch=%6 roll=%7", now, m_iCycle, i, Math.Round(pos[0]),
				Math.Round(pos[2]), Math.Round(pitch), Math.Round(roll)), LogLevel.NORMAL);
		}
	}

	// "scan": the island on a 12 m grid. A spot counts when the ground under a vehicle (7 x 3.5 m, heading north) is one
	// even plane (no corner over 0.35 m off it), dry, and nothing with a mesh stands within 7 m (trees, rocks, buildings;
	// terrain, roads and forest areas are skipped by size). Up to 16 spots per 3-deg bin, 40 m apart.
	protected void Scan()
	{
		BaseWorld world = GetGame().GetWorld();
		map<int, ref array<vector>> bins = new map<int, ref array<vector>>();
		int found;
		for (float x = 100; x < 4000; x += 12)
		{
			for (float z = 100; z < 4000; z += 12)
			{
				float h = world.GetSurfaceY(x, z);
				if (h < 2)
					continue;
				float gz = (world.GetSurfaceY(x, z + 3.5) - world.GetSurfaceY(x, z - 3.5)) / 7;
				float gx = (world.GetSurfaceY(x + 1.75, z) - world.GetSurfaceY(x - 1.75, z)) / 3.5;
				float worst = 0;
				for (int cx = -1; cx <= 1; cx += 2)
				{
					for (int cz = -1; cz <= 1; cz += 2)
					{
						float plane = h + gx * 1.75 * cx + gz * 3.5 * cz;
						worst = Math.Max(worst, Math.AbsFloat(world.GetSurfaceY(x + 1.75 * cx, z + 3.5 * cz) - plane));
					}
				}
				if (worst > 0.35)
					continue;
				float slope = Math.Atan2(Math.Sqrt(gx * gx + gz * gz), 1) * Math.RAD2DEG;
				int bin = Math.Floor(slope / 3);
				if (bin > 9)
					bin = 9;
				array<vector> list;
				if (!bins.Find(bin, list))
				{
					list = {};
					bins.Insert(bin, list);
				}
				if (list.Count() >= 16)
					continue;
				vector here = Vector(x, h, z);
				bool close;
				foreach (vector o : list)
				{
					if (vector.DistanceXZ(o, here) < 40)
					{
						close = true;
						break;
					}
				}
				if (close)
					continue;
				m_iNear = 0;
				world.QueryEntitiesBySphere(here, 7, CountNear, null, EQueryEntitiesFlags.ALL);
				if (m_iNear > 0)
					continue;
				list.Insert(here);
				found++;
				Print(string.Format("[ZCR][SLOPESCAN] bin=%1 x=%2 z=%3 slope=%4 pitch=%5 roll=%6", bin, Math.Round(x), Math.Round(z),
					Math.Round(slope * 10) / 10, Math.Round(Math.Atan2(gz, 1) * Math.RAD2DEG), Math.Round(Math.Atan2(gx, 1) * Math.RAD2DEG)), LogLevel.NORMAL);
			}
		}
		Print(string.Format("[ZCR][SLOPESCAN] done spots=%1", found), LogLevel.NORMAL);
	}

	protected bool CountNear(IEntity e)
	{
		if (!e || !e.GetVObject())
			return true;
		vector mins, maxs;
		e.GetWorldBounds(mins, maxs);
		if (vector.Distance(mins, maxs) > 60)
			return true;          // the terrain, a road, a forest area - not an obstacle
		m_iNear++;
		return true;
	}

	protected void KillOneGettingIn(int now)
	{
		foreach (SCR_AIGroup team : m_aTeams)
		{
			if (!team)
				continue;
			array<AIAgent> agents = {};
			team.GetAgents(agents);
			foreach (AIAgent agent : agents)
			{
				ChimeraCharacter man = ChimeraCharacter.Cast(agent.GetControlledEntity());
				if (!man || !AICF_GroupRuntime.IsAliveCharacter(man))
					continue;
				CompartmentAccessComponent access = man.GetCompartmentAccessComponent();
				if (!access || !access.IsGettingIn())
					continue;
				SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(man.FindComponent(SCR_DamageManagerComponent));
				if (!damage)
					continue;
				damage.SetHealthScaled(0);
				m_iKills++;
				m_iKilledThisCycle++;
				m_iNextKillAt = now + 2;
				Print(string.Format("[ZCR][BOARDTEST] t=%1 cycle=%2 event=KILL_GETTING_IN kills=%3 x=%4 z=%5", now, m_iCycle, m_iKills,
					Math.Round(man.GetOrigin()[0]), Math.Round(man.GetOrigin()[2])), LogLevel.NORMAL);
				return;
			}
		}
	}

	// A squad down to 2 is replaced by a fresh one beside its pad (the kill mode and the fight wear them down).
	protected void Refill()
	{
		for (int i; i < m_aTeams.Count(); i++)
		{
			SCR_AIGroup team = m_aTeams[i];
			int alive;
			if (team)
				alive = AICF_GroupRuntime.CountAliveAgents(team);
			if (alive > 2)
				continue;
			vector at = Pad(i) + Vector(-7, 0, 0);
			at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]);
			EntitySpawnParams params = new EntitySpawnParams();
			params.TransformMode = ETransformMode.WORLD;
			params.Transform[3] = at;
			m_aTeams[i] = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(Resource.Load(m_aTeamPrefabs[i % m_aTeamPrefabs.Count()]), GetGame().GetWorld(), params));
		}
	}

	// One soldier of vehicle i's team into its next free seat (driver, gunner, then the back) - AI Conflict's two calls.
	protected int IssueNext(int i, int now)
	{
		if (i >= m_aTeams.Count() || i >= m_aVehicles.Count())
			return 0;
		SCR_AIGroup team = m_aTeams[i];
		Vehicle v = m_aVehicles[i];
		if (!team || !v)
			return 0;
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(v.FindComponent(SCR_AIVehicleUsageComponent));
		if (usage && team.GetGroupUtilityComponent())
			team.GetGroupUtilityComponent().AddUsableVehicle(usage);
		BaseCompartmentManagerComponent seatsOf = BaseCompartmentManagerComponent.Cast(v.FindComponent(BaseCompartmentManagerComponent));
		if (!seatsOf)
			return 0;
		array<BaseCompartmentSlot> seats = {};
		seatsOf.GetCompartments(seats);
		BaseCompartmentSlot seat;
		array<ECompartmentType> types = {ECompartmentType.PILOT, ECompartmentType.TURRET, ECompartmentType.CARGO};
		foreach (ECompartmentType type : types)
		{
			foreach (BaseCompartmentSlot s : seats)
			{
				if (!seat && s && s.GetType() == type && !s.GetOccupant() && !m_aTaken.Contains(s))
					seat = s;
			}
		}
		if (!seat)
			return 0;
		array<AIAgent> agents = {};
		team.GetAgents(agents);
		foreach (AIAgent agent : agents)
		{
			IEntity man = agent.GetControlledEntity();
			if (!AICF_GroupRuntime.IsAliveCharacter(man) || CompartmentAccessComponent.GetVehicleIn(man) || m_aOrdered.Contains(man))
				continue;
			SCR_AIUtilityComponent utility = SCR_AIUtilityComponent.Cast(agent.FindComponent(SCR_AIUtilityComponent));
			if (!utility)
				continue;
			seat.SetReserved(man);
			EAICompartmentType role = EAICompartmentType.Cargo;
			if (seat.GetType() == ECompartmentType.PILOT)
				role = EAICompartmentType.Pilot;
			else if (seat.GetType() == ECompartmentType.TURRET)
				role = EAICompartmentType.Turret;
			SCR_AIGetInVehicle action = new SCR_AIGetInVehicle(utility, null, v, seat, role, SCR_AIActionBase.PRIORITY_BEHAVIOR_GET_IN_VEHICLE,
				SCR_AIActionBase.PRIORITY_LEVEL_NORMAL);
			utility.AddAction(action);
			m_aOrdered.Insert(man);
			m_aTaken.Insert(seat);
			m_mLast.Set(i, man);
			m_mLastAt.Set(i, now);
			return 1;
		}
		return 0;
	}

	// One by one takes longer: 75 s to board instead of 45.
	protected int BoardTimeout()
	{
		if (m_sMode.Contains("oneby"))
			return 75;
		return 45;
	}

	protected int AlreadyAboard()
	{
		int soldiers, aboard;
		Count(soldiers, aboard);
		return aboard;
	}

	protected int AboardOf(int i)
	{
		Vehicle v = m_aVehicles[i];
		if (!v || i >= m_aTeams.Count() || !m_aTeams[i])
			return 0;
		int inside;
		array<AIAgent> agents = {};
		m_aTeams[i].GetAgents(agents);
		foreach (AIAgent agent : agents)
		{
			IEntity man = agent.GetControlledEntity();
			if (AICF_GroupRuntime.IsAliveCharacter(man) && CompartmentAccessComponent.GetVehicleIn(man) == v)
				inside++;
		}
		return inside;
	}

	static bool Active()
	{
		return s_Instance != null;
	}

	// For the director's camera (Martin, 27 Oct: "can you show it to me in the window at least once?"): the vehicles in turn,
	// each while its team boards or gets out, with what is happening.
	protected int m_iCamTurn;

	static IEntity CameraUnit(out string label)
	{
		if (!s_Instance || s_Instance.m_aVehicles.IsEmpty())
			return null;
		int n = s_Instance.m_aVehicles.Count();
		// Getting out (the demo of Martin's wish - APCs one by one, cars at once): the vehicle with the most still aboard.
		if (s_Instance.m_iPhase == 3)
		{
			int most = -1;
			int best = -1;
			for (int j; j < n; j++)
			{
				if (!s_Instance.m_aVehicles[j])
					continue;
				int inside = s_Instance.AboardOf(j);
				if (inside > most)
				{
					most = inside;
					best = j;
				}
			}
			if (best >= 0)
				s_Instance.m_iCamTurn = (best - 1 + n) % n;
		}
		for (int k = 1; k <= n; k++)
		{
			int i = (s_Instance.m_iCamTurn + k) % n;
			Vehicle v = s_Instance.m_aVehicles[i];
			if (!v)
				continue;
			s_Instance.m_iCamTurn = i;
			int aboard, team;
			if (i < s_Instance.m_aTeams.Count() && s_Instance.m_aTeams[i])
			{
				array<AIAgent> agents = {};
				s_Instance.m_aTeams[i].GetAgents(agents);
				foreach (AIAgent agent : agents)
				{
					IEntity man = agent.GetControlledEntity();
					if (!AICF_GroupRuntime.IsAliveCharacter(man))
						continue;
					team++;
					if (CompartmentAccessComponent.GetVehicleIn(man) == v)
						aboard++;
				}
			}
			bool oneby = s_Instance.m_sMode.Contains("oneby");
			string boarding = "ALL BOARDING AT ONCE";
			if (oneby)
				boarding = "getting in one by one";
			string leaving = "getting out";
			if (ZCR_GetOutOrder.On())
				leaving = "getting out - APC one by one, cars at once";
			array<string> phase = {"waiting", boarding, "aboard", leaving, "out"};
			string what = "";
			if (s_Instance.m_iPhase >= 0 && s_Instance.m_iPhase < phase.Count())
				what = phase[s_Instance.m_iPhase];
			string title = "MASS BOARDING TEST";
			if (oneby)
				title = "BOARDING TEST";
			label = string.Format("%1 cycle %2 - %3: %4 of %5 aboard (%6)", title, s_Instance.m_iCycle, ZCR_LossLog.ShortName(v), aboard, team, what);
			return v;
		}
		return null;
	}

	protected void Log(int now, string what, int soldiers, int n)
	{
		Print(string.Format("[ZCR][BOARDTEST] t=%1 cycle=%2 event=%3 soldiers=%4 n=%5 mode=%6", now, m_iCycle, what, soldiers, n, m_sMode), LogLevel.NORMAL);
	}
}
