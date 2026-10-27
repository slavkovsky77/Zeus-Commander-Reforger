// Martin's wish (27 Oct 02:40, review note 421): "get out should not be exactly at the same time depending on vehicle -
// cars all can get out at once, APC? ... maybe one by one, as they have one exit". The game's group get-out (the GetOut
// waypoint AI Conflict gives a team at its drop point) orders everyone out at once. Here the soldiers in the back of an
// APC leave one after the other GAP_APC s apart and a truck's GAP_TRUCK s apart; a car's all at once. Each vehicle
// keeps its next free exit time (the orders reach the soldiers at different moments, so a rank by occupied seats
// repeated once the first was out - 04:12 test).
// The driver and gunner are left as they are (armed vehicles keep their crew - ZCR_CrewStays). A delay the game set
// itself (its combat dismount: 0.9 s a soldier) is kept. -zcrGetOutOrder on (off until Martin has seen it in the window).
class ZCR_GetOutOrder
{
	static const float GAP_APC = 1.6;
	static const float GAP_TRUCK = 0.7;
	protected static int s_iOn = -1;
	protected static ref map<IEntity, float> s_mNextExit = new map<IEntity, float>();

	static bool On()
	{
		if (s_iOn < 0)
		{
			s_iOn = 0;
			if (System.IsCLIParam("zcrGetOutOrder"))
				s_iOn = 1;
		}
		return s_iOn == 1;
	}

	static float Gap(IEntity vehicle)
	{
		if (!vehicle || !vehicle.GetPrefabData())
			return 0;
		string name = vehicle.GetPrefabData().GetPrefabName();
		if (name.Contains("LAV25") || name.Contains("BTR") || name.Contains("BMP") || name.Contains("M113") || name.Contains("MTLB") ||
			name.Contains("BRDM") || name.Contains("Stryker") || name.Contains("Bradley"))
			return GAP_APC;
		if (name.Contains("M923") || name.Contains("M939") || name.Contains("Ural") || name.Contains("Zil") || name.Contains("Kamaz") ||
			name.Contains("Truck"))
			return GAP_TRUCK;
		return 0;
	}

	// This soldier's get-out delay: the vehicle's next free exit, then the one after is GAP later.
	static float Delay(SCR_AIUtilityComponent utility, IEntity vehicle, float delay)
	{
		if (delay > 0 || !utility || !vehicle || !On())
			return delay;
		float gap = Gap(vehicle);
		if (gap <= 0)
			return delay;
		ChimeraCharacter man = ChimeraCharacter.Cast(utility.m_OwnerEntity);
		if (!man || !man.GetCompartmentAccessComponent())
			return delay;
		BaseCompartmentSlot mine = man.GetCompartmentAccessComponent().GetCompartment();
		if (!mine || mine.GetType() != ECompartmentType.CARGO)
			return delay;
		float now = GetGame().GetWorld().GetWorldTime() / 1000;
		float next;
		s_mNextExit.Find(vehicle, next);
		float wait = Math.Max(0, next - now);
		s_mNextExit.Set(vehicle, now + wait + gap);
		Print(string.Format("[ZCR][GETOUTORDER] t=%1 man=%2 vehicle=%3 delay=%4", ZCR_LossLog.Seconds(), ZCR_LossLog.ShortName(man),
			ZCR_LossLog.ShortName(vehicle), Math.Round(wait * 10) / 10), LogLevel.NORMAL);
		return wait;
	}
}
