// Drone operators (Martin, 24 Oct 15:32: "the drone operator should be seen in the GUI with some tag that this is a drone
// operator, so I know how it works; he should maybe seek cover, and when he is controlling a drone he should have the drone
// controller in hands and goggles, and be stationary like in real life"). A 2-man team that launches drones (the infantry
// test's operators, the commander's drone sites) registers here:
//   - its first soldier is the pilot: a big bag on his back; Realistic Combat Drones' FPV goggles on his head only while a
//     drone of his side is in the air (his helmet otherwise), and its drone controller in his hands then (his rifle otherwise);
//   - the team's post is in cover: inside a building, else under a roof or tree crowns, within 25 m of where it was put,
//     on the side away from the enemy;
//   - while a drone flies the pilot holds still where he is, crouched with the controller: his AI is off for the flight
//     (blind behind his goggles - the guard watches), on again when the drone is down (or after 2 minutes); between
//     flights both are sent back to the post when more than 8 m off it (below a run
//     into a building from an enemy drone - that still comes first);
//   - the other one guards him with his rifle;
//   - the watch screen tags them (ZCR_Watch): "DRONE OPERATOR" over the pilot ("flying FPV" while a drone is up), "drone
//     operator's guard" over the other.
//   [ZCR][OPERATOR] t= side= event=post|kit|flying|landed man= x= z= ...   and every 60 s: t= side= pilots= flying= holds=
class ZCR_OperatorMan
{
	IEntity m_Man;
	string m_sSide;
	bool m_bPilot;
	vector m_vPost;
	IEntity m_Controller;
	bool m_bFlying;
	int m_iAgainAt;
	int m_iFrozenAt;
	int m_iThawUntil;
	int m_iLandedAt;
	SCR_AIGroup m_Group;
	SCR_AIMoveIndividuallyBehavior m_Move;   // his last move to the post
	ResourceName m_sHelmet;                  // what he wears when not flying
	bool m_bMoving;         // the drone site is moving (ZCR_DroneSites): no holding at the post, no flying
}

// A team out on sorties (Martin, 24 Oct 17:58: "operators should have larger bags with some amount of drones, then there
// would be the drone truck or a static drone arsenal and they would resupply there when they are out of them"; "Zeus
// Commander should actually plan where to move the drone truck, the drone operator just knows if he has somewhere close to
// resupply"): the pilot carries CARRY drones; the team walks to a launch position in cover between its resupply point and
// the target, launches them one at a time, walks back to the resupply point (the drone truck or the static arsenal), loads
// for LOAD_S and goes out to a new position.
//   [ZCR][SORTIE] t= side= event=out|launch|empty|resupply|loaded drones= x= z= ...
class ZCR_OperatorTeam
{
	SCR_AIGroup m_Group;
	string m_sSide;
	vector m_vSupply;        // where it resupplies
	vector m_vGoal;          // what its drones go for
	int m_iCarried;
	int m_iState;            // 0 to a launch position, 1 at it (launching), 2 to resupply, 3 loading
	int m_iStateAt;
	int m_iLastLaunchAt;
	int m_iSorties;
	vector m_vPos;           // the launch position
}

class ZCR_DroneOperator
{
	static const ResourceName GOGGLES = "{8951045BFE8BC8E4}Prefabs/Characters/HeadGear/FPV_Goggles.et";
	static const ResourceName CONTROLLER = "{E2434ED1318D8476}Prefabs/Characters/Items/DroneController.et";
	// The pilot's big bag (Martin, 18:20: "let's give the drone operator a big backpack, and he only uses the goggles when he
	// is driving drones"): the game's ALICE, assembled (US - the "frame" prefab is the bare pack frame: 18:33, "one last missing
	// thing is giving him a backpack"), Kolobok (Soviet).
	static const ResourceName BAG_US = "{5C5C6EE05EE2FF1A}Prefabs/Items/Equipment/Backpacks/Backpack_ALICE_Medium_assembled.et";
	static const ResourceName BAG_USSR = "{41A9C55B61F375F0}Prefabs/Items/Equipment/Backpacks/Backpack_Kolobok.et";
	static const float POST_COVER_M = 25;
	static const float POST_COVER_FAR_M = 60;    // none within 25 m (17:40: the farm-site operators stood in the open)
	static const float HOLD_M = 6;          // the pilot while he flies (3 m: he settled 5 m off his post and was sent back every 3 s)
	static const float STAY_M = 8;          // the pilot between flights, the guard always
	static const int MAX_FROZEN_S = 120;    // the pilot's AI back on after this long in one flight
	static const float RANGE_M = 2500;     // a pilot flies his side's drones within this of him
	static const int CARRY = 4;             // drones in the pilot's bag
	static const int LOAD_S = 45;
	static const float SUPPLY_NEAR_M = 15;
	static ref array<ref ZCR_OperatorTeam> s_aTeams = {};
	static ref array<ref ZCR_OperatorMan> s_aMen = {};
	protected static bool s_bStarted;
	protected static int s_iNextLog;
	protected static ref map<string, int> s_mHolds = new map<string, int>();
	protected static ref map<SCR_AIGroup, bool> s_mCovered = new map<SCR_AIGroup, bool>();   // the team's post has cover

	// The team's soldiers spawn over a few frames: tried again for 10 s until they are there.
	static void Register(SCR_AIGroup group, string side, vector post, vector threat, int tries = 0)
	{
		if (!group || !Replication.IsServer())
			return;
		array<AIAgent> agents = {};
		group.GetAgents(agents);
		// Both of the team (15:38: registered with the first one only, the guard came a moment later).
		bool all = agents.Count() >= 2;
		foreach (AIAgent ag : agents)
		{
			if (!ag || !ChimeraCharacter.Cast(ag.GetControlledEntity()))
				all = false;
		}
		if (agents.IsEmpty() || (!all && tries < 5))
		{
			if (tries < 10)
				GetGame().GetCallqueue().CallLater(Register, 1000, false, group, side, post, threat, tries + 1);
			return;
		}
		ChimeraCharacter pilot = ChimeraCharacter.Cast(agents[0].GetControlledEntity());
		vector spot;
		if (ZCR_DroneThreat.CoverSpot(pilot, threat, POST_COVER_M, post, spot) || ZCR_DroneThreat.CoverSpot(pilot, threat, POST_COVER_FAR_M, post, spot))
			post = spot;
		int now = ZCR_LossLog.Seconds();
		foreach (int i, AIAgent a : agents)
		{
			ChimeraCharacter c;
			if (a)
				c = ChimeraCharacter.Cast(a.GetControlledEntity());
			if (!c)
				continue;
			ZCR_OperatorMan m = new ZCR_OperatorMan();
			m.m_Man = c;
			m.m_Group = group;
			m.m_sSide = side;
			m.m_bPilot = i == 0;
			// The guard a few metres off, not on top of the pilot.
			m.m_vPost = post;
			if (!m.m_bPilot)
				m.m_vPost = post + Vector(3, 0, -3);
			s_aMen.Insert(m);
			ToPost(m, now);
			if (m.m_bPilot)
				Kit(m);
		}
		s_mCovered.Set(group, spot != vector.Zero);
		ZCR_Tactical.Get().HoldStill(group);   // DCO: its squad moves off for the team
		Print(string.Format("[ZCR][OPERATOR] t=%1 side=%2 event=post men=%3 cover=%4 x=%5 z=%6 layer=%7", now, side, agents.Count(), spot != vector.Zero,
			Math.Round(post[0]), Math.Round(post[2]), ZCR_Tactical.Get().Layer()), LogLevel.NORMAL);
		if (!s_bStarted)
		{
			s_bStarted = true;
			GetGame().GetCallqueue().CallLater(Tick, 1000, true);
		}
	}

	// The team goes out on sorties from 'supply' against 'goal' (the infantry test's drone site; later the commander's).
	static void Sortie(SCR_AIGroup group, string side, vector supply, vector goal)
	{
		if (!group || Team(group))
			return;
		ZCR_OperatorTeam team = new ZCR_OperatorTeam();
		team.m_Group = group;
		team.m_sSide = side;
		team.m_vSupply = supply;
		team.m_vGoal = goal;
		team.m_iCarried = CARRY;
		team.m_iState = -1;               // out to the first position once the men are registered
		s_aTeams.Insert(team);
	}

	// Where the team's drones go now (the commander's drone target changes with its plan).
	static void SetGoal(SCR_AIGroup group, vector goal)
	{
		ZCR_OperatorTeam team = Team(group);
		if (team && goal != vector.Zero)
			team.m_vGoal = goal;
	}

	static ZCR_OperatorTeam Team(SCR_AIGroup group)
	{
		foreach (ZCR_OperatorTeam team : s_aTeams)
		{
			if (team.m_Group == group)
				return team;
		}
		return null;
	}

	// May the team launch now, and from where: at its launch position with drones in the bag.
	static bool CanLaunch(SCR_AIGroup group, out vector from)
	{
		ZCR_OperatorTeam team = Team(group);
		if (!team || team.m_iState != 1 || team.m_iCarried <= 0)
			return false;
		ChimeraCharacter pilot = Pilot(group);
		if (!pilot || vector.DistanceXZ(pilot.GetOrigin(), team.m_vPos) > STAY_M)
			return false;
		from = LaunchSpot(pilot);
		return true;
	}

	// The take-off spot: the nearest point within 30 m with nothing overhead - the team sits in cover, the drone goes up from
	// the open beside it (18:26: launched 12 m off under the trees, flights ended after 1-14 s).
	protected static vector LaunchSpot(ChimeraCharacter pilot)
	{
		vector at = pilot.GetOrigin();
		BaseWorld world = GetGame().GetWorld();
		array<float> rings = {8, 14, 20, 26, 32};
		foreach (float r : rings)
		{
			for (int k; k < 8; k++)
			{
				float a = k * 45 * Math.DEG2RAD;
				vector p = at + Vector(Math.Cos(a), 0, Math.Sin(a)) * r;
				p[1] = world.GetSurfaceY(p[0], p[2]);
				if (ZCR_DroneThreat.OpenSky(p, pilot))
					return p;
			}
		}
		return at + Vector(12, 0, 0);
	}

	static void Launched(SCR_AIGroup group)
	{
		ZCR_OperatorTeam team = Team(group);
		if (!team)
			return;
		team.m_iCarried--;
		team.m_iLastLaunchAt = ZCR_LossLog.Seconds();
		Print(string.Format("[ZCR][SORTIE] t=%1 side=%2 event=launch drones=%3", team.m_iLastLaunchAt, team.m_sSide, team.m_iCarried), LogLevel.NORMAL);
	}

	// "3 FPVs in the bag", "walking to resupply", "loading at the drone truck", "out to a new position".
	static string TeamText(SCR_AIGroup group)
	{
		ZCR_OperatorTeam team = Team(group);
		if (!team)
			return "";
		if (team.m_iState == 1)
			return string.Format("%1 FPVs in the bag", team.m_iCarried);
		if (team.m_iState == 2)
			return "out of drones - walking back to resupply";
		if (team.m_iState == 3)
			return "loading drones at the resupply point";
		return string.Format("out to a launch position with %1 FPVs", team.m_iCarried);
	}

	static ChimeraCharacter Pilot(SCR_AIGroup group)
	{
		foreach (ZCR_OperatorMan m : s_aMen)
		{
			if (m.m_Group == group && m.m_bPilot)
				return ChimeraCharacter.Cast(m.m_Man);
		}
		return null;
	}

	// The cycle, every second.
	protected static void Sorties(int now)
	{
		foreach (ZCR_OperatorTeam team : s_aTeams)
		{
			ChimeraCharacter pilot = Pilot(team.m_Group);
			if (!pilot || !pilot.GetCharacterController() || pilot.GetCharacterController().GetLifeState() != ECharacterLifeState.ALIVE)
				continue;
			vector at = pilot.GetOrigin();
			if (team.m_iState == -1 || (team.m_iState == 3 && now - team.m_iStateAt >= LOAD_S))
			{
				vector truckNow = ZCR_DroneSites.SupplyOf(team.m_Group);
				if (truckNow != vector.Zero)
					team.m_vSupply = truckNow;
				if (team.m_iState == 3)
				{
					team.m_iCarried = CARRY;
					Print(string.Format("[ZCR][SORTIE] t=%1 side=%2 event=loaded drones=%3", now, team.m_sSide, team.m_iCarried), LogLevel.NORMAL);
				}
				team.m_vPos = LaunchPosition(pilot, team);
				team.m_iState = 0;
				team.m_iStateAt = now;
				team.m_iSorties++;
				SetPost(team.m_Group, team.m_vPos);   // the spot the search found is already in cover (NewPost would look round the pilot, at the truck)
				Print(string.Format("[ZCR][SORTIE] t=%1 side=%2 event=out sortie=%3 drones=%4 from_supply=%5 to_goal=%6 x=%7 z=%8", now, team.m_sSide, team.m_iSorties,
					team.m_iCarried, Math.Round(vector.DistanceXZ(team.m_vPos, team.m_vSupply)), Math.Round(vector.DistanceXZ(team.m_vPos, team.m_vGoal)),
					Math.Round(team.m_vPos[0]), Math.Round(team.m_vPos[2])), LogLevel.NORMAL);
				continue;
			}
			if (team.m_iState == 0 && vector.DistanceXZ(at, team.m_vPos) <= STAY_M)
			{
				team.m_iState = 1;
				team.m_iStateAt = now;
				continue;
			}
			// Out of drones and the last one down (a flight takes ~20-30 s): back to resupply.
			if (team.m_iState == 1 && team.m_iCarried <= 0 && now - team.m_iLastLaunchAt >= 40 && !IsFlying(pilot))
			{
				vector supply = ZCR_DroneSites.SupplyOf(team.m_Group);   // where the truck is now - the commander moves it
				if (supply != vector.Zero)
					team.m_vSupply = supply;
				team.m_iState = 2;
				team.m_iStateAt = now;
				SetPost(team.m_Group, team.m_vSupply);
				Print(string.Format("[ZCR][SORTIE] t=%1 side=%2 event=empty to_supply=%3", now, team.m_sSide, Math.Round(vector.DistanceXZ(at, team.m_vSupply))), LogLevel.NORMAL);
				continue;
			}
			if (team.m_iState == 2)
			{
				vector truck = ZCR_DroneSites.SupplyOf(team.m_Group);
				if (truck != vector.Zero && vector.DistanceXZ(truck, team.m_vSupply) > 30)
				{
					team.m_vSupply = truck;
					SetPost(team.m_Group, truck);
				}
			}
			if (team.m_iState == 2 && vector.DistanceXZ(at, team.m_vSupply) <= SUPPLY_NEAR_M)
			{
				Print(string.Format("[ZCR][SORTIE] t=%1 side=%2 event=resupply walk_s=%3", now, team.m_sSide, now - team.m_iStateAt), LogLevel.NORMAL);
				team.m_iState = 3;
				team.m_iStateAt = now;
			}
		}
	}

	// A launch position near the resupply point (Martin, 18:03: "maybe they should stay close to the truck"; the walks of 330 m
	// took 240 s out and 137 s back): 100-250 m from it, toward the goal or to a side, the one with a roof or tree crowns
	// within 30 m (the team takes its post there); none of 16 with cover - the first tried.
	protected static vector LaunchPosition(ChimeraCharacter pilot, ZCR_OperatorTeam team)
	{
		vector dir = team.m_vGoal - team.m_vSupply;
		dir[1] = 0;
		float span = dir.Length();
		if (span < 1)
			dir = Vector(0, 0, 1);
		dir.Normalize();
		vector side = Vector(dir[2], 0, -dir[0]);
		vector first;
		for (int tries; tries < 16; tries++)
		{
			float reach = Math.RandomFloat(60, 200);
			if (span > 1)
				reach = Math.Min(reach, span - 250);     // not closer than 250 m to the goal
			vector cand = team.m_vSupply + dir * Math.Max(reach, 0) + side * Math.RandomFloat(-120, 120);
			cand[1] = GetGame().GetWorld().GetSurfaceY(cand[0], cand[2]);
			if (tries == 0)
				first = cand;
			vector hide;
			if (ZCR_DroneThreat.CoverNear(pilot, cand, 30, hide))
				return hide;
		}
		return first;
	}

	// The team's post without a search for cover (the resupply point).
	static void SetPost(SCR_AIGroup group, vector post)
	{
		int now = ZCR_LossLog.Seconds();
		foreach (ZCR_OperatorMan m : s_aMen)
		{
			if (m.m_Group != group)
				continue;
			EndMove(m);
			m.m_vPost = post;
			if (!m.m_bPilot)
				m.m_vPost = post + Vector(3, 0, -3);
			if (m.m_Man)
				ToPost(m, now);
		}
	}

	// The team's post in the open (no roof or tree crowns found near it) - false until the team is registered.
	static bool Exposed(SCR_AIGroup group)
	{
		return group && s_mCovered.Contains(group) && !s_mCovered.Get(group);
	}

	static bool IsOperator(IEntity e)
	{
		return Find(e) != null;
	}

	// The team's site packs up and drives off (true) or has set up again (false): while it moves nobody is held at the
	// post or frozen to fly; a pilot frozen when it starts gets his AI back.
	static void Moving(SCR_AIGroup group, bool moving)
	{
		foreach (ZCR_OperatorMan m : s_aMen)
		{
			if (m.m_Group != group)
				continue;
			m.m_bMoving = moving;
			ChimeraCharacter c = ChimeraCharacter.Cast(m.m_Man);
			if (moving && c && m.m_bFlying)
			{
				m.m_bFlying = false;
				Stance(c, false);
				Freeze(c, false);
				m.m_iFrozenAt = 0;
			}
		}
	}

	// A new post for the team where its site set up again (in cover near 'post', away from 'threat').
	static void NewPost(SCR_AIGroup group, vector post, vector threat)
	{
		ZCR_OperatorMan pilot;
		foreach (ZCR_OperatorMan m : s_aMen)
		{
			if (m.m_Group == group && m.m_bPilot)
				pilot = m;
		}
		vector spot;
		ChimeraCharacter pc;
		if (pilot)
			pc = ChimeraCharacter.Cast(pilot.m_Man);
		if (pc && (ZCR_DroneThreat.CoverSpot(pc, threat, POST_COVER_M, post, spot) || ZCR_DroneThreat.CoverSpot(pc, threat, POST_COVER_FAR_M, post, spot)))
			post = spot;
		int now = ZCR_LossLog.Seconds();
		foreach (ZCR_OperatorMan m : s_aMen)
		{
			if (m.m_Group != group)
				continue;
			EndMove(m);
			m.m_vPost = post;
			if (!m.m_bPilot)
				m.m_vPost = post + Vector(3, 0, -3);
			if (m.m_Man)
				ToPost(m, now);
		}
		s_mCovered.Set(group, spot != vector.Zero);
		Print(string.Format("[ZCR][OPERATOR] t=%1 event=new_post cover=%2 x=%3 z=%4", now, spot != vector.Zero, Math.Round(post[0]), Math.Round(post[2])), LogLevel.NORMAL);
	}

	static ZCR_OperatorMan Find(IEntity e)
	{
		if (!e)
			return null;
		foreach (ZCR_OperatorMan m : s_aMen)
		{
			if (m.m_Man == e)
				return m;
		}
		return null;
	}

	// The pilot's kit: the big bag, the controller into a weapon slot (or the kit, if they are full); his helmet remembered -
	// the goggles go on only while he flies (Head).
	protected static void Kit(ZCR_OperatorMan m)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(m.m_Man);
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(c.FindComponent(SCR_InventoryStorageManagerComponent));
		SCR_CharacterInventoryStorageComponent store = SCR_CharacterInventoryStorageComponent.Cast(c.FindComponent(SCR_CharacterInventoryStorageComponent));
		if (!inv || !store)
			return;
		bool bag, controller;
		ResourceName bagPrefab = BAG_US;
		if (m.m_sSide == "USSR")
			bagPrefab = BAG_USSR;
		IEntity b = SpawnAt(bagPrefab, c.GetOrigin());
		if (b)
			bag = Wear(c, inv, store, b);
		// What he has on his head now (the goggles' slot).
		IEntity probe = SpawnAt(GOGGLES, c.GetOrigin());
		if (probe)
		{
			InventoryStorageSlot head = store.FindSuitableSlotForItem(probe);
			if (head && head.GetAttachedEntity() && head.GetAttachedEntity().GetPrefabData())
				m.m_sHelmet = head.GetAttachedEntity().GetPrefabData().GetPrefabName();
			SCR_EntityHelper.DeleteEntityAndChildren(probe);
		}
		IEntity k = SpawnAt(CONTROLLER, c.GetOrigin());
		if (k)
		{
			BaseInventoryStorageComponent weapons = store.GetWeaponStorage();
			if (weapons)
			{
				InventoryStorageSlot ws = weapons.FindSuitableSlotForItem(k);
				if (ws && !ws.GetAttachedEntity())
					controller = inv.TryInsertItemInStorage(k, weapons, ws.GetID());
			}
			if (!controller)
				controller = inv.TryInsertItem(k, EStoragePurpose.PURPOSE_WEAPON_PROXY);
			if (!controller)
				controller = inv.TryInsertItem(k);
			if (controller)
				m.m_Controller = k;
			else
				SCR_EntityHelper.DeleteEntityAndChildren(k);
		}
		Print(string.Format("[ZCR][OPERATOR] t=%1 side=%2 event=kit bag=%3 controller=%4 helmet=%5", ZCR_LossLog.Seconds(), m.m_sSide, bag, controller,
			!m.m_sHelmet.IsEmpty()), LogLevel.NORMAL);
	}

	// 'item' into its slot on him (head, back); what was there is taken away (not left on the ground or in his bag).
	protected static bool Wear(ChimeraCharacter c, SCR_InventoryStorageManagerComponent inv, SCR_CharacterInventoryStorageComponent store, IEntity item)
	{
		InventoryStorageSlot slot = store.FindSuitableSlotForItem(item);
		if (!slot)
		{
			SCR_EntityHelper.DeleteEntityAndChildren(item);
			return false;
		}
		IEntity old = slot.GetAttachedEntity();
		bool ok;
		if (old)
			ok = inv.TryReplaceItem(item, store, slot.GetID());
		else
			ok = inv.TryInsertItemInStorage(item, store, slot.GetID());
		if (!ok)
		{
			SCR_EntityHelper.DeleteEntityAndChildren(item);
			return false;
		}
		// The swap is only queued: the old item goes once the new one is really in the slot (18:28, Martin: "he doesn't have
		// a backpack at all", "he is not wearing the goggles" - the old one was taken away after 0.5 s whether or not).
		GetGame().GetCallqueue().CallLater(Confirm, 500, false, c, item, old, slot.GetID(), 0);
		return true;
	}

	// Every 0.5 s up to 3 s: the new item in the slot - the old one taken away; not - the new one removed, the old one kept.
	protected static void Confirm(ChimeraCharacter c, IEntity item, IEntity old, int slotId, int tries)
	{
		if (!c)
			return;
		SCR_CharacterInventoryStorageComponent store = SCR_CharacterInventoryStorageComponent.Cast(c.FindComponent(SCR_CharacterInventoryStorageComponent));
		InventoryStorageSlot slot;
		if (store)
			slot = store.GetSlot(slotId);
		IEntity on;
		if (slot)
			on = slot.GetAttachedEntity();
		string name = "?";
		if (item && item.GetPrefabData())
			name = FilePath.StripPath(item.GetPrefabData().GetPrefabName());
		if (item && on == item)
		{
			if (old && old != item)
				TakeAway(c, old);
			Print(string.Format("[ZCR][OPERATOR] t=%1 event=worn item=%2 after_s=%3", ZCR_LossLog.Seconds(), name, (tries + 1) * 0.5), LogLevel.NORMAL);
			return;
		}
		if (tries < 5)
		{
			GetGame().GetCallqueue().CallLater(Confirm, 500, false, c, item, old, slotId, tries + 1);
			return;
		}
		if (item && !item.GetParent())
			SCR_EntityHelper.DeleteEntityAndChildren(item);
		string had = "nothing";
		if (on && on.GetPrefabData())
			had = FilePath.StripPath(on.GetPrefabData().GetPrefabName());
		Print(string.Format("[ZCR][OPERATOR] t=%1 event=not_worn item=%2 slot_has=%3", ZCR_LossLog.Seconds(), name, had), LogLevel.NORMAL);
	}

	protected static void TakeAway(ChimeraCharacter c, IEntity old)
	{
		if (!old)
			return;
		SCR_InventoryStorageManagerComponent inv;
		if (c)
			inv = SCR_InventoryStorageManagerComponent.Cast(c.FindComponent(SCR_InventoryStorageManagerComponent));
		if (old.GetParent() && inv && inv.TryDeleteItem(old))
			return;
		SCR_EntityHelper.DeleteEntityAndChildren(old);
	}

	// The goggles on (he flies) or his helmet back on (he doesn't).
	protected static void Head(ChimeraCharacter c, ZCR_OperatorMan m, bool goggles)
	{
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(c.FindComponent(SCR_InventoryStorageManagerComponent));
		SCR_CharacterInventoryStorageComponent store = SCR_CharacterInventoryStorageComponent.Cast(c.FindComponent(SCR_CharacterInventoryStorageComponent));
		if (!inv || !store)
			return;
		ResourceName want = GOGGLES;
		if (!goggles)
			want = m.m_sHelmet;
		if (want.IsEmpty())
		{
			// No helmet to go back to: the goggles off.
			IEntity probe = SpawnAt(GOGGLES, c.GetOrigin());
			if (!probe)
				return;
			InventoryStorageSlot head = store.FindSuitableSlotForItem(probe);
			SCR_EntityHelper.DeleteEntityAndChildren(probe);
			if (head && head.GetAttachedEntity())
				TakeAway(c, head.GetAttachedEntity());
			return;
		}
		IEntity item = SpawnAt(want, c.GetOrigin());
		bool ok;
		if (item)
			ok = Wear(c, inv, store, item);
		string what = "helmet";
		if (goggles)
			what = "goggles";
		Print(string.Format("[ZCR][OPERATOR] t=%1 side=%2 event=%3 ok=%4", ZCR_LossLog.Seconds(), m.m_sSide, what, ok), LogLevel.NORMAL);
	}

	protected static IEntity SpawnAt(ResourceName prefab, vector at)
	{
		Resource res = Resource.Load(prefab);
		if (!res || !res.IsValid())
			return null;
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = at + Vector(0, 1, 0);
		return GetGame().SpawnEntityPrefab(res, GetGame().GetWorld(), params);
	}

	// A drone of his side in the air within RANGE_M.
	protected static bool Flying(string side, vector at)
	{
		BaseWorld world = GetGame().GetWorld();
		for (int i; i < ZCR_Drones.s_aDrones.Count(); i++)
		{
			IEntity d = ZCR_Drones.s_aDrones[i];
			if (!d || ZCR_Drones.s_aDroneSide[i] != side)
				continue;
			vector p = d.GetOrigin();
			if (p[1] - world.GetSurfaceY(p[0], p[2]) > 3 && vector.DistanceXZ(p, at) < RANGE_M)
				return true;
		}
		return false;
	}

	static bool IsFlying(IEntity e)
	{
		ZCR_OperatorMan m = Find(e);
		return m && m.m_bFlying;
	}

	protected static void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		Sorties(now);
		map<string, int> pilots = new map<string, int>();
		map<string, int> flying = new map<string, int>();
		foreach (ZCR_OperatorMan m : s_aMen)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(m.m_Man);
			if (!c || !c.GetCharacterController() || c.GetCharacterController().GetLifeState() != ECharacterLifeState.ALIVE)
				continue;
			if (m.m_bMoving)
				continue;                          // the site is on the move: boarding, driving, getting out
			// Both stay at the post, flying or not (the village storm, 15:40: the pilot 26-60 m off it between flights).
			if (!m.m_bPilot)
			{
				if (vector.DistanceXZ(c.GetOrigin(), m.m_vPost) > STAY_M && now >= m.m_iAgainAt && !ZCR_DroneThreat.Sheltering(c))
				{
					ToPost(m, now);
					s_mHolds.Set(m.m_sSide, s_mHolds.Get(m.m_sSide) + 1);
				}
				continue;
			}
			pilots.Set(m.m_sSide, pilots.Get(m.m_sSide) + 1);
			bool up = Flying(m.m_sSide, c.GetOrigin());
			// A flight longer than MAX_FROZEN_S: his AI back on anyway (a drone that never comes down).
			if (up && m.m_bFlying && m.m_iFrozenAt > 0 && now - m.m_iFrozenAt > MAX_FROZEN_S)
			{
				up = false;
				m.m_iThawUntil = now + 30;
			}
			if (now < m.m_iThawUntil)
				up = false;
			if (up != m.m_bFlying)
			{
				m.m_bFlying = up;
				Stance(c, up);
				string what = "landed";
				if (up)
				{
					what = "flying";
					// Still while he flies (Martin, 24 Oct 15:48: "the drone operator should really just hold still when he is
					// driving the drone"): the controller in his hands, down on a knee, then his AI off - he stands where he
					// is, blind to the world behind his goggles (his guard watches); on again when the drone is down.
					// The goggles first, the controller a second later, then his AI off (18:26: goggles and controller in the same
					// moment - the goggles never went on; one inventory action at a time).
					Head(c, m, true);
					GetGame().GetCallqueue().CallLater(HandsLater, 1000, false, c, true);
					c.GetCharacterController().SetStanceChange(ECharacterStanceChange.STANCECHANGE_TOCROUCH);
					GetGame().GetCallqueue().CallLater(Freeze, 2500, false, c, true);
					m.m_iFrozenAt = now;
				}
				else
				{
					m.m_iLandedAt = now;
					Freeze(c, false);
					Head(c, m, false);                 // his helmet back on, his rifle a second later
					GetGame().GetCallqueue().CallLater(HandsLater, 1000, false, c, false);
					m.m_iFrozenAt = 0;
				}
				Print(string.Format("[ZCR][OPERATOR] t=%1 side=%2 event=%3 x=%4 z=%5 at_post=%6", now, m.m_sSide, what, Math.Round(c.GetOrigin()[0]),
					Math.Round(c.GetOrigin()[2]), Math.Round(vector.DistanceXZ(c.GetOrigin(), m.m_vPost))), LogLevel.NORMAL);
			}
			if (up)
				flying.Set(m.m_sSide, flying.Get(m.m_sSide) + 1);
			else
			{
				if (now - m.m_iLandedAt > 3)
					Hands(c, m.m_Controller, false);
				if (vector.DistanceXZ(c.GetOrigin(), m.m_vPost) > STAY_M && now >= m.m_iAgainAt && !ZCR_DroneThreat.Sheltering(c))
				{
					ToPost(m, now);
					s_mHolds.Set(m.m_sSide, s_mHolds.Get(m.m_sSide) + 1);
				}
			}
		}
		if (now >= s_iNextLog)
		{
			s_iNextLog = now + 60;
			foreach (string side, int n : pilots)
				Print(string.Format("[ZCR][OPERATOR] t=%1 side=%2 pilots=%3 flying=%4 holds=%5", now, side, n, flying.Get(side), s_mHolds.Get(side)), LogLevel.NORMAL);
		}
	}

	protected static void HandsLater(ChimeraCharacter c, bool flying)
	{
		ZCR_OperatorMan m = Find(c);
		if (m && c && m.m_bFlying == flying)
			Hands(c, m.m_Controller, flying);
	}

	// His AI off (frozen where he stands) or on again. Only while he is still flying when the delayed call comes.
	protected static void Freeze(ChimeraCharacter c, bool frozen)
	{
		if (!c || !c.GetCharacterController() || c.GetCharacterController().GetLifeState() != ECharacterLifeState.ALIVE)
			return;
		AIControlComponent control = AIControlComponent.Cast(c.FindComponent(AIControlComponent));
		if (!control)
			return;
		if (frozen)
		{
			ZCR_OperatorMan m = Find(c);
			if (m && m.m_bFlying && control.IsAIActivated())
				control.DeactivateAI();
			return;
		}
		if (!control.IsAIActivated())
			control.ActivateAI();
	}

	protected static void EndMove(ZCR_OperatorMan m)
	{
		if (m.m_Move && m.m_Move.GetActionState() == EAIActionState.RUNNING)
			m.m_Move.Complete();
		m.m_Move = null;
	}

	// Back to (or off to) his post: above the squad's own moves, below a run into a building from an enemy drone.
	protected static void ToPost(ZCR_OperatorMan m, int now)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(m.m_Man);
		SCR_AIUtilityComponent utility = ZCR_DroneThreat.UtilityOf(c);
		if (!utility)
			return;
		// A new order only when the last one has ended (18:06: a fresh one every 3 s on the walk out and back - 332 in 12
		// minutes; the operators stopped, turned and started again all the way: "the operator is acting a bit weird").
		if (m.m_Move && m.m_Move.GetActionState() == EAIActionState.RUNNING)
			return;
		SCR_AIMoveIndividuallyBehavior move = new SCR_AIMoveIndividuallyBehavior(utility, null, m.m_vPost, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_FROM_DANGER + 1,
			SCR_AIActionBase.PRIORITY_LEVEL_NORMAL, null, 1.0);
		ZCR_Reserved.Add(utility, move);
		m.m_Move = move;
		m.m_iAgainAt = now + 3;
	}

	// The controller in his hands while he flies; his own weapon otherwise.
	protected static void Hands(ChimeraCharacter c, IEntity controller, bool flying)
	{
		if (!controller)
			return;
		CharacterControllerComponent ctl = c.GetCharacterController();
		BaseWeaponManagerComponent wm = BaseWeaponManagerComponent.Cast(c.FindComponent(BaseWeaponManagerComponent));
		if (!ctl || !wm)
			return;
		BaseWeaponComponent now = wm.GetCurrentWeapon();
		BaseWeaponComponent pad = BaseWeaponComponent.Cast(controller.FindComponent(BaseWeaponComponent));
		if (!pad)
			return;
		if (flying)
		{
			if (now != pad)
				ctl.SelectWeapon(pad);
			return;
		}
		if (now != pad)
			return;
		array<IEntity> weapons = {};
		wm.GetWeaponsList(weapons);
		foreach (IEntity w : weapons)
		{
			if (w == controller)
				continue;
			BaseWeaponComponent wc = BaseWeaponComponent.Cast(w.FindComponent(BaseWeaponComponent));
			if (wc)
			{
				ctl.SelectWeapon(wc);
				return;
			}
		}
	}

	// Crouched while he flies (the game's own stance setting, as the drone reaction's prone).
	protected static void Stance(ChimeraCharacter c, bool flying)
	{
		AIControlComponent control = AIControlComponent.Cast(c.FindComponent(AIControlComponent));
		if (!control || !control.GetControlAIAgent())
			return;
		SCR_AICharacterSettingsComponent settings = SCR_AICharacterSettingsComponent.Cast(control.GetControlAIAgent().FindComponent(SCR_AICharacterSettingsComponent));
		if (!settings)
			return;
		if (flying)
			settings.AddCharacterSetting(SCR_AICharacterStanceSetting.Create(SCR_EAISettingOrigin.SCENARIO, SCR_EAIBehaviorCause.ALWAYS, ECharacterStance.CROUCH), false, true);
		else
			settings.RemoveSettingsOfTypeAndOrigin(SCR_AICharacterStanceSettingBase, SCR_EAISettingOrigin.SCENARIO);
	}
}
