// The crash fix (27 Oct, review note 421 - Martin: "find the root cause of the crash by simulating it"). A soldier
// climbing into or out of a vehicle that stands tilted crashes the dedicated server: the engine asserts on a bad entity
// matrix (enf_entity.cpp BadMatrix33), then reads bad memory - the release server build too. In the crash sub-lab
// (ZCR_BoardTest: 8 LAV-25s on Moss Hill's hillside, pitch 16-23, roll 4-11 deg) every run crashed, 44 of 62 crashes
// 2.5-9 s into the get-in, the rest in the get-out; the same test on the flat airport apron never did.
// So on a vehicle tilted over the limit a soldier goes straight into his seat when he has walked up to the vehicle
// (no climbing animation), and straight out beside it when he is ordered out; on level ground nothing changes - the
// climb Martin wants to see stays. -zcrSafeBoardDeg N: the limit in degrees (0 = off, the default until it is proven).
// 04:50 the tilt sweep (8 LAV-25s on even, clear spots of one slope): the LAV-25 crashes on level ground too, only less
// often (0-3 deg: 1 of 3 runs, after minutes; 17-24 deg: every run within seconds) - and the BTR-70 on the hillside 0 of
// 8. So into the vehicles of -zcrSafeBoardAlways (default "LAV25"; "none" = the tilt limit only) a soldier always goes
// straight in, whatever the tilt. Getting out stays animated below the limit (climbing out never crashed once they were
// moved in: 0 of 16 runs).
// A soldier who can't be moved in (seat taken, vehicle not accessible) for FAIL_MS has his get-in cancelled rather than
// left to climb in on the tilted vehicle (what=in_cancel); the game's own logic gives him another order.
//   [ZCR][SAFEBOARD] t= what=in|out|in_cancel ok= man= vehicle= tilt= x= z=
class ZCR_SafeBoarding
{
	static const int TICK_MS = 100;
	static const float REACH_M = 6;          // from the vehicle's centre: a LAV-25 is ~7 m long, its door at the back
	static const int WATCH_MAX_MS = 180000;
	static const int FAIL_MS = 1000;
	protected static float s_fLimit = -1;
	protected static ref array<string> s_aAlways;
	protected static ref ZCR_SafeBoarding s_Instance;
	protected ref array<SCR_AIGetInVehicle> m_aWatch = {};
	protected ref array<int> m_aSince = {};
	protected ref array<int> m_aFailedAt = {};

	static float Limit()
	{
		if (s_fLimit >= 0)
			return s_fLimit;
		s_fLimit = 0;
		string value;
		if (System.GetCLIParam("zcrSafeBoardDeg", value) && !value.IsEmpty())
			s_fLimit = Math.Clamp(value.ToFloat(), 0, 90);
		return s_fLimit;
	}

	static bool Always(IEntity vehicle)
	{
		if (!s_aAlways)
		{
			s_aAlways = {};
			string value = "LAV25";
			string given;
			if (System.GetCLIParam("zcrSafeBoardAlways", given) && !given.IsEmpty())
				value = given;
			if (value != "none")
				value.Split(",", s_aAlways, true);
		}
		if (!vehicle || !vehicle.GetPrefabData())
			return false;
		string name = vehicle.GetPrefabData().GetPrefabName();
		foreach (string part : s_aAlways)
		{
			if (name.Contains(part))
				return true;
		}
		return false;
	}

	// The angle between the vehicle's up and the world's up.
	static float Tilt(IEntity vehicle)
	{
		vector mat[4];
		vehicle.GetWorldTransform(mat);
		vector up = mat[1];
		return Math.Acos(Math.Clamp(up[1], -1, 1)) * Math.RAD2DEG;
	}

	// SCR_AIGetInVehicle.OnActionSelected: the soldier starts walking to the vehicle - watch him until he is in.
	static void WatchGetIn(SCR_AIGetInVehicle action)
	{
		if (!action || Limit() <= 0 || !Replication.IsServer())
			return;
		if (!s_Instance)
		{
			s_Instance = new ZCR_SafeBoarding();
			GetGame().GetCallqueue().CallLater(s_Instance.Tick, TICK_MS, true);
		}
		if (s_Instance.m_aWatch.Contains(action))
			return;
		s_Instance.m_aWatch.Insert(action);
		s_Instance.m_aSince.Insert(System.GetTickCount());
		s_Instance.m_aFailedAt.Insert(0);
	}

	protected void Tick()
	{
		int nowMs = System.GetTickCount();
		for (int i = m_aWatch.Count() - 1; i >= 0; i--)
		{
			SCR_AIGetInVehicle action = m_aWatch[i];
			if (!action || nowMs - m_aSince[i] > WATCH_MAX_MS || TryIn(action, i, nowMs))
			{
				m_aWatch.Remove(i);
				m_aSince.Remove(i);
				m_aFailedAt.Remove(i);
			}
		}
	}

	// True when this soldier needs no more watching: in, dead, climbing already, or he reached a level vehicle.
	protected bool TryIn(SCR_AIGetInVehicle action, int i, int nowMs)
	{
		if (!action.m_Utility)
			return true;
		ChimeraCharacter man = ChimeraCharacter.Cast(action.m_Utility.m_OwnerEntity);
		if (!man || !AICF_GroupRuntime.IsAliveCharacter(man))
			return true;
		CompartmentAccessComponent access = man.GetCompartmentAccessComponent();
		if (!access || CompartmentAccessComponent.GetVehicleIn(man) || access.IsGettingIn())
			return true;
		BaseCompartmentSlot seat = action.m_CompartmentToGetIn.m_Value;
		IEntity vehicle = action.m_Vehicle.m_Value;
		if (seat && seat.GetVehicle())
			vehicle = seat.GetVehicle();
		if (!vehicle)
			return true;
		if (vector.Distance(man.GetOrigin(), vehicle.GetOrigin()) > REACH_M)
			return false;                     // still walking up to it
		float tilt = Tilt(vehicle);
		if (tilt <= Limit() && !Always(vehicle))
			return true;                      // level: the normal climb
		if (!seat || (seat.GetOccupant() && seat.GetOccupant() != man))
			seat = access.FindCompartmentReservedBy(vehicle, man);
		if (!seat)
			seat = access.FindFreeCompartment(vehicle, SeatType(action.m_eRoleInVehicle.m_Value), false);
		bool ok;
		if (seat)
			ok = access.GetInVehicle(vehicle, seat, true, -1, ECloseDoorAfterActions.INVALID, false);
		if (ok)
		{
			Log("in", ok, man, vehicle, tilt);
			return true;
		}
		if (m_aFailedAt[i] == 0)
			m_aFailedAt[i] = nowMs;
		if (nowMs - m_aFailedAt[i] < FAIL_MS)
			return false;                     // try again next tick
		access.InterruptVehicleActionQueue(true, true, true);
		action.Fail();
		Log("in_cancel", false, man, vehicle, tilt);
		return true;
	}

	protected static ECompartmentType SeatType(EAICompartmentType role)
	{
		if (role == EAICompartmentType.Pilot)
			return ECompartmentType.PILOT;
		if (role == EAICompartmentType.Turret)
			return ECompartmentType.TURRET;
		return ECompartmentType.CARGO;
	}

	// SCR_AIGetOutVehicle.OnActionSelected: out of a tilted vehicle without the climb. True when he was moved out.
	static bool TryOut(SCR_AIUtilityComponent utility)
	{
		if (!utility || Limit() <= 0 || !Replication.IsServer())
			return false;
		ChimeraCharacter man = ChimeraCharacter.Cast(utility.m_OwnerEntity);
		if (!man)
			return false;
		IEntity vehicle = CompartmentAccessComponent.GetVehicleIn(man);
		CompartmentAccessComponent access = man.GetCompartmentAccessComponent();
		if (!vehicle || !access || access.IsGettingOut() || access.IsGettingIn())
			return false;
		float tilt = Tilt(vehicle);
		if (tilt <= Limit())
			return false;
		bool ok = access.GetOutVehicle(EGetOutType.TELEPORT, -1, ECloseDoorAfterActions.INVALID, false);
		Log("out", ok, man, vehicle, tilt);
		return ok;
	}

	protected static void Log(string what, bool ok, IEntity man, IEntity vehicle, float tilt)
	{
		vector at = vehicle.GetOrigin();
		Print(string.Format("[ZCR][SAFEBOARD] t=%1 what=%2 ok=%3 man=%4 vehicle=%5 tilt=%6 x=%7 z=%8", ZCR_LossLog.Seconds(), what, ok,
			ZCR_LossLog.ShortName(man), ZCR_LossLog.ShortName(vehicle), Math.Round(tilt), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
	}
}

modded class SCR_AIGetInVehicle
{
	override void OnActionSelected()
	{
		super.OnActionSelected();
		ZCR_SafeBoarding.WatchGetIn(this);
	}
}
