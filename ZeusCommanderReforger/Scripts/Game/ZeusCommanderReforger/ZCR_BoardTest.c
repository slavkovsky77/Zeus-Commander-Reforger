// The crash sub-lab's mass-boarding scenario (26 Oct - Martin, note 421: "short tests doing the same thing all over again
// we suspect is causing the crashes"; "mass board ... can be easily simulated"). The bad-matrix crash (enf_entity.cpp
// asserts, then bad memory) came ~40 s into a match while 5-6 rides boarded at once at the main bases, and only with the
// AI Conflict fork whose free pads let every ride spawn at the same moment (5 of 72 runs v 0 of 54). Here nothing else
// happens: count vehicles spawn in the same tick on pads 16 m apart, a team beside each, and every soldier is put into a
// seat at the same moment the way AI Conflict does it (AICF_VehicleBoardingFlow: the seat reserved, the game's
// SCR_AIGetInVehicle action), then they get out the way AI Conflict drops a team (AICF_VehicleWatchdog.
// ResetGroupVehicleActions + a get-out order), and again. Lab only, on a test map: -zcrBoardTest "x,z;count;mode[;kinds]"
//   mode spawnboard  every cycle the vehicles are deleted and spawned anew, boarded at once - the first ride wave
//        board       the same vehicles, boarded and emptied at once, again and again
//        calm        as board, but the get-out without the release/interrupt
//   kinds all (default) | cars (M998, UAZ-452, M1025, UAZ-469) | apc (LAV-25, BTR-70)
//   [ZCR][BOARDTEST] t= cycle= event=SPAWN|BOARD|ABOARD|DROP|OUT vehicles= soldiers= n= mode=
//   [ZCR][BOARDTEST_SUM] t= cycles= issued= seated= timeouts= mode=   (every 60 s)
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
	protected int m_iPhase;        // 0 waiting to board, 1 boarding, 2 aboard -> drop, 3 getting out, 4 rest
	protected int m_iPhaseAt;
	protected int m_iCycle;
	protected int m_iIssued, m_iSeated, m_iTimeouts, m_iNextSum;

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
		array<string> xz = {};
		f[0].Split(",", xz, true);
		s_Instance.m_vAt = Vector(xz[0].ToFloat(), 0, xz[1].ToFloat());
		s_Instance.m_iCount = f[1].ToInt();
		s_Instance.m_sMode = f[2];
		string kinds = "all";
		if (f.Count() > 3)
			kinds = f[3];
		s_Instance.Kinds(kinds);
		s_Instance.m_iPhase = -1;
		GetGame().GetCallqueue().CallLater(s_Instance.Begin, 3000, false);
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 500, true);
		Print(string.Format("[ZCR][BOARDTEST] start vehicles=%1 mode=%2 kinds=%3", s_Instance.m_iCount, s_Instance.m_sMode, kinds), LogLevel.NORMAL);
	}

	// The first ride wave's mix: light cars, armed cars and APCs of both sides, each with a team of its own side.
	protected void Kinds(string kinds)
	{
		if (kinds != "apc")
		{
			Add("{9B1BF9644E0378D6}Prefabs/Vehicles/Wheeled/M998/M998_covered_long.et", "{3BF36BDEEB33AEC9}Prefabs/Groups/BLUFOR/Group_US_SentryTeam.et");
			Add("{1FBB492E86002BF5}Prefabs/Vehicles/Wheeled/UAZ452/UAZ452_transport.et", "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et");
			Add("{428B2BC55F1628E0}Prefabs/Vehicles/Wheeled/Conflict_Variants/M1025_armed_M2HB_Conflict.et", "{3BF36BDEEB33AEC9}Prefabs/Groups/BLUFOR/Group_US_SentryTeam.et");
			Add("{0B4DEA8078B78A9B}Prefabs/Vehicles/Wheeled/UAZ469/UAZ469_PKM.et", "{CB58D90EA14430AD}Prefabs/Groups/OPFOR/Group_USSR_SentryTeam.et");
		}
		if (kinds != "cars")
		{
			Add("{590E677BBCD1D26E}Prefabs/Vehicles/Wheeled/Conflict_Variants/LAV25_Conflict.et", "{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et");
			Add("{BD75A18920BD1278}Prefabs/Vehicles/Wheeled/Conflict_Variants/BTR70_Conflict.et", "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et");
		}
	}

	protected void Add(string car, string team)
	{
		m_aCars.Insert(car);
		m_aTeamPrefabs.Insert(team);
	}

	// The pads: rows of four, 16 m apart (AI Conflict's free pads kept 20 m from a reserved one; its spawns came 16-28 m apart).
	protected vector Pad(int i)
	{
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
			if (since >= 3 && soldiers > 0)
				Board(now, soldiers);
		}
		else if (m_iPhase == 1)
		{
			if (aboard >= soldiers || since >= 45)
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
				if (m_sMode == "spawnboard" && aboard == 0)
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
			foreach (BaseCompartmentSlot s : seats)
			{
				if (s && s.GetType() == ECompartmentType.PILOT)
					order.Insert(s);
			}
			foreach (BaseCompartmentSlot s : seats)
			{
				if (s && s.GetType() == ECompartmentType.TURRET)
					order.Insert(s);
			}
			foreach (BaseCompartmentSlot s : seats)
			{
				if (s && s.GetType() == ECompartmentType.CARGO)
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

	protected void Log(int now, string what, int soldiers, int n)
	{
		Print(string.Format("[ZCR][BOARDTEST] t=%1 cycle=%2 event=%3 soldiers=%4 n=%5 mode=%6", now, m_iCycle, what, soldiers, n, m_sMode), LogLevel.NORMAL);
	}
}
