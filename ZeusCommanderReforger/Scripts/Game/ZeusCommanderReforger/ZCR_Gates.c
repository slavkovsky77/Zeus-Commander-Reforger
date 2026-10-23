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
