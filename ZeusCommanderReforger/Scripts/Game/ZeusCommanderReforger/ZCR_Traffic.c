// ZCR Traffic (23 Oct 2026, Martin: "write the first version of our vehicle mod"): the traffic manager that supervises
// the game's AI drivers. The engine's driver can't be replaced (docs/vehicles/engine.md); what works is the cruise speed,
// so every rule that wants a vehicle slower asks here and the vehicle gets the lowest request - no two rules fighting
// over SetCruiseSpeed any more. Rules in this version:
//   spacing  - no rear-ending: the gap to the same side's driven vehicle ahead in the lane sets the speed (the technique
//              of Advanced AI Command's convoy spacing governor, HOLLOWxPOINT - our own code): under 9 m, or a standing
//              one under 16 m: stop; under 16 m: 12 km/h; under 28 m: the one ahead's speed; under 45 m: a little faster
//              to close up; beyond: free. A stop held 10 s becomes a 6 km/h creep, so the engine's own avoidance can
//              steer round and nobody waits forever.
//   oncoming - ZCR_Oncoming's 15 km/h for a vehicle coming the other way.
//   dodge    - ZCR_Dodge: of two drivers dodging each other, one holds still (0) while the other goes.
//   lab      - -zcrCruiseSpeed N (the lab's speed cap).
//   boarding - (2 Nov, notes 487/488/492 - Martin, watching: "team3 is driving into house", "a0 is stuck driving into
//              house"): a vehicle holds still while its driver's team has no waypoint (AI Conflict's boarding, the
//              drop-off) and a living member within 100 m is not aboard. The driver used to drive towards his team
//              meanwhile, and at Moss Hill, the team standing on the far side of a farmhouse, into the house (3 of 3 from
//              that spot, each ride lost). -zcrNoBoardHold: off. 2 Nov, note 505: in AI Conflict's boarding step at any
//              distance (-zcrBoardHoldNear: 100 m as before), and held with no drive to the wheels - a cruise speed of 0
//              still let the driver creep at 5-6 km/h (-zcrNoBoardGear: the cruise speed only).
//   [ZCR][BOARDHOLD] t= vehicle= step= held= kmh= cruise= far_m= out= gear= x= z=  (a vehicle over 4 km/h while its team boards)
// Not our armour (its guard sets its speed) and not a vehicle under a push. Four times a second.
//   [ZCR][SPACING] t= side= vehicle= ahead= gap_m= band= kmh= ahead_kmh= x= z=   (a vehicle enters stop / crawl / creep; 10 s a vehicle)
//   [ZCR][TRAFFIC] t= cars= limited= stops= crawls= oncoming=                  (every 60 s; counts since the last line)
// -zcrNoTraffic: off (the rules set speeds themselves); -zcrNoSpacing: the spacing rule off.
class ZCR_Traffic
{
	static const int TICK_MS = 250;
	static const float STOP_M = 9;
	static const float CRAWL_M = 16;
	static const float MATCH_M = 28;
	static const float FREE_M = 45;
	static const float LANE_M = 4;
	static const float CRAWL_KMH = 12;
	static const float CREEP_KMH = 6;
	static const int HOLD_S = 10;
	static const float STOPPED_KMH = 3.6;

	protected static ref ZCR_Traffic s_Instance;
	protected static ref map<IEntity, ref map<string, float>> s_mLimits = new map<IEntity, ref map<string, float>>();
	protected static ref map<IEntity, float> s_mApplied = new map<IEntity, float>();
	protected static ref map<IEntity, int> s_mStopSince = new map<IEntity, int>();
	protected static ref map<IEntity, string> s_mBand = new map<IEntity, string>();
	protected static ref map<IEntity, int> s_mLogAt = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mBoardHeld = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mBoardLogAt = new map<IEntity, int>();
	protected static ref map<IEntity, float> s_mGearHeld = new map<IEntity, float>();
	protected static ref map<IEntity, ref array<string>> s_mHoldRules = new map<IEntity, ref array<string>>();   // Hold's rules per vehicle
	protected int m_iNextLog = 60;
	protected int m_iBoardHolds;
	protected int m_iBoardMoving;
	protected int m_iStops;
	protected int m_iCrawls;
	protected int m_iOncoming;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || AICF_Launch.Has("zcrNoTraffic"))
			return;
		s_Instance = new ZCR_Traffic();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, TICK_MS, true);
	}

	static bool Active()
	{
		return s_Instance != null;
	}

	// A rule asks for a speed cap on a vehicle; the lowest request of all rules is applied. False: no AI car component.
	// Without the manager (-zcrNoTraffic) the cap is set directly.
	static bool Limit(IEntity v, string rule, float kmh)
	{
		if (!v)
			return false;
		AICarMovementComponent car = AICarMovementComponent.Cast(v.FindComponent(AICarMovementComponent));
		if (!car)
			return false;
		if (!s_Instance)
		{
			car.SetCruiseSpeed(kmh);
			return true;
		}
		map<string, float> rules = s_mLimits.Get(v);
		if (!rules)
		{
			rules = new map<string, float>();
			s_mLimits.Set(v, rules);
		}
		float had;
		bool again = rules.Find(rule, had);
		rules.Set(rule, kmh);
		if (rule == "oncoming" && !again)
			s_Instance.m_iOncoming++;
		return true;
	}

	// A rule holds a vehicle still: cruise 0 and no drive to the wheels (Gear - a cruise speed of 0 alone still creeps at
	// 5-6 km/h). ZCR_OneLane (3 Nov). Unhold gives it back - the gearbox once no rule and no boarding holds it.
	static void Hold(IEntity v, string rule)
	{
		if (!v)
			return;
		Limit(v, rule, 0);
		array<string> rules = s_mHoldRules.Get(v);
		if (!rules)
		{
			rules = {};
			s_mHoldRules.Set(v, rules);
		}
		if (rules.Find(rule) < 0)
			rules.Insert(rule);
		Gear(v, true);
	}

	static void Unhold(IEntity v, string rule)
	{
		if (!v)
			return;
		Release(v, rule);
		array<string> rules = s_mHoldRules.Get(v);
		if (rules)
		{
			rules.RemoveItem(rule);
			if (rules.IsEmpty())
				s_mHoldRules.Remove(v);
		}
		if (!s_mHoldRules.Contains(v) && !s_mBoardHeld.Contains(v))
			Gear(v, false);
	}

	static void Release(IEntity v, string rule)
	{
		if (!v)
			return;
		if (!s_Instance)
		{
			AICarMovementComponent car = AICarMovementComponent.Cast(v.FindComponent(AICarMovementComponent));
			if (car)
				car.ResetCruiseSpeed();
			return;
		}
		map<string, float> rules = s_mLimits.Get(v);
		if (rules)
			rules.Remove(rule);
	}

	protected static float Kmh(IEntity v)
	{
		Physics p = v.GetPhysics();
		if (!p)
			return 0;
		return p.GetVelocity().Length() * 3.6;
	}

	protected static vector Heading(IEntity v)
	{
		vector f = v.GetTransformAxis(2);
		f[1] = 0;
		f.Normalize();
		return f;
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("traffic");   // ZCR_Cost: our scripts' share of the frame time
		int now = ZCR_LossLog.Seconds();
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		if (!AICF_Launch.Has("zcrNoSpacing"))
			Spacing(cars, now);
		ZCR_Dodge.Tick(cars, now);          // two drivers dodging each other: one gives way (24 Oct, report 27)
		if (!AICF_Launch.Has("zcrNoBoardHold"))
			BoardHold(cars);
		float lab = ZCR_Driving.CruiseLimit();
		if (lab > 0)
		{
			foreach (IEntity c : cars)
			{
				if (c && !ZCR_Armour.IsUnit(c))
					Limit(c, "lab", lab);
			}
		}
		Apply(cars);
		if (now >= m_iNextLog)
		{
			m_iNextLog = now + 60;
			Print(string.Format("[ZCR][TRAFFIC] t=%1 cars=%2 limited=%3 stops=%4 crawls=%5 oncoming=%6 board_holds=%7 board_moving=%8", now, cars.Count(),
				s_mApplied.Count(), m_iStops, m_iCrawls, m_iOncoming, m_iBoardHolds, m_iBoardMoving), LogLevel.NORMAL);
			m_iBoardHolds = 0;
			m_iBoardMoving = 0;
			m_iStops = 0;
			m_iCrawls = 0;
			m_iOncoming = 0;
		}
	}

	// The spacing rule: the nearest driven vehicle of the same side ahead in the lane, going our way or standing.
	protected void Spacing(array<IEntity> cars, int now)
	{
		foreach (IEntity a : cars)
		{
			if (!a)
				continue;
			if (ZCR_Armour.IsUnit(a) || ZCR_Push.Busy(a))
			{
				Clear(a);
				continue;
			}
			vector pa = a.GetOrigin();
			vector fa = Heading(a);
			string side = ZCR_Driving.DrivenSide(a);
			IEntity ahead;
			float gap = FREE_M;
			float aheadKmh;
			foreach (IEntity b : cars)
			{
				if (!b || b == a || ZCR_Driving.DrivenSide(b) != side)
					continue;
				if (ZCR_Dodge.IsYielding(b))
					continue;                  // giving way to us (ZCR_Dodge): no stop for it
				vector rel = b.GetOrigin() - pa;
				rel[1] = 0;
				float along = vector.Dot(rel, fa);
				if (along <= 0 || along >= gap)
					continue;
				if ((rel - fa * along).Length() > LANE_M)
					continue;
				float bKmh = Kmh(b);
				// Moving the other way: the oncoming rule's business.
				if (bKmh > STOPPED_KMH && vector.Dot(Heading(b), fa) < 0.5)
					continue;
				gap = along;
				ahead = b;
				aheadKmh = bKmh;
			}
			if (!ahead)
			{
				Clear(a);
				continue;
			}
			bool aheadStopped = aheadKmh < STOPPED_KMH;
			string band;
			float kmh;
			if (gap < STOP_M || (aheadStopped && gap < CRAWL_M))
			{
				band = "stop";
				kmh = 0;
			}
			else if (gap < CRAWL_M)
			{
				band = "crawl";
				kmh = CRAWL_KMH;
			}
			else if (gap < MATCH_M)
			{
				band = "match";
				kmh = Math.Max(aheadKmh, CRAWL_KMH);
			}
			else
			{
				band = "close";
				kmh = Math.Max(aheadKmh + 8, 20);
			}
			if (band == "stop")
			{
				int since;
				if (!s_mStopSince.Find(a, since))
				{
					since = now;
					s_mStopSince.Set(a, now);
				}
				if (now - since >= HOLD_S)
				{
					band = "creep";
					kmh = CREEP_KMH;
				}
			}
			else
				s_mStopSince.Remove(a);
			Limit(a, "spacing", kmh);
			if (s_mBand.Get(a) == band)
				continue;
			s_mBand.Set(a, band);
			if (band == "stop")
				m_iStops++;
			else if (band == "crawl")
				m_iCrawls++;
			if ((band == "stop" || band == "crawl" || band == "creep") && now - s_mLogAt.Get(a) >= 10)
			{
				s_mLogAt.Set(a, now);
				Print(string.Format("[ZCR][SPACING] t=%1 side=%2 vehicle=%3 ahead=%4 gap_m=%5 band=%6 kmh=%7 ahead_kmh=%8 x=%9", now, side,
					ZCR_LossLog.ShortName(a), ZCR_LossLog.ShortName(ahead), Math.Round(gap), band, Math.Round(kmh), Math.Round(aheadKmh),
					Math.Round(pa[0])) + string.Format(" z=%1", Math.Round(pa[2])), LogLevel.NORMAL);
			}
		}
	}

	// The boarding rule (see the top): 0 km/h while the driver's team, with no waypoint, still has a man outside nearby.
	protected void BoardHold(array<IEntity> cars)
	{
		foreach (IEntity v : cars)
		{
			if (!v)
				continue;
			bool hold;
			SCR_AIGroup group;
			if (!ZCR_Armour.IsUnit(v))
				group = DriverGroupOf(v);
			// 2 Nov, note 502: also while AI Conflict's ride is boarding with the team's walking order still current - a driver
			// drove off at up to 61 km/h with the last man outside, and the ride was lost.
			string step;
			if (group)
				step = AICF_VehicleCoordinator.ZcrRideStep(SlotOf(group));
			bool boarding = group && !group.GetCurrentWaypoint();
			if (group && !boarding)
				boarding = step == "BOARDING" || step == "SPAWN_COMMIT" || step == "DISMOUNT";
			// 2 Nov, note 504: in AI Conflict's boarding step the hold no longer ends at 100 m - Soviet jeeps drove off towards
			// a last man further out, and his seat fallback can't act on a moving vehicle (400-900 deferrals a run).
			bool anyDistance = (step == "BOARDING" || step == "SPAWN_COMMIT") && !AICF_Launch.Has("zcrBoardHoldNear");
			float far = -1;
			int outside;
			if (boarding)
			{
				array<AIAgent> agents = {};
				group.GetAgents(agents);
				foreach (AIAgent agent : agents)
				{
					if (!agent)
						continue;
					IEntity man = agent.GetControlledEntity();
					if (!man || !AICF_GroupRuntime.IsAliveCharacter(man) || CompartmentAccessComponent.GetVehicleIn(man) == v)
						continue;
					outside++;
					float d = vector.DistanceXZ(man.GetOrigin(), v.GetOrigin());
					far = Math.Max(far, d);
					if (d <= 100 || anyDistance)
						hold = true;
				}
			}
			bool held = s_mBoardHeld.Contains(v);
			if (hold)
			{
				Limit(v, "boarding", 0);
				if (!held)
				{
					s_mBoardHeld.Set(v, ZCR_LossLog.Seconds());
					m_iBoardHolds++;
				}
				Gear(v, true);
			}
			else if (held)
			{
				Release(v, "boarding");
				s_mBoardHeld.Remove(v);
				if (!s_mHoldRules.Contains(v))
					Gear(v, false);
			}
			if (boarding && outside > 0)
				BoardMoving(v, step, hold, far, outside);
		}
		// A held vehicle no longer driven (the driver got out, the vehicle gone) gets its gearbox back.
		array<IEntity> drop = {};
		foreach (IEntity hv, float was : s_mGearHeld)
		{
			if (!hv || cars.Find(hv) < 0)
				drop.Insert(hv);
		}
		foreach (IEntity d : drop)
		{
			s_mHoldRules.Remove(d);
			if (d)
				Gear(d, false);
			else
				s_mGearHeld.Remove(d);
		}
	}

	// No drive to the wheels while held: the gearbox efficiency 0, as the game's own cinematics stop a vehicle
	// (VehicleCinematicTrack). The driver overrides both the cruise speed of 0 (held vehicles crept at 5-6 km/h) and the
	// handbrake (released ~200 times a minute) (2 Nov, note 505). Back to the value it had (unless damage changed it meanwhile).
	protected static void Gear(IEntity v, bool on)
	{
		float was;
		bool have = s_mGearHeld.Find(v, was);
		if ((on && AICF_Launch.Has("zcrNoBoardGear")) || (!on && !have))
			return;
		CarControllerComponent car = CarControllerComponent.Cast(v.FindComponent(CarControllerComponent));
		VehicleWheeledSimulation sim;
		if (car)
			sim = car.GetSimulation();
		if (!sim)
		{
			s_mGearHeld.Remove(v);
			return;
		}
		float now = sim.GearboxGetEfficiencyState();
		if (on)
		{
			if (have && now <= 0)
				return;
			s_mGearHeld.Set(v, now);
			sim.GearboxSetEfficiencyState(0);
			return;
		}
		if (now <= 0)
			sim.GearboxSetEfficiencyState(was);
		s_mGearHeld.Remove(v);
	}

	// [ZCR][BOARDHOLD] t= vehicle= step= held= kmh= cruise= far_m= out= gear= x= z= : a vehicle moving over 4 km/h while its team
	// boards, 10 s a vehicle - is it held (and still rolling), or not held at all?
	protected void BoardMoving(IEntity v, string step, bool held, float far, int outside)
	{
		float kmh = Kmh(v);
		if (kmh <= 4)
			return;
		if (held)
			m_iBoardMoving++;
		int now = ZCR_LossLog.Seconds();
		int at;
		if (s_mBoardLogAt.Find(v, at) && now - at < 10)
			return;
		s_mBoardLogAt.Set(v, now);
		float cruise = -1;
		s_mApplied.Find(v, cruise);
		CarControllerComponent car = CarControllerComponent.Cast(v.FindComponent(CarControllerComponent));
		float gear = -1;
		if (car && car.GetSimulation())
			gear = car.GetSimulation().GearboxGetEfficiencyState();
		if (step.IsEmpty())
			step = "NO_WAYPOINT";
		vector p = v.GetOrigin();
		Print(string.Format("[ZCR][BOARDHOLD] t=%1 vehicle=%2 step=%3 held=%4 kmh=%5 cruise=%6 far_m=%7 out=%8", now,
			ZCR_LossLog.ShortName(v), step, held, Math.Round(kmh), cruise, Math.Round(far), outside) +
			string.Format(" gear=%1 x=%2 z=%3", gear, Math.Round(p[0]), Math.Round(p[2])), LogLevel.NORMAL);
	}

	protected static AICF_GroupSlot SlotOf(AIGroup group)
	{
		foreach (FactionKey faction, AICF_FactionState state : ZCR_Strategist.s_mStates)
		{
			for (int s; state && s < state.GetSlotCount(); s++)
			{
				AICF_GroupSlot slot = state.GetSlot(s);
				if (slot && slot.GetGroup() == group)
					return slot;
			}
		}
		return null;
	}

	protected static SCR_AIGroup DriverGroupOf(IEntity vehicle)
	{
		array<BaseCompartmentSlot> seats = {};
		AICF_FIAPatrolCrew.Seats(vehicle, seats);
		foreach (BaseCompartmentSlot seat : seats)
		{
			if (!seat || seat.GetType() != ECompartmentType.PILOT || !seat.GetOccupant())
				continue;
			AIControlComponent control = AIControlComponent.Cast(seat.GetOccupant().FindComponent(AIControlComponent));
			if (!control || !control.GetControlAIAgent())
				return null;
			return SCR_AIGroup.Cast(control.GetControlAIAgent().GetParentGroup());
		}
		return null;
	}

	protected static void Clear(IEntity a)
	{
		Release(a, "spacing");
		s_mStopSince.Remove(a);
		s_mBand.Remove(a);
	}

	// The lowest request per vehicle; a vehicle with no request, or no longer driven, gets the game's own speed back.
	protected void Apply(array<IEntity> cars)
	{
		array<IEntity> gone = {};
		foreach (IEntity v, map<string, float> rules : s_mLimits)
		{
			bool driven = v && cars.Find(v) >= 0;
			float lowest = -1;
			if (driven && rules)
			{
				foreach (string rule, float kmh : rules)
				{
					if (lowest < 0 || kmh < lowest)
						lowest = kmh;
				}
			}
			AICarMovementComponent car;
			if (v)
				car = AICarMovementComponent.Cast(v.FindComponent(AICarMovementComponent));
			if (lowest < 0)
			{
				if (car && s_mApplied.Contains(v))
					car.ResetCruiseSpeed();
				s_mApplied.Remove(v);
				if (!driven)
					gone.Insert(v);
				continue;
			}
			float applied;
			if (car && (!s_mApplied.Find(v, applied) || Math.AbsFloat(applied - lowest) > 0.5))
			{
				car.SetCruiseSpeed(lowest);
				s_mApplied.Set(v, lowest);
			}
		}
		foreach (IEntity g : gone)
		{
			s_mLimits.Remove(g);
			s_mBand.Remove(g);
			s_mStopSince.Remove(g);
			s_mLogAt.Remove(g);
		}
	}
}
