// The crash sub-lab's small scenario (26 Oct - Martin, note 421: "make a sub-lab reproducing the crash and try to fix it").
// The night's engine crashes (a bad entity matrix, then bad memory) came within 2 s of AI Conflict starting a dismount ~6x
// more often than by chance, and within 1 s of the engine resetting a soldier stuck getting into a vehicle ~4x; AI
// Conflict's dismount and its giving up on a ride both cut every team member's vehicle actions mid-animation
// (AICF_VehicleWatchdog.ResetGroupVehicleActions: ReleaseCompartments + InterruptVehicleActionQueue). Here rides do nothing
// else: count cars, each with a team, shuttle between A and a point ~400 m on and back - board, drive, drop the team, board
// again - about 20x a battle's boardings and dismounts. Lab only, -zcrBoardTest "ax,az;bx,bz;count;mode", mode:
//   getout_moving   the team is dropped 120 m short while the car still drives - AI Conflict's way (release, interrupt, get out)
//   getout_stopped  the car is stopped first (a move order where it is), then the same drop
//   board_abort     every boarding is cut 4 s after the order (members mid-animation), then ordered again; drops as calm
//   calm            stopped first, a get-out order only - no release, no interrupt (the control)
//   [ZCR][BOARDTEST] t= car= event=SPAWN|BOARD|BOARDED|ABORT|DROP|OUT|STUCK speed= aboard= ...
//   [ZCR][BOARDTEST_SUM] t= cars= boarded= drops= aborts= stuck=   (every 60 s)
class ZCR_BoardCar
{
	int m_iIndex;
	Vehicle m_Vehicle;
	SCR_AIGroup m_Group;
	int m_iState;          // 0 spawned, 1 boarding, 2 driving, 3 stopping, 4 getting out, 5 resting
	int m_iStateAt;
	bool m_bToB;
	bool m_bAborted;       // this boarding was already cut once
}

class ZCR_BoardTest
{
	static const string MOVE = "{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et";
	static const string GET_IN = "{8AD8C82346156494}Prefabs/AI/Waypoints/AIWaypoint_GetInSelected.et";
	static const string GET_OUT = "{C40316EE26846CAB}Prefabs/AI/Waypoints/AIWaypoint_GetOut.et";
	static const float DROP_M = 120;
	protected static ref ZCR_BoardTest s_Instance;
	protected ref array<ref ZCR_BoardCar> m_aCars = {};
	protected vector m_vA;
	protected vector m_vB;
	protected string m_sMode;
	protected int m_iBoarded, m_iDrops, m_iAborts, m_iStuck, m_iNextSum;

	static void Start()
	{
		string spec;
		if (s_Instance || !Replication.IsServer() || !System.GetCLIParam("zcrBoardTest", spec) || spec.IsEmpty())
			return;
		array<string> f = {};
		spec.Split(";", f, true);
		if (f.Count() < 4)
			return;
		s_Instance = new ZCR_BoardTest();
		s_Instance.m_vA = Point(f[0]);
		s_Instance.m_vB = Point(f[1]);
		s_Instance.m_sMode = f[3];
		int count = f[2].ToInt();
		for (int i; i < count; i++)
			GetGame().GetCallqueue().CallLater(s_Instance.Spawn, 2000 + i * 3000, false, i);
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 500, true);
		Print(string.Format("[ZCR][BOARDTEST] start cars=%1 mode=%2", count, s_Instance.m_sMode), LogLevel.NORMAL);
	}

	protected static vector Point(string xz)
	{
		array<string> p = {};
		xz.Split(",", p, true);
		vector v = Vector(p[0].ToFloat(), 0, p[1].ToFloat());
		v[1] = GetGame().GetWorld().GetSurfaceY(v[0], v[2]);
		return v;
	}

	// A mix of AI Conflict's rides: light and armed cars, an APC; US and Soviet, each team of its own side.
	protected void Spawn(int i)
	{
		array<string> cars = {"{9B1BF9644E0378D6}Prefabs/Vehicles/Wheeled/M998/M998_covered_long.et",
			"{1FBB492E86002BF5}Prefabs/Vehicles/Wheeled/UAZ452/UAZ452_transport.et",
			"{428B2BC55F1628E0}Prefabs/Vehicles/Wheeled/Conflict_Variants/M1025_armed_M2HB_Conflict.et",
			"{0B4DEA8078B78A9B}Prefabs/Vehicles/Wheeled/UAZ469/UAZ469_PKM.et",
			"{590E677BBCD1D26E}Prefabs/Vehicles/Wheeled/Conflict_Variants/LAV25_Conflict.et",
			"{BD75A18920BD1278}Prefabs/Vehicles/Wheeled/Conflict_Variants/BTR70_Conflict.et"};
		array<string> teams = {"{3BF36BDEEB33AEC9}Prefabs/Groups/BLUFOR/Group_US_SentryTeam.et",
			"{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et",
			"{3BF36BDEEB33AEC9}Prefabs/Groups/BLUFOR/Group_US_SentryTeam.et",
			"{CB58D90EA14430AD}Prefabs/Groups/OPFOR/Group_USSR_SentryTeam.et",
			"{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et",
			"{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et"};
		int k = i % cars.Count();
		vector dir = m_vB - m_vA;
		dir[1] = 0;
		dir.Normalize();
		vector side = Vector(-dir[2], 0, dir[0]);
		int col = i % 4;
		int row = i / 4;
		float across = 12 * col - 18;
		float back = 14 * row;
		vector at = m_vA + side * across - dir * back;
		at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]) + 0.5;
		vector pose[4];
		Math3D.DirectionAndUpMatrix(dir, "0 1 0", pose);
		pose[3] = at;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		for (int axis; axis < 4; axis++)
			params.Transform[axis] = pose[axis];
		Vehicle vehicle = Vehicle.Cast(GetGame().SpawnEntityPrefab(Resource.Load(cars[k]), GetGame().GetWorld(), params));
		params.Transform[3] = at + side * 6;
		SCR_AIGroup group = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(Resource.Load(teams[k]), GetGame().GetWorld(), params));
		if (!vehicle || !group)
			return;
		ZCR_BoardCar car = new ZCR_BoardCar();
		car.m_iIndex = i + 1;
		car.m_Vehicle = vehicle;
		car.m_Group = group;
		car.m_bToB = true;
		car.m_iStateAt = ZCR_LossLog.Seconds();
		m_aCars.Insert(car);
		Print(string.Format("[ZCR][BOARDTEST] t=%1 car=%2 event=SPAWN vehicle=%3", ZCR_LossLog.Seconds(), car.m_iIndex, ZCR_LossLog.ShortName(vehicle)), LogLevel.NORMAL);
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		foreach (ZCR_BoardCar car : m_aCars)
		{
			if (!car.m_Vehicle || !car.m_Group)
				continue;
			Step(car, now);
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 60;
			Print(string.Format("[ZCR][BOARDTEST_SUM] t=%1 cars=%2 boarded=%3 drops=%4 aborts=%5 stuck=%6 mode=%7", now, m_aCars.Count(), m_iBoarded,
				m_iDrops, m_iAborts, m_iStuck, m_sMode), LogLevel.NORMAL);
		}
	}

	protected void Step(ZCR_BoardCar car, int now)
	{
		int since = now - car.m_iStateAt;
		int alive = AICF_GroupRuntime.CountAliveAgents(car.m_Group);
		int aboard = Aboard(car);
		float speed;
		if (car.m_Vehicle.GetPhysics())
			speed = car.m_Vehicle.GetPhysics().GetVelocity().Length();
		vector goal = m_vA;
		if (car.m_bToB)
			goal = m_vB;
		float toGoal = vector.DistanceXZ(car.m_Vehicle.GetOrigin(), goal);
		if (car.m_iState == 0)
		{
			if (since >= 3 && alive > 0)
				Board(car, now);
		}
		else if (car.m_iState == 1)
		{
			if (alive > 0 && aboard >= alive)
			{
				m_iBoarded++;
				Log(car, now, "BOARDED", speed, aboard);
				Drive(car, goal, now);
			}
			else if (m_sMode == "board_abort" && !car.m_bAborted && since >= 4)
			{
				// Cut the boarding mid-way, as AI Conflict does when it gives up on a ride - then order it again.
				m_iAborts++;
				car.m_bAborted = true;
				Interrupt(car);
				Log(car, now, "ABORT", speed, aboard);
				Board(car, now);
			}
			else if (since >= 90)
			{
				m_iStuck++;
				Log(car, now, "STUCK", speed, aboard);
				Board(car, now);
			}
		}
		else if (car.m_iState == 2)
		{
			if (toGoal <= DROP_M || since >= 240)
			{
				if (m_sMode == "getout_moving")
					Drop(car, now, speed, aboard);
				else
				{
					Clear(car);
					AddWaypoint(car, MOVE, car.m_Vehicle.GetOrigin());   // stop where it is
					car.m_iState = 3;
					car.m_iStateAt = now;
				}
			}
		}
		else if (car.m_iState == 3)
		{
			if (speed < 1 || since >= 20)
				Drop(car, now, speed, aboard);
		}
		else if (car.m_iState == 4)
		{
			if (aboard == 0 || since >= 60)
			{
				Log(car, now, "OUT", speed, aboard);
				car.m_iState = 5;
				car.m_iStateAt = now;
				car.m_bToB = !car.m_bToB;
			}
		}
		else if (car.m_iState == 5)
		{
			if (since >= 8)
				Board(car, now);
		}
	}

	protected int Aboard(ZCR_BoardCar car)
	{
		array<AIAgent> agents = {};
		car.m_Group.GetAgents(agents);
		int n;
		foreach (AIAgent agent : agents)
		{
			IEntity man = agent.GetControlledEntity();
			if (man && CompartmentAccessComponent.GetVehicleIn(man) == car.m_Vehicle)
				n++;
		}
		return n;
	}

	protected void Board(ZCR_BoardCar car, int now)
	{
		Clear(car);
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(car.m_Vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (usage && car.m_Group.GetGroupUtilityComponent())
			car.m_Group.GetGroupUtilityComponent().AddUsableVehicle(usage);
		SCR_BoardingEntityWaypoint board = SCR_BoardingEntityWaypoint.Cast(Waypoint(GET_IN, car.m_Vehicle.GetOrigin()));
		if (board)
		{
			board.SetEntity(car.m_Vehicle);
			board.SetCompletionRadius(25);
			car.m_Group.AddWaypoint(board);
		}
		if (car.m_iState != 1)
			car.m_bAborted = false;
		car.m_iState = 1;
		car.m_iStateAt = now;
		Log(car, now, "BOARD", 0, Aboard(car));
	}

	protected void Drive(ZCR_BoardCar car, vector goal, int now)
	{
		Clear(car);
		AddWaypoint(car, MOVE, goal);
		car.m_iState = 2;
		car.m_iStateAt = now;
	}

	// AI Conflict's dismount (AICF_VehicleDismountFlow.Begin): the group's vehicle actions reset, then a get-out order.
	protected void Drop(ZCR_BoardCar car, int now, float speed, int aboard)
	{
		m_iDrops++;
		Clear(car);
		if (m_sMode != "calm")
			Interrupt(car);
		SCR_BoardingWaypoint getOut = SCR_BoardingWaypoint.Cast(Waypoint(GET_OUT, car.m_Vehicle.GetOrigin()));
		if (getOut)
		{
			getOut.SetAllowance(true, true, true);
			getOut.SetCompletionRadius(25);
			car.m_Group.AddWaypoint(getOut);
		}
		car.m_iState = 4;
		car.m_iStateAt = now;
		Log(car, now, "DROP", speed, aboard);
	}

	// AICF_VehicleWatchdog.ResetGroupVehicleActions, line for line.
	protected void Interrupt(ZCR_BoardCar car)
	{
		car.m_Group.ReleaseCompartments();
		array<AIAgent> agents = {};
		car.m_Group.GetAgents(agents);
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

	protected void Clear(ZCR_BoardCar car)
	{
		array<AIWaypoint> old = {};
		car.m_Group.GetWaypoints(old);
		foreach (AIWaypoint w : old)
			car.m_Group.RemoveWaypoint(w);
	}

	protected void AddWaypoint(ZCR_BoardCar car, string prefab, vector at)
	{
		AIWaypoint w = Waypoint(prefab, at);
		if (w)
			car.m_Group.AddWaypoint(w);
	}

	protected AIWaypoint Waypoint(string prefab, vector at)
	{
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]);
		params.Transform[3] = at;
		return AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx(prefab, false, params: params));
	}

	protected void Log(ZCR_BoardCar car, int now, string what, float speed, int aboard)
	{
		Print(string.Format("[ZCR][BOARDTEST] t=%1 car=%2 event=%3 speed=%4 aboard=%5 mode=%6 x=%7 z=%8", now, car.m_iIndex, what,
			Math.Round(speed * 10) / 10, aboard, m_sMode, Math.Round(car.m_Vehicle.GetOrigin()[0]), Math.Round(car.m_Vehicle.GetOrigin()[2])), LogLevel.NORMAL);
	}
}
