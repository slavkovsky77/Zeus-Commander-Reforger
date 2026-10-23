// Every gate on the map open (23 Oct night). The Everon US base exit has two closed metal gates (DoorSet_MetalGate_01,
// found by the door probe); test cars queued at them for whole runs - 0-4 trips and 2-4 cars lost in 10 minutes, in every
// setup. Mostly nobody even asks to open them (the game's navlink-door goal below came in one run of three). With both
// gate areas opened at the start: 7 trips, no car lost. So at the start every door whose prefab is a gate is opened - base
// gates and farm gates on the fenced fields where rides got trapped - and checked again every minute.
// LAB ONLY, opt-in -zcrOpenGates: Martin decided on 21 Oct that gates and road blocks stay on the map - "improve the
// driving" - and liked seeing the AI open a gate (review notes 241, 242). This proves the cause; the fix is the driving's.
//   [ZCR][GATES] t= opened= checked=
class ZCR_OpenGates
{
	protected static ref ZCR_OpenGates s_Instance;
	protected ref array<IEntity> m_aGates = {};
	protected int m_iChecked;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || !System.IsCLIParam("zcrOpenGates"))
			return;
		s_Instance = new ZCR_OpenGates();
		GetGame().GetCallqueue().CallLater(s_Instance.Find, 3000, false);
		GetGame().GetCallqueue().CallLater(s_Instance.Open, 60000, true);
	}

	protected bool Add(IEntity e)
	{
		if (!e || !e.FindComponent(DoorComponent))
			return true;
		m_iChecked++;
		IEntity named = e;
		while (named)
		{
			if (named.GetPrefabData())
			{
				string name = named.GetPrefabData().GetPrefabName();
				name.ToLower();
				if (name.Contains("gate"))
				{
					m_aGates.Insert(e);
					return true;
				}
			}
			named = named.GetParent();
		}
		return true;
	}

	protected void Find()
	{
		vector min, max;
		BaseWorld world = GetGame().GetWorld();
		world.GetBoundBox(min, max);
		vector center = (min + max) * 0.5;
		world.QueryEntitiesBySphere(center, vector.Distance(min, max) * 0.5, Add, null, EQueryEntitiesFlags.ALL);
		Open();
	}

	protected void Open()
	{
		int opened;
		foreach (IEntity e : m_aGates)
		{
			if (!e)
				continue;
			DoorComponent door = DoorComponent.Cast(e.FindComponent(DoorComponent));
			if (door && Math.AbsFloat(door.GetNormalizedDoorState()) < 0.5)
			{
				door.SetControlValue(1, RplId.Invalid());
				opened++;
			}
		}
		if (opened > 0)
			Print(string.Format("[ZCR][GATES] t=%1 opened=%2 gates=%3 doors_checked=%4", ZCR_LossLog.Seconds(), opened, m_aGates.Count(), m_iChecked), LogLevel.NORMAL);
	}
}

// Gates open themselves for vehicles (23 Oct night). A vehicle whose route crosses a gate makes the game send one of its
// soldiers an "open the navlink door" goal; for a soldier in a vehicle the game queues get out - open - get back in
// (SCR_AIUtilityComponent.WrapBehaviorOutsideOfVehicle). The get-out probe caught it: 2 of 6 test cars at the Everon US
// base exit lost their driver this way within 70 s of starting, and one stood there 50 s later, blocking the road
// ([ZCR][JAM]). Now the gate is opened from the seat, the way the AI would open it by hand (SCR_AIOpenDoor's actions),
// and nobody gets out. On foot nothing changes. Lab only, opt-in -zcrAutoGate (it replaces the gate opening Martin likes to see).
//   [ZCR][GATE] t= vehicle= x= z= doors=
modded class SCR_AIGoalReaction_OpenNavlinkDoor
{
	override void PerformReaction(notnull SCR_AIUtilityComponent utility, SCR_AIMessageBase message)
	{
		SCR_AIMessage_OpenNavlinkDoor msg = SCR_AIMessage_OpenNavlinkDoor.Cast(message);
		ChimeraCharacter soldier = ChimeraCharacter.Cast(utility.m_OwnerEntity);
		if (ZCR_GetOutProbe.On() && msg && msg.m_DoorEntity)
		{
			vector d = msg.m_DoorEntity.GetOrigin();
			Print(string.Format("[ZCR][GATEMSG] t=%1 door=%2 x=%3 z=%4 in_vehicle=%5", ZCR_LossLog.Seconds(), ZCR_LossLog.ShortName(msg.m_DoorEntity),
				Math.Round(d[0]), Math.Round(d[2]), soldier && soldier.IsInVehicle()), LogLevel.NORMAL);
		}
		if (!msg || !msg.m_DoorEntity || !soldier || !soldier.IsInVehicle() || !System.IsCLIParam("zcrAutoGate"))
		{
			super.PerformReaction(utility, message);
			return;
		}
		array<ScriptedUserAction> actions = {};
		SCR_AIOpenDoor.FindDoorActions(msg.m_DoorEntity, actions, true);
		int opened;
		foreach (ScriptedUserAction action : actions)
		{
			IEntity owner = action.GetOwner();
			if (!owner)
				continue;
			DoorComponent door = DoorComponent.Cast(owner.FindComponent(DoorComponent));
			if (!door || door.IsOpening() || Math.AbsFloat(door.GetNormalizedDoorState()) > 0.99)
				continue;
			action.PerformAction(owner, soldier);
			opened++;
		}
		if (actions.IsEmpty())
		{
			super.PerformReaction(utility, message);   // no door action found: the game's own way
			return;
		}
		IEntity vehicle = CompartmentAccessComponent.GetVehicleIn(soldier);
		vector at = soldier.GetOrigin();
		Print(string.Format("[ZCR][GATE] t=%1 vehicle=%2 x=%3 z=%4 doors=%5", ZCR_LossLog.Seconds(), ZCR_LossLog.ShortName(vehicle), Math.Round(at[0]),
			Math.Round(at[2]), opened), LogLevel.NORMAL);
	}
}

// Gate nudge (23 Oct night, review notes 316). Cars wait at a closed gate and nobody is sent to open it: the Everon US base
// exit with its gates closed gave 0 trips in 10 minutes, all six cars queued, no "open the navlink door" goal in the log.
// Gates stay on the map (Martin, 21 Oct, note 242: "improve the driving"; he liked the AI opening a gate, 241), so a car
// that has stood still for 6 s with closed gates within 15 m ahead gets what the game's own open-the-gate reaction gives a
// soldier (SCR_AIGoalReaction_OpenNavlinkDoor): its driver gets out, opens them and gets back in. (Sending him the goal
// message did nothing - no reaction ran; and the nearest gate was the pedestrian gate beside the vehicle gate, so every
// closed gate ahead is opened.) One nudge a gate per 30 s. Lab only, opt-in -zcrGateNudge (the test showed it too late: once
// cars wait at a gate, opening it no longer frees the queue - review note 316). -zcrGateSelfOpen: the gate swings open by
// itself instead (in the first test the soldier got out but no gate ever moved, and 2 crews didn't get back in).
//   [ZCR][GATENUDGE] t= vehicle= gate= m= waited_s= action=0|1 x= z=
class ZCR_GateNudge
{
	protected static ref ZCR_GateNudge s_Instance;
	protected ref map<IEntity, int> m_mStillSince = new map<IEntity, int>();
	protected ref map<IEntity, int> m_mNudged = new map<IEntity, int>();
	protected ref array<IEntity> m_aDoors = {};

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || !System.IsCLIParam("zcrGateNudge"))
			return;
		s_Instance = new ZCR_GateNudge();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	protected bool AddDoor(IEntity e)
	{
		if (e && e.FindComponent(DoorComponent))
			m_aDoors.Insert(e);
		return true;
	}

	protected static string PrefabTail(IEntity e)
	{
		IEntity named = e;
		while (named)
		{
			if (named.GetPrefabData())
			{
				string name = named.GetPrefabData().GetPrefabName();
				int slash = name.LastIndexOf("/");
				if (slash >= 0)
					name = name.Substring(slash + 1, name.Length() - slash - 1);
				return name;
			}
			named = named.GetParent();
		}
		return "?";
	}

	protected static bool IsGate(IEntity e)
	{
		IEntity named = e;
		while (named)
		{
			if (named.GetPrefabData())
			{
				string name = named.GetPrefabData().GetPrefabName();
				name.ToLower();
				if (name.Contains("gate"))
					return true;
			}
			named = named.GetParent();
		}
		return false;
	}

	// The closed gates within 10 m of the vehicle.
	protected void ClosedGatesAhead(IEntity v, notnull array<IEntity> gates)
	{
		m_aDoors.Clear();
		vector at = v.GetOrigin();
		GetGame().GetWorld().QueryEntitiesBySphere(at, 15, AddDoor, null, EQueryEntitiesFlags.ALL);
		vector forward = v.GetTransformAxis(2);
		forward[1] = 0;
		forward.Normalize();
		bool verbose = System.IsCLIParam("zcrGateDebug");
		foreach (IEntity e : m_aDoors)
		{
			DoorComponent door = DoorComponent.Cast(e.FindComponent(DoorComponent));
			vector to = e.GetOrigin() - at;
			to[1] = 0;
			float d = to.Length();
			float dot = 0;
			if (d > 0.1)
				dot = vector.Dot(to * (1 / d), forward);
			vector eo = e.GetOrigin();
			if (verbose)
				Print(string.Format("[ZCR][GATESEEN] t=%1 door=%2 gate=%3 m=%4 dot=%5 state=%6 x=%7 z=%8", ZCR_LossLog.Seconds(), PrefabTail(e), IsGate(e),
					Math.Round(d), Math.Round(dot * 100) / 100, Math.Round(door.GetNormalizedDoorState() * 100) / 100, Math.Round(eo[0]), Math.Round(eo[2])), LogLevel.NORMAL);
			// Any side: cars waiting at the Everon exit stood beside the vehicle gate, facing the guard house (direction ~0).
			if (!door || Math.AbsFloat(door.GetNormalizedDoorState()) > 0.5 || !IsGate(e) || d > 10)
				continue;
			gates.Insert(e);
		}
	}

	protected static AIAgent Driver(IEntity v)
	{
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(v, seats);
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (!seat || seat.GetType() != ECompartmentType.PILOT || !seat.GetOccupant())
				continue;
			AIControlComponent control = AIControlComponent.Cast(seat.GetOccupant().FindComponent(AIControlComponent));
			if (control)
				return control.GetControlAIAgent();
		}
		return null;
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		foreach (IEntity v : cars)
		{
			if (!v || !v.GetPhysics() || v.GetPhysics().GetVelocity().Length() * 3.6 > 3)
			{
				m_mStillSince.Remove(v);
				continue;
			}
			int since;
			if (!m_mStillSince.Find(v, since))
			{
				m_mStillSince.Set(v, now);
				continue;
			}
			if (now - since < 6)
				continue;
			array<IEntity> gates = {};
			ClosedGatesAhead(v, gates);
			if (gates.IsEmpty())
				continue;
			AIAgent driver = Driver(v);
			SCR_AIUtilityComponent utility;
			if (driver)
				utility = SCR_AIUtilityComponent.Cast(driver.FindComponent(SCR_AIUtilityComponent));
			if (!utility)
				continue;
			foreach (IEntity gate : gates)
			{
				int last;
				if (m_mNudged.Find(gate, last) && now - last < 30)
					continue;
				// The gate's "OpenGate" smart action, on the door entity or its parent - as the game's reaction finds it.
				SCR_AISmartActionComponent action = SCR_AISmartActionHandling.FindSmartAction(gate, SCR_AIGoalReaction_OpenNavlinkDoor.SMART_ACTION_TAG, false);
				if (!action && gate.GetParent())
					action = SCR_AISmartActionHandling.FindSmartAction(gate.GetParent(), SCR_AIGoalReaction_OpenNavlinkDoor.SMART_ACTION_TAG, false);
				m_mNudged.Set(gate, now);
				vector g = gate.GetOrigin();
				string name = PrefabTail(gate);
				bool self = System.IsCLIParam("zcrGateSelfOpen");
				Print(string.Format("[ZCR][GATENUDGE] t=%1 vehicle=%2 gate=%3 m=%4 waited_s=%5 action=%6 self=%7 x=%8 z=%9", now, ZCR_LossLog.ShortName(v), name,
					Math.Round(vector.DistanceXZ(g, v.GetOrigin())), now - since, action != null, self, Math.Round(g[0]), Math.Round(g[2])), LogLevel.NORMAL);
				if (self)
				{
					DoorComponent.Cast(gate.FindComponent(DoorComponent)).SetControlValue(1, RplId.Invalid());
					continue;
				}
				if (!action)
					continue;
				SCR_AIPerformActionBehavior open = new SCR_AIPerformActionBehavior(utility, null, action, priority: SCR_AIActionBase.PRIORITY_BEHAVIOR_OPEN_NAVLINK_DOOR,
					priorityLevel: SCR_AIActionBase.PRIORITY_LEVEL_NORMAL);
				utility.WrapBehaviorOutsideOfVehicle(open);
				utility.AddAction(open);
			}
		}
	}
}
