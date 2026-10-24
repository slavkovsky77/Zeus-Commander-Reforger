// The guns test (23 Oct, Martin: "a subtest with guns being used, maybe against each other or against some infantry -
// this sub-lab should test some tanks and APCs"; review note 322). Lab only, -zcrGunTest "US spec;USSR spec":
//   side spec  group+group+...   group = kind:count:x,z[:role]
//   kind       btr70 | lav25 | t72 | m1a1 | bmp1 | bradley (the last four Workshop mods, lab --armour), or squad (the
//              game's rifle squad: 9 men, 2 of them with light anti-tank rockets)
//   role       vehicles: attack (default: drive at the objective) | overwatch (stop 300 m short of it and fire from there) |
//              hold (stay where they are) | carry (an APC with a rifle squad of its side in the back: drives at the
//              objective, the squad gets out 250 m short of it and assaults it - Search and Destroy - and 20 s later the APC
//              follows them in and fights (Search and Destroy too); Martin, 23 Oct: "the APC would carry infantry to the
//              enemy, they disembark and storm"; "the crew of the vehicle should continue and attack the enemies");
//              squads: hold (default: stay where they are) | defend (the game's Defend waypoint: take positions round
//              their point) | attack (Search and Destroy at the objective)
// A side's objective is the other side's first group's point. Vehicles get a crew in the driver's and every turret seat
// (the faction's crewmen, fire at will). The points are used as given (open ground: the airfield).
//   [ZCR][GUNTEST] t= event=SPAWN side= unit= kind= crew= x= z=
//   [ZCR][GUNTEST] t= event=FIRST_SIGHT side= unit= kind= m=  (first clear line from the turret to an enemy, checked every 2 s:
//                                                              terrain, buildings, trees and bushes block it)
//   [ZCR][GUNTEST] t= event=FIRST_DETECT side= unit= kind= m=  (a crewman's perception first lists an enemy; m: its distance)
//   [ZCR][GUNTEST] t= event=FIRST_TARGET side= unit= kind= m=  (a crewman's combat AI first picks an enemy to fire at)
//   [ZCR][GUNTEST] t= event=FIRST_SHOT side= unit= kind= m=   (the distance to the nearest living enemy then)
//   [ZCR][GUNTEST] t= event=LOST side= unit= kind= why=destroyed|crew_dead|crew_out|squad_dead
//   [ZCR][GUNTEST] t= event=RIDERS side= unit= men= carrier=        (the squad seated in the APC's back)
//   [ZCR][GUNTEST] t= event=DISMOUNT side= unit= m= enemy_m= men= why=near|carrier_lost|stopped   (m: to the objective)
//   [ZCR][GUNTEST] t= event=ADVANCE side= unit=   (the APC follows its squad in, 20 s after the dismount)
//   [ZCR][GUNTEST] t= event=TAKEN side= men_near=   (the side's soldiers within 40 m of its objective, no enemy within 60 m)
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
	ZCR_GunUnit m_Carrier;   // riders: the APC they sit in
	bool m_bDismounted;
	int m_iStillSince;       // riders: the carrier standing still since
	string m_sRole;
	int m_iNextLaunch;       // drone operators: the next FPV team
}

class ZCR_GunSpec
{
	string m_sSide;
	string m_sKind;
	int m_iCount;
	vector m_vAt;
	string m_sRole;
}

class ZCR_GunTest
{
	protected static ref ZCR_GunTest s_Instance;
	protected ref array<ref ZCR_GunUnit> m_aUnits = {};
	protected ref array<ref ZCR_GunSpec> m_aSpecs = {};
	protected ref map<string, vector> m_mObjective = new map<string, vector>();
	protected ref map<string, int> m_mTaken = new map<string, int>();
	protected static const float DISMOUNT_M = 250;
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
		ZCR_CoverScan.Start(); // lab: buildings, trees and walls on the ground, for the infantry tests (-zcrCoverScan)
		if (System.IsCLIParam("zcrSoldierLayer"))
			ZCR_Danger.Start();   // infantry tests' "ours": never standing in danger, as in matches (the commander starts it there)
		string spec;
		if (s_Instance || !Replication.IsServer() || !System.GetCLIParam("zcrGunTest", spec) || spec.IsEmpty())
			return;
		ZCR_GunTest test = new ZCR_GunTest();
		array<string> sides = {};
		spec.Split(";", sides, true);
		array<string> names = {"US", "USSR"};
		map<string, vector> first = new map<string, vector>();
		for (int i; i < 2 && i < sides.Count(); i++)
		{
			test.m_mFirstM.Set(names[i], -1);
			test.m_mSightM.Set(names[i], -1);
			array<string> groups = {};
			sides[i].Split("+", groups, true);
			foreach (string g : groups)
			{
				array<string> parts = {};
				g.Split(":", parts, true);
				if (parts.Count() < 3)
					continue;
				array<string> xz = {};
				parts[2].Split(",", xz, true);
				if (xz.Count() < 2)
					continue;
				ZCR_GunSpec gs = new ZCR_GunSpec();
				gs.m_sSide = names[i];
				gs.m_sKind = parts[0];
				gs.m_iCount = Math.Max(1, parts[1].ToInt());
				gs.m_vAt = Vector(xz[0].ToFloat(), 0, xz[1].ToFloat());
				gs.m_sRole = "";
				if (parts.Count() > 3)
					gs.m_sRole = parts[3];
				test.m_aSpecs.Insert(gs);
				if (!first.Contains(names[i]))
					first.Set(names[i], gs.m_vAt);
			}
		}
		if (first.Count() < 2)
		{
			Print("[ZCR][GUNTEST] needs two sides: kind:count:x,z[:role][+...];kind:count:x,z[:role][+...]", LogLevel.WARNING);
			return;
		}
		// Each side's objective: the other side's first group's point.
		test.m_mObjective.Set("US", first.Get("USSR"));
		test.m_mObjective.Set("USSR", first.Get("US"));
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
			foreach (ZCR_GunSpec spec : m_aSpecs)
			{
				for (int n; n < spec.m_iCount; n++)
					Spawn(spec, n, now);
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
			Storm(now);
			if (now % 5 == 0)
			{
				Taken(now);
				EndWhenDecided(now);
				Operators(now);
			}
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 30;
			Print(string.Format("[ZCR][GUNTEST_SUM] t=%1 %2 %3 first_us_m=%4 first_ussr_m=%5 sight_us_m=%6 sight_ussr_m=%7", now, SideSum("US", "us"),
				SideSum("USSR", "ussr"), m_mFirstM.Get("US"), m_mFirstM.Get("USSR"), m_mSightM.Get("US"), m_mSightM.Get("USSR")), LogLevel.NORMAL);
		}
	}

	// Drone operators: while one of a team lives, an FPV team of 4 at the enemy's position every DRONE_EVERY_S, at most
	// DRONE_MAX_UP teams of the side in the air; the teams retarget at enemies their side has seen (ZCR_Drones.Tend). The
	// soldiers' drone reactions (ZCR_DroneThreat, ZCR_AntiDrone) run as in matches.
	// One FPV at a time (Martin, 24 Oct: "mostly they fly independently - launched by one"): a drone every 35 s, at most 3
	// of a side's in the air.
	static const int DRONE_EVERY_S = 35;
	static const int DRONE_MAX_UP = 3;
	static const int DRONES_PER_LAUNCH = 1;
	protected bool m_bDroneLayers;

	protected void Operators(int now)
	{
		bool any;
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if ((u.m_sKind != "drones" && u.m_sKind != "site") || u.m_bLost || !u.m_Group || AICF_GroupRuntime.CountAliveAgents(u.m_Group) == 0)
				continue;
			any = true;
			if (now < u.m_iNextLaunch)
				continue;
			vector goal;
			if (!m_mObjective.Find(u.m_sSide, goal))
				continue;
			array<AIAgent> agents = {};
			u.m_Group.GetAgents(agents);
			vector from = u.m_Group.GetOrigin();
			if (!agents.IsEmpty() && agents[0] && agents[0].GetControlledEntity())
				from = agents[0].GetControlledEntity().GetOrigin();
			from = from + Vector(12, 0, 0);   // beside the operators, not on them
			if (u.m_sKind == "site")
			{
				// From where the team is - only at its launch position with drones in the bag (ZCR_DroneOperator sorties).
				ZCR_DroneSites.Tick(u.m_sSide, goal);
				if (!ZCR_DroneOperator.CanLaunch(u.m_Group, from))
				{
					u.m_iNextLaunch = now + 3;
					continue;
				}
			}
			if (ZCR_Drones.LaunchTest(u.m_sSide, from, goal, DRONE_MAX_UP, DRONES_PER_LAUNCH))
			{
				u.m_iNextLaunch = now + DRONE_EVERY_S;
				if (u.m_sKind == "site")
					ZCR_DroneOperator.Launched(u.m_Group);
			}
			else
				u.m_iNextLaunch = now + 10;
		}
		if (!any)
			return;
		if (!m_bDroneLayers)
		{
			m_bDroneLayers = true;
			ZCR_DroneThreat.Start();
			ZCR_AntiDrone.Start();
		}
		ZCR_Drones.Tend("US");
		ZCR_Drones.Tend("USSR");
	}

	// -zcrEndWhenDecided (the infantry sub-lab; Martin, 24 Oct: "it should end when one side's soldiers are dead"): a side
	// with no soldier left alive anywhere on the map (counted per soldier - DCO moves soldiers into groups of its own), or
	// the position taken and held 30 s -> a last summary and [ZCR][TEST_END]; lab/reforger.py then closes the game.
	//   [ZCR][TEST_END] t= why=us_wiped|ussr_wiped|taken us_men= ussr_men=
	protected bool m_bEnded;

	protected void EndWhenDecided(int now)
	{
		if (m_bEnded || !System.IsCLIParam("zcrEndWhenDecided") || now < 30)
			return;
		int us = AliveMen("US", now);
		int ussr = AliveMen("USSR", now);
		// A side with only drone operators or a drone site (the farm-site storm) is wiped when they are dead.
		if (us == 0 && !Fighters("US"))
			us = OperatorMen("US");
		if (ussr == 0 && !Fighters("USSR"))
			ussr = OperatorMen("USSR");
		string why;
		if (us == 0)
			why = "us_wiped";
		else if (ussr == 0)
			why = "ussr_wiped";
		else
		{
			foreach (string side, int at : m_mTaken)
			{
				if (now - at >= 30)
					why = "taken";
			}
		}
		if (why.IsEmpty())
			return;
		m_bEnded = true;
		Print(string.Format("[ZCR][GUNTEST_SUM] t=%1 %2 %3 first_us_m=%4 first_ussr_m=%5 sight_us_m=%6 sight_ussr_m=%7", now, SideSum("US", "us"),
			SideSum("USSR", "ussr"), m_mFirstM.Get("US"), m_mFirstM.Get("USSR"), m_mSightM.Get("US"), m_mSightM.Get("USSR")), LogLevel.NORMAL);
		Print(string.Format("[ZCR][TEST_END] t=%1 why=%2 us_men=%3 ussr_men=%4", now, why, us, ussr), LogLevel.NORMAL);
	}

	// Has the side any unit besides drone operators and drone sites?
	protected bool Fighters(string side)
	{
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if (u.m_sSide == side && u.m_sKind != "drones" && u.m_sKind != "site")
				return true;
		}
		return false;
	}

	// The side's drone operators (operator teams and drone sites) alive.
	protected int OperatorMen(string side)
	{
		int n;
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if (u.m_sSide == side && (u.m_sKind == "drones" || u.m_sKind == "site") && u.m_Group)
				n += AICF_GroupRuntime.CountAliveAgents(u.m_Group);
		}
		return n;
	}

	// Fighting soldiers of a side alive anywhere on the map (on foot or aboard) - not its drone operators, who stay back.
	protected int AliveMen(string side, int now)
	{
		array<AIGroup> operators = {};
		foreach (ZCR_GunUnit u : m_aUnits)
		{
			if ((u.m_sKind == "drones" || u.m_sKind == "site") && u.m_Group)
				operators.Insert(u.m_Group);
		}
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		int n;
		foreach (AIAgent a : agents)
		{
			ChimeraCharacter c = null;
			if (a)
				c = ChimeraCharacter.Cast(a.GetControlledEntity());
			if (!c || ZCR_LossLog.SideOf(c) != side || operators.Find(a.GetParentGroup()) >= 0)
				continue;
			CharacterControllerComponent ctl = c.GetCharacterController();
			if (ctl && ctl.GetLifeState() != ECharacterLifeState.DEAD)
				n++;
		}
		return n;
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
		if (now - u.m_iSpawnedAt < 20)
			return "";   // squads too: a group's soldiers appear a moment after it (one was "dead" at t=11, 23 Oct)
		if (u.m_sKind == "squad" || u.m_sKind == "riders" || u.m_sKind == "drones" || u.m_sKind == "site")
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
			// Done once a crewman has it - the crew is seated 1.5 s after the vehicle appears (23 Oct: marked done before
			// anyone was aboard, the factor never reached them; the integration test spot-far caught it).
			IEntity crewman = u.m_Vehicle.GetChildren();
			while (crewman)
			{
				SCR_AICombatComponent sharp = SCR_AICombatComponent.Cast(crewman.FindComponent(SCR_AICombatComponent));
				if (sharp)
				{
					sharp.SetPerceptionFactor(factor.ToFloat());
					u.m_bPerceptionSet = true;
				}
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

	protected void Spawn(ZCR_GunSpec spec, int n, int now)
	{
		string side = spec.m_sSide;
		string kind = spec.m_sKind;
		vector home = spec.m_vAt;
		vector target = m_mObjective.Get(side);
		vector dir = target - home;
		dir[1] = 0;
		if (dir.Length() < 1)
			dir = "1 0 0";
		dir.Normalize();
		vector right = Vector(dir[2], 0, -dir[0]);
		// Side by side, 15 m apart across the line of advance.
		vector at = home + right * ((n - (spec.m_iCount - 1) * 0.5) * 15);
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
		unit.m_sRole = spec.m_sRole;
		int crew;
		if (kind == "drones")
		{
			// A drone operator team (Martin, 24 Oct: "each team would get a drone operator"): the game's 2-man sentry team, as
			// our drone sites use; it launches an FPV team of 4 at the enemy every DRONE_EVERY_S while one of them lives.
			string ops = "{3BF36BDEEB33AEC9}Prefabs/Groups/BLUFOR/Group_US_SentryTeam.et";
			if (side == "USSR")
				ops = "{CB58D90EA14430AD}Prefabs/Groups/OPFOR/Group_USSR_SentryTeam.et";
			unit.m_Group = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(Resource.Load(ops), GetGame().GetWorld(), params));
			ZCR_Sampler.AddTestGroup(unit.m_Group, side);
			if (unit.m_Group)
				Waypoint(unit, at, "{93291E72AC23930F}Prefabs/AI/Waypoints/AIWaypoint_Defend.et", 15);
			// Pilot (goggles, controller, holding still while he flies) and guard, a post in cover, tags on the watch screen.
			if (unit.m_Group)
				ZCR_DroneOperator.Register(unit.m_Group, side, at, target);
			unit.m_iNextLaunch = now + 20;
		}
		else if (kind == "site")
		{
			// A drone site as in the main battle (truck + operator team) that launches from its own launch spot and moves
			// (ZCR_DroneSites: after 3 launches, 8 minutes, or once seen).
			unit.m_Group = ZCR_DroneSites.CreateTest(side, at, target);
			if (unit.m_Group)
			{
				ZCR_Sampler.AddTestGroup(unit.m_Group, side);
				ZCR_DroneOperator.Sortie(unit.m_Group, side, ZCR_DroneSites.SupplyOf(unit.m_Group), target);   // walks out with drones in the bag
			}
			unit.m_iNextLaunch = now + 25;
		}
		else if (kind == "squad")
		{
			string squad = "{DDF3799FA1387848}Prefabs/Groups/BLUFOR/Group_US_RifleSquad.et";
			if (side == "USSR")
				squad = "{E552DABF3636C2AD}Prefabs/Groups/OPFOR/Group_USSR_RifleSquad.et";
			unit.m_Group = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(Resource.Load(squad), GetGame().GetWorld(), params));
			ZCR_Sampler.AddTestGroup(unit.m_Group, side);   // cover, stance and deaths measured as in matches
			if (unit.m_Group && spec.m_sRole == "defend")
				Waypoint(unit, at, "{93291E72AC23930F}Prefabs/AI/Waypoints/AIWaypoint_Defend.et", 40);
			else if (unit.m_Group && spec.m_sRole == "attack")
			{
				Waypoint(unit, target, "{B3E7B8DC2BAB8ACC}Prefabs/AI/Waypoints/AIWaypoint_SearchAndDestroy.et", 30);
				if (System.IsCLIParam("zcrStormPush"))
					ZCR_Tactical.Storming(unit.m_Group, true);   // the tactical layer lets it push (DCO: its contact drills off)
			}
		}
		else
		{
			unit.m_Vehicle = Vehicle.Cast(GetGame().SpawnEntityPrefab(Resource.Load(Prefab(kind)), GetGame().GetWorld(), params));
			// The crew 1.5 s later, as ZCR_Armour does: seated in the same frame the vehicle appears, the watched game
			// (the game hosting the match itself) left them out of the seats - no turret manned, nobody driving.
			// Overwatch: stop 300 m short of the objective, on the line from home.
			vector goal = target;
			if (spec.m_sRole == "overwatch" && vector.DistanceXZ(home, target) > 300)
				goal = target - dir * 300;
			if (spec.m_sRole == "hold")
				goal = vector.Zero;   // no order: stays where it is
			if (spec.m_sRole == "carry" && vector.DistanceXZ(home, target) > DISMOUNT_M)
				goal = target - dir * (DISMOUNT_M - 20);
			if (unit.m_Vehicle)
				GetGame().GetCallqueue().CallLater(CrewLater, 1500, false, unit, side, goal);
			if (unit.m_Vehicle && spec.m_sRole == "carry")
				GetGame().GetCallqueue().CallLater(SeatRiders, 2500, false, unit, side);
		}
		m_aUnits.Insert(unit);
		Print(string.Format("[ZCR][GUNTEST] t=%1 event=SPAWN side=%2 unit=%3 kind=%4 role=%5 x=%6 z=%7", now, side, unit.m_iIndex, kind, spec.m_sRole,
			Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
	}

	// A rifle squad of the side in the APC's passenger seats (a group of its own; the crew is another).
	protected void SeatRiders(ZCR_GunUnit carrier, string side)
	{
		if (!carrier || !carrier.m_Vehicle)
			return;
		array<string> men = {"{E45F1E163F5CA080}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_SL.et",
			"{E398E44759DA1A43}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_TL.et",
			"{5B1996C05B1E51A4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_AR.et",
			"{84029128FA6F6BB9}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_GL.et",
			"{27BF1FF235DD6036}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_LAT.et",
			"{E398E44759DA1A43}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_TL.et",
			"{5B1996C05B1E51A4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_AR.et",
			"{84029128FA6F6BB9}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_GL.et"};
		if (side == "USSR")
			men = {"{5436629450D8387A}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_SL.et",
				"{23ADBBC31B6A3DC6}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_AR.et",
				"{1C78331E156A3D65}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_AT.et",
				"{631158F6898738A4}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_AAT.et",
				"{333DA6244C7DA34C}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_SR.et",
				"{BF643BE4ADBDFDD3}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_LAT.et",
				"{23ADBBC31B6A3DC6}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_AR.et",
				"{BF643BE4ADBDFDD3}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_LAT.et"};
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(carrier.m_Vehicle, seats);
		AIGroup group;
		int seated;
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (seated >= men.Count())
				break;
			if (!seat || seat.GetType() != ECompartmentType.CARGO || !seat.IsCompartmentAccessible() || seat.GetOccupant())
				continue;
			if (seat.SpawnCharacterInCompartment(men[seated], group))
				seated++;
		}
		ZCR_GunUnit riders = new ZCR_GunUnit();
		riders.m_iIndex = m_aUnits.Count() + 1;
		riders.m_iSpawnedAt = ZCR_LossLog.Seconds();
		riders.m_sSide = side;
		riders.m_sKind = "riders";
		riders.m_Group = SCR_AIGroup.Cast(group);
		riders.m_Carrier = carrier;
		ZCR_Sampler.AddTestGroup(riders.m_Group, side);
		m_aUnits.Insert(riders);
		Print(string.Format("[ZCR][GUNTEST] t=%1 event=RIDERS side=%2 unit=%3 men=%4 carrier=%5", ZCR_LossLog.Seconds(), side, riders.m_iIndex, seated, carrier.m_iIndex), LogLevel.NORMAL);
	}

	// Riders get out 250 m short of the objective (or when their APC is lost, or has stood still 20 s), then assault it.
	protected void Storm(int now)
	{
		foreach (ZCR_GunUnit r : m_aUnits)
		{
			if (r.m_sKind != "riders" || r.m_bDismounted || r.m_bLost || !r.m_Group)
				continue;
			vector objective = m_mObjective.Get(r.m_sSide);
			string why = "";
			Vehicle apc;
			if (r.m_Carrier)
				apc = r.m_Carrier.m_Vehicle;
			if (!apc || r.m_Carrier.m_bLost)
				why = "carrier_lost";
			else if (vector.DistanceXZ(apc.GetOrigin(), objective) <= DISMOUNT_M + 10)
				why = "near";
			else
			{
				bool still = !apc.GetPhysics() || apc.GetPhysics().GetVelocity().Length() < 0.5;
				if (!still || now - r.m_iSpawnedAt < 30)
					r.m_iStillSince = 0;
				else if (r.m_iStillSince == 0)
					r.m_iStillSince = now;
				if (r.m_iStillSince > 0 && now - r.m_iStillSince >= 20)
					why = "stopped";
			}
			if (why.IsEmpty())
				continue;
			r.m_bDismounted = true;
			vector at = objective;
			if (apc)
				at = apc.GetOrigin();
			Waypoint(r, at, "{C40316EE26846CAB}Prefabs/AI/Waypoints/AIWaypoint_GetOut.et", 15);
			Waypoint(r, objective, "{B3E7B8DC2BAB8ACC}Prefabs/AI/Waypoints/AIWaypoint_SearchAndDestroy.et", 30);
			float enemy = 100000;
			if (apc && r.m_Carrier)
				enemy = NearestEnemy(r.m_Carrier);
			Print(string.Format("[ZCR][GUNTEST] t=%1 event=DISMOUNT side=%2 unit=%3 m=%4 enemy_m=%5 men=%6 why=%7", now, r.m_sSide, r.m_iIndex,
				Math.Round(vector.DistanceXZ(at, objective)), Math.Round(enemy), AICF_GroupRuntime.CountAliveAgents(r.m_Group), why), LogLevel.NORMAL);
			if (r.m_Carrier && !r.m_Carrier.m_bLost)
				GetGame().GetCallqueue().CallLater(Advance, 20000, false, r.m_Carrier, objective);
		}
	}

	// The APC follows its squad in and fights, instead of standing where it dropped them (Martin, watching the storm).
	protected void Advance(ZCR_GunUnit carrier, vector objective)
	{
		if (!carrier || carrier.m_bLost || !carrier.m_Group || !carrier.m_Vehicle)
			return;
		Waypoint(carrier, objective, "{B3E7B8DC2BAB8ACC}Prefabs/AI/Waypoints/AIWaypoint_SearchAndDestroy.et", 40);
		Print(string.Format("[ZCR][GUNTEST] t=%1 event=ADVANCE side=%2 unit=%3", ZCR_LossLog.Seconds(), carrier.m_sSide, carrier.m_iIndex), LogLevel.NORMAL);
	}

	// A side's objective taken: its living soldiers (any group) within 40 m of it, no living enemy within 60 m.
	protected void Taken(int now)
	{
		foreach (string side, vector objective : m_mObjective)
		{
			if (m_mTaken.Contains(side))
				continue;
			int ours, theirs;
			foreach (ZCR_GunUnit u : m_aUnits)
			{
				if (!u.m_Group)
					continue;
				array<AIAgent> agents = {};
				u.m_Group.GetAgents(agents);
				foreach (AIAgent a : agents)
				{
					IEntity man = null;
					if (a)
						man = a.GetControlledEntity();
					if (!man || AICF_GroupRuntime.CountAliveAgents(u.m_Group) == 0)
						continue;
					SCR_DamageManagerComponent dm = SCR_DamageManagerComponent.Cast(man.FindComponent(SCR_DamageManagerComponent));
					if (dm && dm.IsDestroyed())
						continue;
					float d = vector.DistanceXZ(man.GetOrigin(), objective);
					if (u.m_sSide == side && d <= 40)
						ours++;
					else if (u.m_sSide != side && d <= 60)
						theirs++;
				}
			}
			if (ours > 0 && theirs == 0)
			{
				m_mTaken.Set(side, now);
				Print(string.Format("[ZCR][GUNTEST] t=%1 event=TAKEN side=%2 men_near=%3", now, side, ours), LogLevel.NORMAL);
			}
		}
	}

	protected void CrewLater(ZCR_GunUnit unit, string side, vector target)
	{
		if (!unit || !unit.m_Vehicle)
			return;
		int crew = Crew(unit, side);
		Print(string.Format("[ZCR][GUNTEST] t=%1 event=CREW side=%2 unit=%3 kind=%4 crew=%5", ZCR_LossLog.Seconds(), side, unit.m_iIndex, unit.m_sKind, crew), LogLevel.NORMAL);
		if (unit.m_Group && target != vector.Zero)
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
		Waypoint(unit, target, "{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", 30);
	}

	protected static void Waypoint(ZCR_GunUnit unit, vector at, string prefab, float radius)
	{
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]);
		params.Transform[3] = at;
		AIWaypoint waypoint = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx(prefab, false, params: params));
		if (!waypoint)
			return;
		waypoint.SetCompletionRadius(radius);
		unit.m_Group.AddWaypoint(waypoint);
	}

	// For the director's PREV / NEXT: every living unit (a squad by its first soldier).
	static void Units(notnull array<IEntity> units, notnull array<string> labels)
	{
		if (!s_Instance)
			return;
		foreach (ZCR_GunUnit u : s_Instance.m_aUnits)
		{
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
			units.Insert(e);
			labels.Insert(Caption(u, e));
		}
	}

	// The camera caption: squads (the infantry tests) by what they do, how many are alive and how far the objective is;
	// vehicles by their rounds fired.
	protected static string Caption(ZCR_GunUnit u, IEntity e)
	{
		if (!u.m_Group || u.m_Vehicle)
			return string.Format("GUN TEST: %1 %2 %3 - %4 rounds fired", u.m_sSide, u.m_sKind, u.m_iIndex, u.m_iShots);
		if (u.m_sKind == "site")
			return string.Format("DRONE TEAM: %1 pilot and guard - %2 (resupply: the drone truck)", u.m_sSide, ZCR_DroneOperator.TeamText(u.m_Group));
		if (u.m_sKind == "drones")
		{
			// The caption stays for the whole shot - the pilot's state now is on his tag (ZCR_Watch), not here (24 Oct: shots that
			// began as a drone took off said "between flights" all through the flight).
			return string.Format("DRONE OPERATOR: %1 pilot (FPV goggles; the controller in hand and holding still while his FPV flies) and his guard - one FPV every %2 s, %3 men alive",
				u.m_sSide, DRONE_EVERY_S, AICF_GroupRuntime.CountAliveAgents(u.m_Group));
		}
		string doing = "holding";
		if (u.m_sRole == "attack" || u.m_sKind == "riders")
			doing = "attacking";
		else if (u.m_sRole == "defend")
			doing = "defending";
		string where;
		vector objective;
		if (s_Instance && s_Instance.m_mObjective.Find(u.m_sSide, objective) && u.m_sRole != "defend")
			where = string.Format(", %1 m to the objective", Math.Round(vector.DistanceXZ(e.GetOrigin(), objective)));
		return string.Format("INFANTRY: %1 squad %2 %3 - %4 men alive%5", u.m_sSide, u.m_iIndex, doing, AICF_GroupRuntime.CountAliveAgents(u.m_Group), where);
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
			label = Caption(u, e);
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
