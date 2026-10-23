// The guns test (23 Oct, Martin: "a subtest with guns being used, maybe against each other or against some infantry -
// this sub-lab should test some tanks and APCs"; review note 322). Lab only, -zcrGunTest "US spec;USSR spec":
//   side spec  kind:count:x,z   kind = btr70 | lav25 | t72 | m1a1 | bmp1 | bradley (the last four are Workshop mods,
//              lab --armour) or squad (the game's rifle squad: 9 men, 2 of them with light anti-tank rockets)
// Vehicles get a crew in the driver's and every turret seat (the faction's crewmen, fire at will) and drive at the other
// side's point; a squad holds its ground. Both points snap to the nearest road.
//   [ZCR][GUNTEST] t= event=SPAWN side= unit= kind= crew= x= z=
//   [ZCR][GUNTEST] t= event=FIRST_SHOT side= unit= kind= m=   (the distance to the nearest living enemy then)
//   [ZCR][GUNTEST] t= event=LOST side= unit= kind= why=destroyed|crew_dead|crew_out|squad_dead
//   [ZCR][GUNTEST_SUM] t= us_units= us_alive= us_men= us_shots= ussr_units= ussr_alive= ussr_men= ussr_shots= first_us_m= first_ussr_m=   (every 30 s)
// Shots come from ZCR_VehicleGuns (the turrets' ammunition, read every second).
class ZCR_GunUnit
{
	int m_iIndex;
	string m_sSide;
	string m_sKind;
	Vehicle m_Vehicle;
	SCR_AIGroup m_Group;
	int m_iShots;
	int m_iFirstShotAt = -1;
	bool m_bLost;
}

class ZCR_GunTest
{
	protected static ref ZCR_GunTest s_Instance;
	protected ref array<ref ZCR_GunUnit> m_aUnits = {};
	protected ref map<string, string> m_mKind = new map<string, string>();
	protected ref map<string, int> m_mCount = new map<string, int>();
	protected ref map<string, vector> m_mAt = new map<string, vector>();
	protected ref map<string, int> m_mFirstM = new map<string, int>();
	protected bool m_bSpawned;
	protected int m_iNextSum = 30;
	protected int m_iCamTurn;
	protected static const string US_CREW = "{E1CB513B8B9B08F4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_Crew.et";
	protected static const string USSR_CREW = "{9FFEF10757E742EB}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_Crew.et";

	static void Start()
	{
		string spec;
		if (s_Instance || !Replication.IsServer() || !System.GetCLIParam("zcrGunTest", spec) || spec.IsEmpty())
			return;
		ZCR_GunTest test = new ZCR_GunTest();
		array<string> sides = {};
		spec.Split(";", sides, true);
		array<string> names = {"US", "USSR"};
		for (int i; i < 2 && i < sides.Count(); i++)
		{
			array<string> parts = {};
			sides[i].Split(":", parts, true);
			if (parts.Count() < 3)
				continue;
			array<string> xz = {};
			parts[2].Split(",", xz, true);
			if (xz.Count() < 2)
				continue;
			test.m_mKind.Set(names[i], parts[0]);
			test.m_mCount.Set(names[i], Math.Max(1, parts[1].ToInt()));
			test.m_mAt.Set(names[i], Vector(xz[0].ToFloat(), 0, xz[1].ToFloat()));
			test.m_mFirstM.Set(names[i], -1);
		}
		if (test.m_mKind.Count() < 2)
		{
			Print("[ZCR][GUNTEST] needs two sides: kind:count:x,z;kind:count:x,z", LogLevel.WARNING);
			return;
		}
		s_Instance = test;
		ZCR_LossLog.Register();   // [ZCR][LOSS]: who killed whom, from which turret
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	static bool Active()
	{
		return s_Instance != null;
	}

	// From ZCR_VehicleGuns: rounds fired from a turret of this vehicle.
	static void OnShot(string side, IEntity vehicle, int rounds)
	{
		if (!s_Instance || !vehicle)
			return;
		foreach (ZCR_GunUnit u : s_Instance.m_aUnits)
		{
			if (u.m_Vehicle != vehicle)
				continue;
			u.m_iShots += rounds;
			if (u.m_iFirstShotAt < 0)
			{
				u.m_iFirstShotAt = ZCR_LossLog.Seconds();
				int m = Math.Round(s_Instance.NearestEnemy(u));
				if (s_Instance.m_mFirstM.Get(u.m_sSide) < 0)
					s_Instance.m_mFirstM.Set(u.m_sSide, m);
				Print(string.Format("[ZCR][GUNTEST] t=%1 event=FIRST_SHOT side=%2 unit=%3 kind=%4 m=%5", u.m_iFirstShotAt, u.m_sSide, u.m_iIndex, u.m_sKind, m), LogLevel.NORMAL);
			}
			return;
		}
	}

	protected static string Prefab(string kind)
	{
		if (kind == "btr70")
			return "{C012BB3488BEA0C2}Prefabs/Vehicles/Wheeled/BTR70/BTR70.et";
		if (kind == "lav25")
			return "{0FBF8F010F81A4E5}Prefabs/Vehicles/Wheeled/LAV25/LAV25.et";
		if (kind == "t72")
			return "{726286E1F9570EA1}Prefabs/Vehicles/Tracked/T72B/T72B_Base.et";
		if (kind == "m1a1")
			return "{E80B119CFDF50ABE}Prefabs/Vehicles/Tracked/M1A1/M1A1_Olive.et";
		if (kind == "bmp1")
			return "{1DC01AAACFFA8B63}Prefabs/Vehicles/Tracked/BMP1/BMP1_Base.et";
		if (kind == "bradley")
			return "{24223D0679CDD612}Prefabs/Vehicles/Tracked/M2A2/M2A2_OD.et";
		return "";
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		ZCR_LabWeather.Apply();
		if (!m_bSpawned)
		{
			if (now < 10)
				return;
			m_bSpawned = true;
			foreach (string side, string kind : m_mKind)
			{
				vector at = ZCR_DriveTest.OnRoad(m_mAt.Get(side));
				m_mAt.Set(side, at);
			}
			foreach (string spawnSide, string spawnKind : m_mKind)
			{
				for (int n; n < m_mCount.Get(spawnSide); n++)
					Spawn(spawnSide, spawnKind, n, now);
			}
			return;
		}
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if (u.m_bLost)
				continue;
			string why = LostWhy(u);
			if (why.IsEmpty())
				continue;
			u.m_bLost = true;
			Print(string.Format("[ZCR][GUNTEST] t=%1 event=LOST side=%2 unit=%3 kind=%4 why=%5", now, u.m_sSide, u.m_iIndex, u.m_sKind, why), LogLevel.NORMAL);
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 30;
			Print(string.Format("[ZCR][GUNTEST_SUM] t=%1 %2 %3 first_us_m=%4 first_ussr_m=%5", now, SideSum("US", "us"), SideSum("USSR", "ussr"),
				m_mFirstM.Get("US"), m_mFirstM.Get("USSR")), LogLevel.NORMAL);
		}
	}

	protected string SideSum(string side, string tag)
	{
		int units, alive, men, shots;
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if (u.m_sSide != side)
				continue;
			units++;
			if (!u.m_bLost)
				alive++;
			if (u.m_Group)
				men += AICF_GroupRuntime.CountAliveAgents(u.m_Group);
			shots += u.m_iShots;
		}
		return string.Format("%1_units=%2 %1_alive=%3 %1_men=%4 %1_shots=%5", tag, units, alive, men, shots);
	}

	protected static string LostWhy(ZCR_GunUnit u)
	{
		if (u.m_sKind == "squad")
		{
			if (!u.m_Group || AICF_GroupRuntime.CountAliveAgents(u.m_Group) == 0)
				return "squad_dead";
			return "";
		}
		if (!u.m_Vehicle)
			return "destroyed";
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(u.m_Vehicle.FindComponent(SCR_DamageManagerComponent));
		if (damage && damage.GetState() == EDamageState.DESTROYED)
			return "destroyed";
		if (!u.m_Group || AICF_GroupRuntime.CountAliveAgents(u.m_Group) == 0)
			return "crew_dead";
		if (!ZCR_Wrecks.Occupied(u.m_Vehicle))
			return "crew_out";
		return "";
	}

	// The nearest living enemy: a unit's vehicle, or a soldier of an enemy squad.
	protected float NearestEnemy(ZCR_GunUnit from)
	{
		vector at = from.m_Vehicle.GetOrigin();
		float best = 100000;
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if (u.m_sSide == from.m_sSide || u.m_bLost)
				continue;
			if (u.m_Vehicle)
			{
				best = Math.Min(best, vector.Distance(at, u.m_Vehicle.GetOrigin()));
				continue;
			}
			if (!u.m_Group)
				continue;
			array<AIAgent> agents = {};
			u.m_Group.GetAgents(agents);
			foreach (AIAgent a : agents)
			{
				if (a && a.GetControlledEntity())
					best = Math.Min(best, vector.Distance(at, a.GetControlledEntity().GetOrigin()));
			}
		}
		return best;
	}

	protected void Spawn(string side, string kind, int n, int now)
	{
		vector home = m_mAt.Get(side);
		string other = "USSR";
		if (side == "USSR")
			other = "US";
		vector target = m_mAt.Get(other);
		vector dir = target - home;
		dir[1] = 0;
		dir.Normalize();
		vector right = Vector(dir[2], 0, -dir[0]);
		// Side by side, 15 m apart across the line of advance.
		vector at = home + right * ((n - (m_mCount.Get(side) - 1) * 0.5) * 15);
		at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]) + 0.5;
		vector pose[4];
		Math3D.DirectionAndUpMatrix(dir, "0 1 0", pose);
		pose[3] = at;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		for (int axis; axis < 4; axis++)
			params.Transform[axis] = pose[axis];
		ZCR_GunUnit unit = new ZCR_GunUnit();
		unit.m_iIndex = m_aUnits.Count() + 1;
		unit.m_sSide = side;
		unit.m_sKind = kind;
		int crew;
		if (kind == "squad")
		{
			string squad = "{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et";
			if (side == "USSR")
				squad = "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et";
			unit.m_Group = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(Resource.Load(squad), GetGame().GetWorld(), params));
		}
		else
		{
			unit.m_Vehicle = Vehicle.Cast(GetGame().SpawnEntityPrefab(Resource.Load(Prefab(kind)), GetGame().GetWorld(), params));
			if (unit.m_Vehicle)
				crew = Crew(unit, side);
		}
		m_aUnits.Insert(unit);
		Print(string.Format("[ZCR][GUNTEST] t=%1 event=SPAWN side=%2 unit=%3 kind=%4 crew=%5 x=%6 z=%7", now, side, unit.m_iIndex, kind, crew,
			Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
		if (unit.m_Vehicle && unit.m_Group)
			Order(unit, target);
	}

	// The driver's and every turret seat, as ZCR_Armour crews its units; the group fires at will.
	protected static int Crew(ZCR_GunUnit unit, string side)
	{
		string character = US_CREW;
		if (side == "USSR")
			character = USSR_CREW;
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(unit.m_Vehicle, seats);
		AIGroup group;
		int pilots, turrets;
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (!seat || !seat.IsCompartmentAccessible() || seat.GetOccupant())
				continue;
			if (seat.GetType() != ECompartmentType.PILOT && seat.GetType() != ECompartmentType.TURRET)
				continue;
			if (seat.GetType() == ECompartmentType.PILOT && pilots > 0)
				continue;
			if (!seat.SpawnCharacterInCompartment(character, group))
				continue;
			if (seat.GetType() == ECompartmentType.PILOT)
				pilots++;
			else
				turrets++;
		}
		unit.m_Group = SCR_AIGroup.Cast(group);
		if (!unit.m_Group)
			return 0;
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(unit.m_Vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		SCR_AIGroupUtilityComponent utility = unit.m_Group.GetGroupUtilityComponent();
		if (usage && utility && !utility.IsUsableVehicle(usage))
			utility.AddUsableVehicle(usage);
		if (utility)
		{
			utility.SetCombatMode(EAIGroupCombatMode.FIRE_AT_WILL);
			utility.EvaluateCombatMode();
		}
		return pilots + turrets;
	}

	protected static void Order(ZCR_GunUnit unit, vector target)
	{
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = target;
		AIWaypoint waypoint = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", false, params: params));
		if (!waypoint)
			return;
		waypoint.SetCompletionRadius(30);
		unit.m_Group.AddWaypoint(waypoint);
	}

	// For the watch camera: the units by turns, living ones only.
	static IEntity CameraUnit(out string label)
	{
		if (!s_Instance || s_Instance.m_aUnits.IsEmpty())
			return null;
		for (int i; i < s_Instance.m_aUnits.Count(); i++)
		{
			s_Instance.m_iCamTurn++;
			ZCR_GunUnit u = s_Instance.m_aUnits[s_Instance.m_iCamTurn % s_Instance.m_aUnits.Count()];
			if (u.m_bLost)
				continue;
			IEntity e = u.m_Vehicle;
			if (!e && u.m_Group)
			{
				array<AIAgent> agents = {};
				u.m_Group.GetAgents(agents);
				if (!agents.IsEmpty() && agents[0])
					e = agents[0].GetControlledEntity();
			}
			if (!e)
				continue;
			label = string.Format("GUN TEST: %1 %2 %3 - %4 rounds fired", u.m_sSide, u.m_sKind, u.m_iIndex, u.m_iShots);
			return e;
		}
		return null;
	}
}
