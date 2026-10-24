// Drone operators (Martin, 24 Oct 15:32: "the drone operator should be seen in the GUI with some tag that this is a drone
// operator, so I know how it works; he should maybe seek cover, and when he is controlling a drone he should have the drone
// controller in hands and goggles, and be stationary like in real life"). A 2-man team that launches drones (the infantry
// test's operators, the commander's drone sites) registers here:
//   - its first soldier is the pilot: Realistic Combat Drones' FPV goggles on his head in place of the helmet, and its
//     drone controller, which he holds while a drone of his side is in the air (his rifle again when none is);
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
	SCR_AIGroup m_Group;
	bool m_bMoving;         // the drone site is moving (ZCR_DroneSites): no holding at the post, no flying
}

class ZCR_DroneOperator
{
	static const ResourceName GOGGLES = "{8951045BFE8BC8E4}Prefabs/Characters/HeadGear/FPV_Goggles.et";
	static const ResourceName CONTROLLER = "{E2434ED1318D8476}Prefabs/Characters/Items/DroneController.et";
	static const float POST_COVER_M = 25;
	static const float POST_COVER_FAR_M = 60;    // none within 25 m (17:40: the farm-site operators stood in the open)
	static const float HOLD_M = 6;          // the pilot while he flies (3 m: he settled 5 m off his post and was sent back every 3 s)
	static const float STAY_M = 8;          // the pilot between flights, the guard always
	static const int MAX_FROZEN_S = 120;    // the pilot's AI back on after this long in one flight
	static const float RANGE_M = 2500;     // a pilot flies his side's drones within this of him
	static ref array<ref ZCR_OperatorMan> s_aMen = {};
	protected static bool s_bStarted;
	protected static int s_iNextLog;
	protected static ref map<string, int> s_mHolds = new map<string, int>();

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
		ZCR_Tactical.Get().HoldStill(group);   // DCO: its squad moves off for the team
		Print(string.Format("[ZCR][OPERATOR] t=%1 side=%2 event=post men=%3 cover=%4 x=%5 z=%6 layer=%7", now, side, agents.Count(), spot != vector.Zero,
			Math.Round(post[0]), Math.Round(post[2]), ZCR_Tactical.Get().Layer()), LogLevel.NORMAL);
		if (!s_bStarted)
		{
			s_bStarted = true;
			GetGame().GetCallqueue().CallLater(Tick, 1000, true);
		}
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
			m.m_vPost = post;
			if (!m.m_bPilot)
				m.m_vPost = post + Vector(3, 0, -3);
			if (m.m_Man)
				ToPost(m, now);
		}
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

	// Goggles on the head (the helmet goes), the controller into a weapon slot (or the kit, if they are full).
	protected static void Kit(ZCR_OperatorMan m)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(m.m_Man);
		SCR_InventoryStorageManagerComponent inv = SCR_InventoryStorageManagerComponent.Cast(c.FindComponent(SCR_InventoryStorageManagerComponent));
		SCR_CharacterInventoryStorageComponent store = SCR_CharacterInventoryStorageComponent.Cast(c.FindComponent(SCR_CharacterInventoryStorageComponent));
		if (!inv || !store)
			return;
		bool goggles, controller;
		IEntity g = SpawnAt(GOGGLES, c.GetOrigin());
		if (g)
		{
			InventoryStorageSlot slot = store.FindSuitableSlotForItem(g);
			if (slot)
				goggles = inv.TryReplaceItem(g, store, slot.GetID());
			if (!goggles)
				goggles = inv.TryInsertItem(g, EStoragePurpose.PURPOSE_LOADOUT_PROXY);
			if (!goggles)
				SCR_EntityHelper.DeleteEntityAndChildren(g);
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
		Print(string.Format("[ZCR][OPERATOR] t=%1 side=%2 event=kit goggles=%3 controller=%4", ZCR_LossLog.Seconds(), m.m_sSide, goggles, controller), LogLevel.NORMAL);
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
					Hands(c, m.m_Controller, true);
					c.GetCharacterController().SetStanceChange(ECharacterStanceChange.STANCECHANGE_TOCROUCH);
					GetGame().GetCallqueue().CallLater(Freeze, 1500, false, c, true);
					m.m_iFrozenAt = now;
				}
				else
				{
					Freeze(c, false);
					m.m_iFrozenAt = 0;
				}
				Print(string.Format("[ZCR][OPERATOR] t=%1 side=%2 event=%3 x=%4 z=%5 at_post=%6", now, m.m_sSide, what, Math.Round(c.GetOrigin()[0]),
					Math.Round(c.GetOrigin()[2]), Math.Round(vector.DistanceXZ(c.GetOrigin(), m.m_vPost))), LogLevel.NORMAL);
			}
			if (up)
				flying.Set(m.m_sSide, flying.Get(m.m_sSide) + 1);
			else
			{
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

	// Back to (or off to) his post: above the squad's own moves, below a run into a building from an enemy drone.
	protected static void ToPost(ZCR_OperatorMan m, int now)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(m.m_Man);
		SCR_AIUtilityComponent utility = ZCR_DroneThreat.UtilityOf(c);
		if (!utility)
			return;
		ZCR_Reserved.Add(utility, new SCR_AIMoveIndividuallyBehavior(utility, null, m.m_vPost, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_FROM_DANGER + 1,
			SCR_AIActionBase.PRIORITY_LEVEL_NORMAL, null, 1.0));
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
