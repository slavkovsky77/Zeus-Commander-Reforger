// Crossing paths (23 Oct, Martin watching the supply run: "these trucks kind of crashed into each other where they met on
// a crossroad"): the oncoming rule only sees a car coming straight at it on the same line (8 m either side), so trucks
// meeting at the junction and round the bend at (2515, 1580-1690) on Arland were noticed 9-26 m apart - three hits in
// that watched run.
// Every half second: two AI-driven vehicles (not our armour), both over 8 km/h, within 70 m, heading more than 30 degrees
// apart (closer to the same line is the oncoming and spacing rules' business), whose straight lines cross ahead of both
// within 50 m, reaching that point within 3 s of each other -> the one that gets there later stops (the "crossing" cap,
// 0 km/h, through ZCR_Traffic's arbiter) until the other is 6 m past the point, or 70 m away, or 8 s have gone; then its
// own speed again, and the pair isn't stopped again for 10 s.
//   [ZCR][CROSSING] t= side= vehicle= other= m= other_m= dt= kmh= other_kmh= x= z=     (gives way: m to the crossing)
//   [ZCR][CROSSING] t= side= vehicle= event=go wait_s= why=passed|far|gone|timeout
//   [ZCR][CROSSING_SUM] t= give_ways= passed= timeouts=                              (every 60 s, totals)
// OFF by default since 23 Oct 19:40 (-zcrCrossing on): measured on the supply route (6 trucks, 10 min) it made things
// worse - car-on-car hits 2, 2, 2 in three runs against 2, 0, 0, 0, 0 without it (trucks stopping at bad spots); the
// junction slow-down (ZCR_Junction) is the junction rule now.
class ZCR_Crossing
{
	static const float SEE_M = 70;
	static const float AHEAD_M = 50;
	static const float MIN_KMH = 8;
	static const float SAME_LINE = 0.87;   // |cos| of the headings above this: (nearly) the same line
	static const float WINDOW_S = 3;
	static const int MAX_WAIT_S = 8;
	static const int AGAIN_S = 10;
	static const float PAST_M = 6;

	protected static ref ZCR_Crossing s_Instance;
	protected static ref map<IEntity, IEntity> s_mFor = new map<IEntity, IEntity>();   // waiting vehicle -> the one it lets by
	protected static ref map<IEntity, vector> s_mPoint = new map<IEntity, vector>();
	protected static ref map<IEntity, int> s_mSince = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mDoneAt = new map<IEntity, int>();
	protected int m_iNextSum = 60;
	protected int m_iGiveWays;
	protected int m_iPassed;
	protected int m_iTimeouts;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || !System.IsCLIParam("zcrCrossing") || System.IsCLIParam("zcrNoCrossing"))
			return;
		s_Instance = new ZCR_Crossing();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 500, true);
	}

	static bool Waiting(IEntity v)
	{
		return s_mFor.Contains(v);
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

	// How far along each heading their lines meet (pa + ha * sa = pb + hb * sb, on the ground); false when parallel.
	protected static bool Cross(vector pa, vector ha, vector pb, vector hb, out float sa, out float sb)
	{
		float den = ha[0] * hb[2] - ha[2] * hb[0];
		if (Math.AbsFloat(den) < 0.05)
			return false;
		float dx = pb[0] - pa[0];
		float dz = pb[2] - pa[2];
		sa = (dx * hb[2] - dz * hb[0]) / den;
		sb = (dx * ha[2] - dz * ha[0]) / den;
		return true;
	}

	// How far b is to the side of a's line of travel.
	protected static float Lateral(IEntity a, IEntity b)
	{
		vector ha = Heading(a);
		vector rel = b.GetOrigin() - a.GetOrigin();
		rel[1] = 0;
		return (rel - ha * vector.Dot(rel, ha)).Length();
	}

	// v is PAST_M beyond the point along its heading.
	protected static bool Past(IEntity v, vector point)
	{
		vector rel = point - v.GetOrigin();
		rel[1] = 0;
		return vector.Dot(rel, Heading(v)) < -PAST_M;
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("crossing");   // ZCR_Cost: our scripts' share of the frame time
		int now = ZCR_LossLog.Seconds();
		// Ends first.
		array<IEntity> done = {};
		array<string> whys = {};
		foreach (IEntity v, IEntity other : s_mFor)
		{
			string why;
			if (!v || !other)
				why = "gone";
			else if (vector.DistanceXZ(v.GetOrigin(), other.GetOrigin()) > SEE_M)
				why = "far";
			else if (Past(other, s_mPoint.Get(v)))
				why = "passed";
			else if (now - s_mSince.Get(v) >= MAX_WAIT_S)
				why = "timeout";
			if (!why.IsEmpty())
			{
				done.Insert(v);
				whys.Insert(why);
			}
		}
		for (int d; d < done.Count(); d++)
		{
			IEntity v = done[d];
			if (v)
			{
				ZCR_Traffic.Release(v, "crossing");
				s_mDoneAt.Set(v, now);
				Print(string.Format("[ZCR][CROSSING] t=%1 side=%2 vehicle=%3 event=go wait_s=%4 why=%5", now, ZCR_LossLog.SideOf(v), ZCR_LossLog.ShortName(v),
					now - s_mSince.Get(v), whys[d]), LogLevel.NORMAL);
			}
			if (whys[d] == "timeout")
				m_iTimeouts++;
			else if (whys[d] == "passed")
				m_iPassed++;
			s_mFor.Remove(v);
			s_mPoint.Remove(v);
			s_mSince.Remove(v);
		}
		// New pairs.
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		for (int i = 0; i < cars.Count(); i++)
		{
			IEntity a = cars[i];
			if (!a || ZCR_Armour.IsUnit(a) || s_mFor.Contains(a))
				continue;
			float ka = Kmh(a);
			if (ka < MIN_KMH)
				continue;
			for (int k = i + 1; k < cars.Count(); k++)
			{
				IEntity b = cars[k];
				if (!b || ZCR_Armour.IsUnit(b) || s_mFor.Contains(b) || s_mFor.Contains(a))
					continue;
				float kb = Kmh(b);
				if (kb < MIN_KMH || vector.DistanceXZ(a.GetOrigin(), b.GetOrigin()) > SEE_M)
					continue;
				vector ha = Heading(a);
				vector hb = Heading(b);
				if (Math.AbsFloat(vector.Dot(ha, hb)) > SAME_LINE)
					continue;
				// One following the other round a bend (the one ahead already turning): the spacing rule's.
				if (vector.Dot(ha, hb) > 0.5 && (Lateral(a, b) < 6 || Lateral(b, a) < 6))
					continue;
				float sa, sb;
				if (!Cross(a.GetOrigin(), ha, b.GetOrigin(), hb, sa, sb))
					continue;
				if (sa < 0 || sb < 0 || sa > AHEAD_M || sb > AHEAD_M)
					continue;
				float ta = sa / (ka / 3.6);
				float tb = sb / (kb / 3.6);
				if (Math.AbsFloat(ta - tb) > WINDOW_S)
					continue;
				vector point = a.GetOrigin() + ha * sa;
				if (ta > tb)
					GiveWay(a, b, point, now, sa, sb, ta - tb);
				else
					GiveWay(b, a, point, now, sb, sa, tb - ta);
			}
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 60;
			Print(string.Format("[ZCR][CROSSING_SUM] t=%1 give_ways=%2 passed=%3 timeouts=%4", now, m_iGiveWays, m_iPassed, m_iTimeouts), LogLevel.NORMAL);
		}
	}

	protected void GiveWay(IEntity v, IEntity other, vector point, int now, float m, float otherM, float dt)
	{
		int doneAt;
		if (s_mDoneAt.Find(v, doneAt) && now - doneAt < AGAIN_S)
			return;
		if (!ZCR_Traffic.Limit(v, "crossing", 0))
			return;
		s_mFor.Set(v, other);
		s_mPoint.Set(v, point);
		s_mSince.Set(v, now);
		m_iGiveWays++;
		string otherSide = ZCR_LossLog.SideOf(other);
		if (otherSide.IsEmpty())
			otherSide = "none";
		vector at = v.GetOrigin();
		Print(string.Format("[ZCR][CROSSING] t=%1 side=%2 vehicle=%3 other=%4 other_side=%5 m=%6 other_m=%7 dt=%8 kmh=%9", now, ZCR_LossLog.SideOf(v),
			ZCR_LossLog.ShortName(v), ZCR_LossLog.ShortName(other), otherSide, Math.Round(m), Math.Round(otherM), Math.Round(dt * 10) / 10,
			Math.Round(Kmh(v))) + string.Format(" other_kmh=%1 x=%2 z=%3", Math.Round(Kmh(other)), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
	}
}
