// Crews of armed vehicles stay aboard (23 Oct, Martin watching two BTR-70s attack a rifle squad: "lol, the crew went out and
// didn't use the vehicles, that's stupid"). The get-out probe: the group's move failed (UNREACHABLE, 416 m short of the
// squad) and the game's answer to any failed move is the whole group out (SCR_AIProcessFailedMovementResult) - an undamaged
// BTR left empty in the open, its crew on foot, before a shot was fired. Now the driver and the turret crew of a vehicle
// with a gun stay aboard while it is intact (35%+ health, as ZCR_Armour's own units); passengers still get out (AI
// Conflict's rides unload their teams), static weapons are left as the game has them. -zcrCrewsLeave turns it off.
//   [ZCR][CREWSTAYS] t= vehicle= seat= health= x= z=   (once a vehicle a minute)
class ZCR_CrewStays
{
	protected static ref map<IEntity, bool> s_mArmed = new map<IEntity, bool>();
	protected static ref map<IEntity, int> s_mLogged = new map<IEntity, int>();
	protected static int s_iOff = -1;

	static bool Keep(IEntity soldier, IEntity vehicle)
	{
		if (s_iOff < 0)
		{
			s_iOff = 0;
			if (System.IsCLIParam("zcrCrewsLeave"))
				s_iOff = 1;
		}
		if (s_iOff == 1 || !soldier || !vehicle)
			return false;
		ChimeraCharacter man = ChimeraCharacter.Cast(soldier);
		if (!man || !man.IsInVehicle())
			return false;
		CompartmentAccessComponent access = man.GetCompartmentAccessComponent();
		if (!access || !access.GetCompartment())
			return false;
		ECompartmentType seat = access.GetCompartment().GetType();
		if (seat != ECompartmentType.PILOT && seat != ECompartmentType.TURRET)
			return false;
		IEntity root = vehicle.GetRootParent();
		if (!root)
			root = vehicle;
		if (!Armed(root))
			return false;
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(root.FindComponent(SCR_DamageManagerComponent));
		if (!damage || damage.IsDestroyed() || damage.GetHealthScaled() < 0.35)
			return false;
		int now = ZCR_LossLog.Seconds();
		int last;
		if (!s_mLogged.Find(root, last) || now - last >= 60)
		{
			s_mLogged.Set(root, now);
			vector at = root.GetOrigin();
			Print(string.Format("[ZCR][CREWSTAYS] t=%1 vehicle=%2 seat=%3 health=%4 x=%5 z=%6", now, ZCR_LossLog.ShortName(root),
				typename.EnumToString(ECompartmentType, seat), Math.Round(damage.GetHealthScaled() * 100), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
		}
		return true;
	}

	// A whole group ordered out of an armed, intact vehicle (the failed-move case).
	static bool HoldGroup(IEntity vehicle)
	{
		if (s_iOff < 0)
		{
			s_iOff = 0;
			if (System.IsCLIParam("zcrCrewsLeave"))
				s_iOff = 1;
		}
		if (s_iOff == 1 || !vehicle)
			return false;
		IEntity root = vehicle.GetRootParent();
		if (!root)
			root = vehicle;
		if (!Armed(root))
			return false;
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(root.FindComponent(SCR_DamageManagerComponent));
		if (!damage || damage.IsDestroyed() || damage.GetHealthScaled() < 0.35)
			return false;
		int now = ZCR_LossLog.Seconds();
		int last;
		if (!s_mLogged.Find(root, last) || now - last >= 60)
		{
			s_mLogged.Set(root, now);
			vector at = root.GetOrigin();
			Print(string.Format("[ZCR][CREWSTAYS] t=%1 vehicle=%2 seat=GROUP health=%3 x=%4 z=%5", now, ZCR_LossLog.ShortName(root),
				Math.Round(damage.GetHealthScaled() * 100), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
		}
		return true;
	}

	// A fighting vehicle: a turret seat, not a static weapon.
	static bool Armed(IEntity vehicle)
	{
		bool armed;
		if (s_mArmed.Find(vehicle, armed))
			return armed;
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(vehicle.FindComponent(SCR_AIVehicleUsageComponent));
		if (usage && usage.GetVehicleType() == EAIVehicleType.STATIC_WEAPON)
		{
			s_mArmed.Set(vehicle, false);
			return false;
		}
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(vehicle, seats);
		foreach (BaseCompartmentSlot s : seats)
		{
			if (s && s.GetType() == ECompartmentType.TURRET)
			{
				armed = true;
				break;
			}
		}
		s_mArmed.Set(vehicle, armed);
		return armed;
	}
}
