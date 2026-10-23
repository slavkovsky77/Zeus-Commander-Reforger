// Traffic simulation (23 Oct night, Martin: "can that test also run supply runs - actually simulate transporting soldiers
// and supplies just by many cars, a traffic simulation"). Lab only, inert without the switch:
//   -zcrTrafficSim "x,z;x,z;x,z;..."  stops on one map (snapped to the nearest road)
//   -zcrTrafficCars N                 vehicles on the roads at once (default 8)
//   -zcrTrafficKinds "uaz,ural,uralsupply"  by turns: uaz (UAZ-452 van, 1 soldier beside the driver), ural (Ural troop
//                                     truck, 8 soldiers in the back), uralsupply (the same truck with supplies, nobody in the
//                                     back); US: m998 (3 soldiers), m923 (8), m923supply. One side only - mixed sides would fight.
// Each vehicle drives to a random other stop, stands there 10 s (loading: held at 0 km/h with its next order already
// given - a group left without a waypoint gets out, the drive test's "crew out near B"; 20 s was long enough for the
// game's driver to call itself STUCK with other cars at the same stop and the crew got out), and drives on. A lost vehicle
// (crew dead or out, destroyed, gone) stays where it is, as in a match; a new one starts at a stop 30 s later (2x N at most).
//   [ZCR][TRAFFICSIM] t= car= event=SPAWN|DELIVER|LOST kind= from= to= s= km= kmh= why= x= z=
//   [ZCR][TRAFFICSIM_SUM] t= cars= deliveries= km= lost= median_kmh=   (every 60 s; km driven by all, kmh stop to stop)
class ZCR_SimCar
{
	int m_iIndex;
	string m_sKind;
	Vehicle m_Vehicle;
	SCR_AIGroup m_Group;
	AIWaypoint m_Waypoint;
	int m_iFrom;
	int m_iTo;
	int m_iLegStart;
	int m_iSpawnedAt;
	int m_iLoadUntil;     // standing at a stop until then (0 = driving)
	bool m_bLost;
	int m_iOutSince;      // the driver out of the seat since (0 = in); lost after 20 s (a gate opened by hand)
	float m_fMeters;
	vector m_vLast;
	int m_iAboard;        // soldiers in the back
}

class ZCR_TrafficSim
{
	protected static ref ZCR_TrafficSim s_Instance;
	protected ref array<vector> m_aStops = {};
	protected ref array<ref ZCR_SimCar> m_aCars = {};
	protected ref array<string> m_aKinds = {};
	protected ref array<int> m_aKmh = {};
	protected int m_iCount = 8;
	protected int m_iNextSpawn = 15;
	protected int m_iNextSum = 60;
	protected int m_iDeliveries;
	protected int m_iLost;
	protected float m_fMeters;
	protected bool m_bSnapped;
	protected int m_iCamTurn;
	protected static const int LOAD_S = 10;
	protected static const string USSR_CREW = "{9FFEF10757E742EB}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_Crew.et";
	protected static const string US_CREW = "{E1CB513B8B9B08F4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_Crew.et";

	static void Start()
	{
		string spec;
		if (s_Instance || !Replication.IsServer() || !System.GetCLIParam("zcrTrafficSim", spec) || spec.IsEmpty())
			return;
		ZCR_TrafficSim sim = new ZCR_TrafficSim();
		array<string> parts = {};
		spec.Split(";", parts, true);
		foreach (string p : parts)
		{
			array<string> xz = {};
			p.Split(",", xz, true);
			if (xz.Count() >= 2)
				sim.m_aStops.Insert(Vector(xz[0].ToFloat(), 0, xz[1].ToFloat()));
		}
		string value;
		if (System.GetCLIParam("zcrTrafficCars", value) && !value.IsEmpty())
			sim.m_iCount = Math.Max(1, value.ToInt());
		string kinds = "uaz,ural,uralsupply";
		if (System.GetCLIParam("zcrTrafficKinds", value) && !value.IsEmpty())
			kinds = value;
		kinds.Split(",", sim.m_aKinds, true);
		if (sim.m_aStops.Count() < 2 || sim.m_aKinds.IsEmpty())
		{
			Print("[ZCR][TRAFFICSIM] needs two stops or more", LogLevel.WARNING);
			return;
		}
		s_Instance = sim;
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	static bool Active()
	{
		return s_Instance != null;
	}

	protected static string Prefab(string kind)
	{
		if (kind == "ural" || kind == "uralsupply")
			return "{16C1F16C9B053801}Prefabs/Vehicles/Wheeled/Ural4320/Ural4320_transport.et";
		if (kind == "m998")
			return "{9B1BF9644E0378D6}Prefabs/Vehicles/Wheeled/M998/M998_covered_long.et";
		if (kind == "m923" || kind == "m923supply")
			return "{F1FBD0972FA5FE09}Prefabs/Vehicles/Wheeled/M923A1/M923A1_transport.et";
		return "{01F65EFB8D767A91}Prefabs/Vehicles/Wheeled/UAZ452/UAZ452_cargo.et";
	}

	// Supplies aboard (nobody in the back).
	protected static bool Truck(string kind)
	{
		return kind == "uralsupply" || kind == "m923supply";
	}

	protected static int Troops(string kind)
	{
		if (Truck(kind))
			return 0;
		if (kind == "ural" || kind == "m923")
			return 8;
		return 3;
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		ZCR_LabWeather.Apply();
		if (!m_bSnapped)
		{
			if (now < 10)
				return;
			string list = "";
			for (int i; i < m_aStops.Count(); i++)
			{
				m_aStops[i] = ZCR_DriveTest.OnRoad(m_aStops[i]);
				list += string.Format(" %1,%2", Math.Round(m_aStops[i][0]), Math.Round(m_aStops[i][2]));
			}
			m_bSnapped = true;
			Print(string.Format("[ZCR][TRAFFICSIM] t=%1 stops=%2 cars=%3 kinds=%4 at%5", now, m_aStops.Count(), m_iCount, m_aKinds.Count(), list), LogLevel.NORMAL);
		}
		int alive;
		foreach (ZCR_SimCar c : m_aCars)
		{
			if (!c.m_bLost)
				alive++;
		}
		if (alive < m_iCount && m_aCars.Count() < 2 * m_iCount && now >= m_iNextSpawn)
		{
			Spawn(now);
			m_iNextSpawn = now + 8;
		}
		foreach (ZCR_SimCar car : m_aCars)
		{
			if (car.m_bLost)
				continue;
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
				m_iLost++;
				m_iNextSpawn = Math.Max(m_iNextSpawn, now + 30);
				vector lostAt;
				if (car.m_Vehicle)
					lostAt = car.m_Vehicle.GetOrigin();
				Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=LOST kind=%3 from=%4 to=%5 why=%6 km=%7 x=%8 z=%9", now, car.m_iIndex, car.m_sKind,
					car.m_iFrom + 1, car.m_iTo + 1, Why(car), Math.Round(car.m_fMeters / 100) / 10, Math.Round(lostAt[0]), Math.Round(lostAt[2])), LogLevel.NORMAL);
				continue;
			}
			vector at = car.m_Vehicle.GetOrigin();
			float step = vector.DistanceXZ(at, car.m_vLast);
			if (step < 60)
			{
				car.m_fMeters += step;
				m_fMeters += step;
			}
			car.m_vLast = at;
			if (car.m_iLoadUntil > 0)
			{
				if (now >= car.m_iLoadUntil)
				{
					car.m_iLoadUntil = 0;
					car.m_iLegStart = now;
					ZCR_Traffic.Release(car.m_Vehicle, "load");
				}
				continue;
			}
			if (vector.DistanceXZ(at, m_aStops[car.m_iTo]) > 30)
				continue;
			int legS = Math.Max(1, now - car.m_iLegStart);
			float km = vector.DistanceXZ(m_aStops[car.m_iFrom], m_aStops[car.m_iTo]) / 1000;
			int kmh = Math.Round(km * 3600 / legS);
			m_aKmh.Insert(kmh);
			m_iDeliveries++;
			string cargo = string.Format("soldiers=%1", car.m_iAboard);
			if (Truck(car.m_sKind))
				cargo = "supplies=1";
			Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=DELIVER kind=%3 from=%4 to=%5 s=%6 km=%7 kmh=%8 %9", now, car.m_iIndex, car.m_sKind,
				car.m_iFrom + 1, car.m_iTo + 1, legS, Math.Round(km * 10) / 10, kmh, cargo), LogLevel.NORMAL);
			// Loading: the next order now (a group without a waypoint gets out), the car held still for LOAD_S.
			car.m_iFrom = car.m_iTo;
			car.m_iTo = NextStop(car.m_iFrom);
			car.m_iLoadUntil = now + LOAD_S;
			ZCR_Traffic.Limit(car.m_Vehicle, "load", 0);
			Order(car);
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 60;
			array<int> kmhs = {};
			kmhs.Copy(m_aKmh);
			kmhs.Sort();
			int median = -1;
			if (!kmhs.IsEmpty())
				median = kmhs[kmhs.Count() / 2];
			Print(string.Format("[ZCR][TRAFFICSIM_SUM] t=%1 cars=%2 deliveries=%3 km=%4 lost=%5 median_kmh=%6", now, alive, m_iDeliveries,
				Math.Round(m_fMeters / 100) / 10, m_iLost, median), LogLevel.NORMAL);
		}
	}

	protected int NextStop(int from)
	{
		int next = Math.RandomInt(0, m_aStops.Count() - 1);
		if (next >= from)
			next++;
		return next;
	}

	protected void Spawn(int now)
	{
		int index = m_aCars.Count();
		string kind = m_aKinds[index % m_aKinds.Count()];
		// Start at the stop with the fewest cars near it.
		int from;
		int fewest = 1000;
		for (int s; s < m_aStops.Count(); s++)
		{
			int near;
			foreach (ZCR_SimCar o : m_aCars)
			{
				if (o.m_Vehicle && vector.DistanceXZ(o.m_Vehicle.GetOrigin(), m_aStops[s]) < 40)
					near++;
			}
			if (near < fewest)
			{
				fewest = near;
				from = s;
			}
		}
		if (fewest > 0)
			return;   // every stop has a car on it: wait
		int to = NextStop(from);
		vector dir = m_aStops[to] - m_aStops[from];
		dir[1] = 0;
		dir.Normalize();
		vector pose[4];
		Math3D.DirectionAndUpMatrix(dir, "0 1 0", pose);
		pose[3] = m_aStops[from] + "0 0.5 0";
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		for (int axis; axis < 4; axis++)
			params.Transform[axis] = pose[axis];
		Vehicle vehicle = Vehicle.Cast(GetGame().SpawnEntityPrefab(Resource.Load(Prefab(kind)), GetGame().GetWorld(), params));
		if (!vehicle)
			return;
		string crew = USSR_CREW;
		if (kind.StartsWith("m9"))
			crew = US_CREW;
		AIGroup group;
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(vehicle, seats);
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (seat && seat.GetType() == ECompartmentType.PILOT && !seat.GetOccupant())
			{
				seat.SpawnCharacterInCompartment(crew, group);
				break;
			}
		}
		ZCR_SimCar car = new ZCR_SimCar();
		car.m_iIndex = index + 1;
		car.m_sKind = kind;
		car.m_Vehicle = vehicle;
		car.m_Group = SCR_AIGroup.Cast(group);
		car.m_iFrom = from;
		car.m_iTo = to;
		car.m_iSpawnedAt = now;
		car.m_iLegStart = now;
		car.m_vLast = vehicle.GetOrigin();
		// Soldiers in the back (the supply trucks carry none): the driver's group, so they ride along.
		if (group)
		{
			foreach (BaseCompartmentSlot back : seats)
			{
				if (car.m_iAboard >= Troops(kind))
					break;
				if (back && back.GetType() == ECompartmentType.CARGO && !back.GetOccupant())
				{
					back.SpawnCharacterInCompartment(crew, group);
					car.m_iAboard++;
				}
			}
		}
		m_aCars.Insert(car);
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (car.m_Group && usage && car.m_Group.GetGroupUtilityComponent() && !car.m_Group.GetGroupUtilityComponent().IsUsableVehicle(usage))
			car.m_Group.GetGroupUtilityComponent().AddUsableVehicle(usage);
		Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=SPAWN kind=%3 from=%4 to=%5 aboard=%6 crew=%7", now, car.m_iIndex, kind, from + 1, to + 1,
			car.m_iAboard, car.m_Group != null), LogLevel.NORMAL);
		Order(car);
	}

	protected void Order(ZCR_SimCar car)
	{
		if (!car.m_Group)
			return;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = m_aStops[car.m_iTo];
		AIWaypoint waypoint = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", false, params: params));
		if (!waypoint)
			return;
		waypoint.SetCompletionRadius(8);   // inside the 30-m arrival check, so the order never runs out before the next one
		car.m_Group.AddWaypoint(waypoint);
		if (car.m_Waypoint)
		{
			car.m_Group.RemoveWaypoint(car.m_Waypoint);
			RplComponent.DeleteRplEntity(car.m_Waypoint, false);
		}
		car.m_Waypoint = waypoint;
	}

	protected static bool Driven(ZCR_SimCar car)
	{
		array<AIAgent> agents = {};
		car.m_Group.GetAgents(agents);
		foreach (AIAgent agent : agents)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (!c || !c.IsInVehicle() || CompartmentAccessComponent.GetVehicleIn(c) != car.m_Vehicle)
				continue;
			BaseCompartmentSlot seat = c.GetCompartmentAccessComponent().GetCompartment();
			if (seat && seat.GetType() == ECompartmentType.PILOT)
				return true;
		}
		return false;
	}

	protected static string Why(ZCR_SimCar car)
	{
		if (!car.m_Vehicle)
			return "vehicle_gone";
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(car.m_Vehicle.FindComponent(SCR_DamageManagerComponent));
		if (damage && damage.GetState() == EDamageState.DESTROYED)
			return "vehicle_destroyed";
		if (!car.m_Group)
			return "group_gone";
		if (AICF_GroupRuntime.CountAliveAgents(car.m_Group) == 0)
			return "all_dead";
		return "crew_out";
	}

	// For the watch camera: by turns, each car that is driving (not loading).
	static IEntity CameraCar(out string label)
	{
		if (!s_Instance || s_Instance.m_aCars.IsEmpty())
			return null;
		int now = ZCR_LossLog.Seconds();
		for (int i; i < s_Instance.m_aCars.Count(); i++)
		{
			s_Instance.m_iCamTurn++;
			ZCR_SimCar c = s_Instance.m_aCars[s_Instance.m_iCamTurn % s_Instance.m_aCars.Count()];
			if (c.m_bLost || !c.m_Vehicle || c.m_iLoadUntil > 0)
				continue;
			string cargo = string.Format("%1 soldiers", c.m_iAboard);
			if (Truck(c.m_sKind))
				cargo = "supplies";
			label = string.Format("TRAFFIC: CAR %1 (%2, %3) stop %4 -> %5, %6 s - %7 deliveries so far", c.m_iIndex, c.m_sKind, cargo, c.m_iFrom + 1,
				c.m_iTo + 1, now - c.m_iLegStart, s_Instance.m_iDeliveries);
			return c.m_Vehicle;
		}
		return null;
	}
}
