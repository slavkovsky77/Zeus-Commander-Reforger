// Junction caution (23 Oct evening): the crossing rule missed the hit on the supply route at (2550, 1707) - a truck came
// round the corner onto the east road at 12 km/h while another came down that road at 49 km/h; while the first was still
// turning its straight line pointed away from the other, and once it had turned they were 30 m apart, too close for the
// head-on slow-down. Both of the day's junction crashes (the watched supply run's three at 2515,1580-1690 and this one)
// were at the same junction. So, as drivers do: two vehicles heading for the same junction both slow down there.
//   junctions - where three or more road branches meet (road ends within 6 m, or a road's end on the middle of
//               another), found from the game's road network per 200-m map cell the first time a car is in it;
//               and sharp bends (21:55: the head-on lane's one hit of the evening was at the blind bend at 2512,1600 -
//               the same place as the watched supply run's three - a bend, not a junction): a road turning more than
//               40 degrees between 25 m before and 25 m after a point (50 within 15 m missed that one);
//   caution   - a driven vehicle (not our armour) with a junction ahead within 50 m, while another driven vehicle is
//               within 60 m of that junction and not past it: 20 km/h (the "junction" cap) until it is 12 m past the
//               junction or the other one is gone, past it or away. The head-on and crossing rules then have time.
//   [ZCR][JUNCTIONS] cell= roads= junctions=                                   (once per map cell)
//   [ZCR][JUNCTION] t= side= vehicle= other= m= other_m= kmh= other_kmh= x= z= jx= jz=   (slowing starts)
//   [ZCR][JUNCTION] t= side= vehicle= event=clear slow_s= why=past|alone
//   [ZCR][JUNCTION_SUM] t= slowdowns= cells= junctions=                       (every 60 s, totals)
// -zcrNoJunction turns it off.
class ZCR_Junction
{
	static const float CELL_M = 200;
	static const float NEAR_M = 6;
	static const float AHEAD_M = 50;
	static const float OTHER_M = 60;
	static const float PAST_M = 12;
	static const float SLOW_KMH = 20;
	static const float MIN_KMH = 5;
	static const float BEND_M = 25;
	static const float BEND_COS = 0.77;   // cos 40 degrees

	protected static ref ZCR_Junction s_Instance;
	protected static ref map<int, ref array<vector>> s_mCells = new map<int, ref array<vector>>();
	protected static ref map<IEntity, vector> s_mAt = new map<IEntity, vector>();   // slowed vehicle -> its junction
	protected static ref map<IEntity, int> s_mSince = new map<IEntity, int>();
	protected int m_iNextSum = 60;
	protected int m_iSlowdowns;
	protected int m_iJunctions;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || System.IsCLIParam("zcrNoJunction"))
			return;
		s_Instance = new ZCR_Junction();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 500, true);
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

	// How far the point is ahead of v along its heading (negative: behind).
	protected static float Ahead(IEntity v, vector point)
	{
		vector rel = point - v.GetOrigin();
		rel[1] = 0;
		return vector.Dot(rel, Heading(v));
	}

	// Distance on the ground from p to the segment a-b.
	protected static float SegDist(vector p, vector a, vector b)
	{
		vector ab = b - a;
		ab[1] = 0;
		vector ap = p - a;
		ap[1] = 0;
		float len2 = vector.Dot(ab, ab);
		float t = 0;
		if (len2 > 0.01)
			t = Math.Clamp(vector.Dot(ap, ab) / len2, 0, 1);
		vector q = a + ab * t;
		return vector.DistanceXZ(p, q);
	}

	// The junctions of one map cell, found once.
	protected array<vector> Cell(int cx, int cz)
	{
		int key = cx * 100000 + cz;
		array<vector> found = s_mCells.Get(key);
		if (found)
			return found;
		found = {};
		s_mCells.Set(key, found);
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (!aiWorld || !aiWorld.GetRoadNetworkManager())
			return found;
		array<BaseRoad> roads = {};
		aiWorld.GetRoadNetworkManager().GetRoadsInAABB(Vector(cx * CELL_M - 20, -100, cz * CELL_M - 20), Vector((cx + 1) * CELL_M + 20, 2000, (cz + 1) * CELL_M + 20), roads);
		array<ref array<vector>> lines = {};
		foreach (BaseRoad road : roads)
		{
			array<vector> points = {};
			if (road)
				road.GetPoints(points);
			lines.Insert(points);
		}
		for (int r; r < lines.Count(); r++)
		{
			array<vector> own = lines[r];
			if (own.Count() < 2)
				continue;
			for (int e; e < 2; e++)
			{
				vector end = own[0];
				if (e == 1)
					end = own[own.Count() - 1];
				// each junction belongs to the cell it lies in
				if (Math.Floor(end[0] / CELL_M) != cx || Math.Floor(end[2] / CELL_M) != cz)
					continue;
				int branches = 1;
				for (int k; k < lines.Count(); k++)
				{
					array<vector> other = lines[k];
					if (k == r || other.Count() < 2)
						continue;
					if (vector.DistanceXZ(end, other[0]) < NEAR_M || vector.DistanceXZ(end, other[other.Count() - 1]) < NEAR_M)
					{
						branches++;
						continue;
					}
					for (int s; s < other.Count() - 1; s++)
					{
						if (SegDist(end, other[s], other[s + 1]) < NEAR_M)
						{
							branches += 2;   // a road passing through: two branches
							break;
						}
					}
				}
				if (branches < 3)
					continue;
				bool known;
				foreach (vector j : found)
				{
					if (vector.DistanceXZ(j, end) < 15)
						known = true;
				}
				if (!known)
					found.Insert(end);
			}
		}
		int junctions = found.Count();
		// Sharp bends.
		foreach (array<vector> line : lines)
		{
			for (int b = 1; b < line.Count() - 1; b++)
			{
				vector at = line[b];
				if (Math.Floor(at[0] / CELL_M) != cx || Math.Floor(at[2] / CELL_M) != cz)
					continue;
				vector before = Along(line, b, -BEND_M);
				vector after = Along(line, b, BEND_M);
				vector d1 = at - before;
				vector d2 = after - at;
				d1[1] = 0;
				d2[1] = 0;
				if (d1.Length() < 8 || d2.Length() < 8)
					continue;
				d1.Normalize();
				d2.Normalize();
				if (vector.Dot(d1, d2) > BEND_COS)
					continue;
				bool near;
				foreach (vector q : found)
				{
					if (vector.DistanceXZ(q, at) < 25)
						near = true;
				}
				if (!near)
				{
					found.Insert(at);
					Print(string.Format("[ZCR][JUNCTIONS] bend x=%1 z=%2 turn=%3", Math.Round(at[0]), Math.Round(at[2]), Math.Round(Math.Acos(vector.Dot(d1, d2)) * Math.RAD2DEG)), LogLevel.NORMAL);
				}
			}
		}
		m_iJunctions += found.Count();
		Print(string.Format("[ZCR][JUNCTIONS] cell=%1,%2 roads=%3 junctions=%4 bends=%5", cx, cz, roads.Count(), junctions, found.Count() - junctions), LogLevel.NORMAL);
		return found;
	}

	// The road point about 'metres' along the line from point i (negative: back), on the line's own points.
	protected static vector Along(array<vector> line, int i, float metres)
	{
		float gone = 0;
		int k = i;
		int step = 1;
		if (metres < 0)
			step = -1;
		while (k + step >= 0 && k + step < line.Count() && gone < Math.AbsFloat(metres))
		{
			gone += vector.DistanceXZ(line[k], line[k + step]);
			k += step;
		}
		return line[k];
	}

	// The nearest junction within AHEAD_M ahead of v (not more than PAST_M behind it); false when none.
	protected bool NextJunction(IEntity v, out vector junction)
	{
		vector at = v.GetOrigin();
		int cx = Math.Floor(at[0] / CELL_M);
		int cz = Math.Floor(at[2] / CELL_M);
		float best = AHEAD_M;
		bool any;
		for (int dx = -1; dx <= 1; dx++)
		{
			for (int dz = -1; dz <= 1; dz++)
			{
				foreach (vector j : Cell(cx + dx, cz + dz))
				{
					float d = vector.DistanceXZ(at, j);
					if (d >= best || Ahead(v, j) < -PAST_M)
						continue;
					best = d;
					junction = j;
					any = true;
				}
			}
		}
		return any;
	}

	// Another driven vehicle near the junction and not past it.
	protected static IEntity Other(IEntity v, vector junction, array<IEntity> cars)
	{
		foreach (IEntity o : cars)
		{
			if (!o || o == v || vector.DistanceXZ(o.GetOrigin(), junction) > OTHER_M)
				continue;
			if (Ahead(o, junction) < -PAST_M)
				continue;
			if (Kmh(o) < MIN_KMH && vector.DistanceXZ(o.GetOrigin(), junction) > 15)
				continue;   // standing well short of it
			return o;
		}
		return null;
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("junction");   // ZCR_Cost: our scripts' share of the frame time
		int now = ZCR_LossLog.Seconds();
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		// Ends first.
		array<IEntity> done = {};
		array<string> whys = {};
		foreach (IEntity v, vector j : s_mAt)
		{
			string why;
			if (!v || cars.Find(v) < 0)
				why = "gone";
			else if (Ahead(v, j) < -PAST_M || vector.DistanceXZ(v.GetOrigin(), j) > AHEAD_M + 10)
				why = "past";
			else if (!Other(v, j, cars))
				why = "alone";
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
				ZCR_Traffic.Release(v, "junction");
				Print(string.Format("[ZCR][JUNCTION] t=%1 side=%2 vehicle=%3 event=clear slow_s=%4 why=%5", now, ZCR_LossLog.SideOf(v), ZCR_LossLog.ShortName(v),
					now - s_mSince.Get(v), whys[d]), LogLevel.NORMAL);
			}
			s_mAt.Remove(v);
			s_mSince.Remove(v);
		}
		// New ones.
		foreach (IEntity v : cars)
		{
			if (!v || s_mAt.Contains(v) || ZCR_Armour.IsUnit(v) || Kmh(v) < MIN_KMH)
				continue;
			vector j;
			if (!NextJunction(v, j))
				continue;
			IEntity other = Other(v, j, cars);
			if (!other || !ZCR_Traffic.Limit(v, "junction", SLOW_KMH))
				continue;
			s_mAt.Set(v, j);
			s_mSince.Set(v, now);
			m_iSlowdowns++;
			vector at = v.GetOrigin();
			Print(string.Format("[ZCR][JUNCTION] t=%1 side=%2 vehicle=%3 other=%4 m=%5 other_m=%6 kmh=%7 other_kmh=%8 x=%9", now, ZCR_LossLog.SideOf(v),
				ZCR_LossLog.ShortName(v), ZCR_LossLog.ShortName(other), Math.Round(vector.DistanceXZ(at, j)), Math.Round(vector.DistanceXZ(other.GetOrigin(), j)),
				Math.Round(Kmh(v)), Math.Round(Kmh(other)), Math.Round(at[0])) + string.Format(" z=%1 jx=%2 jz=%3", Math.Round(at[2]), Math.Round(j[0]), Math.Round(j[2])),
				LogLevel.NORMAL);
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 60;
			Print(string.Format("[ZCR][JUNCTION_SUM] t=%1 slowdowns=%2 cells=%3 junctions=%4", now, m_iSlowdowns, s_mCells.Count(), m_iJunctions), LogLevel.NORMAL);
		}
	}
}
