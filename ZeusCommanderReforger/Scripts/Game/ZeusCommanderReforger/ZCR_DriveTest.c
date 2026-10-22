// The driving test track (22 Oct, Martin: "if you know where the bug happens on Moss Hill, do a simple scenario that
// reproduces it ... to optimise it faster"). Lab only, -zcrDriveTest "ax,az;bx,bz;count[;kind[;vx,vz]]": count crewed vehicles
// (kind m998 - the US M998, default - or uaz - the USSR UAZ-452) leave A one at a time, 12 s apart, and drive A -> B ->
// A ... on the game's own routes, through V both ways when given (a waypoint on the trap itself, so the route can't
// go round it). A, B and V are snapped to the nearest road. Every vehicle is watched by ZCR_Driving like
// any other ([ZCR][JAM] / [STUCKVEH] / [MOVEFAIL] / [PUSH] / [OFFROAD]), so a fix can be tried on the same stretch in
// minutes instead of waiting for a match to send rides through it.
//   [ZCR][DRIVETEST] t= car= event=SPAWN|ARRIVE|LOST leg= leg_s= to= x= z=
//   [ZCR][DRIVETEST_SUM] t= cars= legs= median_leg_s= max_leg_s= open_legs= oldest_open_s=   (every 60 s)
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
	bool m_bLost;
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
	protected string m_sPrefab = "{9B1BF9644E0378D6}Prefabs/Vehicles/Wheeled/M998/M998_covered_long.et";
	protected string m_sCrew = "{E1CB513B8B9B08F4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_Crew.et";
	protected int m_iNextSpawn = 15;
	protected int m_iNextSum = 60;

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
		if (parts.Count() > 4)
			s_Instance.m_vVia = Point(parts[4]);
		if (parts.Count() > 3 && parts[3] == "uaz")
		{
			s_Instance.m_sPrefab = "{01F65EFB8D767A91}Prefabs/Vehicles/Wheeled/UAZ452/UAZ452_cargo.et";
			s_Instance.m_sCrew = "{9FFEF10757E742EB}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_Crew.et";
		}
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
	protected static vector OnRoad(vector p)
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
		if (m_vA[1] == 0 && now >= 10)
		{
			m_vA = OnRoad(m_vA);
			m_vB = OnRoad(m_vB);
			if (m_vVia != vector.Zero)
				m_vVia = OnRoad(m_vVia);
			Print(string.Format("[ZCR][DRIVETEST] t=%1 track a=%2,%3 b=%4,%5 straight_m=%6 cars=%7 prefab=%8", now, Math.Round(m_vA[0]), Math.Round(m_vA[2]),
				Math.Round(m_vB[0]), Math.Round(m_vB[2]), Math.Round(vector.DistanceXZ(m_vA, m_vB)), m_iCount, m_sPrefab), LogLevel.NORMAL);
		}
		if (m_aCars.Count() < m_iCount && now >= m_iNextSpawn && m_vA[1] != 0)
		{
			// One at a time and only with the start clear - like a base sending its rides out.
			if (!StartBusy())
				Spawn(now);
			m_iNextSpawn = now + 12;
		}
		foreach (ZCR_DriveCar car : m_aCars)
		{
			if (car.m_bLost)
				continue;
			if (!car.m_Vehicle || !car.m_Group || AICF_GroupRuntime.CountAliveAgents(car.m_Group) == 0)
			{
				car.m_bLost = true;
				Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=LOST leg=%3", now, car.m_iIndex, car.m_iLeg), LogLevel.NORMAL);
				continue;
			}
			vector target = m_vA;
			if (car.m_bToB)
				target = m_vB;
			if (vector.DistanceXZ(car.m_Vehicle.GetOrigin(), target) > 30)
				continue;
			int legS = now - car.m_iLegStart;
			m_aLegs.Insert(legS);
			Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=ARRIVE leg=%3 leg_s=%4 to=%5", now, car.m_iIndex, car.m_iLeg, legS, ToName(car.m_bToB)), LogLevel.NORMAL);
			car.m_bToB = !car.m_bToB;
			Order(car, now);
		}
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
				if (c.m_bLost)
					continue;
				open++;
				oldest = Math.Max(oldest, now - c.m_iLegStart);
			}
			Print(string.Format("[ZCR][DRIVETEST_SUM] t=%1 cars=%2 legs=%3 median_leg_s=%4 max_leg_s=%5 open_legs=%6 oldest_open_s=%7", now, m_aCars.Count(),
				m_aLegs.Count(), median, longest, open, oldest), LogLevel.NORMAL);
		}
	}

	protected bool StartBusy()
	{
		foreach (ZCR_DriveCar c : m_aCars)
		{
			if (c.m_Vehicle && vector.DistanceXZ(c.m_Vehicle.GetOrigin(), m_vA) < 10)
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
		vector dir = m_vB - m_vA;
		dir[1] = 0;
		dir.Normalize();
		vector pose[4];
		Math3D.DirectionAndUpMatrix(dir, "0 1 0", pose);
		pose[3] = m_vA + "0 0.5 0";
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
		car.m_bToB = true;
		m_aCars.Insert(car);
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (car.m_Group && usage && car.m_Group.GetGroupUtilityComponent() && !car.m_Group.GetGroupUtilityComponent().IsUsableVehicle(usage))
			car.m_Group.GetGroupUtilityComponent().AddUsableVehicle(usage);
		Print(string.Format("[ZCR][DRIVETEST] t=%1 car=%2 event=SPAWN prefab=%3 crew=%4 x=%5 z=%6", now, car.m_iIndex, ZCR_LossLog.ShortName(vehicle),
			car.m_Group != null, Math.Round(pose[3][0]), Math.Round(pose[3][2])), LogLevel.NORMAL);
		Order(car, now);
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
		waypoint.SetCompletionRadius(20);
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
		if (Replication.IsServer() && System.IsCLIParam("zcrDriveTest"))
			ZCR_Driving.Start();
	}
}
