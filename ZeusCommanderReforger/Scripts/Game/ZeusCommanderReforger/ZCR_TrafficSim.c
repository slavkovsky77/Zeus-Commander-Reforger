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
// Supply runs (23 Oct, Martin: "a supply run from A to B, several on the same map"; then: "no combination, that's too
// complicated, even real players don't act like that - either a supply run or manpower reinforcements"; "one of the
// trucks should pick up an infantry group somewhere where they want to be transported"):
//   -zcrTrafficShuttle      the first stop is the pickup (supply point / where the squad waits), the second the
//                           destination; the trucks start at the destination, drive to the pickup, load, drive back
//   kind uralsupply/m923supply  the supply run: the truck's supply container filled at the pickup, emptied at the destination
//   kind uralpickup/m923pickup  the manpower run: a rifle squad waits on foot beside the pickup; the truck stops there, the
//                           squad boards (the game's get-in-selected waypoint), the truck takes it to the destination,
//                           the squad gets out (delivered, then taken off the map); a new squad waits for the next truck
// While loading or boarding a test truck keeps its driver aboard (ZCR_CrewStays.Hold: a standing truck is "stuck" to the
// game, which orders the driver out).
//   Supplies are real: the truck's own supply container (the game's resource system, as AI Conflict's trucks carry them)
//   is filled to its maximum at A and emptied at B (Martin: "are supplies in the truck now? why are they not visible?" -
//   the game shows them as the vehicle's supply amount, not as crates).
//   [ZCR][TRAFFICSIM] t= car= event=UNLOAD men= supplies=   /   event=BOARD men= supplies=   /   _SUM ... men_delivered= supplies_delivered=
// Driver and passengers are seated 1.5 s after the truck appears (seated in the same frame, the watched game left them
// out); the passengers are a group of their own, as in the guns test's storm.
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
	SCR_AIGroup m_Riders; // the passengers' own group
	int m_iPickupAt;      // manpower: waiting at the pickup since (0 = not waiting)
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
	protected int m_iMenDelivered;
	protected ref array<SCR_AIGroup> m_aWaiting = {};   // manpower: squads waiting at the pickup
	protected float m_fSuppliesDelivered;
	protected bool m_bShuttle;
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
		sim.m_bShuttle = System.IsCLIParam("zcrTrafficShuttle");
		s_Instance = sim;
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	static bool Active()
	{
		return s_Instance != null;
	}

	protected static string Prefab(string kind)
	{
		if (kind == "ural" || kind == "uralsupply" || kind == "uralpickup")
			return "{16C1F16C9B053801}Prefabs/Vehicles/Wheeled/Ural4320/Ural4320_transport.et";
		if (kind == "m998")
			return "{9B1BF9644E0378D6}Prefabs/Vehicles/Wheeled/M998/M998_covered_long.et";
		if (kind == "m923" || kind == "m923supply" || kind == "m923pickup")
			return "{F1FBD0972FA5FE09}Prefabs/Vehicles/Wheeled/M923A1/M923A1_transport.et";
		return "{01F65EFB8D767A91}Prefabs/Vehicles/Wheeled/UAZ452/UAZ452_cargo.et";
	}

	// Supplies aboard.
	protected static bool Truck(string kind)
	{
		return kind == "uralsupply" || kind == "m923supply";
	}

	// The manpower run: picks up a waiting squad.
	protected static bool Pickup(string kind)
	{
		return kind == "uralpickup" || kind == "m923pickup";
	}

	protected static int Troops(string kind)
	{
		if (Truck(kind) || Pickup(kind))
			return 0;   // the supply trucks carry supplies; the pickup trucks the squad they collect
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
			if (now - car.m_iSpawnedAt <= 10)
				continue;   // the driver is seated 1.5 s after the truck appears
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
			// Where each truck is every 5 s in the supply runs (23 Oct: trucks lose 30-150 s turning round at the pickup).
			if (m_bShuttle && now % 5 == 0)
			{
				Physics body = car.m_Vehicle.GetPhysics();
				int kmhNow;
				if (body)
					kmhNow = Math.Round(body.GetVelocity().Length() * 3.6);
				vector fwd = car.m_Vehicle.GetTransformAxis(2);
				Print(string.Format("[ZCR][TRAFFICSIM_POS] t=%1 car=%2 x=%3 z=%4 kmh=%5 to=%6 head=%7 wait=%8", now, car.m_iIndex, Math.Round(at[0]), Math.Round(at[2]),
					kmhNow, car.m_iTo + 1, Math.Round(Math.Atan2(fwd[0], fwd[2]) * Math.RAD2DEG), car.m_iPickupAt > 0 || car.m_iLoadUntil > 0), LogLevel.NORMAL);
			}
			if (car.m_iPickupAt > 0)
			{
				Waiting(car, now);
				continue;
			}
			// One truck at the pickup at a time: the next waits 70 m short (23 Oct: two trucks 20 s apart boxed each other in
			// among the boarding squad - STUCK again and again).
			if (m_bShuttle && car.m_iTo == 0 && Pickup(car.m_sKind))
			{
				bool busy;
				foreach (ZCR_SimCar o : m_aCars)
				{
					// boarding, or boarded and still turning round there (23 Oct: the next truck arrived 10 s after the first
					// left - both STUCK, 2 minutes lost)
					if (o != car && !o.m_bLost && o.m_Vehicle && (o.m_iPickupAt > 0 || vector.DistanceXZ(o.m_Vehicle.GetOrigin(), m_aStops[0]) < 60))
						busy = true;
				}
				if (busy && vector.DistanceXZ(at, m_aStops[0]) < 70)
					ZCR_Traffic.Limit(car.m_Vehicle, "queue", 0);
				else
					ZCR_Traffic.Release(car.m_Vehicle, "queue");
			}
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
				cargo = string.Format("supplies=1 soldiers=%1", car.m_iAboard);
			Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=DELIVER kind=%3 from=%4 to=%5 s=%6 km=%7 kmh=%8 %9", now, car.m_iIndex, car.m_sKind,
				car.m_iFrom + 1, car.m_iTo + 1, legS, Math.Round(km * 10) / 10, kmh, cargo), LogLevel.NORMAL);
			if (m_bShuttle && car.m_iTo == 1)
				Unload(car, now);
			else if (m_bShuttle && car.m_iTo == 0 && Pickup(car.m_sKind))
			{
				// Waits here for a squad to board; leaves when they're aboard (Waiting).
				car.m_iFrom = 0;
				car.m_iTo = 1;
				car.m_iPickupAt = now;
				Call(car, now);
				continue;
			}
			else if (m_bShuttle && car.m_iTo == 0 && Truck(car.m_sKind))
				GetGame().GetCallqueue().CallLater(Board, 1500, false, car, false);
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
			Print(string.Format("[ZCR][TRAFFICSIM_SUM] t=%1 cars=%2 deliveries=%3 km=%4 lost=%5 median_kmh=%6 men_delivered=%7", now, alive, m_iDeliveries,
				Math.Round(m_fMeters / 100) / 10, m_iLost, median, m_iMenDelivered), LogLevel.NORMAL);
			Print(string.Format("[ZCR][TRAFFICSIM_SUPPLY] t=%1 supplies_delivered=%2", now, Math.Round(m_fSuppliesDelivered)), LogLevel.NORMAL);
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
		int to = NextStop(from);
		if (m_bShuttle)
		{
			// The destination: to the pickup first - once the last truck has left it (23 Oct: the second truck appeared
			// 2 m from the first and both stuck).
			from = 1;
			to = 0;
			fewest = 0;
			foreach (ZCR_SimCar o : m_aCars)
			{
				if (o.m_Vehicle && vector.DistanceXZ(o.m_Vehicle.GetOrigin(), m_aStops[1]) < 40)
					fewest++;
			}
		}
		if (fewest > 0)
			return;   // every stop has a car on it: wait
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
		ZCR_SimCar car = new ZCR_SimCar();
		car.m_iIndex = index + 1;
		car.m_sKind = kind;
		car.m_Vehicle = vehicle;
		car.m_iFrom = from;
		car.m_iTo = to;
		car.m_iSpawnedAt = now;
		car.m_iLegStart = now;
		car.m_vLast = vehicle.GetOrigin();
		m_aCars.Insert(car);
		Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=SPAWN kind=%3 from=%4 to=%5", now, car.m_iIndex, kind, from + 1, to + 1), LogLevel.NORMAL);
		if (m_bShuttle && Pickup(kind) && m_aWaiting.IsEmpty())
			SquadWaits(now);   // the first squad is already waiting at the pickup
		GetGame().GetCallqueue().CallLater(Board, 1500, false, car, true);
	}

	// The driver (the first time) and the soldiers in the back, a group of their own (the supply trucks carry none).
	protected void Board(ZCR_SimCar car, bool first)
	{
		if (!car || !car.m_Vehicle || car.m_bLost)
			return;
		string crew = USSR_CREW;
		if (car.m_sKind.StartsWith("m9"))
			crew = US_CREW;
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(car.m_Vehicle, seats);
		if (first)
		{
			AIGroup group;
			foreach (BaseCompartmentSlot seat : seats)
			{
				if (seat && seat.GetType() == ECompartmentType.PILOT && !seat.GetOccupant())
				{
					seat.SpawnCharacterInCompartment(crew, group);
					break;
				}
			}
			car.m_Group = SCR_AIGroup.Cast(group);
			if (m_bShuttle)
				ZCR_CrewStays.Hold(car.m_Vehicle);
			SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(car.m_Vehicle.FindComponent(SCR_AIVehicleUsageComponent));
			if (car.m_Group && usage && car.m_Group.GetGroupUtilityComponent() && !car.m_Group.GetGroupUtilityComponent().IsUsableVehicle(usage))
				car.m_Group.GetGroupUtilityComponent().AddUsableVehicle(usage);
		}
		AIGroup riders;
		car.m_iAboard = 0;
		foreach (BaseCompartmentSlot back : seats)
		{
			if (car.m_iAboard >= Troops(car.m_sKind))
				break;
			if (back && back.GetType() == ECompartmentType.CARGO && back.IsCompartmentAccessible() && !back.GetOccupant())
			{
				if (back.SpawnCharacterInCompartment(crew, riders))
					car.m_iAboard++;
			}
		}
		car.m_Riders = SCR_AIGroup.Cast(riders);
		float supplies;
		SCR_ResourceContainer cargo = Supplies(car.m_Vehicle);
		if (cargo && Truck(car.m_sKind))
		{
			// Empty from the start (it drives to the supply point first); full when it loads there.
			if (first && m_bShuttle)
				cargo.SetResourceValue(0);
			else
				cargo.SetResourceValue(cargo.GetMaxResourceValue());
			supplies = cargo.GetResourceValue();
		}
		Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=BOARD men=%3 supplies=%4 driver=%5", ZCR_LossLog.Seconds(), car.m_iIndex, car.m_iAboard,
			Math.Round(supplies), car.m_Group != null), LogLevel.NORMAL);
		if (first && car.m_Group)
			Order(car);
	}

	// A squad waiting beside the pickup, off the road (the manpower run; 23 Oct: 25 m east of the stop was the road the
	// truck stopped on - the next squad appeared around it and the truck never moved again).
	protected void SquadWaits(int now)
	{
		vector at = Aside(m_aStops[0]);
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = at;
		string prefab = "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et";
		if (!m_aCars.IsEmpty() && m_aCars[0].m_sKind.StartsWith("m9"))
			prefab = "{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et";
		SCR_AIGroup squad = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(Resource.Load(prefab), GetGame().GetWorld(), params));
		if (!squad)
			return;
		m_aWaiting.Insert(squad);
		Print(string.Format("[ZCR][TRAFFICSIM] t=%1 event=SQUAD_WAITS x=%2 z=%3", now, Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
	}

	// The first point 20-30 m from the stop at least 12 m from any road (eight directions), else 25 m east.
	protected static vector Aside(vector stop)
	{
		vector at = stop + Vector(25, 0, 0);
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (aiWorld && aiWorld.GetRoadNetworkManager())
		{
			bool found;
			for (int r = 20; r <= 30 && !found; r += 5)
			{
				for (int i; i < 8 && !found; i++)
				{
					float a = i * Math.PI / 4;
					vector p = stop + Vector(Math.Cos(a) * r, 0, Math.Sin(a) * r);
					p[1] = GetGame().GetWorld().GetSurfaceY(p[0], p[2]);
					BaseRoad road;
					float distance;
					aiWorld.GetRoadNetworkManager().GetClosestRoad(p, road, distance, true);
					if (!road || distance >= 12)
					{
						at = p;
						found = true;
					}
				}
			}
		}
		at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]);
		return at;
	}

	// A pickup truck at the pickup: the first waiting squad is told to board it; once all of it is aboard (or 90 s) the
	// truck leaves for the destination.
	protected void Call(ZCR_SimCar car, int now)
	{
		ZCR_CrewStays.Hold(car.m_Vehicle);
		ZCR_Traffic.Limit(car.m_Vehicle, "load", 0);
		if (m_aWaiting.IsEmpty())
			SquadWaits(now);
		if (m_aWaiting.IsEmpty())
			return;
		SCR_AIGroup squad = m_aWaiting[0];
		m_aWaiting.Remove(0);
		car.m_Riders = squad;
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(car.m_Vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (usage && squad.GetGroupUtilityComponent())
			squad.GetGroupUtilityComponent().AddUsableVehicle(usage);
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = car.m_Vehicle.GetOrigin();
		SCR_BoardingEntityWaypoint board = SCR_BoardingEntityWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{8AD8C82346156494}Prefabs/AI/Waypoints/AIWaypoint_GetInSelected.et", false, params: params));
		if (board)
		{
			board.SetEntity(car.m_Vehicle);
			board.SetCompletionRadius(25);
			squad.AddWaypoint(board);
		}
		Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=CALL men=%3", now, car.m_iIndex, AICF_GroupRuntime.CountAliveAgents(squad)), LogLevel.NORMAL);
	}

	protected void Waiting(ZCR_SimCar car, int now)
	{
		int alive, aboard;
		if (car.m_Riders)
		{
			alive = AICF_GroupRuntime.CountAliveAgents(car.m_Riders);
			array<AIAgent> agents = {};
			car.m_Riders.GetAgents(agents);
			foreach (AIAgent a : agents)
			{
				ChimeraCharacter man = null;
				if (a)
					man = ChimeraCharacter.Cast(a.GetControlledEntity());
				if (man && man.IsInVehicle() && CompartmentAccessComponent.GetVehicleIn(man) == car.m_Vehicle)
					aboard++;
			}
		}
		if ((alive == 0 || aboard < alive) && now - car.m_iPickupAt < 90)
			return;
		car.m_iAboard = aboard;
		// The squad gives up its claim on the truck: the driver's group alone drives it.
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(car.m_Vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (car.m_Riders && usage && car.m_Riders.GetGroupUtilityComponent())
			car.m_Riders.GetGroupUtilityComponent().RemoveUsableVehicle(usage);
		Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=BOARD men=%3 of=%4 s=%5", now, car.m_iIndex, aboard, alive, now - car.m_iPickupAt), LogLevel.NORMAL);
		car.m_iPickupAt = 0;
		car.m_iLegStart = now;
		ZCR_Traffic.Release(car.m_Vehicle, "load");
		Order(car);
		// The next squad turns up once this truck has gone.
		GetGame().GetCallqueue().CallLater(NextSquad, 30000, false, now + 30);
	}

	protected void NextSquad(int now)
	{
		if (m_aWaiting.IsEmpty())
			SquadWaits(now);
	}

	// The truck's supply container (the game's resource system), null on a vehicle without one.
	protected static SCR_ResourceContainer Supplies(IEntity vehicle)
	{
		SCR_ResourceComponent resource = SCR_ResourceComponent.FindResourceComponent(vehicle);
		if (!resource)
			return null;
		return resource.GetContainer(EResourceType.SUPPLIES);
	}

	// At the front the supplies are emptied (delivered), the soldiers get out (delivered) and are taken off the map 20 s later.
	protected void Unload(ZCR_SimCar car, int now)
	{
		float supplies;
		SCR_ResourceContainer cargo = Supplies(car.m_Vehicle);
		if (cargo && Truck(car.m_sKind))
		{
			supplies = cargo.GetResourceValue();
			m_fSuppliesDelivered += supplies;
			cargo.SetResourceValue(0);
		}
		if (!car.m_Riders)
		{
			Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=UNLOAD men=0 supplies=%3 delivered=%4 supplies_delivered=%5", now, car.m_iIndex,
				Math.Round(supplies), m_iMenDelivered, Math.Round(m_fSuppliesDelivered)), LogLevel.NORMAL);
			return;
		}
		int men = AICF_GroupRuntime.CountAliveAgents(car.m_Riders);
		m_iMenDelivered += men;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = car.m_Vehicle.GetOrigin();
		AIWaypoint getOut = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{C40316EE26846CAB}Prefabs/AI/Waypoints/AIWaypoint_GetOut.et", false, params: params));
		if (getOut)
		{
			getOut.SetCompletionRadius(15);
			car.m_Riders.AddWaypoint(getOut);
		}
		Print(string.Format("[ZCR][TRAFFICSIM] t=%1 car=%2 event=UNLOAD men=%3 supplies=%4 delivered=%5 supplies_delivered=%6", now, car.m_iIndex, men,
			Math.Round(supplies), m_iMenDelivered, Math.Round(m_fSuppliesDelivered)), LogLevel.NORMAL);
		GetGame().GetCallqueue().CallLater(Dismiss, 20000, false, car.m_Riders, 0);
		car.m_Riders = null;
		car.m_iAboard = 0;
	}

	// Only soldiers already on foot are deleted (deleting one still in a seat is an engine risk - the watched supply run of
	// 23 Oct 17:25 crashed in UpdateEntities); the rest are tried again 10 s later, three times.
	protected static void Dismiss(SCR_AIGroup riders, int tries = 0)
	{
		if (!riders)
			return;
		array<AIAgent> agents = {};
		riders.GetAgents(agents);
		int seated;
		foreach (AIAgent a : agents)
		{
			ChimeraCharacter man = null;
			if (a)
				man = ChimeraCharacter.Cast(a.GetControlledEntity());
			if (!man)
				continue;
			if (man.IsInVehicle())
				seated++;
			else
				RplComponent.DeleteRplEntity(man, false);
		}
		if (seated > 0 && tries < 3)
			GetGame().GetCallqueue().CallLater(Dismiss, 10000, false, riders, tries + 1);
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

	// For the director's PREV / NEXT: every truck or car.
	static void Units(notnull array<IEntity> units, notnull array<string> labels)
	{
		if (!s_Instance)
			return;
		foreach (ZCR_SimCar c : s_Instance.m_aCars)
		{
			if (c.m_bLost || !c.m_Vehicle)
				continue;
			units.Insert(c.m_Vehicle);
			labels.Insert(string.Format("TRAFFIC: CAR %1 (%2) stop %3 -> %4, %5 aboard", c.m_iIndex, c.m_sKind, c.m_iFrom + 1, c.m_iTo + 1, c.m_iAboard));
		}
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
