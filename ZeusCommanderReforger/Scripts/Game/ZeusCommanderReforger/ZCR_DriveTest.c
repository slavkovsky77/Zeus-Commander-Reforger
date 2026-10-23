// The driving test track (22 Oct, Martin: "if you know where the bug happens on Moss Hill, do a simple scenario that
// reproduces it ... to optimise it faster"). Lab only, -zcrDriveTest "ax,az;bx,bz;count[;kind[;vx,vz[;both]]]": count crewed
// vehicles (kind m998, uaz, ural or m923 trucks; "both": every second car starts at B, so they meet head-on on the way)
// (kind m998 - the US M998, default - or uaz - the USSR UAZ-452) leave A one at a time, 12 s apart, and drive A -> B ->
// A ... on the game's own routes, through V both ways when given (a waypoint on the trap itself, so the route can't
// go round it). A, B and V are snapped to the nearest road. Every vehicle is watched by ZCR_Driving like
// any other ([ZCR][JAM] / [STUCKVEH] / [MOVEFAIL] / [PUSH] / [OFFROAD]), so a fix can be tried on the same stretch in
// minutes instead of waiting for a match to send rides through it.
//   [ZCR][DRIVETEST] t= car= event=SPAWN|ARRIVE|LOST leg= leg_s= to= x= z=
//   [ZCR][DRIVETEST_SUM] t= cars= legs= median_leg_s= max_leg_s= open_legs= oldest_open_s=   (every 60 s)
// Sixth field "convoy" instead of "both" (23 Oct night, Martin: "convoy test would be great too"): the cars leave A as one
// convoy, 2 s apart with the start clear, drive to B and are taken off the map there; when every car of the convoy has
// arrived or is lost (or after 10 minutes) the next convoy leaves.  [ZCR][DRIVETEST] event=CONVOY convoy= cars= arrived= lost= first_s= last_s=
// Seventh field "blast" (Martin: "they would meet and one of them would explode, so we see how the other direction
// reacts to the blocked road"; "spawn one drone that would kill one ... maybe a convoy and the front one"): the first car
// within 25 m of the via point is hit by a mortar-shell warhead and its crew killed - a wreck on the lane, cleared a minute
// later like in matches (ZCR_Wrecks; -zcrKeepWrecks keeps it). Head-on: a hit every 150 s; convoy: the lead of convoys
// 1, 3, 5 ... (the others drive the clear road, for comparison). Every car that meets the wreck (within 40 m, the wreck
// between it and its goal) is followed until it is past:
//   [ZCR][DRIVETEST] event=BLAST car= convoy= x= z=  /  event=PASSWRECK car= s= wreck_there=0|1  /  event=BLOCKED car= s=  (120 s, not past)
//   /  event=WRECK_GONE s=
class ZCR_DriveCar
{
	int m_iIndex;
	Vehicle m_Vehicle;
	SCR_AIGroup m_Group;
	AIWaypoint m_Waypoint;
	AIWaypoint m_Via;
	bool m_bToB;
	int m_iLeg;
	int m_iLegStart;
	int m_iSpawnedAt;
	bool m_bLost;
	int m_iOutSince;        // the driver out of the seat since (0 = in)
	int m_iWaterLogged;     // last [ZCR][WATER] line
	int m_iConvoy = 1;
	bool m_bDone;           // convoy: arrived at B and taken off the map
	int m_iArrivedAt;
	bool m_bBlasted;
	int m_iNearWreckAt;     // first second within 40 m of the wreck, with the wreck between it and its goal
	bool m_bPastWreck;
	bool m_bBlockedLogged;
}

class ZCR_DriveTest
{
	protected static ref ZCR_DriveTest s_Instance;
	protected ref array<ref ZCR_DriveCar> m_aCars = {};
	protected ref array<int> m_aLegs = {};
	protected vector m_vA;
	protected vector m_vB;
	protected vector m_vVia;
	protected int m_iCount = 6;
	protected bool m_bBoth;
	protected string m_sPrefab = "{9B1BF9644E0378D6}Prefabs/Vehicles/Wheeled/M998/M998_covered_long.et";
	protected string m_sCrew = "{E1CB513B8B9B08F4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_Crew.et";
	protected int m_iNextSpawn = 15;
	protected int m_iNextSum = 60;
	protected bool m_bConvoy;
	protected int m_iConvoy = 1;
	protected int m_iConvoySpawned;
	protected int m_iConvoyStart;
	protected bool m_bBlast;
	protected int m_iNextBlast;
	protected int m_iBlastConvoy;
	protected IEntity m_Wreck;
	protected vector m_vWreck;
	protected int m_iBlastAt = -1;
	protected bool m_bWreckGone;
	protected static const string WARHEAD = "{D584F2FFFDC7DE49}Prefabs/Weapons/Warheads/Warhead_Shell_HE.et";   // the mortar shell's

	static void Start()
	{
		if (s_Instance || !Replication.IsServer())
			return;
		string spec;
		if (!System.GetCLIParam("zcrDriveTest", spec) || spec.IsEmpty())
			return;
		array<string> parts = {};
		spec.Split(";", parts, true);
		if (parts.Count() < 2)
			return;
		s_Instance = new ZCR_DriveTest();
		s_Instance.m_vA = Point(parts[0]);
		s_Instance.m_vB = Point(parts[1]);
		if (parts.Count() > 2)
			s_Instance.m_iCount = Math.Max(1, parts[2].ToInt());
		if (parts.Count() > 4 && parts[4] != "-")
			s_Instance.m_vVia = Point(parts[4]);
		s_Instance.m_bBoth = parts.Count() > 5 && parts[5] == "both";
		s_Instance.m_bConvoy = parts.Count() > 5 && parts[5] == "convoy";
		s_Instance.m_bBlast = parts.Count() > 6 && parts[6] == "blast";
		string ussrCrew = "{9FFEF10757E742EB}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_Crew.et";
		if (parts.Count() > 3 && parts[3] == "uaz")
		{
			s_Instance.m_sPrefab = "{01F65EFB8D767A91}Prefabs/Vehicles/Wheeled/UAZ452/UAZ452_cargo.et";
			s_Instance.m_sCrew = ussrCrew;
		}
		else if (parts.Count() > 3 && parts[3] == "ural")
		{
			s_Instance.m_sPrefab = "{16C1F16C9B053801}Prefabs/Vehicles/Wheeled/Ural4320/Ural4320_transport.et";
			s_Instance.m_sCrew = ussrCrew;
		}
		else if (parts.Count() > 3 && parts[3] == "m923")
			s_Instance.m_sPrefab = "{F1FBD0972FA5FE09}Prefabs/Vehicles/Wheeled/M923A1/M923A1_transport.et";
		// Armour (Martin, 23 Oct: "this sub-lab should test some tanks and APCs"): the game's APCs, and the Workshop
		// tanks and IFVs (lab --armour; on 21 Oct the tanks crashed the game in 8-10 game minutes).
		else if (parts.Count() > 3 && parts[3] == "btr70")
		{
			s_Instance.m_sPrefab = "{C012BB3488BEA0C2}Prefabs/Vehicles/Wheeled/BTR70/BTR70.et";
			s_Instance.m_sCrew = ussrCrew;
		}
		else if (parts.Count() > 3 && parts[3] == "lav25")
			s_Instance.m_sPrefab = "{0FBF8F010F81A4E5}Prefabs/Vehicles/Wheeled/LAV25/LAV25.et";
		else if (parts.Count() > 3 && parts[3] == "t72")
		{
			s_Instance.m_sPrefab = "{726286E1F9570EA1}Prefabs/Vehicles/Tracked/T72B/T72B_Base.et";
			s_Instance.m_sCrew = ussrCrew;
		}
		else if (parts.Count() > 3 && parts[3] == "bmp1")
		{
			s_Instance.m_sPrefab = "{1DC01AAACFFA8B63}Prefabs/Vehicles/Tracked/BMP1/BMP1_Base.et";
			s_Instance.m_sCrew = ussrCrew;
		}
		else if (parts.Count() > 3 && parts[3] == "m1a1")
			s_Instance.m_sPrefab = "{E80B119CFDF50ABE}Prefabs/Vehicles/Tracked/M1A1/M1A1_Olive.et";
		else if (parts.Count() > 3 && parts[3] == "bradley")
			s_Instance.m_sPrefab = "{24223D0679CDD612}Prefabs/Vehicles/Tracked/M2A2/M2A2_OD.et";
		// The world's minefields across roads go, as in matches (AI Conflict's step, off with -aicfOff): on the Conflict map
		// the first cars hit TM-62M mines east of A in every run (review note 317).
		AICF_RoadMines.Start();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	protected static vector Point(string xz)
	{
		array<string> v = {};
		xz.Split(",", v, true);
		if (v.Count() < 2)
			return vector.Zero;
		return Vector(v[0].ToFloat(), 0, v[1].ToFloat());
	}

	// The road point nearest to p, on the ground; p itself without a road near.
	static vector OnRoad(vector p)
	{
		vector best = p;
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (aiWorld && aiWorld.GetRoadNetworkManager())
		{
			BaseRoad road;
			float distance;
			aiWorld.GetRoadNetworkManager().GetClosestRoad(p, road, distance, true);
			if (road && distance < 100)
			{
				array<vector> points = {};
				road.GetPoints(points);
				float d = 1e9;
				foreach (vector q : points)
				{
					if (vector.DistanceXZ(q, p) < d)
					{
						d = vector.DistanceXZ(q, p);
						best = q;
					}
				}
			}
		}
		best[1] = GetGame().GetWorld().GetSurfaceY(best[0], best[2]);
		return best;
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		ZCR_LabWeather.Apply();   // clear midday with -zcrLabWeather (the stock Conflict map starts at night)
		if (m_vA[1] == 0 && now >= 10)
		{
			m_vA = OnRoad(m_vA);
			m_vB = OnRoad(m_vB);
			if (m_vVia != vector.Zero)
				m_vVia = OnRoad(m_vVia);
			Print(string.Format("[ZCR][DRIVETEST] t=%1 track a=%2,%3 b=%4,%5 straight_m=%6 cars=%7 prefab=%8", now, Math.Round(m_vA[0]), Math.Round(m_vA[2]),
				Math.Round(m_vB[0]), Math.Round(m_vB[2]), Math.Round(vector.DistanceXZ(m_vA, m_vB)), m_iCount, m_sPrefab), LogLevel.NORMAL);
		}
		bool wantCar = m_aCars.Count() < m_iCount;
		if (m_bConvoy)
			wantCar = m_iConvoySpawned < m_iCount;
		if (wantCar && now >= m_iNextSpawn && m_vA[1] != 0)
		{
			// One at a time and only with the start clear - like a base sending its rides out.
			if (!StartBusy())
				Spawn(now);
			m_iNextSpawn = now + 12;
			if (m_bConvoy)
				m_iNextSpawn = now + 2;
		}
		if (m_bBlast)
			BlastTick(now);
		foreach (ZCR_DriveCar car : m_aCars)
		{
			if (car.m_bLost || car.m_bDone)
				continue;
			// The driver is seated a moment after the spawn: the "crew out" check waits 10 s (23 Oct: both test cars were
			// marked lost in the second they spawned). Out of the seat counts after 20 s: a driver may get out to open a
			// gate and back in (the get-out probe, 23 Oct night).
			bool seatLeft = now - car.m_iSpawnedAt > 10 && car.m_Vehicle && car.m_Group && !Driven(car);
			if (!seatLeft)
				car.m_iOutSince = 0;
			else if (car.m_iOutSince == 0)
				car.m_iOutSince = now;
			if (seatLeft && now - car.m_iOutSince <= 20)
				continue;
			if (!car.m_Vehicle || !car.m_Group || AICF_GroupRuntime.CountAliveAgents(car.m_Group) == 0 || seatLeft)
			{
				car.m_bLost = true;
				vector at;
				if (car.m_Vehicle)
					at = car.m_Vehicle.GetOrigin();
				Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=LOST leg=%3 why=%4 x=%5 z=%6", now, car.m_iIndex, car.m_iLeg, LostWhy(car),
					Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
				continue;
			}
			Water(car, now);
			vector target = m_vA;
			if (car.m_bToB)
				target = m_vB;
			if (vector.DistanceXZ(car.m_Vehicle.GetOrigin(), target) > 30)
				continue;
			int legS = now - car.m_iLegStart;
			m_aLegs.Insert(legS);
			Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=ARRIVE leg=%3 leg_s=%4 to=%5", now, car.m_iIndex, car.m_iLeg, legS, ToName(car.m_bToB)), LogLevel.NORMAL);
			if (m_bConvoy)
			{
				car.m_bDone = true;
				car.m_iArrivedAt = now;
				Remove(car);
				continue;
			}
			car.m_bToB = !car.m_bToB;
			Order(car, now);
		}
		if (m_bConvoy && m_iConvoySpawned >= m_iCount)
			ConvoyTick(now);
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 60;
			array<int> legs = {};
			legs.Copy(m_aLegs);
			legs.Sort();
			int median = -1;
			int longest = -1;
			if (!legs.IsEmpty())
			{
				median = legs[legs.Count() / 2];
				longest = legs[legs.Count() - 1];
			}
			int open, oldest;
			foreach (ZCR_DriveCar c : m_aCars)
			{
				if (c.m_bLost || c.m_bDone)
					continue;
				open++;
				oldest = Math.Max(oldest, now - c.m_iLegStart);
			}
			Print(string.Format("[ZCR][DRIVETEST_SUM] t=%1 cars=%2 legs=%3 median_leg_s=%4 max_leg_s=%5 open_legs=%6 oldest_open_s=%7", now, m_aCars.Count(),
				m_aLegs.Count(), median, longest, open, oldest), LogLevel.NORMAL);
		}
	}

	// For the watch camera (22 Oct: on the test map the director had no teams to show - a black picture): the car to
	// follow - one within 200 m of the trap first, else the next car in turn.
	protected int m_iCamTurn;

	static bool Active()
	{
		return s_Instance != null;
	}

	static IEntity CameraCar(out string label)
	{
		if (!s_Instance)
			return null;
		ZCR_DriveCar pick;
		float best = 200;
		int now = ZCR_LossLog.Seconds();
		if (s_Instance.m_iBlastAt >= 0 && !s_Instance.m_bWreckGone && now - s_Instance.m_iBlastAt < 150)
		{
			float nearM = 150;
			foreach (ZCR_DriveCar w : s_Instance.m_aCars)
			{
				if (w.m_bLost || w.m_bDone || !w.m_Vehicle || vector.DistanceXZ(w.m_Vehicle.GetOrigin(), s_Instance.m_vWreck) >= nearM)
					continue;
				nearM = vector.DistanceXZ(w.m_Vehicle.GetOrigin(), s_Instance.m_vWreck);
				pick = w;
			}
			if (pick)
			{
				label = string.Format("TEST CAR %1 - ROAD BLOCKED BY A WRECK (hit %2 s ago), %3 m from it", pick.m_iIndex, now - s_Instance.m_iBlastAt, Math.Round(nearM));
				return pick.m_Vehicle;
			}
		}
		if (s_Instance.m_vVia != vector.Zero)
		{
			foreach (ZCR_DriveCar c : s_Instance.m_aCars)
			{
				if (c.m_bLost || c.m_bDone || !c.m_Vehicle)
					continue;
				float d = vector.DistanceXZ(c.m_Vehicle.GetOrigin(), s_Instance.m_vVia);
				if (d < best)
				{
					best = d;
					pick = c;
				}
			}
		}
		for (int i; !pick && i < s_Instance.m_aCars.Count(); i++)
		{
			s_Instance.m_iCamTurn++;
			ZCR_DriveCar next = s_Instance.m_aCars[s_Instance.m_iCamTurn % s_Instance.m_aCars.Count()];
			if (!next.m_bLost && !next.m_bDone && next.m_Vehicle)
				pick = next;
		}
		if (!pick)
			return null;
		string where = "";
		if (pick.m_Vehicle && s_Instance.m_vVia != vector.Zero && vector.DistanceXZ(pick.m_Vehicle.GetOrigin(), s_Instance.m_vVia) < 200)
			where = " - AT THE MOSS HILL TRAP";
		string who = "TEST CAR";
		if (s_Instance.m_bConvoy)
			who = string.Format("CONVOY %1, CAR", pick.m_iConvoy);
		label = string.Format("%1 %2 to %3, leg %4, %5 s%6", who, pick.m_iIndex, ToName(pick.m_bToB), pick.m_iLeg, now - pick.m_iLegStart, where);
		return pick.m_Vehicle;
	}

	// The driver still in the driver's seat (a crew that got out leaves the car standing - lost too).
	protected static bool Driven(ZCR_DriveCar car)
	{
		array<AIAgent> agents = {};
		car.m_Group.GetAgents(agents);
		foreach (AIAgent agent : agents)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (c && c.IsInVehicle() && CompartmentAccessComponent.GetVehicleIn(c) == car.m_Vehicle)
				return true;
		}
		return false;
	}

	protected static string LostWhy(ZCR_DriveCar car)
	{
		if (!car.m_Vehicle)
			return "vehicle_gone";
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(car.m_Vehicle.FindComponent(SCR_DamageManagerComponent));
		if (damage && damage.GetState() == EDamageState.DESTROYED)
			return "vehicle_destroyed";
		if (!car.m_Group)
			return "group_gone";
		if (AICF_GroupRuntime.CountAliveAgents(car.m_Group) == 0)
			return "driver_dead";
		return "crew_out";
	}

	protected bool StartBusy()
	{
		float clear = 10;
		if (m_bConvoy)
			clear = 15;
		foreach (ZCR_DriveCar c : m_aCars)
		{
			if (c.m_bDone)
				continue;
			if (c.m_Vehicle && (vector.DistanceXZ(c.m_Vehicle.GetOrigin(), m_vA) < clear || (m_bBoth && vector.DistanceXZ(c.m_Vehicle.GetOrigin(), m_vB) < clear)))
				return true;
		}
		return false;
	}

	protected static string ToName(bool toB)
	{
		if (toB)
			return "B";
		return "A";
	}

	protected void Spawn(int now)
	{
		// "both": every second car starts at B heading for A.
		bool fromB = m_bBoth && m_aCars.Count() % 2 == 1;
		vector start = m_vA;
		vector goal = m_vB;
		if (fromB)
		{
			start = m_vB;
			goal = m_vA;
		}
		vector dir = goal - start;
		dir[1] = 0;
		dir.Normalize();
		vector pose[4];
		Math3D.DirectionAndUpMatrix(dir, "0 1 0", pose);
		pose[3] = start + "0 0.5 0";
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		for (int axis; axis < 4; axis++)
			params.Transform[axis] = pose[axis];
		Vehicle vehicle = Vehicle.Cast(GetGame().SpawnEntityPrefab(Resource.Load(m_sPrefab), GetGame().GetWorld(), params));
		if (!vehicle)
			return;
		AIGroup group;
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(vehicle, seats);
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (seat && seat.GetType() == ECompartmentType.PILOT && !seat.GetOccupant())
			{
				seat.SpawnCharacterInCompartment(m_sCrew, group);
				break;
			}
		}
		ZCR_DriveCar car = new ZCR_DriveCar();
		car.m_iIndex = m_aCars.Count() + 1;
		car.m_Vehicle = vehicle;
		car.m_Group = SCR_AIGroup.Cast(group);
		car.m_bToB = !fromB;
		car.m_iSpawnedAt = now;
		car.m_iConvoy = m_iConvoy;
		if (m_bConvoy)
		{
			if (m_iConvoySpawned == 0)
				m_iConvoyStart = now;
			m_iConvoySpawned++;
		}
		m_aCars.Insert(car);
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (car.m_Group && usage && car.m_Group.GetGroupUtilityComponent() && !car.m_Group.GetGroupUtilityComponent().IsUsableVehicle(usage))
			car.m_Group.GetGroupUtilityComponent().AddUsableVehicle(usage);
		Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=SPAWN prefab=%3 crew=%4 x=%5 z=%6 convoy=%7", now, car.m_iIndex, ZCR_LossLog.ShortName(vehicle),
			car.m_Group != null, Math.Round(pose[3][0]), Math.Round(pose[3][2]), car.m_iConvoy), LogLevel.NORMAL);
		Order(car, now);
	}

	// Under water (23 Oct night: on the Conflict map drivers died where the route crosses water east of A, with no killer -
	// the game's drowning). A car whose body is under water logs every 10 s: [ZCR][WATER] t= car= depth= x= z=
	protected void Water(ZCR_DriveCar car, int now)
	{
		if (now - car.m_iWaterLogged < 10)
			return;
		vector at = car.m_Vehicle.GetOrigin();
		vector surface;
		EWaterSurfaceType type;
		vector transform[4];
		vector extents;
		if (!ChimeraWorldUtils.TryGetWaterSurface(GetGame().GetWorld(), at + "0 0.5 0", surface, type, transform, extents))
			return;
		car.m_iWaterLogged = now;
		Print(string.Format("[ZCR][WATER] t=%1 car=%2 depth=%3 x=%4 z=%5", now, car.m_iIndex, Math.Round((surface[1] - at[1]) * 10) / 10, Math.Round(at[0]),
			Math.Round(at[2])), LogLevel.NORMAL);
	}

	// Convoy: every car of this convoy arrived or lost (or 10 minutes gone) - the summary, then the next convoy.
	protected void ConvoyTick(int now)
	{
		int arrived, lost, open;
		int first = -1;
		int last = -1;
		bool blasted;
		foreach (ZCR_DriveCar c : m_aCars)
		{
			if (c.m_iConvoy != m_iConvoy)
				continue;
			if (c.m_bBlasted)
				blasted = true;
			else if (c.m_bDone)
			{
				arrived++;
				if (first < 0)
					first = c.m_iArrivedAt - m_iConvoyStart;
				last = Math.Max(last, c.m_iArrivedAt - m_iConvoyStart);
			}
			else if (c.m_bLost)
				lost++;
			else
				open++;
		}
		if (open > 0 && now - m_iConvoyStart < 600)
			return;
		Print(string.Format("[ZCR][DRIVETEST] t=%1 event=CONVOY convoy=%2 cars=%3 arrived=%4 lost=%5 open=%6 blast=%7 first_s=%8 last_s=%9", now, m_iConvoy,
			m_iConvoySpawned, arrived, lost, open, blasted, first, last), LogLevel.NORMAL);
		m_iConvoy++;
		m_iConvoySpawned = 0;
		m_iNextSpawn = now + 15;
	}

	// Convoy cars at B leave the map (crew first, the car a second later), so the next convoy finds the road and B clear.
	protected void Remove(ZCR_DriveCar car)
	{
		array<IEntity> gone = {car.m_Waypoint, car.m_Via};
		if (car.m_Group)
		{
			foreach (IEntity w : gone)
			{
				if (AIWaypoint.Cast(w))
					car.m_Group.RemoveWaypoint(AIWaypoint.Cast(w));
			}
			array<AIAgent> agents = {};
			car.m_Group.GetAgents(agents);
			foreach (AIAgent agent : agents)
			{
				if (agent && agent.GetControlledEntity())
					gone.Insert(agent.GetControlledEntity());
			}
		}
		foreach (IEntity e : gone)
		{
			if (e)
				RplComponent.DeleteRplEntity(e, false);
		}
		if (car.m_Vehicle)
			GetGame().GetCallqueue().CallLater(DeleteLater, 1000, false, car.m_Vehicle);
	}

	protected static void DeleteLater(IEntity e)
	{
		if (e)
			RplComponent.DeleteRplEntity(e, false);
	}

	protected void BlastTick(int now)
	{
		if (m_vVia != vector.Zero && now >= m_iNextBlast && (!m_bConvoy || (m_iConvoy % 2 == 1 && m_iBlastConvoy != m_iConvoy)))
		{
			foreach (ZCR_DriveCar c : m_aCars)
			{
				if (c.m_bLost || c.m_bDone || !c.m_Vehicle || now - c.m_iSpawnedAt < 20 || (m_bConvoy && c.m_iConvoy != m_iConvoy))
					continue;
				if (vector.DistanceXZ(c.m_Vehicle.GetOrigin(), m_vVia) < 25)
				{
					Blast(c, now);
					break;
				}
			}
		}
		if (m_iBlastAt < 0)
			return;
		if (!m_bWreckGone && !m_Wreck)
		{
			m_bWreckGone = true;
			Print(string.Format("[ZCR][DRIVETEST] t=%1 event=WRECK_GONE s=%2", now, now - m_iBlastAt), LogLevel.NORMAL);
		}
		foreach (ZCR_DriveCar car : m_aCars)
		{
			if (car.m_bLost || car.m_bDone || !car.m_Vehicle || car.m_bPastWreck)
				continue;
			vector target = m_vA;
			if (car.m_bToB)
				target = m_vB;
			vector at = car.m_Vehicle.GetOrigin();
			float d = vector.DistanceXZ(at, m_vWreck);
			if (car.m_iNearWreckAt == 0)
			{
				if (!m_bWreckGone && d < 40 && vector.DistanceXZ(at, target) > vector.DistanceXZ(m_vWreck, target))
					car.m_iNearWreckAt = now;
				continue;
			}
			if (d > 30 && vector.DistanceXZ(at, target) < vector.DistanceXZ(m_vWreck, target) - 10)
			{
				car.m_bPastWreck = true;
				Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=PASSWRECK s=%3 wreck_there=%4", now, car.m_iIndex, now - car.m_iNearWreckAt, !m_bWreckGone), LogLevel.NORMAL);
			}
			else if (!car.m_bBlockedLogged && now - car.m_iNearWreckAt > 120)
			{
				car.m_bBlockedLogged = true;
				Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=BLOCKED s=%3 m=%4 x=%5 z=%6", now, car.m_iIndex, now - car.m_iNearWreckAt, Math.Round(d),
					Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
			}
		}
	}

	// The hit: a mortar-shell warhead set off over the car (the game's own explosion: damage, flash, sound, crater), then the
	// car and its crew made sure of - a burnt-out wreck on the lane, as a drone or a shell leaves one in a match.
	protected void Blast(ZCR_DriveCar car, int now)
	{
		vector at = car.m_Vehicle.GetOrigin();
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = at + "0 1.5 0";
		IEntity warhead = GetGame().SpawnEntityPrefab(Resource.Load(WARHEAD), GetGame().GetWorld(), params);
		BaseTriggerComponent trigger;
		if (warhead)
			trigger = BaseTriggerComponent.Cast(warhead.FindComponent(BaseTriggerComponent));
		if (trigger)
			trigger.OnUserTrigger(warhead);
		GetGame().GetCallqueue().CallLater(Wreck, 400, false, car.m_Vehicle);
		car.m_bLost = true;
		car.m_bBlasted = true;
		m_Wreck = car.m_Vehicle;
		m_vWreck = at;
		m_iBlastAt = now;
		m_bWreckGone = false;
		m_iNextBlast = now + 150;
		m_iBlastConvoy = m_iConvoy;
		foreach (ZCR_DriveCar c : m_aCars)
		{
			c.m_iNearWreckAt = 0;
			c.m_bPastWreck = false;
			c.m_bBlockedLogged = false;
		}
		Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=BLAST convoy=%3 warhead=%4 x=%5 z=%6", now, car.m_iIndex, car.m_iConvoy, trigger != null,
			Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
	}

	protected static void Wreck(IEntity vehicle)
	{
		if (!vehicle)
			return;
		IEntity child = vehicle.GetChildren();
		while (child)
		{
			SCR_DamageManagerComponent crew = SCR_DamageManagerComponent.Cast(child.FindComponent(SCR_DamageManagerComponent));
			if (ChimeraCharacter.Cast(child) && crew && !crew.IsDestroyed())
				crew.SetHealthScaled(0);
			child = child.GetSibling();
		}
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(vehicle.FindComponent(SCR_DamageManagerComponent));
		if (damage && !damage.IsDestroyed())
			damage.SetHealthScaled(0);
		ZCR_Wrecks.Add(vehicle);   // a minute later off the road, as in matches
	}

	protected void Order(ZCR_DriveCar car, int now)
	{
		if (!car.m_Group)
			return;
		vector target = m_vA;
		if (car.m_bToB)
			target = m_vB;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = target;
		AIWaypoint waypoint = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", false, params: params));
		if (!waypoint)
			return;
		// 8 m, inside the 30-m arrival check: at 20 m a car doing 50 km/h completed the order between two 1-s checks, stood
		// without one and its crew got out (the "crew_out near B" losses, 23 Oct).
		waypoint.SetCompletionRadius(8);
		AIWaypoint old = car.m_Waypoint;
		AIWaypoint oldVia = car.m_Via;
		car.m_Via = null;
		if (m_vVia != vector.Zero)
		{
			params.Transform[3] = m_vVia;
			car.m_Via = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", false, params: params));
			if (car.m_Via)
			{
				car.m_Via.SetCompletionRadius(12);
				car.m_Group.AddWaypoint(car.m_Via);
			}
		}
		car.m_Group.AddWaypoint(waypoint);
		array<AIWaypoint> gone = {old, oldVia};
		foreach (AIWaypoint w : gone)
		{
			if (!w)
				continue;
			car.m_Group.RemoveWaypoint(w);
			RplComponent.DeleteRplEntity(w, false);
		}
		car.m_Waypoint = waypoint;
		car.m_iLeg++;
		car.m_iLegStart = now;
	}
}

// On a test map (the game's Game Master missions) nothing else starts our driving code: the game mode starts it.
modded class SCR_BaseGameMode
{
	protected override void OnGameStart()
	{
		super.OnGameStart();
		if (Replication.IsServer() && (System.IsCLIParam("zcrDriveTest") || System.IsCLIParam("zcrTrafficSim") || System.IsCLIParam("zcrGunTest")))
			ZCR_Driving.Start();
	}
}
