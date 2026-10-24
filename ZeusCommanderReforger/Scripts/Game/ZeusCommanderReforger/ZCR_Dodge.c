// Two drivers dodging each other (24 Oct, report 27 - the Soviet supply vans at the Farm's wall corner: both drivers in the
// game's move-from-incoming-vehicle for 100+ s, each making way for the other, and our spacing rule stopping them; Martin:
// "this is a pretty big issue, let's simulate it in the sub-lab and fix it"). A driver dodging for AFTER_S with another of
// our driven vehicles within NEAR_M: one of the two gives way - the one that has the other in front of it (it would drive
// into it; both - the one facing it more squarely) holds still for YIELD_S (the traffic manager's "dodge" cap at 0) and
// stops dodging; the other stops dodging and drives on along its route. The spacing rule doesn't stop anyone for a vehicle
// that is giving way (ZCR_Traffic). Once a second from the traffic manager; -zcrNoDodge off.
//   [ZCR][DODGE] t= side= passer= yielder= dodge_s= gap_m= x= z=      and every 60 s: t= broken= dodging=
class ZCR_Dodge
{
	static const float NEAR_M = 25;
	static const int AFTER_S = 4;
	static const int YIELD_S = 12;
	protected static ref map<IEntity, int> s_mDodgeSince = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mYieldUntil = new map<IEntity, int>();
	protected static int s_iLastTick = -1;
	protected static int s_iNextLog = 60;
	protected static int s_iBroken;

	static bool IsYielding(IEntity v)
	{
		int until;
		return v && s_mYieldUntil.Find(v, until) && ZCR_LossLog.Seconds() < until;
	}

	static void Tick(array<IEntity> cars, int now)
	{
		if (now == s_iLastTick || System.IsCLIParam("zcrNoDodge"))
			return;
		s_iLastTick = now;
		// Give-ways that are over.
		array<IEntity> done = {};
		foreach (IEntity v, int until : s_mYieldUntil)
		{
			if (!v || now >= until)
				done.Insert(v);
		}
		foreach (IEntity v : done)
		{
			s_mYieldUntil.Remove(v);
			if (v)
				ZCR_Traffic.Release(v, "dodge");
		}
		int dodging;
		foreach (IEntity a : cars)
		{
			if (!a || ZCR_Armour.IsUnit(a))
				continue;
			SCR_AIUtilityComponent ua = Driver(a);
			if (!Dodging(ua))
			{
				s_mDodgeSince.Remove(a);
				continue;
			}
			dodging++;
			if (!s_mDodgeSince.Contains(a))
			{
				s_mDodgeSince.Set(a, now);
				continue;
			}
			if (now - s_mDodgeSince.Get(a) < AFTER_S || IsYielding(a))
				continue;
			// The other one: the nearest driven vehicle within NEAR_M.
			IEntity b;
			float best = NEAR_M;
			foreach (IEntity c : cars)
			{
				if (!c || c == a)
					continue;
				float d = vector.DistanceXZ(a.GetOrigin(), c.GetOrigin());
				if (d < best)
				{
					best = d;
					b = c;
				}
			}
			if (!b || IsYielding(b))
				continue;
			// Who gives way: the one with the other in front of it.
			vector ab = b.GetOrigin() - a.GetOrigin();
			ab[1] = 0;
			ab.Normalize();
			float aFaces = vector.Dot(Heading(a), ab);
			float bFaces = vector.Dot(Heading(b), -ab);
			IEntity yielder = a;
			IEntity passer = b;
			if (bFaces > aFaces)
			{
				yielder = b;
				passer = a;
			}
			s_mYieldUntil.Set(yielder, now + YIELD_S);
			ZCR_Traffic.Limit(yielder, "dodge", 0);
			StopDodging(Driver(yielder));
			StopDodging(Driver(passer));
			s_mDodgeSince.Remove(a);
			s_mDodgeSince.Remove(b);
			s_iBroken++;
			vector at = a.GetOrigin();
			Print(string.Format("[ZCR][DODGE] t=%1 side=%2 passer=%3 yielder=%4 dodge_s=%5 gap_m=%6 x=%7 z=%8", now, ZCR_Driving.DrivenSide(passer),
				ZCR_LossLog.ShortName(passer), ZCR_LossLog.ShortName(yielder), now - s_mDodgeSince.Get(a), Math.Round(best), Math.Round(at[0]),
				Math.Round(at[2])), LogLevel.NORMAL);
		}
		if (now >= s_iNextLog)
		{
			s_iNextLog = now + 60;
			if (s_iBroken > 0 || dodging > 0)
				Print(string.Format("[ZCR][DODGE] t=%1 broken=%2 dodging=%3", now, s_iBroken, dodging), LogLevel.NORMAL);
			s_iBroken = 0;
		}
	}

	// The vehicle's driver's AI (the pilot's seat).
	protected static SCR_AIUtilityComponent Driver(IEntity v)
	{
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(v, seats);
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (!seat || seat.GetType() != ECompartmentType.PILOT || !seat.GetOccupant())
				continue;
			AIControlComponent control = AIControlComponent.Cast(seat.GetOccupant().FindComponent(AIControlComponent));
			if (!control || !control.GetControlAIAgent())
				return null;
			return SCR_AIUtilityComponent.Cast(control.GetControlAIAgent().FindComponent(SCR_AIUtilityComponent));
		}
		return null;
	}

	protected static bool Dodging(SCR_AIUtilityComponent u)
	{
		return u && u.GetCurrentAction() && u.GetCurrentAction().ClassName() == "SCR_AIPilotMoveFromIncomingVehicleBehavior";
	}

	protected static void StopDodging(SCR_AIUtilityComponent u)
	{
		if (Dodging(u))
			u.GetCurrentAction().Fail();
	}

	protected static vector Heading(IEntity v)
	{
		vector f = v.GetTransformAxis(2);
		f[1] = 0;
		f.Normalize();
		return f;
	}
}
