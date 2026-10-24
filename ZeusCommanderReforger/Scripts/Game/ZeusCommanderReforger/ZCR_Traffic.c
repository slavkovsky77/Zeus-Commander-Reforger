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
//   lab      - -zcrCruiseSpeed N (the lab's speed cap).
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
	protected int m_iNextLog = 60;
	protected int m_iStops;
	protected int m_iCrawls;
	protected int m_iOncoming;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || System.IsCLIParam("zcrNoTraffic"))
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
		if (!System.IsCLIParam("zcrNoSpacing"))
			Spacing(cars, now);
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
			Print(string.Format("[ZCR][TRAFFIC] t=%1 cars=%2 limited=%3 stops=%4 crawls=%5 oncoming=%6", now, cars.Count(), s_mApplied.Count(),
				m_iStops, m_iCrawls, m_iOncoming), LogLevel.NORMAL);
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
