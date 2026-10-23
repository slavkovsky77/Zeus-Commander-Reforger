// The guns test (23 Oct, Martin: "a subtest with guns being used, maybe against each other or against some infantry -
// this sub-lab should test some tanks and APCs"; review note 322). Lab only, -zcrGunTest "US spec;USSR spec":
//   side spec  kind:count:x,z   kind = btr70 | lav25 | t72 | m1a1 | bmp1 | bradley (the last four are Workshop mods,
//              lab --armour) or squad (the game's rifle squad: 9 men, 2 of them with light anti-tank rockets)
// Vehicles get a crew in the driver's and every turret seat (the faction's crewmen, fire at will) and drive at the other
// side's point; a squad holds its ground. The points are used as given (open ground: the airfield).
//   [ZCR][GUNTEST] t= event=SPAWN side= unit= kind= crew= x= z=
//   [ZCR][GUNTEST] t= event=FIRST_SIGHT side= unit= kind= m=  (first clear line from the turret to an enemy, checked every 2 s:
//                                                              terrain, buildings, trees and bushes block it)
//   [ZCR][GUNTEST] t= event=FIRST_DETECT side= unit= kind= m=  (a crewman's perception first lists an enemy; m: its distance)
//   [ZCR][GUNTEST] t= event=FIRST_TARGET side= unit= kind= m=  (a crewman's combat AI first picks an enemy to fire at)
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
	int m_iSpawnedAt;
	int m_iFirstShotAt = -1;
	int m_iFirstSightAt = -1;
	int m_iFirstDetectAt = -1;
	int m_iFirstTargetAt = -1;
	bool m_bPerceptionSet;
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
	protected int m_iNextSight;
	protected ref TraceParam m_Trace;
	protected ref map<string, int> m_mSightM = new map<string, int>();
	protected static const string US_CREW = "{E1CB513B8B9B08F4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_Crew.et";
	protected static const string USSR_CREW = "{9FFEF10757E742EB}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_Crew.et";

	static void Start()
	{
		ZCR_LosScan.Start();   // lab: open ground for the guns test (-zcrLosScan)
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
			test.m_mSightM.Set(names[i], -1);
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
			string why = LostWhy(u, now);
			if (why.IsEmpty())
				continue;
			u.m_bLost = true;
			Print(string.Format("[ZCR][GUNTEST] t=%1 event=LOST side=%2 unit=%3 kind=%4 why=%5", now, u.m_sSide, u.m_iIndex, u.m_sKind, why), LogLevel.NORMAL);
		}
		if (now >= m_iNextSight)
		{
			m_iNextSight = now + 1;
			Sight(now);
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 30;
			Print(string.Format("[ZCR][GUNTEST_SUM] t=%1 %2 %3 first_us_m=%4 first_ussr_m=%5 sight_us_m=%6 sight_ussr_m=%7", now, SideSum("US", "us"),
				SideSum("USSR", "ussr"), m_mFirstM.Get("US"), m_mFirstM.Get("USSR"), m_mSightM.Get("US"), m_mSightM.Get("USSR")), LogLevel.NORMAL);
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

	protected static string LostWhy(ZCR_GunUnit u, int now)
	{
		// The crew is seated 1.5 s after the vehicle appears: nothing counts as lost in the first 20 s (23 Oct: in the
		// watched game every vehicle was "lost" a second after it spawned, its crew not yet aboard).
		if (now - u.m_iSpawnedAt < 20 && u.m_Vehicle)
			return "";
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

	// Each vehicle that hasn't seen an enemy yet: a clear line from its turret (2.6 m up) to the nearest enemy vehicle's
	// hull or soldier's chest - the view geometry and foliage of terrain, buildings, trees and bushes block it.
	protected void Sight(int now)
	{
		BaseWorld world = GetGame().GetWorld();
		if (!m_Trace)
			m_Trace = new TraceParam();
		foreach (ZCR_GunUnit c : m_aUnits)
		{
			if (!c.m_bLost && c.m_Vehicle)
				Crew(c, now);
		}
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if (u.m_bLost || !u.m_Vehicle || u.m_iFirstSightAt >= 0)
				continue;
			float d;
			IEntity target = NearestEnemyEntity(u, d);
			if (!target)
				continue;
			m_Trace.Flags = TraceFlags.ENTS | TraceFlags.WORLD;
			m_Trace.TargetLayers = EPhysicsLayerDefs.ViewGeometry | EPhysicsLayerDefs.Foliage;
			m_Trace.Exclude = u.m_Vehicle;
			m_Trace.Start = u.m_Vehicle.GetOrigin() + "0 2.6 0";
			m_Trace.End = target.GetOrigin() + "0 1.3 0";
			float f = world.TraceMove(m_Trace, null);
			if (f < 0.97 && !(m_Trace.TraceEnt && m_Trace.TraceEnt.GetRootParent() == target.GetRootParent()))
				continue;
			u.m_iFirstSightAt = now;
			int m = Math.Round(d);
			if (m_mSightM.Get(u.m_sSide) < 0)
				m_mSightM.Set(u.m_sSide, m);
			Print(string.Format("[ZCR][GUNTEST] t=%1 event=FIRST_SIGHT side=%2 unit=%3 kind=%4 m=%5", now, u.m_sSide, u.m_iIndex, u.m_sKind, m), LogLevel.NORMAL);
		}
	}

	// What the crew knows: the first enemy any crewman's perception lists, and the first one a crewman's combat AI picks to
	// fire at - against the clear line of sight and the first shot this tells whether they don't see far or don't fire far.
	protected void Crew(ZCR_GunUnit u, int now)
	{
		// -zcrCrewPerception N: the crew recognise what they see N times faster (the game's SCR_AICombatComponent
		// perception factor, 1 normally) - on the airfield they noticed enemy vehicles only at ~490 m with a clear view from 750-800 m.
		string factor;
		if (!u.m_bPerceptionSet && System.GetCLIParam("zcrCrewPerception", factor) && !factor.IsEmpty())
		{
			u.m_bPerceptionSet = true;
			IEntity crewman = u.m_Vehicle.GetChildren();
			while (crewman)
			{
				SCR_AICombatComponent sharp = SCR_AICombatComponent.Cast(crewman.FindComponent(SCR_AICombatComponent));
				if (sharp)
					sharp.SetPerceptionFactor(factor.ToFloat());
				crewman = crewman.GetSibling();
			}
		}
		if (u.m_iFirstDetectAt >= 0 && u.m_iFirstTargetAt >= 0)
			return;
		IEntity child = u.m_Vehicle.GetChildren();
		while (child)
		{
			ChimeraCharacter man = ChimeraCharacter.Cast(child);
			child = child.GetSibling();
			if (!man)
				continue;
			PerceptionComponent perception = PerceptionComponent.Cast(man.FindComponent(PerceptionComponent));
			if (u.m_iFirstDetectAt < 0 && perception && perception.GetTargetCount(ETargetCategory.ENEMY) > 0)
			{
				BaseTarget seen = perception.GetClosestTarget(ETargetCategory.ENEMY, 100000, 100000);
				if (seen)
				{
					u.m_iFirstDetectAt = now;
					Print(string.Format("[ZCR][GUNTEST] t=%1 event=FIRST_DETECT side=%2 unit=%3 kind=%4 m=%5", now, u.m_sSide, u.m_iIndex, u.m_sKind, Math.Round(seen.GetDistance())), LogLevel.NORMAL);
				}
			}
			SCR_AICombatComponent combat = SCR_AICombatComponent.Cast(man.FindComponent(SCR_AICombatComponent));
			if (u.m_iFirstTargetAt < 0 && combat && combat.GetCurrentTarget())
			{
				u.m_iFirstTargetAt = now;
				Print(string.Format("[ZCR][GUNTEST] t=%1 event=FIRST_TARGET side=%2 unit=%3 kind=%4 m=%5", now, u.m_sSide, u.m_iIndex, u.m_sKind,
					Math.Round(combat.GetCurrentTarget().GetDistance())), LogLevel.NORMAL);
			}
		}
	}

	protected IEntity NearestEnemyEntity(ZCR_GunUnit from, out float distance)
	{
		vector at = from.m_Vehicle.GetOrigin();
		distance = 100000;
		IEntity best;
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if (u.m_sSide == from.m_sSide || u.m_bLost)
				continue;
			if (u.m_Vehicle)
			{
				float dv = vector.Distance(at, u.m_Vehicle.GetOrigin());
				if (dv < distance)
				{
					distance = dv;
					best = u.m_Vehicle;
				}
				continue;
			}
			if (!u.m_Group)
				continue;
			array<AIAgent> agents = {};
			u.m_Group.GetAgents(agents);
			foreach (AIAgent a : agents)
			{
				if (!a || !a.GetControlledEntity())
					continue;
				float ds = vector.Distance(at, a.GetControlledEntity().GetOrigin());
				if (ds < distance)
				{
					distance = ds;
					best = a.GetControlledEntity();
				}
			}
		}
		return best;
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
		unit.m_iSpawnedAt = now;
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
			// The crew 1.5 s later, as ZCR_Armour does: seated in the same frame the vehicle appears, the watched game
			// (the game hosting the match itself) left them out of the seats - no turret manned, nobody driving.
			if (unit.m_Vehicle)
				GetGame().GetCallqueue().CallLater(CrewLater, 1500, false, unit, side, target);
		}
		m_aUnits.Insert(unit);
		Print(string.Format("[ZCR][GUNTEST] t=%1 event=SPAWN side=%2 unit=%3 kind=%4 crew=%5 x=%6 z=%7", now, side, unit.m_iIndex, kind, crew,
			Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
	}

	protected void CrewLater(ZCR_GunUnit unit, string side, vector target)
	{
		if (!unit || !unit.m_Vehicle)
			return;
		int crew = Crew(unit, side);
		Print(string.Format("[ZCR][GUNTEST] t=%1 event=CREW side=%2 unit=%3 kind=%4 crew=%5", ZCR_LossLog.Seconds(), side, unit.m_iIndex, unit.m_sKind, crew), LogLevel.NORMAL);
		if (unit.m_Group)
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

// -zcrLosScan "step,length" (23 Oct): where on the map two vehicles 600-900 m apart can see each other - for the guns
// test's ground (on the north farm road hedges and trees hid them until 45-95 m). Every point of a grid on land, 8
// directions: a clear line at turret height (2.6 m) both ends on land; the flattest 40 printed.
//   [ZCR][LOSSCAN] a=x,z b=x,z m= rise= (the ground's highest minus lowest point along the line)   /   [ZCR][LOSSCAN] done pairs= clear=
class ZCR_LosScan
{
	static void Start()
	{
		string spec;
		if (!Replication.IsServer() || !System.GetCLIParam("zcrLosScan", spec) || spec.IsEmpty())
			return;
		GetGame().GetCallqueue().CallLater(Scan, 5000, false, spec);
	}

	protected static void Scan(string spec)
	{
		array<string> p = {};
		spec.Split(",", p, true);
		float step = 150;
		float len = 800;
		if (p.Count() > 0)
			step = Math.Max(50, p[0].ToFloat());
		if (p.Count() > 1)
			len = Math.Max(200, p[1].ToFloat());
		BaseWorld world = GetGame().GetWorld();
		vector mins, maxs;
		world.GetBoundBox(mins, maxs);
		TraceParam trace = new TraceParam();
		trace.Flags = TraceFlags.ENTS | TraceFlags.WORLD;
		trace.TargetLayers = EPhysicsLayerDefs.ViewGeometry | EPhysicsLayerDefs.Foliage;
		array<string> lines = {};
		array<float> rises = {};
		int pairs, clear;
		for (float x = mins[0] + step; x < maxs[0] - step; x += step)
		{
			for (float z = mins[2] + step; z < maxs[2] - step; z += step)
			{
				float ya = world.GetSurfaceY(x, z);
				if (ya < world.GetOceanBaseHeight() + 2)
					continue;
				for (int dir; dir < 4; dir++)   // 4 directions: the other 4 are the same lines from the other end
				{
					float angle = dir * 45 * Math.DEG2RAD;
					float bx = x + Math.Sin(angle) * len;
					float bz = z + Math.Cos(angle) * len;
					if (bx < mins[0] || bx > maxs[0] || bz < mins[2] || bz > maxs[2])
						continue;
					float yb = world.GetSurfaceY(bx, bz);
					if (yb < world.GetOceanBaseHeight() + 2)
						continue;
					pairs++;
					trace.Start = Vector(x, ya + 2.6, z);
					trace.End = Vector(bx, yb + 2.6, bz);
					if (world.TraceMove(trace, null) < 0.99)
						continue;
					clear++;
					float lo = 100000;
					float hi = -100000;
					bool wet;
					for (float t = 0; t <= 1.001; t += 0.05)
					{
						float y = world.GetSurfaceY(x + (bx - x) * t, z + (bz - z) * t);
						lo = Math.Min(lo, y);
						hi = Math.Max(hi, y);
						if (y < world.GetOceanBaseHeight() + 1)
							wet = true;
					}
					if (wet)
						continue;
					rises.Insert(hi - lo);
					lines.Insert(string.Format("a=%1,%2 b=%3,%4 m=%5 rise=%6", Math.Round(x), Math.Round(z), Math.Round(bx), Math.Round(bz), Math.Round(len), Math.Round(hi - lo)));
				}
			}
		}
		// The 40 flattest clear lines.
		for (int n; n < 40 && !rises.IsEmpty(); n++)
		{
			int best;
			for (int i = 1; i < rises.Count(); i++)
			{
				if (rises[i] < rises[best])
					best = i;
			}
			Print("[ZCR][LOSSCAN] " + lines[best], LogLevel.NORMAL);
			rises.Remove(best);
			lines.Remove(best);
		}
		Print(string.Format("[ZCR][LOSSCAN] done pairs=%1 clear=%2 step=%3 length=%4", pairs, clear, step, len), LogLevel.NORMAL);
	}
}
