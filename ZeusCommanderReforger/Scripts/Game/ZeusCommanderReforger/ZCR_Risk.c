// Collision risk (23 Oct 2026, Martin: "slow down if there is a collision course - track what happens, predict whether
// there will be a collision, slow down until the probability drops"). One rule for head-on, crossing and rear-end:
//   track    - each AI-driven vehicle's position, speed and heading four times a second; from the last 3 s its turn rate,
//              its speed change and how much both wobble (the AI driver's steering noise - more at the 3x speed-up);
//   predict  - for each nearby pair, 24 futures over the next 4 s with the turn rate and speed drawn from what each
//              vehicle has really been doing; the share of futures where they come within touching distance is the risk;
//   slow     - a vehicle tries 100%, 70%, 40%, 15 km/h, 5 km/h and stop for itself, the other carrying on, and takes the
//              fastest speed whose risk stays under 10%; held 1.5 s at least; a stop held 8 s becomes a 5 km/h creep;
//   soldiers - our side's or neutral soldiers ahead are obstacles walking at up to 1.5 m/s in any direction, with a 2%
//              limit (enemies: the game's combat);
// The cap goes through ZCR_Traffic's arbiter ("risk"). Logged for calibration:
//   [ZCR][RISK] t= side= vehicle= id= other= other_id= kind=car|parked|man risk= kmh= free_kmh= dist= x= z=   (a cap starts or changes)
//   [ZCR][FORECAST] t= id= other_id= risk= dist=                                                         (risk >= 5%, a pair once in 2 s)
// On with -zcrRisk (the lab's variant "risk" also turns the oncoming and spacing rules off).
class ZCR_RiskTrack
{
	ref array<vector> m_aPos = {};
	ref array<float> m_aHeading = {};   // radians, around the vertical
	ref array<float> m_aSpeed = {};     // m/s
	float m_fTurn;                      // rad/s
	float m_fTurnNoise;                 // rad/s
	float m_fAccelNoise;                // m/s2
	float m_fRadius;
	int m_iCapAt;
	int m_iStopSince;
}

class ZCR_Risk
{
	static const int TICK_MS = 250;
	static const int HISTORY = 12;          // 3 s at 4 Hz
	static const int SAMPLES = 24;
	static const float HORIZON_S = 4;
	static const float STEP_S = 0.25;
	static const float PAIR_M = 60;
	static const float LIMIT = 0.10;
	static const float MAN_LIMIT = 0.02;
	static const float MAN_M = 40;
	static const float PARKED_M = 40;

	protected static ref ZCR_Risk s_Instance;
	protected static ref map<IEntity, ref ZCR_RiskTrack> s_mTrack = new map<IEntity, ref ZCR_RiskTrack>();
	protected static ref map<string, int> s_mForecastAt = new map<string, int>();
	protected static ref map<IEntity, float> s_mCap = new map<IEntity, float>();

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || !System.IsCLIParam("zcrRisk"))
			return;
		s_Instance = new ZCR_Risk();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, TICK_MS, true);
	}

	protected static float Yaw(IEntity v)
	{
		vector f = v.GetTransformAxis(2);
		return Math.Atan2(f[0], f[2]);
	}

	protected static float AngleDiff(float a, float b)
	{
		float d = a - b;
		while (d > Math.PI)
			d -= 2 * Math.PI;
		while (d < -Math.PI)
			d += 2 * Math.PI;
		return d;
	}

	protected static float Radius(IEntity v)
	{
		vector mins, maxs;
		v.GetBounds(mins, maxs);
		return Math.Max(1.2, 0.5 * Math.Max(maxs[0] - mins[0], maxs[2] - mins[2]) * 0.9);
	}

	// Track: the history and what it says about turning and wobble.
	protected void Observe(IEntity v)
	{
		ZCR_RiskTrack t = s_mTrack.Get(v);
		if (!t)
		{
			t = new ZCR_RiskTrack();
			t.m_fRadius = Radius(v);
			s_mTrack.Set(v, t);
		}
		Physics p = v.GetPhysics();
		float speed = 0;
		if (p)
			speed = p.GetVelocity().Length();
		t.m_aPos.Insert(v.GetOrigin());
		t.m_aHeading.Insert(Yaw(v));
		t.m_aSpeed.Insert(speed);
		while (t.m_aPos.Count() > HISTORY)
		{
			t.m_aPos.RemoveOrdered(0);
			t.m_aHeading.RemoveOrdered(0);
			t.m_aSpeed.RemoveOrdered(0);
		}
		int n = t.m_aHeading.Count();
		if (n < 3)
			return;
		float sum = 0, sum2 = 0, acc2 = 0;
		for (int i = 1; i < n; i++)
		{
			float w = AngleDiff(t.m_aHeading[i], t.m_aHeading[i - 1]) / STEP_S;
			sum += w;
			sum2 += w * w;
			float a = (t.m_aSpeed[i] - t.m_aSpeed[i - 1]) / STEP_S;
			acc2 += a * a;
		}
		float m = n - 1;
		t.m_fTurn = sum / m;
		t.m_fTurnNoise = Math.Max(0.05, Math.Sqrt(Math.Max(0, sum2 / m - t.m_fTurn * t.m_fTurn)));
		t.m_fAccelNoise = Math.Max(0.3, Math.Sqrt(acc2 / m));
	}

	// The share of futures in which a (at speed `as`) and b come within touching distance.
	protected static float Risk(IEntity a, ZCR_RiskTrack ta, float as, IEntity b, ZCR_RiskTrack tb, bool man)
	{
		vector pa = a.GetOrigin();
		vector pb = b.GetOrigin();
		float ha = Yaw(a);
		float hb = 0;
		float sb = 0;
		if (!man)
		{
			hb = Yaw(b);
			if (b.GetPhysics())
				sb = b.GetPhysics().GetVelocity().Length();
		}
		float touch = ta.m_fRadius + 1.0;
		if (man)
			touch = ta.m_fRadius + 0.8;
		else if (tb)
			touch = ta.m_fRadius + tb.m_fRadius;
		int hits = 0;
		int steps = HORIZON_S / STEP_S;
		for (int k = 0; k < SAMPLES; k++)
		{
			float wa = ta.m_fTurn + Math.RandomGaussFloat(0, ta.m_fTurnNoise);
			float aa = Math.RandomGaussFloat(0, ta.m_fAccelNoise);
			float wb = 0, ab = 0, mvx = 0, mvz = 0;
			if (man)
			{
				float dir = Math.RandomFloat(0, 2 * Math.PI);
				float ms = Math.RandomFloat(0, 1.5);
				mvx = Math.Sin(dir) * ms;
				mvz = Math.Cos(dir) * ms;
			}
			else if (tb)
			{
				wb = tb.m_fTurn + Math.RandomGaussFloat(0, tb.m_fTurnNoise);
				ab = Math.RandomGaussFloat(0, tb.m_fAccelNoise);
			}
			float xa = pa[0], za = pa[2], ya = ha, va = as;
			float xb = pb[0], zb = pb[2], yb = hb, vb = sb;
			for (int s = 1; s <= steps; s++)
			{
				va = Math.Max(0, va + aa * STEP_S);
				ya += wa * STEP_S;
				xa += Math.Sin(ya) * va * STEP_S;
				za += Math.Cos(ya) * va * STEP_S;
				if (man)
				{
					xb += mvx * STEP_S;
					zb += mvz * STEP_S;
				}
				else
				{
					vb = Math.Max(0, vb + ab * STEP_S);
					yb += wb * STEP_S;
					xb += Math.Sin(yb) * vb * STEP_S;
					zb += Math.Cos(yb) * vb * STEP_S;
				}
				float dx = xa - xb, dz = za - zb;
				if (dx * dx + dz * dz < touch * touch)
				{
					hits++;
					break;
				}
			}
		}
		return hits / SAMPLES;
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		// Forget vehicles no longer driven.
		array<IEntity> gone = {};
		foreach (IEntity v, ZCR_RiskTrack t : s_mTrack)
		{
			if (!v || cars.Find(v) < 0)
				gone.Insert(v);
		}
		foreach (IEntity g : gone)
		{
			s_mTrack.Remove(g);
			if (g && s_mCap.Contains(g))
				ZCR_Traffic.Release(g, "risk");
			s_mCap.Remove(g);
		}
		foreach (IEntity c : cars)
		{
			if (c && !ZCR_Armour.IsUnit(c))
				Observe(c);
		}
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		foreach (IEntity a : cars)
		{
			if (!a || ZCR_Armour.IsUnit(a) || ZCR_Push.Busy(a))
				continue;
			ZCR_RiskTrack ta = s_mTrack.Get(a);
			if (!ta || ta.m_aSpeed.IsEmpty())
				continue;
			float current = ta.m_aSpeed[ta.m_aSpeed.Count() - 1];
			// The speeds a may take: its own speed (the game's), 70%, 40%, 15 km/h, 5 km/h, stop.
			float free = Math.Max(current, 4);
			array<float> options = {free, free * 0.7, free * 0.4, 15 / 3.6, 5 / 3.6, 0};
			float chosen = free;
			float worst = 0;
			IEntity worstOther;
			string worstKind = "";
			string side = ZCR_Driving.DrivenSide(a);
			// Other driven vehicles.
			foreach (IEntity b : cars)
			{
				if (!b || b == a || vector.DistanceXZ(a.GetOrigin(), b.GetOrigin()) > PAIR_M)
					continue;
				ZCR_RiskTrack tb = s_mTrack.Get(b);
				float rFree = Risk(a, ta, free, b, tb, false);
				Forecast(now, a, b, rFree);
				if (rFree < LIMIT)
					continue;
				float pick = 0;
				foreach (float o : options)
				{
					if (Risk(a, ta, o, b, tb, false) < LIMIT)
					{
						pick = o;
						break;
					}
				}
				if (pick < chosen)
				{
					chosen = pick;
					worst = rFree;
					worstOther = b;
					worstKind = "car";
				}
			}
			// Soldiers of our side or neutral in front within 40 m.
			vector fa = a.GetTransformAxis(2);
			foreach (AIAgent agent : agents)
			{
				ChimeraCharacter man = ChimeraCharacter.Cast(agent.GetControlledEntity());
				if (!man || man.IsInVehicle())
					continue;
				vector rel = man.GetOrigin() - a.GetOrigin();
				rel[1] = 0;
				if (rel.Length() > MAN_M || vector.Dot(rel, fa) <= 0)
					continue;
				string manSide = ZCR_LossLog.SideOf(man);
				if (!manSide.IsEmpty() && manSide != side && !side.IsEmpty())
					continue;
				float rMan = Risk(a, ta, free, man, null, true);
				if (rMan < MAN_LIMIT)
					continue;
				float pickMan = 0;
				foreach (float om : options)
				{
					if (Risk(a, ta, om, man, null, true) < MAN_LIMIT)
					{
						pickMan = om;
						break;
					}
				}
				if (pickMan < chosen)
				{
					chosen = pickMan;
					worst = rMan;
					worstOther = man;
					worstKind = "man";
				}
			}
			Apply(a, ta, now, chosen, free, worst, worstOther, worstKind, side);
		}
	}

	protected static void Forecast(int now, IEntity a, IEntity b, float risk)
	{
		if (risk < 0.05)
			return;
		string key = a.GetID().ToString() + "/" + b.GetID().ToString();
		int last;
		if (s_mForecastAt.Find(key, last) && now - last < 2)
			return;
		s_mForecastAt.Set(key, now);
		Print(string.Format("[ZCR][FORECAST] t=%1 id=%2 other_id=%3 risk=%4 dist=%5", now, a.GetID(), b.GetID(), Math.Round(risk * 100) / 100,
			Math.Round(vector.DistanceXZ(a.GetOrigin(), b.GetOrigin()))), LogLevel.NORMAL);
	}

	protected static void Apply(IEntity a, ZCR_RiskTrack ta, int now, float chosen, float free, float worst, IEntity other, string kind, string side)
	{
		bool capped = s_mCap.Contains(a);
		if (chosen >= free - 0.01)
		{
			// Free again - but a cap is held 1.5 s at least (no flicker).
			if (capped && (now - ta.m_iCapAt) * 1000 >= 1500)
			{
				ZCR_Traffic.Release(a, "risk");
				s_mCap.Remove(a);
				ta.m_iStopSince = -1;
			}
			return;
		}
		float kmh = chosen * 3.6;
		if (kmh < 0.5)
		{
			if (ta.m_iStopSince < 0 || !capped)
				ta.m_iStopSince = now;
			if (now - ta.m_iStopSince >= 8)
				kmh = 5;   // nobody waits forever: creep, the engine's avoidance steers
		}
		else
			ta.m_iStopSince = -1;
		float had;
		bool changed = !s_mCap.Find(a, had) || Math.AbsFloat(had - kmh) > 3;
		ZCR_Traffic.Limit(a, "risk", kmh);
		s_mCap.Set(a, kmh);
		if (!capped)
			ta.m_iCapAt = now;
		if (!changed || !other)
			return;
		vector at = a.GetOrigin();
		Print(string.Format("[ZCR][RISK] t=%1 side=%2 vehicle=%3 id=%4 other=%5 other_id=%6 kind=%7 risk=%8 kmh=%9", now, side, ZCR_LossLog.ShortName(a),
			a.GetID(), ZCR_LossLog.ShortName(other), other.GetID(), kind, Math.Round(worst * 100) / 100, Math.Round(kmh)) +
			string.Format(" free_kmh=%1 dist=%2 x=%3 z=%4", Math.Round(free * 3.6), Math.Round(vector.DistanceXZ(at, other.GetOrigin())), Math.Round(at[0]), Math.Round(at[2])),
			LogLevel.NORMAL);
	}
}
