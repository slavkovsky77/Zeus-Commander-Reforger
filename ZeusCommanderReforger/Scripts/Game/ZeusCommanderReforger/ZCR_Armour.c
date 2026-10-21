// Armour (Martin, 21 Oct: "usage of more types of vehicles - APC, tanks etc., maybe use some mods...
// make AI use them also for combat. That's important."). AI Conflict's rides carry a team and leave the
// vehicle empty at the objective; these fight. Each side keeps up to MAX crewed fighting vehicles:
//   unit 1: a tank  - US M1A1 Abrams, USSR T-72B (mods), else the IFV, else the game's LAV-25 / BTR-70
//   unit 2: an IFV  - US M2A2 Bradley, USSR BMP-1 (mods), else the LAV-25 / BTR-70
// Bought at the side's HQ for supplies (tank 800, IFV 500, APC 300 - the HQs sit full at 4000-4200 all
// match, the stock the trucks can't move to the front), on a road clear of things within 200 m. The
// crew (the faction's crewmen, in every driver and turret seat) is a group of its own, spawned in the
// seats the way the Game Master does. Orders every 15 s: the side's front (the plan's main effort, or
// where most of its attack teams go) - first a support position SHORT_M short of it on the way in,
// then into the base itself (Move waypoints: the crew stays aboard and fights from the vehicle). A unit lost (vehicle destroyed, no crew aboard) is
// bought again after REBUY_S.
// Logs [ZCR][ARMOUR] t= side= unit= event=BOUGHT|CREW|ORDER|STATUS|LOST|SKIP ...; kills and losses
// tagged in [ZCR][LOSS] (armour=, armour_hit=). -zcrNoArmour turns it off, -zcrArmourMax N (2).
// From 21 Oct 21:50 the tank slot takes an IFV too unless -zcrArmourTanks: the mods' tanks crash the game.
// Crash hunting (armour made the watched matches crash: 13 in 33 game hours vs 1 in 51 without, 21 Oct):
//   -zcrArmourStress  up to 6 units a side (tanks and IFVs in turn), free, from 30 s, bought again 30 s after a loss;
//   -zcrArmourKeepType  the vehicle keeps its own type (not made an APC);
//   -zcrArmourVanilla  the game's own LAV-25 / BTR-70 only (not the mods' vehicles);
//   -zcrArmourSet CIE  another author's vehicles (CIE T-72B, Leopard 2A6, Marder 1A3), nothing from WCS - the crash test;
//   -zcrArmourHold  bought and crewed, but no orders (stays where it was bought);
//   -zcrArmourOnly TANK|IFV  only the mods' tanks, or only their IFVs.
class ZCR_ArmourUnit
{
	FactionKey m_sSide;
	int m_iNo;
	Vehicle m_Vehicle;
	string m_sPrefab;
	string m_sKind;
	SCR_AIGroup m_Group;
	AIWaypoint m_Waypoint;
	vector m_vOrder;
	vector m_vFront;
	int m_iStill;
	int m_iDetour;
	int m_iRemounts;
	int m_iRemountAt;
	bool m_bSlow;
	int m_iSlowed;
	int m_iOrderedAt;
	int m_iRelocations;
	string m_sPhase;
	int m_iBoughtAt;
	int m_iLostAt = -1;
	int m_iCrew;
	vector m_vWas;
	vector m_vBoughtAt;
	int m_iNextStatus;
	int m_iRecrews;
	int m_iRecrewAt;
	bool m_bRecrewKicked;
	SCR_CampaignMilitaryBaseComponent m_RecrewBase;
}

class ZCR_Armour
{
	static const int START_S = 120;
	static const int REBUY_S = 300;
	static const float SHORT_M = 350;
	static const int RESERVE = 1200;     // the HQ keeps this much for its recruits and builders

	protected static ref array<ref ZCR_ArmourUnit> s_aUnits = {};
	protected static ref map<IEntity, ZCR_ArmourUnit> s_mVehicle = new map<IEntity, ZCR_ArmourUnit>();
	protected static ref map<string, int> s_mNextTick = new map<string, int>();
	protected static ref map<string, vector> s_mFront = new map<string, vector>();
	protected static ref map<string, int> s_mFrontAt = new map<string, int>();

	static void Tick(FactionKey side, SCR_CampaignFaction faction, vector front)
	{
		if (!Replication.IsServer() || System.IsCLIParam("zcrNoArmour") || !faction)
			return;
		int now = ZCR_LossLog.Seconds();
		if (!s_bGuard)
		{
			s_bGuard = true;
			GetGame().GetCallqueue().CallLater(Guard, 1000, true);
		}
		if (now < StartS() || now < s_mNextTick.Get(side))
			return;
		s_mNextTick.Set(side, now + 15);
		front = Front(side, front);
		// Held 3 minutes: AI Conflict's main target moved Airport Base > Farm > Military Training Area within
		// 4 minutes and the Abrams chased each (21 Oct test). A front taken by the side is left at once.
		vector held;
		if (s_mFront.Find(side, held) && held != vector.Zero && front != vector.Zero && vector.DistanceXZ(held, front) > 300 &&
			now - s_mFrontAt.Get(side) < 180 && !Own(side, held))
			front = held;
		else if (front != vector.Zero && (!s_mFront.Find(side, held) || vector.DistanceXZ(held, front) > 300))
		{
			s_mFront.Set(side, front);
			s_mFrontAt.Set(side, now);
		}
		for (int no = 1; no <= Max(); no++)
		{
			ZCR_ArmourUnit unit = Find(side, no);
			if (!unit)
			{
				unit = new ZCR_ArmourUnit();
				unit.m_sSide = side;
				unit.m_iNo = no;
				s_aUnits.Insert(unit);
			}
			if (unit.m_Vehicle)
			{
				if (Lost(unit, now))
					continue;
				if (!System.IsCLIParam("zcrArmourHold") && !Recrewing(unit, now) && !Remounting(unit, now))
					Order(unit, front, now);
				Status(unit, front, now);
			}
			else if (front != vector.Zero && (unit.m_iLostAt < 0 || now - unit.m_iLostAt >= RebuyS()))
				Buy(unit, faction, front, now);
		}
	}

	// Where the armour goes: the plan's main effort (or AI Conflict's main target) unless that is a base of
	// the side's own - 21 Oct test: an attack team "attacking" the USSR's own main base made it the front
	// and the T-72 and BMP-1 were sent to assault their own HQ - else the enemy-held base most of the
	// side's attack teams are sent to.
	protected static vector Front(FactionKey side, vector given)
	{
		if (given != vector.Zero && !Own(side, given))
			return given;
		AICF_FactionState state = ZCR_Strategist.s_mStates.Get(side);
		if (!state)
			return vector.Zero;
		map<IEntity, int> votes = new map<IEntity, int>();
		IEntity best;
		int most;
		for (int s; s < state.GetSlotCount(); s++)
		{
			AICF_GroupSlot slot = state.GetSlot(s);
			if (!slot || slot.GetRole() != AICF_EGroupRole.ATTACK || !slot.GetTargetBase() || !slot.GetTargetBase().GetOwner())
				continue;
			if (slot.GetTargetBase().GetFaction() && slot.GetTargetBase().GetFaction().GetFactionKey() == side)
				continue;
			IEntity owner = slot.GetTargetBase().GetOwner();
			int n = votes.Get(owner) + 1;
			votes.Set(owner, n);
			if (n > most)
			{
				most = n;
				best = owner;
			}
		}
		if (!best)
			return vector.Zero;
		return best.GetOrigin();
	}

	// A base of the side's own within 150 m of the spot.
	protected static bool Own(FactionKey side, vector at)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return false;
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (base && base.GetOwner() && base.GetFaction() && base.GetFaction().GetFactionKey() == side &&
				vector.DistanceXZ(base.GetOwner().GetOrigin(), at) < 150)
				return true;
		}
		return false;
	}

	// Friendly soldiers in the way: the T-72 and BMP-1 ran over their own MG gunner and medic in 15 minutes
	// (21 Oct) - the game's AI driver doesn't steer round soldiers on foot. Every second: a friendly soldier
	// on foot within 30 m ahead of the hull and 7 m of its line slows it to 5 km/h; clear, it cruises at
	// CRUISE_KMH (the game's own cruise limit for an AI driver). Vehicles too (Martin's /bad 21 Oct 21:03, "soviet tank
	// crashing vehicles": the T-72, driving back for a new crew against its own column, rammed a USSR UAZ-452 on the
	// road and ran over a medic and a machine gunner) - any vehicle not the enemy's within 20 m ahead and 5 m of the line.
	static const float CRUISE_KMH = 35;
	protected static bool s_bGuard;
	protected static ref array<IEntity> s_aAhead;

	protected static void Guard()
	{
		foreach (ZCR_ArmourUnit unit : s_aUnits)
		{
			if (!unit.m_Vehicle || !unit.m_Group)
				continue;
			AICarMovementComponent car = AICarMovementComponent.Cast(unit.m_Vehicle.FindComponent(AICarMovementComponent));
			if (!car)
				continue;
			bool slow = FriendAhead(unit);
			if (slow == unit.m_bSlow && unit.m_iSlowed > 0)
				continue;
			if (slow)
			{
				car.SetCruiseSpeed(5);
				unit.m_iSlowed++;
			}
			else
			{
				car.SetCruiseSpeed(CRUISE_KMH);
				if (unit.m_iSlowed == 0)
					unit.m_iSlowed = -1;     // the cruise limit is set (no slowdown yet)
			}
			unit.m_bSlow = slow;
		}
	}

	protected static bool FriendAhead(ZCR_ArmourUnit unit)
	{
		vector mat[4];
		unit.m_Vehicle.GetTransform(mat);
		vector forward = mat[2];
		forward[1] = 0;
		forward.Normalize();
		s_aAhead = {};
		GetGame().GetWorld().QueryEntitiesBySphere(mat[3] + forward * 10, 22, CollectMan, null, EQueryEntitiesFlags.DYNAMIC);
		foreach (IEntity e : s_aAhead)
		{
			if (Vehicle.Cast(e))
			{
				if (e == unit.m_Vehicle || e.GetRootParent() == unit.m_Vehicle)
					continue;
				string owner = ZCR_LossLog.SideOf(e);
				if ((owner == "US" || owner == "USSR") && owner != unit.m_sSide)
					continue;
				vector off3 = e.GetOrigin() - mat[3];
				off3[1] = 0;
				float ahead = vector.Dot(off3, forward);
				if (ahead > 0 && ahead < 20 && (off3 - forward * ahead).Length() < 5)
					return true;
				continue;
			}
			ChimeraCharacter c = ChimeraCharacter.Cast(e);
			if (!c || c.IsInVehicle() || !AICF_GroupRuntime.IsAliveCharacter(c) || ZCR_LossLog.SideOf(c) != unit.m_sSide)
				continue;
			vector rel = c.GetOrigin() - mat[3];
			rel[1] = 0;
			// Anyone within 10 m round the hull too: a tracked hull turns on the spot (the BMP-1 killed its
			// side's squad leader 5 m away 18 s after it was bought, before moving off).
			if (rel.Length() < 10)
				return true;
			float along = vector.Dot(rel, forward);
			if (along < 0 || along > 30)
				continue;
			vector off = rel - forward * along;
			if (off.Length() < 7)
				return true;
		}
		return false;
	}

	protected static bool CollectMan(IEntity e)
	{
		if (ChimeraCharacter.Cast(e) || Vehicle.Cast(e))
			s_aAhead.Insert(e);
		return true;
	}

	static int Max()
	{
		string value;
		if (System.GetCLIParam("zcrArmourMax", value) && !value.IsEmpty())
			return Math.ClampInt(value.ToInt(), 0, 6);
		if (Stress())
			return 6;
		return 2;
	}

	static bool Stress()
	{
		return System.IsCLIParam("zcrArmourStress");
	}

	protected static int StartS()
	{
		if (Stress())
			return 30;
		return START_S;
	}

	protected static int RebuyS()
	{
		if (Stress())
			return 30;
		return REBUY_S;
	}

	// The watch labels (kind A): "US TANK M1A1_Olive - ASSAULT Farm, crew 3/3, 87%".
	static void List(array<vector> at, array<string> sides, array<string> labels)
	{
		foreach (ZCR_ArmourUnit unit : s_aUnits)
		{
			if (!unit.m_Vehicle)
				continue;
			float health = 1;
			SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(unit.m_Vehicle.FindComponent(SCR_DamageManagerComponent));
			if (damage)
				health = damage.GetHealthScaled();
			string doing = "at base";
			if (!unit.m_sPhase.IsEmpty())
				doing = Doing(unit.m_sPhase) + " " + FrontName(unit.m_vFront);
			at.Insert(unit.m_Vehicle.GetOrigin());
			sides.Insert(unit.m_sSide);
			// "M1A1 Abrams" on the screen; with DETAILS "US TANK M1A1 Abrams - attacking Farm, crew 3/3, 100%".
			labels.Insert(Display(unit.m_sPrefab) + "|" + string.Format("%1 %2 %3 - %4, crew %5/%6, ", unit.m_sSide, unit.m_sKind, Display(unit.m_sPrefab), doing, Aboard(unit), unit.m_iCrew) +
				string.Format("%1", Math.Round(100 * health)) + "%");
		}
	}

	// One to show (the director's armour shot): the wanted side first, a unit going in (ASSAULT) before
	// one on its way, crewed.
	static bool Pick(string want, out IEntity vehicle, out string label)
	{
		ZCR_ArmourUnit best;
		int bestScore = -1;
		foreach (ZCR_ArmourUnit unit : s_aUnits)
		{
			if (!unit.m_Vehicle || unit.m_sPhase.IsEmpty() || Aboard(unit) == 0)
				continue;
			int score = 1;
			if (unit.m_sPhase == "ASSAULT")
				score += 1;
			if (unit.m_sSide == want)
				score += 2;
			if (score > bestScore)
			{
				bestScore = score;
				best = unit;
			}
		}
		if (!best)
			return false;
		vehicle = best.m_Vehicle;
		s_ShownVehicle = best.m_Vehicle;
		s_iShownAt = ZCR_LossLog.Seconds();
		label = string.Format("%1 %2 %3 - %4 %5, crew %6/%7", best.m_sSide, best.m_sKind, Display(best.m_sPrefab), Doing(best.m_sPhase), FrontName(best.m_vFront), Aboard(best), best.m_iCrew);
		return true;
	}

	// The crew stays in an intact vehicle of ours (ZCR_AIGetOutVehicle below): over 35% health and not
	// burning off below it.
	static bool KeepAboard(IEntity vehicle)
	{
		if (!vehicle || System.IsCLIParam("zcrArmourLetOut"))
			return false;
		IEntity root = vehicle.GetRootParent();
		if (!root)
			root = vehicle;
		ZCR_ArmourUnit unit;
		if (!s_mVehicle.Find(root, unit) || !unit)
			return false;
		return Health(unit) >= 0.35;
	}

	// What the watcher reads: the vehicle's common name and what it is doing.
	protected static string Display(string prefab)
	{
		if (prefab.Contains("M1A1"))
			return "M1A1 Abrams";
		if (prefab.Contains("M2A2"))
			return "M2A2 Bradley";
		if (prefab.Contains("T72"))
			return "T-72";
		if (prefab.Contains("BMP1"))
			return "BMP-1";
		if (prefab.Contains("LAV25"))
			return "LAV-25";
		if (prefab.Contains("BTR70"))
			return "BTR-70";
		return prefab;
	}

	protected static string Doing(string phase)
	{
		if (phase == "APPROACH")
			return "moving up to";
		if (phase == "ASSAULT")
			return "attacking";
		if (phase == "REMOUNT")
			return "crew boarding, front";
		if (phase == "RECREW")
			return "back to a base for a new crew, front";
		return phase;
	}

	// Own soldiers within 20 m of a gunner's target or 8 m of his line of fire (ZCR_AIAttackBehavior below holds the gun): the main
	// gun's rounds burst among them - armour-6: a T-72 killed 3 of its own at once 8-42 m away, another at
	// 93 m. Only our armour's gunners; checked at most every 0.5 s a gunner.
	protected static ref map<IEntity, int> s_mHoldCheckAt = new map<IEntity, int>();
	protected static ref map<IEntity, bool> s_mHold = new map<IEntity, bool>();
	protected static int s_iHeld;

	static bool FriendsNearTarget(IEntity gunner, vector target)
	{
		if (!gunner || target == vector.Zero || System.IsCLIParam("zcrArmourFreeFire") || !IsCrew(gunner))
			return false;
		int now = System.GetTickCount();
		int at;
		if (s_mHoldCheckAt.Find(gunner, at) && now - at < 500)
			return s_mHold.Get(gunner);
		s_mHoldCheckAt.Set(gunner, now);
		string side = ZCR_LossLog.SideOf(gunner);
		// Near the target (20 m) or near the line of fire (8 m either side, from 5 m out to 60 m past the
		// target): armour-11's Abrams killed 10 of its own at 13-321 m - soldiers between it and its target.
		vector from = gunner.GetOrigin();
		vector line = target - from;
		line[1] = 0;
		float length = line.Length();
		if (length < 1)
			return false;
		vector dir = line * (1 / length);
		s_aAhead = {};
		GetGame().GetWorld().QueryEntitiesBySphere(from + line * 0.5, Math.Min(length * 0.5 + 25, 450), CollectMan, null, EQueryEntitiesFlags.DYNAMIC);
		bool hold;
		foreach (IEntity e : s_aAhead)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(e);
			if (!c || c.IsInVehicle() || !AICF_GroupRuntime.IsAliveCharacter(c) || ZCR_LossLog.SideOf(c) != side)
				continue;
			vector rel = c.GetOrigin() - from;
			rel[1] = 0;
			if (vector.DistanceXZ(c.GetOrigin(), target) < 20)
			{
				hold = true;
				break;
			}
			float along = vector.Dot(rel, dir);
			if (along < 5 || along > length + 60)     // rounds that miss fly on: armour-16 killed a friendly 68 m out, its target 35 m
				continue;
			if ((rel - dir * along).Length() < 8)
			{
				hold = true;
				break;
			}
		}
		if (hold && !s_mHold.Get(gunner))
			s_iHeld++;
		s_mHold.Set(gunner, hold);
		return hold;
	}

	// The soldier crews one of our armour units (the soldier layers leave him in his seat).
	static bool IsCrew(IEntity soldier)
	{
		if (!soldier)
			return false;
		AIControlComponent control = AIControlComponent.Cast(soldier.FindComponent(AIControlComponent));
		if (!control || !control.GetAIAgent())
			return false;
		AIGroup group = control.GetAIAgent().GetParentGroup();
		if (!group)
			return false;
		foreach (ZCR_ArmourUnit unit : s_aUnits)
		{
			if (unit.m_Group == group)
				return true;
		}
		return false;
	}

	// [ZCR][LOSS] tags: the killer was one of our armour units (its vehicle or crew), the victim was.
	static string Note(IEntity victim, IEntity killer)
	{
		string note;
		ZCR_ArmourUnit by = UnitOf(killer);
		if (by)
		{
			note += string.Format(" armour=%1", by.m_sKind);
			// Our own killed by armour: what its gunner was firing at (friendly fire, note 250).
			if (victim && ZCR_LossLog.SideOf(victim) == by.m_sSide && killer)
			{
				SCR_AICombatComponent combat = SCR_AICombatComponent.Cast(killer.FindComponent(SCR_AICombatComponent));
				BaseTarget target;
				if (combat)
					target = combat.GetCurrentTarget();
				if (target)
				{
					vector tp = target.GetLastSeenPosition();
					note += string.Format(" gunner_target=%1 target_m=%2 target_side=%3", ZCR_LossLog.ShortName(target.GetTargetEntity()),
						Math.Round(vector.Distance(killer.GetOrigin(), tp)), ZCR_LossLog.SideOf(target.GetTargetEntity()));
				}
				else
					note += " gunner_target=none";
				note += string.Format(" held=%1", s_mHold.Get(killer));
			}
		}
		ZCR_ArmourUnit hit = UnitOf(victim);
		if (hit)
			note += string.Format(" armour_hit=%1", hit.m_sKind);
		return note;
	}

	// The unit the entity belongs to: its vehicle, a soldier of its crew, or anything sitting in its vehicle.
	protected static ZCR_ArmourUnit UnitOf(IEntity e)
	{
		if (!e)
			return null;
		ZCR_ArmourUnit unit;
		if (s_mVehicle.Find(e, unit))
			return unit;
		ChimeraCharacter character = ChimeraCharacter.Cast(e);
		if (character && character.GetCompartmentAccessComponent())
		{
			IEntity vehicle = character.GetCompartmentAccessComponent().GetVehicleIn(character);
			if (vehicle && s_mVehicle.Find(vehicle, unit))
				return unit;
		}
		AIControlComponent control = AIControlComponent.Cast(e.FindComponent(AIControlComponent));
		if (control && control.GetAIAgent() && control.GetAIAgent().GetParentGroup())
		{
			foreach (ZCR_ArmourUnit u : s_aUnits)
			{
				if (u.m_Group && u.m_Group == control.GetAIAgent().GetParentGroup())
					return u;
			}
		}
		return null;
	}

	protected static ZCR_ArmourUnit Find(FactionKey side, int no)
	{
		foreach (ZCR_ArmourUnit unit : s_aUnits)
		{
			if (unit.m_sSide == side && unit.m_iNo == no)
				return unit;
		}
		return null;
	}

	// Most wanted first; a prefab whose mod isn't loaded doesn't load and the next one is used.
	protected static void Choices(FactionKey side, int no, array<string> prefabs, array<string> kinds, array<int> costs)
	{
		bool us = side == "US";
		if (System.IsCLIParam("zcrArmourVanilla"))
		{
			prefabs.Insert(Pick(us, "{590E677BBCD1D26E}Prefabs/Vehicles/Wheeled/Conflict_Variants/LAV25_Conflict.et", "{BD75A18920BD1278}Prefabs/Vehicles/Wheeled/Conflict_Variants/BTR70_Conflict.et"));
			kinds.Insert("APC");
			costs.Insert(300);
			return;
		}
		// -zcrArmourOnly TANK|IFV: every unit a tank (Abrams / T-72) or every unit an IFV (Bradley / BMP-1).
		// No tanks unless -zcrArmourTanks (21 Oct stress test: the mods' tanks crash the game - tanks only froze or
		// crashed in 8-10 game minutes, with or without our APC typing; IFVs only ran 40 minutes clean, and the
		// game's own LAV-25 / BTR-70 too). -zcrArmourTankSide US|USSR: tanks for that side only (which tank is it).
		string only;
		System.GetCLIParam("zcrArmourOnly", only);
		bool tank = no == 1 || (Stress() && no % 2 == 1);
		if (only == "TANK")
			tank = true;
		else if (only == "IFV")
			tank = false;
		string tankSide;
		if (System.GetCLIParam("zcrArmourTankSide", tankSide) && !tankSide.IsEmpty())
			tank = tank && side == tankSide;
		else if (!System.IsCLIParam("zcrArmourTanks") && only != "TANK")
			tank = false;
		// -zcrArmourSet CIE (Martin, 21 Oct 21:35: "maybe another vehicle mod?"): another author's vehicles with
		// nothing from WCS / SpaceCore, for the crash test - CIE T-72B for the USSR, CIE Leopard 2A6 as the US
		// tank, the Marder 1A3 as both sides' IFV (the only non-WCS IFV downloaded). lab/stress.py --variant cie.
		string armourSet;
		System.GetCLIParam("zcrArmourSet", armourSet);
		if (armourSet == "CIE")
		{
			if (tank)
			{
				prefabs.Insert(Pick(us, "{1C5FE7B7FF49BB8E}Prefabs/Vehicles/Tracked/Leopard/Leopard2A_Base.et", "{E87F0D0B1C88BFD7}Prefabs/Vehicles/Tracked/T72B_RU.et"));
				kinds.Insert("TANK");
				costs.Insert(800);
			}
			prefabs.Insert("{7D0A4C3F2E19B6A8}Prefabs/Vehicles/Tracked/Marder_1A3.et");
			kinds.Insert("IFV");
			costs.Insert(500);
		}
		else
		{
			if (tank)
			{
				prefabs.Insert(Pick(us, "{E80B119CFDF50ABE}Prefabs/Vehicles/Tracked/M1A1/M1A1_Olive.et", "{726286E1F9570EA1}Prefabs/Vehicles/Tracked/T72B/T72B_Base.et"));
				kinds.Insert("TANK");
				costs.Insert(800);
			}
			prefabs.Insert(Pick(us, "{24223D0679CDD612}Prefabs/Vehicles/Tracked/M2A2/M2A2_OD.et", "{1DC01AAACFFA8B63}Prefabs/Vehicles/Tracked/BMP1/BMP1_Base.et"));
			kinds.Insert("IFV");
			costs.Insert(500);
		}
		prefabs.Insert(Pick(us, "{590E677BBCD1D26E}Prefabs/Vehicles/Wheeled/Conflict_Variants/LAV25_Conflict.et", "{BD75A18920BD1278}Prefabs/Vehicles/Wheeled/Conflict_Variants/BTR70_Conflict.et"));
		kinds.Insert("APC");
		costs.Insert(300);
		prefabs.Insert(Pick(us, "{0FBF8F010F81A4E5}Prefabs/Vehicles/Wheeled/LAV25/LAV25.et", "{C012BB3488BEA0C2}Prefabs/Vehicles/Wheeled/BTR70/BTR70.et"));
		kinds.Insert("APC");
		costs.Insert(300);
	}

	protected static string Pick(bool us, string usPrefab, string ussrPrefab)
	{
		if (us)
			return usPrefab;
		return ussrPrefab;
	}

	protected static void Buy(ZCR_ArmourUnit unit, SCR_CampaignFaction faction, vector front, int now)
	{
		SCR_CampaignMilitaryBaseComponent hq = faction.GetMainBase();
		if (!hq || !hq.GetOwner())
			return;
		array<string> prefabs = {};
		array<string> kinds = {};
		array<int> costs = {};
		Choices(unit.m_sSide, unit.m_iNo, prefabs, kinds, costs);
		if (Stress())
		{
			for (int c; c < costs.Count(); c++)
				costs[c] = 0;
		}
		int pick = -1;
		for (int i; i < prefabs.Count(); i++)
		{
			Resource res = Resource.Load(prefabs[i]);
			if (res && res.IsValid())
			{
				pick = i;
				break;
			}
		}
		if (pick < 0)
		{
			Skip(unit, now, "NO_PREFAB");
			return;
		}
		// Bought at the side's base nearest its front, 400 m+ short of it, when it has the supplies (keeping
		// FORWARD_RESERVE) and a road spot; else at the HQ (keeping RESERVE). From the HQ the armour drove
		// 1-1.5 km to its front and FPV drones took its crews on the way (watched match 05:38).
		vector pose[4];
		SCR_CampaignMilitaryBaseComponent from = Forward(unit.m_sSide, hq, front, costs[pick]);
		if (!from || !FindSpot(from.GetOwner().GetOrigin(), front, pose))
		{
			from = hq;
			if (!Stress() && hq.GetSupplies() < costs[pick] + RESERVE)
			{
				Skip(unit, now, string.Format("NO_SUPPLIES have=%1 need=%2", Math.Round(hq.GetSupplies()), costs[pick] + RESERVE));
				return;
			}
			if (!FindSpot(hq.GetOwner().GetOrigin(), front, pose))
			{
				Skip(unit, now, "NO_SPOT " + s_sSpotWhy);
				return;
			}
		}
		hq = from;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		for (int axis; axis < 4; axis++)
			params.Transform[axis] = pose[axis];
		ZCR_Trace.At("spawn", prefabs[pick], pose[3], "armour_bought");
		Vehicle vehicle = Vehicle.Cast(GetGame().SpawnEntityPrefab(Resource.Load(prefabs[pick]), GetGame().GetWorld(), params));
		if (!vehicle)
		{
			Skip(unit, now, "SPAWN_FAILED");
			return;
		}
		// Typed APC: the game keeps gunners of APCs in their turret when they can't hit what they see; the
		// mods' tanks and IFVs aren't, and with no driver aboard their gunners got out to look (21 Oct test).
		string typeWas = typename.EnumToString(EVehicleType, vehicle.m_eVehicleType);
		if (!System.IsCLIParam("zcrArmourKeepType"))
			vehicle.m_eVehicleType = EVehicleType.APC;
		hq.AddSupplies(-costs[pick]);
		unit.m_Vehicle = vehicle;
		unit.m_sPrefab = ZCR_LossLog.ShortName(vehicle);
		unit.m_sKind = kinds[pick];
		unit.m_Group = null;
		unit.m_Waypoint = null;
		unit.m_vOrder = vector.Zero;
		unit.m_vFront = vector.Zero;
		unit.m_iStill = 0;
		unit.m_iDetour = 0;
		unit.m_iRemounts = 0;
		unit.m_iRemountAt = 0;
		unit.m_bSlow = false;
		unit.m_iSlowed = 0;
		unit.m_iRelocations = 0;
		unit.m_iRecrews = 0;
		unit.m_bRecrewKicked = false;
		unit.m_RecrewBase = null;
		unit.m_sPhase = "";
		unit.m_iBoughtAt = now;
		unit.m_iCrew = 0;
		unit.m_vWas = pose[3];
		unit.m_vBoughtAt = pose[3];
		unit.m_iNextStatus = now + 60;
		s_mVehicle.Set(vehicle, unit);
		Log(unit, now, "BOUGHT", string.Format("prefab=%1 kind=%2 cost=%3 base=%4 stock_after=%5 x=%6 z=%7 type_was=%8" + string.Format(" road_w=%1 trees=%2", Math.Round(s_fSpotWidth), s_iSpotTrees), unit.m_sPrefab, unit.m_sKind,
			costs[pick], ZCR_Strategist.BaseName(hq), Math.Round(hq.GetSupplies()), Math.Round(pose[3][0]), Math.Round(pose[3][2]), typeWas));
		// The turrets are slotted entities: their seats are there a moment after the hull.
		GetGame().GetCallqueue().CallLater(Crew, 1500, false, unit);
	}

	static const int FORWARD_RESERVE = 500;

	protected static SCR_CampaignMilitaryBaseComponent Forward(FactionKey side, SCR_CampaignMilitaryBaseComponent hq, vector front, int cost)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system || front == vector.Zero)
			return null;
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		SCR_CampaignMilitaryBaseComponent best;
		float bestDist = vector.DistanceXZ(hq.GetOwner().GetOrigin(), front) - 300;
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || base == hq || !base.GetOwner() || !base.GetFaction() || base.GetFaction().GetFactionKey() != side ||
				base.GetType() == SCR_ECampaignBaseType.RELAY || base.GetSupplies() < cost + FORWARD_RESERVE)
				continue;
			float d = vector.DistanceXZ(base.GetOwner().GetOrigin(), front);
			if (d >= 400 && d < bestDist)
			{
				bestDist = d;
				best = base;
			}
		}
		return best;
	}

	protected static void Skip(ZCR_ArmourUnit unit, int now, string reason)
	{
		// Once a minute at most per unit (the tick is every 15 s).
		if (now < unit.m_iNextStatus)
			return;
		unit.m_iNextStatus = now + 60;
		Log(unit, now, "SKIP", "reason=" + reason);
	}

	// The faction's crewman in every accessible driver and turret seat (the turrets' own seats included).
	protected static void Crew(ZCR_ArmourUnit unit)
	{
		if (!unit || !unit.m_Vehicle)
			return;
		string character = "{E1CB513B8B9B08F4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_Crew.et";
		if (unit.m_sSide != "US")
			character = "{9FFEF10757E742EB}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_Crew.et";
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
			// One driver: tanks with a second driver's seat (the FIA copies) take one.
			if (seat.GetType() == ECompartmentType.PILOT && pilots > 0)
				continue;
			ZCR_Trace.Ent("crew", unit.m_Vehicle, "armour_crew");
			if (!seat.SpawnCharacterInCompartment(character, group))
				continue;
			if (seat.GetType() == ECompartmentType.PILOT)
				pilots++;
			else
				turrets++;
		}
		unit.m_Group = SCR_AIGroup.Cast(group);
		unit.m_iCrew = pilots + turrets;
		// The vehicle registered as the group's own (the game does it when soldiers join from inside a vehicle;
		// made sure here, as AI Conflict does for its crews).
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(unit.m_Vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (unit.m_Group && usage && unit.m_Group.GetGroupUtilityComponent() && !unit.m_Group.GetGroupUtilityComponent().IsUsableVehicle(usage))
			unit.m_Group.GetGroupUtilityComponent().AddUsableVehicle(usage);
		if (unit.m_Group && unit.m_Group.GetGroupUtilityComponent())
		{
			unit.m_Group.GetGroupUtilityComponent().SetCombatMode(EAIGroupCombatMode.FIRE_AT_WILL);
			unit.m_Group.GetGroupUtilityComponent().EvaluateCombatMode();
		}
		// The hull's world bounds: AI Conflict keeps recruits 2 m off any vehicle's bounds - a mod hull with
		// oversized bounds would block a base's spawn area (recruit timeouts came only with the mods loaded).
		vector mins, maxs;
		unit.m_Vehicle.GetWorldBounds(mins, maxs);
		Log(unit, ZCR_LossLog.Seconds(), "CREW", string.Format("prefab=%1 seats=%2 driver=%3 turret=%4 group=%5 bounds=%6x%7x%8", unit.m_sPrefab, seats.Count(),
			pilots, turrets, unit.m_Group != null, Math.Round(maxs[0] - mins[0]), Math.Round(maxs[1] - mins[1]), Math.Round(maxs[2] - mins[2])));
	}

	// Lost: the vehicle destroyed or gone, or nobody of the crew aboard any more.
	protected static bool Lost(ZCR_ArmourUnit unit, int now)
	{
		string reason;
		if (!unit.m_Vehicle)
			reason = "GONE";
		else
		{
			SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(unit.m_Vehicle.FindComponent(SCR_DamageManagerComponent));
			if (damage && damage.GetState() == EDamageState.DESTROYED)
				reason = "DESTROYED";
			else if (now - unit.m_iBoughtAt > 20 && Aboard(unit) == 0 && unit.m_sPhase != "REMOUNT" &&
				(unit.m_iRemounts >= 3 || !unit.m_Group || AICF_GroupRuntime.CountAliveAgents(unit.m_Group) == 0 || Health(unit) < 0.35))
				reason = "CREW_OUT";
		}
		if (reason.IsEmpty())
			return false;
		vector at;
		if (unit.m_Vehicle)
			at = unit.m_Vehicle.GetOrigin();
		Log(unit, now, "LOST", string.Format("prefab=%1 reason=%2 lived_s=%3 phase=%4 x=%5 z=%6", unit.m_sPrefab, reason, now - unit.m_iBoughtAt,
			unit.m_sPhase, Math.Round(at[0]), Math.Round(at[2])));
		// The crew that got out walks on as infantry with its last order.
		if (unit.m_Vehicle)
			s_mVehicle.Remove(unit.m_Vehicle);
		unit.m_Vehicle = null;
		unit.m_Group = null;
		unit.m_Waypoint = null;
		unit.m_iLostAt = now;
		unit.m_iNextStatus = 0;
		return true;
	}

	// The crew still in the vehicle: the crew group's living soldiers sitting in a vehicle (they board only
	// theirs). Not by walking the vehicle's seats - that reads the turrets' attached entities several times a
	// second, and watched matches crashed in the engine's entity update soon after FPV drones went for the
	// armour (a turret hit mid-deletion is a suspect).
	protected static int Aboard(ZCR_ArmourUnit unit)
	{
		if (!unit.m_Vehicle || !unit.m_Group)
			return 0;
		array<AIAgent> agents = {};
		unit.m_Group.GetAgents(agents);
		int n;
		foreach (AIAgent agent : agents)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (c && AICF_GroupRuntime.IsAliveCharacter(c) && c.IsInVehicle())
				n++;
		}
		return n;
	}

	// The new order first, then the old one out of the group, deleted 20 s later: watched matches crashed in
	// the engine's entity update 3-60 s after a stuck unit's waypoint was swapped (06:28, 06:30) - a deleted
	// waypoint the moving vehicle's path may still have pointed at.
	protected static void ReplaceWaypoint(ZCR_ArmourUnit unit, AIWaypoint waypoint)
	{
		AIWaypoint old = unit.m_Waypoint;
		unit.m_Group.AddWaypoint(waypoint);
		if (old)
		{
			unit.m_Group.RemoveWaypoint(old);
			GetGame().GetCallqueue().CallLater(DeleteLater, 20000, false, old);
		}
	}

	protected static void DeleteLater(AIWaypoint waypoint)
	{
		if (waypoint)
			SCR_EntityHelper.DeleteEntityAndChildren(waypoint);
	}

	// Where the side fights near its front: the middle of the last 150 s's losses (either side) within 700 m
	// of the front, when there are 3 or more; else the front itself. Watched two-army matches: armour drove to
	// the enemy base's centre while the fighting was elsewhere - 0-3 kills a match.
	protected static vector FightNear(vector front, int now)
	{
		vector sum;
		int n;
		for (int i = ZCR_LossLog.s_aRecentPos.Count() - 1; i >= 0; i--)
		{
			if (now - ZCR_LossLog.s_aRecentAt[i] > 150)
				break;
			vector p = ZCR_LossLog.s_aRecentPos[i];
			if (vector.DistanceXZ(p, front) > 700)
				continue;
			sum = sum + p;
			n++;
		}
		if (n < 3)
			return front;
		return sum * (1.0 / n);
	}

	// Stuck for good (3 detours tried): moved along the road to a clear spot 25-250 m on, nearest the front -
	// the way AI Conflict frees its stuck FIA patrol vehicles (velocity zeroed, transform set). Not while the
	// director is showing it, at most twice a unit. Watched 08:22: US armour sat all match at two spots by
	// the north HQ (1542 3336, 1611 3083).
	protected static IEntity s_ShownVehicle;
	protected static int s_iShownAt;

	protected static bool Relocate(ZCR_ArmourUnit unit, vector front, int now)
	{
		if (System.IsCLIParam("zcrArmourNoRelocate") || unit.m_iRelocations >= 2 || Health(unit) < 0.35)
			return false;
		if (s_ShownVehicle == unit.m_Vehicle && now - s_iShownAt < 40)
			return false;
		Physics physics = unit.m_Vehicle.GetPhysics();
		if (!physics || physics.GetVelocity().Length() > 3)
			return false;
		vector from = unit.m_Vehicle.GetOrigin();
		vector pose[4];
		if (!FindSpot(from, front, pose) || vector.DistanceXZ(pose[3], from) < 30)
			return false;
		physics.SetVelocity(vector.Zero);
		physics.SetAngularVelocity(vector.Zero);
		ZCR_Trace.Ent("move", unit.m_Vehicle, string.Format("relocate_to_%1_%2", Math.Round(pose[3][0]), Math.Round(pose[3][2])));
		if (!unit.m_Vehicle.SetWorldTransform(pose))
			return false;
		unit.m_iRelocations++;
		unit.m_vWas = pose[3];
		Log(unit, now, "RELOCATED", string.Format("prefab=%1 from_x=%2 from_z=%3 to_x=%4 to_z=%5 count=%6", unit.m_sPrefab, Math.Round(from[0]), Math.Round(from[2]),
			Math.Round(pose[3][0]), Math.Round(pose[3][2]), unit.m_iRelocations));
		return true;
	}

	protected static float Health(ZCR_ArmourUnit unit)
	{
		if (!unit.m_Vehicle)
			return 0;
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(unit.m_Vehicle.FindComponent(SCR_DamageManagerComponent));
		if (!damage)
			return 1;
		return damage.GetHealthScaled();
	}

	// Goals on the road network: a vehicle's move to a spot it can't path to fails, and the game then
	// releases the group's vehicle - the BMP-1's crew got out 75 s after its order (21 Oct test).
	protected static vector OnRoad(vector from, vector goal)
	{
		SCR_AIWorld ai = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		vector road;
		// Only a road point near the goal: the T-72 and BMP-1's support point was pulled back to the HQ's own
		// roads 40 m from where they stood, 486 m from the front, and they sat there 10 minutes.
		if (ai && ai.GetRoadNetworkManager() && ai.GetRoadNetworkManager().GetReachableWaypointInRoad(from, goal, 150, road) &&
			vector.DistanceXZ(road, goal) < 150)
			return road;
		return goal;
	}

	// Crew out of an intact vehicle (a gunner gone to look, a failed move): the group is ordered back in
	// (the game's Get In waypoint on this vehicle) - up to 3 times, 90 s each; then the orders go on.
	protected static bool Remounting(ZCR_ArmourUnit unit, int now)
	{
		if (!unit.m_Group)
			return false;
		int alive = AICF_GroupRuntime.CountAliveAgents(unit.m_Group);
		int aboard = Aboard(unit);
		int want = Math.Min(alive, unit.m_iCrew);
		if (unit.m_sPhase == "REMOUNT")
		{
			if (aboard < want && now - unit.m_iRemountAt <= 90)
				return true;
			// 90 s and still short (the Abrams' crew stayed at 1 of 3 through three tries): who is within 50 m
			// is seated the way the Game Master seats a crew, the driver's seat first - a tank with a gunner
			// and no driver stood at its HQ for 5 minutes.
			int seated;
			if (aboard < want)
				seated = Seat(unit);
			Log(unit, now, "REMOUNTED", string.Format("prefab=%1 aboard=%2/%3 took_s=%4 seated=%5", unit.m_sPrefab, Aboard(unit), want, now - unit.m_iRemountAt, seated));
			unit.m_sPhase = "";
			unit.m_vFront = vector.Zero;
			return false;
		}
		if (alive == 0 || aboard >= want || unit.m_iRemounts >= 3 || Health(unit) < 0.35)
			return false;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = unit.m_Vehicle.GetOrigin();
		// Get In on this very vehicle, registered with the group first (the game's own get-in command does it so):
		// "Get In Nearest" could pick another vehicle the group doesn't use - the 07:35 watched crash's assert
		// was "vehicle provided is not registered as used inside group".
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(unit.m_Vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (usage && unit.m_Group.GetGroupUtilityComponent())
			unit.m_Group.GetGroupUtilityComponent().AddUsableVehicle(usage);
		SCR_BoardingEntityWaypoint waypoint = SCR_BoardingEntityWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{8AD8C82346156494}Prefabs/AI/Waypoints/AIWaypoint_GetInSelected.et", false, params: params));
		if (!waypoint)
			return false;
		waypoint.SetEntity(unit.m_Vehicle);
		waypoint.SetCompletionRadius(25);
		ReplaceWaypoint(unit, waypoint);
		unit.m_Waypoint = waypoint;
		unit.m_sPhase = "REMOUNT";
		unit.m_iRemounts++;
		unit.m_iRemountAt = now;
		Log(unit, now, "REMOUNT", string.Format("prefab=%1 aboard=%2/%3 try=%4", unit.m_sPrefab, aboard, want, unit.m_iRemounts));
		return true;
	}

	// Crewmen killed in an intact vehicle: FPV drone hits killed two of three crewmen at once with the hull fine
	// (armour_hit=TANK, no killer), and the Abrams and T-72 then drove on with their driver alone - no gunner,
	// 0-1 armour kills a watched match (21 Oct, w22-w29). The unit drives back to its side's nearest base for a
	// new crew - the bodies out of their seats the way the game's "remove casualty" does it, a crewman a seat
	// for RECREW_COST supplies from that base - then goes on. At most twice a unit, 5 game minutes to get
	// there. -zcrNoRecrew: off. Logs RECREW / RECREWED / RECREW_FAILED.
	static const int RECREW_COST = 100;

	protected static bool Recrewing(ZCR_ArmourUnit unit, int now)
	{
		if (System.IsCLIParam("zcrNoRecrew") || !unit.m_Group || !unit.m_Vehicle)
			return false;
		if (unit.m_sPhase == "RECREW")
		{
			SCR_CampaignMilitaryBaseComponent base = unit.m_RecrewBase;
			bool ours = base && base.GetOwner() && base.GetFaction() && base.GetFaction().GetFactionKey() == unit.m_sSide;
			if (!ours || now - unit.m_iRecrewAt > 300)
			{
				Log(unit, now, "RECREW_FAILED", string.Format("prefab=%1 reason=%2 after_s=%3", unit.m_sPrefab, ours, now - unit.m_iRecrewAt));
				unit.m_sPhase = "";
				unit.m_vFront = vector.Zero;
				return false;
			}
			if (unit.m_bRecrewKicked || vector.DistanceXZ(unit.m_Vehicle.GetOrigin(), base.GetOwner().GetOrigin()) > 150)
				return true;
			unit.m_bRecrewKicked = true;
			KickDead(unit);
			// The seats free a moment later; Refill ends the phase.
			GetGame().GetCallqueue().CallLater(Refill, 2000, false, unit);
			return true;
		}
		int alive = AICF_GroupRuntime.CountAliveAgents(unit.m_Group);
		if (alive == 0 || alive >= unit.m_iCrew || unit.m_iRecrews >= 2 || unit.m_sPhase == "REMOUNT" || Health(unit) < 0.35 || Aboard(unit) == 0)
			return false;
		vector at = unit.m_Vehicle.GetOrigin();
		SCR_CampaignMilitaryBaseComponent best;
		float bestDist = 1e9;
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		array<SCR_MilitaryBaseComponent> bases = {};
		if (system)
			system.GetBases(bases);
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent cb = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!cb || !cb.GetOwner() || !cb.GetFaction() || cb.GetFaction().GetFactionKey() != unit.m_sSide || cb.GetType() == SCR_ECampaignBaseType.RELAY ||
				cb.GetSupplies() < RECREW_COST * (unit.m_iCrew - alive))
				continue;
			float d = vector.DistanceXZ(cb.GetOwner().GetOrigin(), at);
			if (d < bestDist)
			{
				bestDist = d;
				best = cb;
			}
		}
		if (!best)
			return false;
		vector goal = OnRoad(at, best.GetOwner().GetOrigin());
		goal[1] = GetGame().GetWorld().GetSurfaceY(goal[0], goal[2]);
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = goal;
		AIWaypoint waypoint = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx("{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", false, params: params));
		if (!waypoint)
			return false;
		waypoint.SetCompletionRadius(60);
		ReplaceWaypoint(unit, waypoint);
		unit.m_Waypoint = waypoint;
		unit.m_vOrder = goal;
		unit.m_sPhase = "RECREW";
		unit.m_iRecrewAt = now;
		unit.m_bRecrewKicked = false;
		unit.m_RecrewBase = best;
		unit.m_iRecrews++;
		Log(unit, now, "RECREW", string.Format("prefab=%1 crew=%2/%3 base=%4 dist=%5 try=%6", unit.m_sPrefab, alive, unit.m_iCrew,
			ZCR_Strategist.BaseName(best), Math.Round(bestDist), unit.m_iRecrews));
		return true;
	}

	protected static void KickDead(ZCR_ArmourUnit unit)
	{
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(unit.m_Vehicle, seats);
		foreach (BaseCompartmentSlot seat : seats)
		{
			ChimeraCharacter body = ChimeraCharacter.Cast(seat.GetOccupant());
			if (!body || AICF_GroupRuntime.IsAliveCharacter(body))
				continue;
			CompartmentAccessComponent access = body.GetCompartmentAccessComponent();
			if (access)
			{
				ZCR_Trace.Ent("kick", body, "recrew_dead");
				access.KickFromVehicle(0);
			}
		}
	}

	protected static void Refill(ZCR_ArmourUnit unit)
	{
		if (!unit || !unit.m_Vehicle || unit.m_sPhase != "RECREW")
			return;
		int now = ZCR_LossLog.Seconds();
		string character = "{E1CB513B8B9B08F4}Prefabs/Characters/Factions/BLUFOR/US_Army/Character_US_Crew.et";
		if (unit.m_sSide != "US")
			character = "{9FFEF10757E742EB}Prefabs/Characters/Factions/OPFOR/USSR_Army/Character_USSR_Crew.et";
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(unit.m_Vehicle, seats);
		bool driver;
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (seat && seat.GetType() == ECompartmentType.PILOT && seat.GetOccupant())
				driver = true;
		}
		AIGroup group = unit.m_Group;
		int added;
		SCR_CampaignMilitaryBaseComponent base = unit.m_RecrewBase;
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (!seat || !seat.IsCompartmentAccessible() || seat.GetOccupant() || !base || base.GetSupplies() < RECREW_COST)
				continue;
			if (seat.GetType() == ECompartmentType.PILOT && driver)
				continue;
			if (seat.GetType() != ECompartmentType.PILOT && seat.GetType() != ECompartmentType.TURRET)
				continue;
			ZCR_Trace.Ent("crew", unit.m_Vehicle, "recrew");
			if (!seat.SpawnCharacterInCompartment(character, group))
				continue;
			if (seat.GetType() == ECompartmentType.PILOT)
				driver = true;
			base.AddSupplies(-RECREW_COST);
			added++;
		}
		int aboard = Aboard(unit);
		if (aboard > unit.m_iCrew)
			unit.m_iCrew = aboard;
		Log(unit, now, "RECREWED", string.Format("prefab=%1 added=%2 aboard=%3/%4 base=%5 stock_after=%6 took_s=%7", unit.m_sPrefab, added, aboard, unit.m_iCrew,
			ZCR_Strategist.BaseName(base), Math.Round(base.GetSupplies()), now - unit.m_iRecrewAt));
		unit.m_sPhase = "";
		unit.m_vFront = vector.Zero;
	}

	protected static int Seat(ZCR_ArmourUnit unit)
	{
		array<AIAgent> agents = {};
		unit.m_Group.GetAgents(agents);
		int seated;
		foreach (AIAgent agent : agents)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (!c || !AICF_GroupRuntime.IsAliveCharacter(c) || c.IsInVehicle() || vector.DistanceXZ(c.GetOrigin(), unit.m_Vehicle.GetOrigin()) > 50)
				continue;
			SCR_CompartmentAccessComponent access = SCR_CompartmentAccessComponent.Cast(c.GetCompartmentAccessComponent());
			if (!access)
				continue;
			ZCR_Trace.Ent("board", c, "remount");
			if (access.MoveInVehicle(unit.m_Vehicle, ECompartmentType.PILOT) || access.MoveInVehicle(unit.m_Vehicle, ECompartmentType.TURRET))
				seated++;
		}
		return seated;
	}

	// Approach: a support position SHORT_M short of the front on the vehicle's way in; there (or within
	// SHORT_M + 100 of the front), Search and Destroy at the front itself.
	protected static void Order(ZCR_ArmourUnit unit, vector front, int now)
	{
		if (!unit.m_Group || front == vector.Zero)
			return;
		vector at = unit.m_Vehicle.GetOrigin();
		float dist = vector.DistanceXZ(at, front);
		// One order per front: the support point is fixed when the front is set (recomputing it as the
		// vehicle moved re-ordered the Bradley every tick in the first test). The assault follows once the
		// vehicle is within SHORT_M + 100 of the front.
		bool sameFront = unit.m_vFront != vector.Zero && vector.DistanceXZ(unit.m_vFront, front) < 100;
		// At its support point (within 80 m of it): on into the base, however far that is.
		bool arrived = sameFront && unit.m_sPhase == "APPROACH" && vector.DistanceXZ(at, unit.m_vOrder) < 80;
		// In the assault the goal follows the fight (re-aimed when it moved 200 m+, at most once a minute).
		bool reaim = sameFront && unit.m_sPhase == "ASSAULT" && now - unit.m_iOrderedAt >= 60 &&
			vector.DistanceXZ(FightNear(front, now), unit.m_vOrder) > 200;
		if (sameFront && unit.m_Waypoint && !arrived && !reaim && (unit.m_sPhase == "ASSAULT" || dist > SHORT_M + 100))
			return;
		string phase = "APPROACH";
		vector goal;
		if (dist <= SHORT_M + 100 || arrived || (unit.m_sPhase == "ASSAULT" && sameFront))
		{
			phase = "ASSAULT";
			goal = FightNear(front, now);
		}
		else
		{
			vector way = at - front;
			way[1] = 0;
			way.Normalize();
			// A unit stuck on its way (STILL) tries another way in: the support point turned 70 degrees a try.
			if (unit.m_iDetour > 0)
			{
				float turn = unit.m_iDetour * 70 * Math.DEG2RAD;
				if (unit.m_iDetour % 2 == 0)
					turn = -turn;
				way = Vector(way[0] * Math.Cos(turn) - way[2] * Math.Sin(turn), 0, way[0] * Math.Sin(turn) + way[2] * Math.Cos(turn));
			}
			goal = front + way * SHORT_M;
		}
		goal = OnRoad(at, goal);
		goal[1] = GetGame().GetWorld().GetSurfaceY(goal[0], goal[2]);
		// Move waypoints only: the game's Search and Destroy searches on foot (no vehicles) - in the first test
		// the Abrams crew got out a minute after it. A group on a Move stays in its vehicles and fights from
		// them (the game's vehicle combat activity takes over when it meets a threat).
		ResourceName prefab = "{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et";
		float radius = 40;
		if (phase == "ASSAULT")
			radius = 60;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = goal;
		AIWaypoint waypoint = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx(prefab, false, params: params));
		if (!waypoint)
			return;
		waypoint.SetCompletionRadius(radius);
		ReplaceWaypoint(unit, waypoint);
		unit.m_Waypoint = waypoint;
		unit.m_vOrder = goal;
		unit.m_sPhase = phase;
		unit.m_vFront = front;
		unit.m_iOrderedAt = now;
		Log(unit, now, "ORDER", string.Format("prefab=%1 phase=%2 front=%3 dist=%4 goal_x=%5 goal_z=%6", unit.m_sPrefab, phase, FrontName(front),
			Math.Round(dist), Math.Round(goal[0]), Math.Round(goal[2])));
	}

	protected static void Status(ZCR_ArmourUnit unit, vector front, int now)
	{
		if (now < unit.m_iNextStatus)
			return;
		unit.m_iNextStatus = now + 60;
		vector at = unit.m_Vehicle.GetOrigin();
		float health = 1;
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(unit.m_Vehicle.FindComponent(SCR_DamageManagerComponent));
		if (damage)
			health = damage.GetHealthScaled();
		float dist = -1;
		if (front != vector.Zero)
			dist = vector.DistanceXZ(at, front);
		int slowedN = unit.m_iSlowed;
		if (slowedN < 0)
			slowedN = 0;
		string slowedText = string.Format(" slowed=%1 held_total=%2", slowedN, s_iHeld);
		Log(unit, now, "STATUS", string.Format("prefab=%1 phase=%2 front=%3 dist=%4 moved_m=%5 aboard=%6/%7 health=%8" + slowedText + " x=%9", unit.m_sPrefab, unit.m_sPhase,
			FrontName(front), Math.Round(dist), Math.Round(vector.DistanceXZ(at, unit.m_vWas)), Aboard(unit), unit.m_iCrew, Math.Round(100 * health),
			string.Format("%1 z=%2", Math.Round(at[0]), Math.Round(at[2]))));
		if (now - unit.m_iBoughtAt >= 180 && vector.DistanceXZ(at, unit.m_vBoughtAt) < 40 && !BadSpot(unit.m_vBoughtAt))
		{
			s_aBadSpots.Insert(unit.m_vBoughtAt);
			Log(unit, now, "BAD_SPOT", string.Format("x=%1 z=%2 (not bought there again)", Math.Round(unit.m_vBoughtAt[0]), Math.Round(unit.m_vBoughtAt[2])));
		}
		// Still (under 25 m a minute) for two minutes short of its order: re-ordered with another way in.
		float holdM = 80;
		if (unit.m_sPhase == "ASSAULT")
			holdM = 200;     // in the fight at the base: holding a firing spot is not stuck
		if (unit.m_sPhase != "REMOUNT" && unit.m_sPhase != "RECREW" && vector.DistanceXZ(at, unit.m_vWas) < 25 && unit.m_Waypoint && vector.DistanceXZ(at, unit.m_vOrder) > holdM)
			unit.m_iStill++;
		else
			unit.m_iStill = 0;
		unit.m_vWas = at;
		// Never moved off since bought (a first order it can't drive to): another way after one still minute.
		if (unit.m_iStill >= 2 || (unit.m_iStill >= 1 && vector.DistanceXZ(at, unit.m_vBoughtAt) < 40))
		{
			unit.m_iStill = 0;
			unit.m_iDetour++;
			Log(unit, now, "STILL", string.Format("prefab=%1 phase=%2 order_m=%3 detour=%4 x=%5 z=%6", unit.m_sPrefab, unit.m_sPhase,
				Math.Round(vector.DistanceXZ(at, unit.m_vOrder)), unit.m_iDetour, Math.Round(at[0]), Math.Round(at[2])));
			unit.m_vFront = vector.Zero;
			if (unit.m_iDetour >= 3)
				Relocate(unit, front, now);
			Order(unit, front, now);
		}
	}

	protected static string FrontName(vector front)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system || front == vector.Zero)
			return "-";
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		SCR_CampaignMilitaryBaseComponent best;
		float bestDist = 300;
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || !base.GetOwner())
				continue;
			float d = vector.DistanceXZ(base.GetOwner().GetOrigin(), front);
			if (d < bestDist)
			{
				bestDist = d;
				best = base;
			}
		}
		if (!best)
			return "-";
		return ZCR_Strategist.BaseName(best);
	}

	// A road spot 25-250 m from the HQ, facing away from it, where a tank's box (4.6 x 11 m, 0.6-3.6 m up)
	// hits nothing on the vehicle layer (the test AI Conflict uses for its own vehicles) and clear of
	// building sites. s_sSpotWhy: how many spots failed and why.
	protected static string s_sSpotWhy;
	protected static float s_fSpotWidth;
	protected static int s_iSpotTrees;

	protected static bool FindSpot(vector center, vector toward, out vector pose[4])
	{
		SCR_AIWorld ai = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (!ai || !ai.GetRoadNetworkManager())
			return false;
		BaseWorld world = GetGame().GetWorld();
		int noRoad, far, wet, site, blocked, checkpoint, spawnPoint, bad;
		float bestScore = -1;
		vector best[4];
		for (int candidate; candidate < 40; candidate++)
		{
			int bearing = candidate % 8;
			int ring = candidate / 8;
			float angle = bearing * 45 * Math.DEG2RAD;
			float radius = 40 + ring * 45;
			vector requested = center + Vector(Math.Cos(angle) * radius, 0, Math.Sin(angle) * radius);
			vector road;
			if (!ai.GetRoadNetworkManager().GetReachableWaypointInRoad(center, requested, 60, road))
			{
				noRoad++;
				continue;
			}
			float fromCenter = vector.DistanceXZ(center, road);
			if (fromCenter < 25 || fromCenter > 250)
			{
				far++;
				continue;
			}
			road[1] = world.GetSurfaceY(road[0], road[2]);
			if (world.IsOcean() && road[1] < world.GetOceanBaseHeight() + 1)
			{
				wet++;
				continue;
			}
			if (!AICF_ConstructionPlanner.VehicleAreaClear(road, 12))
			{
				site++;
				continue;
			}
			// Along the road: the direction to the next road point a little further from the HQ.
			vector direction = road - center;
			direction[1] = 0;
			direction.Normalize();
			vector next;
			if (ai.GetRoadNetworkManager().GetReachableWaypointInRoad(road, road + direction * 15, 20, next) && vector.DistanceXZ(next, road) > 3)
			{
				direction = next - road;
				direction[1] = 0;
				direction.Normalize();
			}
			// Laid on the ground under the hull (the slope 5 m ahead/behind and to the sides), 0.5 m up: a 10 m
			// hull set level on a slope starts inside the ground (the way AI Conflict fits its own vehicles).
			vector side = Vector(direction[2], 0, -direction[0]);
			vector front = road + direction * 5;
			vector back = road - direction * 5;
			vector left = road + side * 2;
			vector right = road - side * 2;
			front[1] = world.GetSurfaceY(front[0], front[2]);
			back[1] = world.GetSurfaceY(back[0], back[2]);
			left[1] = world.GetSurfaceY(left[0], left[2]);
			right[1] = world.GetSurfaceY(right[0], right[2]);
			vector along = front - back;
			vector across = left - right;
			vector up = Vector(across[1] * along[2] - across[2] * along[1], across[2] * along[0] - across[0] * along[2], across[0] * along[1] - across[1] * along[0]);
			if (up[1] < 0)
				up = -up;
			up.Normalize();
			if (up[1] < 0.85)
			{
				blocked++;
				continue;
			}
			along.Normalize();
			Math3D.DirectionAndUpMatrix(along, up, pose);
			vector place = road;
			place[1] = Math.Max(Math.Max(front[1], back[1]), road[1]) + 0.5;
			pose[3] = place;
			TraceOBB body = new TraceOBB();
			for (int axis; axis < 3; axis++)
				body.Mat[axis] = pose[axis];
			body.Start = pose[3];
			body.Mins = Vector(-2.3, 0.6, -5.5);
			body.Maxs = Vector(2.3, 3.6, 5.5);
			body.Flags = TraceFlags.ENTS;
			body.LayerMask = EPhysicsLayerPresets.Vehicle;
			if (world.TracePosition(body, null) < 0)
			{
				blocked++;
				continue;
			}
			// Not a spot a unit got stuck at before, and one with a road on towards the front: units bought by
			// the south HQ (1619 1122, 1638 1108) sat there for up to 15 minutes in the watched matches.
			// (Ranked last rather than refused, so a side always gets a spot.)
			float penalty = 0;
			if (BadSpot(road))
				penalty += 50000;
			vector onward;
			if (toward != vector.Zero && !ai.GetRoadNetworkManager().GetReachableWaypointInRoad(road, toward, 400, onward))
				penalty += 100000;
			// A narrow road (a forest track) last too: the units bought on the south HQ's tracks (1619 1122,
			// 1638 1108) sat there in most watched matches.
			BaseRoad nearRoad;
			float roadDist;
			float width = -1;
			ai.GetRoadNetworkManager().GetClosestRoad(road, nearRoad, roadDist);
			if (nearRoad)
				width = nearRoad.GetWidth();
			if (width >= 0 && width < 5)
				penalty += 30000;
			// In a wood (4+ trees within 12 m) last too: watched matches crashed in 6 of 12 when the US armour was
			// bought at the south HQ's wooded track (1619 1122) - it got stuck among the pines - and in 1 of 13
			// elsewhere.
			s_iTrees = 0;
			world.QueryEntitiesBySphere(road, 12, CountTree, null, EQueryEntitiesFlags.STATIC);
			if (s_iTrees >= 4)
				penalty += 40000;
			if (penalty > 0)
				bad++;
			// Not on a spawn point: soldiers can't appear where a tank stands - recruits for the north HQ
			// timed out (GROUP_SPAWN_TIMEOUT) only in the armour tests, with its armour parked there.
			if (NearSpawnPoint(road, 40))
			{
				spawnPoint++;
				continue;
			}
			// Not by a road block (hedgehogs, dragon's teeth, gates, barriers - kept on the map, Martin): the
			// 21 Oct probe found the Bradley spawned inside the north HQ's checkpoint (5 hedgehogs, two gates)
			// and stuck there 10 minutes.
			s_iBlocks = 0;
			world.QueryEntitiesBySphere(road, 40, CountBlock, null, EQueryEntitiesFlags.STATIC);
			if (s_iBlocks > 0)
			{
				checkpoint++;
				continue;
			}
			// Of the clear spots, the one nearest the front (the way out it needn't turn back through).
			float score = penalty;
			if (toward != vector.Zero)
				score += vector.DistanceXZ(road, toward);
			if (bestScore < 0 || score < bestScore)
			{
				bestScore = score;
				s_fSpotWidth = width;
				s_iSpotTrees = s_iTrees;
				for (int k; k < 4; k++)
					best[k] = pose[k];
			}
		}
		if (bestScore >= 0)
		{
			for (int m; m < 4; m++)
				pose[m] = best[m];
			return true;
		}
		s_sSpotWhy = string.Format("no_road=%1 far=%2 wet=%3 site=%4 blocked=%5 checkpoint=%6 spawn_point=%7 bad=%8", noRoad, far, wet, site, blocked, checkpoint, spawnPoint, bad);
		return false;
	}

	// Known from the watched matches (the list starts each match with them; units stuck there are added):
	// Arland's south HQ track - units bought there sat stuck all match, and the game crashed in 6 of 12 such
	// matches (1 of 13 elsewhere). Only 1 tree near, so not the wood check.
	protected static ref array<vector> s_aBadSpots = {"1619 0 1122", "1638 0 1108"};

	protected static bool BadSpot(vector at)
	{
		foreach (vector b : s_aBadSpots)
		{
			if (vector.DistanceXZ(b, at) < 40)
				return true;
		}
		return false;
	}

	protected static bool NearSpawnPoint(vector at, float radius)
	{
		array<SCR_SpawnPoint> points = SCR_SpawnPoint.GetSpawnPoints();
		if (!points)
			return false;
		foreach (SCR_SpawnPoint point : points)
		{
			if (point && vector.DistanceXZ(point.GetOrigin(), at) < radius)
				return true;
		}
		return false;
	}

	protected static int s_iBlocks;
	protected static int s_iTrees;

	protected static bool CountTree(IEntity e)
	{
		if (e && e.GetPrefabData() && e.GetPrefabData().GetPrefabName().Contains("Vegetation/Tree/"))
			s_iTrees++;
		return true;
	}

	protected static bool CountBlock(IEntity e)
	{
		if (!e || !e.GetPrefabData())
			return true;
		string name = e.GetPrefabData().GetPrefabName();
		if (name.Contains("Hedgehog") || name.Contains("Dragontooth") || name.Contains("BarGate") || name.Contains("MetalGate") ||
			name.Contains("RoadBarrier") || name.Contains("Roadblock") || name.Contains("RoadBlock"))
			s_iBlocks++;
		return true;
	}

	protected static void Log(ZCR_ArmourUnit unit, int now, string what, string details)
	{
		Print(string.Format("[ZCR][ARMOUR] t=%1 side=%2 unit=%3 event=%4 %5", now, unit.m_sSide, unit.m_iNo, what, details), LogLevel.NORMAL);
	}
}

// Armour crews stay aboard (watched match 21 Oct 05:17: the BMP-1's crew got out three times, the
// Bradley's and T-72's crews were lost out of intact vehicles - no armour kill in the match). The game
// takes a crew out through this behaviour for every reason - a group move that failed releases the
// vehicle, gunners leave the turret to look round, danger and fire reactions. For the crew of one of
// our armour units it waits while the vehicle is intact (35%+ health); damaged below that, they get
// out as before. -zcrArmourLetOut turns it off.
modded class SCR_AIGetOutVehicle
{
	override float CustomEvaluate()
	{
		if (m_Vehicle && ZCR_Armour.KeepAboard(m_Vehicle.m_Value))
			return 0;
		return super.CustomEvaluate();
	}
}

// Armour gunners hold fire at a target with their own soldiers within 20 m of it (see FriendsNearTarget).
// -zcrArmourFreeFire turns it off.
modded class SCR_AIAttackBehavior
{
	override float CustomEvaluate()
	{
		float value = super.CustomEvaluate();
		if (value <= 0 || !m_Utility || !m_Utility.m_AIInfo || !m_Utility.m_AIInfo.HasUnitState(EUnitState.IN_TURRET))
			return value;
		BaseTarget target = m_Target.m_Value;
		if (target && ZCR_Armour.FriendsNearTarget(m_Utility.m_OwnerEntity, target.GetLastSeenPosition()))
			return 0;
		return value;
	}
}
