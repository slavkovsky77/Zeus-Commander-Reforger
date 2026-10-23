// Oncoming traffic (22 Oct, Martin watching the Moss Hill test track: "they still crash into each other"): the game's
// AI drivers don't slow down for a car coming the other way - on a farm lane both keep the middle at ~50 km/h until they
// hit (two head-on crashes in two track runs, both drivers dead each time). No Workshop mod does this either.
// Every half second: two AI-driven vehicles each with the other ahead within 90 m, less than 8 m off its line and
// facing it, at least one of them over 8 km/h (a standing one counts, since 23 Oct 22:00) -> both cruise at 15 km/h (the game's own avoidance steers round at that speed)
// until the other is behind or 100 m away, then the game's own speed again. Not our armour (its guard sets its speed).
// The cap goes through ZCR_Traffic's speed arbiter (the lowest of all rules' requests).
//   [ZCR][ONCOMING] t= side= vehicle= other= other_side= m= kmh= other_kmh= x= z=      (slowing starts)
//   [ZCR][ONCOMING] t= side= vehicle= event=passed slow_s=                             (back to normal)
// -zcrNoOncoming turns it off.
class ZCR_Oncoming
{
	static const float SEE_M = 90;
	static const float LANE_M = 8;
	static const float MIN_KMH = 8;
	static const float SLOW_KMH = 15;
	static const float CLEAR_M = 100;

	protected static ref ZCR_Oncoming s_Instance;
	protected static ref map<IEntity, IEntity> s_mSlowFor = new map<IEntity, IEntity>();   // vehicle -> the one it slows for
	protected static ref map<IEntity, int> s_mSlowAt = new map<IEntity, int>();

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || System.IsCLIParam("zcrNoOncoming"))
			return;
		s_Instance = new ZCR_Oncoming();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 500, true);
	}

	static bool Slowing(IEntity v)
	{
		return s_mSlowFor.Contains(v);
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

	// b is ahead of a within SEE_M, near a's line, and coming towards a.
	protected static bool Towards(IEntity a, IEntity b, out float distance)
	{
		vector fa = Heading(a);
		vector rel = b.GetOrigin() - a.GetOrigin();
		rel[1] = 0;
		float ahead = vector.Dot(rel, fa);
		distance = rel.Length();
		if (ahead <= 0 || ahead > SEE_M)
			return false;
		if ((rel - fa * ahead).Length() > LANE_M)
			return false;
		// b heads back towards a (its heading within ~45 degrees of the way to a).
		vector back = -rel;
		back.Normalize();
		return vector.Dot(Heading(b), back) > 0.7;
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		// Ends first: the other one behind, gone or far away.
		array<IEntity> done = {};
		foreach (IEntity v, IEntity other : s_mSlowFor)
		{
			float d;
			// Passed (the other behind), or gone, or far away.
			if (!v || !other || !Ahead(v, other) || vector.DistanceXZ(v.GetOrigin(), other.GetOrigin()) > CLEAR_M)
				done.Insert(v);
		}
		foreach (IEntity v : done)
		{
			if (v)
			{
				ZCR_Traffic.Release(v, "oncoming");
				Print(string.Format("[ZCR][ONCOMING] t=%1 side=%2 vehicle=%3 event=passed slow_s=%4", now, ZCR_LossLog.SideOf(v), ZCR_LossLog.ShortName(v),
					now - s_mSlowAt.Get(v)), LogLevel.NORMAL);
			}
			s_mSlowFor.Remove(v);
			s_mSlowAt.Remove(v);
		}
		// New pairs.
		// One of the two may be standing or crawling (23 Oct 22:00: on the head-on lane a UAZ stopped in a queue facing
		// north at 2514,1607 was ignored - both had to be over 8 km/h - and one came at it at 51 km/h).
		for (int i = 0; i < cars.Count(); i++)
		{
			IEntity a = cars[i];
			if (!a || ZCR_Armour.IsUnit(a))
				continue;
			for (int k = i + 1; k < cars.Count(); k++)
			{
				IEntity b = cars[k];
				if (!b || ZCR_Armour.IsUnit(b) || (Kmh(a) < MIN_KMH && Kmh(b) < MIN_KMH))
					continue;
				if (vector.DistanceXZ(a.GetOrigin(), b.GetOrigin()) > SEE_M)
					continue;
				float dab, dba;
				if (!Towards(a, b, dab) || !Towards(b, a, dba))
					continue;
				Slow(a, b, now, dab);
				Slow(b, a, now, dab);
			}
		}
	}

	protected static bool Ahead(IEntity a, IEntity b)
	{
		vector rel = b.GetOrigin() - a.GetOrigin();
		rel[1] = 0;
		return vector.Dot(rel, Heading(a)) > 0;
	}

	protected static void Slow(IEntity v, IEntity other, int now, float distance)
	{
		if (s_mSlowFor.Contains(v))
			return;
		if (!ZCR_Traffic.Limit(v, "oncoming", SLOW_KMH))
			return;
		s_mSlowFor.Set(v, other);
		s_mSlowAt.Set(v, now);
		string otherSide = ZCR_LossLog.SideOf(other);
		if (otherSide.IsEmpty())
			otherSide = "none";
		vector at = v.GetOrigin();
		Print(string.Format("[ZCR][ONCOMING] t=%1 side=%2 vehicle=%3 other=%4 other_side=%5 m=%6 kmh=%7 other_kmh=%8 x=%9", now, ZCR_LossLog.SideOf(v),
			ZCR_LossLog.ShortName(v), ZCR_LossLog.ShortName(other), otherSide, Math.Round(distance), Math.Round(Kmh(v)), Math.Round(Kmh(other)),
			Math.Round(at[0])) + string.Format(" z=%1", Math.Round(at[2])), LogLevel.NORMAL);
	}
}
