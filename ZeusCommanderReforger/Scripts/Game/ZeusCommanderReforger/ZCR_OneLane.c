// One car at a time over a one-lane bridge (3 Nov night, review note 512 - Martin, watching the Soviet rides: "team a6 and
// other get stuck next to small bridge its too narrow"; and /good "they try to resolve it somehow"). Arland's old stone
// bridges (Castle_01_Bridge: east of Farm at 2401,2775, 1942,1917 and 2934,2014) are one vehicle wide - the deck 4.7 m by
// 18.6 m, the road piece over the Farm one 3 m wide where the roads either side are 4-4.5 m. Two cars coming from both ends
// met on the deck and stood there head-on; the unjam rule backed one off 8 m every 20 s, and they met again: 62 of the 130
// jams in Martin's 3x Soviet run, 22 of 97 in a 115-minute run.
// The rule, as drivers do it: whoever reaches the bridge first has it, and cars behind it going the same way may follow; a
// car coming the other way stops short of the bridge (held still through ZCR_Traffic - cruise 0 and no drive to the wheels)
// until the deck is clear and nobody is coming onto it its way. Once a car has waited TURN_S, the bridge turns to its side
// as soon as the deck is clear. A wait ends after MAX_WAIT_S anyway (that car isn't held again for AGAIN_S), so a wreck on
// the deck can't close the road.
// A car up to EXIT_M past its end going away still has the bridge (the road off it is as narrow for a while).
//   bridges - stone bridges (Castle_01_Bridge) and any other "Bridge" prefab with a deck under 6 m wide and 8-60 m long
//             (not pillars or obstacles), looked for once per 200-m map cell the first time a driven car is in it; the deck
//             runs along its long side, END_M past each end of its bounds
//   [ZCR][ONELANE] event=bridge prefab= x= z= deck_m= wide_m= ax= az= bx= bz=                (found)
//   [ZCR][ONELANE] t= side= vehicle= event=wait m= for= dir= x= z=                         (held short of the bridge)
//   [ZCR][ONELANE] t= vehicle= event=held s= m= kmh=                                         (every 5 s while held)
//   [ZCR][ONELANE] t= side= vehicle= event=go wait_s= why=turn|timeout|away|gone max_kmh=  (let go; max_kmh after 2 s held)
//   [ZCR][ONELANE_SUM] t= waits= timeouts= turns= bridges= cells=                           (every 60 s)
// -zcrNoOneLane turns it off.
class ZCR_OneLaneBridge
{
	vector m_vC;        // the deck's middle
	vector m_vAxis;     // along the deck, A -> B
	float m_fHalf;      // half the deck's length, END_M past its bounds included
	int m_iDir;         // who has it: +1 A -> B, -1 B -> A, 0 nobody
	int m_iDirSince;
}

class ZCR_OneLane
{
	static const float CELL_M = 200;
	static const float END_M = 3;
	static const float COMMIT_M = 5;         // this close past its end a car counts as on the deck (never held at the end)
	static const float DECK_SIDE_M = 6;      // off the deck's line by more than this: not on it
	static const float APPROACH_M = 110;     // from its end of the deck: coming onto it (45, then 60 at first: the held car stood
	                                         // on the narrow stretch the other one came off the bridge on, 3 Nov)
	static const float EXIT_M = 30;          // a car this far past its end, going away, still has the bridge (the vans met
	                                         // 20 m past the east end, on the narrow cutting up from the river)
	static const float NEAR_M = 80;          // a bridge with no car this close isn't looked at
	static const float TOWARD_COS = 0.5;     // heading within 60 degrees of the deck's middle
	static const int TURN_S = 30;
	static const int MAX_WAIT_S = 60;
	static const int AGAIN_S = 30;
	static const float HELD_EXTRA_M = 20;    // a held car keeps waiting until this much further out than APPROACH_M
	static const float BRAKE_FAST = 0.92;    // ... over 20 km/h
	static const float BRAKE = 0.8;          // a held car's speed times this every 100 ms (cruise 0 and no drive still let
	                                         // it roll down the slope to the river onto the deck: 11 s from 32 m, 3 Nov)

	protected static ref ZCR_OneLane s_Instance;
	protected static ref map<int, ref array<ref ZCR_OneLaneBridge>> s_mCells = new map<int, ref array<ref ZCR_OneLaneBridge>>();
	protected static ref array<IEntity> s_aFound = {};
	protected static ref map<IEntity, int> s_mWaitSince = new map<IEntity, int>();   // held vehicle -> since
	protected static ref map<IEntity, float> s_mWaitMaxKmh = new map<IEntity, float>();
	protected static ref map<IEntity, int> s_mNoHoldUntil = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mTraceAt = new map<IEntity, int>();
	protected static float s_fApproachM = APPROACH_M;   // -zcrOneLaneHoldM N: where a car coming the other way is stopped
	protected int m_iNextSum = 60;
	protected int m_iWaits;
	protected int m_iTimeouts;
	protected int m_iTurns;
	protected int m_iBridges;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || AICF_Launch.Has("zcrNoOneLane"))
			return;
		s_Instance = new ZCR_OneLane();
		string holdM;
		if (AICF_Launch.Get("zcrOneLaneHoldM", holdM) && holdM.ToFloat() > 10)
			s_fApproachM = holdM.ToFloat();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 500, true);
		GetGame().GetCallqueue().CallLater(s_Instance.Brake, 100, true);
	}

	// Held cars stand still: their speed cut every 100 ms (the AI driver doesn't override a set velocity - docs/vehicles/
	// engine.md, as ZCR_Push). The vertical part too, so a car on a slope doesn't slide.
	protected void Brake()
	{
		foreach (IEntity v, int since : s_mWaitSince)
		{
			if (!v)
				continue;
			Physics p = v.GetPhysics();
			if (!p)
				continue;
			vector vel = p.GetVelocity();
			float mps = vel.Length();
			if (mps < 0.2)
				continue;
			// Fast: firm but not a wall (from 55 km/h it stands within ~20 m); slow: the roll stopped at once.
			if (mps > 5.5)
				p.SetVelocity(vel * BRAKE_FAST);
			else
				p.SetVelocity(vel * BRAKE);
		}
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

	protected static bool AddFound(IEntity e)
	{
		s_aFound.Insert(e);
		return true;
	}

	// The one-lane bridges of one map cell, found once.
	protected array<ref ZCR_OneLaneBridge> Cell(int cx, int cz)
	{
		int key = cx * 100000 + cz;
		array<ref ZCR_OneLaneBridge> found = s_mCells.Get(key);
		if (found)
			return found;
		found = {};
		s_mCells.Set(key, found);
		s_aFound.Clear();
		GetGame().GetWorld().QueryEntitiesByAABB(Vector(cx * CELL_M, -500, cz * CELL_M), Vector((cx + 1) * CELL_M, 2000, (cz + 1) * CELL_M), AddFound, null,
			EQueryEntitiesFlags.STATIC);
		foreach (IEntity e : s_aFound)
		{
			if (!e || e.GetRootParent() != e || !e.GetPrefabData())
				continue;
			string prefab = FilePath.StripPath(e.GetPrefabData().GetPrefabName());
			if (!prefab.Contains("Bridge") || prefab.Contains("Pillar") || prefab.Contains("Obstacle"))
				continue;
			vector o = e.GetOrigin();
			if (Math.Floor(o[0] / CELL_M) != cx || Math.Floor(o[2] / CELL_M) != cz)
				continue;   // its own cell has it
			vector mins, maxs;
			e.GetBounds(mins, maxs);
			float sx = maxs[0] - mins[0];
			float sz = maxs[2] - mins[2];
			float wide = Math.Min(sx, sz);
			float deck = Math.Max(sx, sz);
			if (wide > DECK_SIDE_M || deck < 8 || deck > 60)
				continue;
			vector axis = e.GetTransformAxis(2);
			if (sx > sz)
				axis = e.GetTransformAxis(0);
			axis[1] = 0;
			axis.Normalize();
			ZCR_OneLaneBridge b = new ZCR_OneLaneBridge();
			b.m_vC = e.CoordToParent((mins + maxs) * 0.5);
			b.m_vAxis = axis;
			b.m_fHalf = deck * 0.5 + END_M;
			found.Insert(b);
			m_iBridges++;
			vector endA = b.m_vC - axis * b.m_fHalf;
			vector endB = b.m_vC + axis * b.m_fHalf;
			Print(string.Format("[ZCR][ONELANE] event=bridge prefab=%1 x=%2 z=%3 deck_m=%4 wide_m=%5 ax=%6 az=%7 bx=%8 bz=%9", prefab, Math.Round(b.m_vC[0]),
				Math.Round(b.m_vC[2]), Math.Round(deck), Math.Round(wide * 10) / 10, Math.Round(endA[0]), Math.Round(endA[2]), Math.Round(endB[0]), Math.Round(endB[2])), LogLevel.NORMAL);
		}
		return found;
	}

	// Where v stands to the bridge: on the deck (+1 / -1 its way along it, 0 across), coming onto it (its way and the metres to
	// its end of the deck), just off it going away (its way), else not at it. Returns 2 on the deck or just off it, 1 coming,
	// 0 neither.
	protected static int Place(ZCR_OneLaneBridge b, IEntity v, bool held, out int dir, out float toEnd)
	{
		vector rel = v.GetOrigin() - b.m_vC;
		rel[1] = 0;
		float s = vector.Dot(rel, b.m_vAxis);
		vector side = Vector(-b.m_vAxis[2], 0, b.m_vAxis[0]);
		float off = Math.AbsFloat(vector.Dot(rel, side));
		vector h = Heading(v);
		float along = vector.Dot(h, b.m_vAxis);
		dir = 0;
		toEnd = 0;
		if (Math.AbsFloat(s) <= b.m_fHalf + COMMIT_M && off <= DECK_SIDE_M)
		{
			if (along > 0.3)
				dir = 1;
			else if (along < -0.3)
				dir = -1;
			return 2;
		}
		vector end = b.m_vC + b.m_vAxis * b.m_fHalf;
		dir = -1;
		if (s < 0)
		{
			end = b.m_vC - b.m_vAxis * b.m_fHalf;
			dir = 1;
		}
		toEnd = vector.DistanceXZ(v.GetOrigin(), end);
		vector toMid = b.m_vC - v.GetOrigin();
		toMid[1] = 0;
		toMid.Normalize();
		float facing = vector.Dot(h, toMid);
		if (toEnd <= EXIT_M && facing < -0.3)
		{
			dir = -dir;   // leaving on its side: going away from the deck
			return 2;
		}
		// A held car keeps its wait a little further out and turned a little more (it crept back and forth over the 45-m
		// line: wait / go 12 times in 25 s, 3 Nov).
		float reach = s_fApproachM;
		float toward = TOWARD_COS;
		if (held)
		{
			reach = s_fApproachM + HELD_EXTRA_M;
			toward = 0;
		}
		if (toEnd > reach || facing < toward)
			return 0;
		return 1;
	}

	protected void Let(IEntity v, string why, int now)
	{
		int since = s_mWaitSince.Get(v);
		if (v)
		{
			ZCR_Traffic.Unhold(v, "onelane");
			Print(string.Format("[ZCR][ONELANE] t=%1 side=%2 vehicle=%3 event=go wait_s=%4 why=%5 max_kmh=%6", now, ZCR_LossLog.SideOf(v), ZCR_LossLog.ShortName(v),
				now - since, why, Math.Round(s_mWaitMaxKmh.Get(v))), LogLevel.NORMAL);
		}
		s_mWaitSince.Remove(v);
		s_mWaitMaxKmh.Remove(v);
		s_mTraceAt.Remove(v);
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("onelane");   // ZCR_Cost: our scripts' share of the frame time
		int now = ZCR_LossLog.Seconds();
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		// The bridges near a driven car.
		array<ZCR_OneLaneBridge> near = {};
		foreach (IEntity v : cars)
		{
			if (!v)
				continue;
			vector at = v.GetOrigin();
			int cx = Math.Floor(at[0] / CELL_M);
			int cz = Math.Floor(at[2] / CELL_M);
			for (int dx = -1; dx <= 1; dx++)
			{
				for (int dz = -1; dz <= 1; dz++)
				{
					foreach (ZCR_OneLaneBridge cb : Cell(cx + dx, cz + dz))
					{
						if (near.Find(cb) < 0 && vector.DistanceXZ(at, cb.m_vC) <= NEAR_M)
							near.Insert(cb);
					}
				}
			}
		}
		map<IEntity, bool> keep = new map<IEntity, bool>();   // held vehicles still waiting at a bridge
		foreach (ZCR_OneLaneBridge b : near)
		{
			array<IEntity> deck = {};
			array<int> deckDir = {};
			array<IEntity> coming = {};
			array<int> comingDir = {};
			array<float> comingM = {};
			foreach (IEntity c : cars)
			{
				if (!c)
					continue;
				int dir;
				float toEnd;
				int place = Place(b, c, s_mWaitSince.Contains(c), dir, toEnd);
				if (place == 2)
				{
					deck.Insert(c);
					deckDir.Insert(dir);
				}
				else if (place == 1)
				{
					coming.Insert(c);
					comingDir.Insert(dir);
					comingM.Insert(toEnd);
				}
			}
			// Who has the bridge: the way of the cars on the deck (the one that had it, when both are there), else - nobody on
			// it - the way that has it while its next car is close behind (within 15 m) and nobody on the other side waited
			// TURN_S; else the car nearest its end (the longest-waiting side first once it waited TURN_S).
			int owner = 0;
			for (int i; i < deck.Count(); i++)
			{
				if (deckDir[i] != 0 && (owner == 0 || deckDir[i] == b.m_iDir))
					owner = deckDir[i];
			}
			if (owner == 0 && deck.IsEmpty())
			{
				int longWait = 0;
				int longest = -1;
				for (int k; k < coming.Count(); k++)
				{
					int since;
					if (comingDir[k] != b.m_iDir && s_mWaitSince.Find(coming[k], since) && now - since >= TURN_S && now - since > longest)
					{
						longest = now - since;
						longWait = comingDir[k];
					}
				}
				bool close;
				for (int k2; k2 < coming.Count(); k2++)
				{
					if (b.m_iDir != 0 && comingDir[k2] == b.m_iDir && comingM[k2] <= 15)
						close = true;
				}
				if (longWait != 0)
					owner = longWait;
				else if (close)
					owner = b.m_iDir;
				else
				{
					float best = 1e9;
					for (int k3; k3 < coming.Count(); k3++)
					{
						if (comingM[k3] < best)
						{
							best = comingM[k3];
							owner = comingDir[k3];
						}
					}
				}
			}
			if (owner != b.m_iDir)
			{
				if (owner != 0 && b.m_iDir != 0)
					m_iTurns++;
				b.m_iDir = owner;
				b.m_iDirSince = now;
			}
			// Hold the cars coming the other way; let go the ones whose way it is now.
			for (int q; q < coming.Count(); q++)
			{
				IEntity w = coming[q];
				bool waiting = s_mWaitSince.Contains(w);
				if (owner == 0 || comingDir[q] == owner)
				{
					if (waiting)
						Let(w, "turn", now);
					continue;
				}
				if (waiting)
				{
					keep.Set(w, true);
					int heldFor = now - s_mWaitSince.Get(w);
					if (heldFor >= 2)
						s_mWaitMaxKmh.Set(w, Math.Max(s_mWaitMaxKmh.Get(w), Kmh(w)));   // after its first 2 s of braking
					if (heldFor > 0 && heldFor % 5 == 0 && s_mTraceAt.Get(w) != now)
					{
						s_mTraceAt.Set(w, now);
						Print(string.Format("[ZCR][ONELANE] t=%1 vehicle=%2 event=held s=%3 m=%4 kmh=%5", now, ZCR_LossLog.ShortName(w), heldFor, Math.Round(comingM[q]),
							Math.Round(Kmh(w))), LogLevel.NORMAL);
					}
					if (now - s_mWaitSince.Get(w) >= MAX_WAIT_S)
					{
						m_iTimeouts++;
						s_mNoHoldUntil.Set(w, now + AGAIN_S);
						Let(w, "timeout", now);
						keep.Remove(w);
					}
					continue;
				}
				if (ZCR_Armour.IsUnit(w) || s_mNoHoldUntil.Get(w) > now)
					continue;
				IEntity first;
				for (int f; f < deck.Count(); f++)
				{
					if (deckDir[f] == owner)
						first = deck[f];
				}
				for (int g; g < coming.Count() && !first; g++)
				{
					if (comingDir[g] == owner)
						first = coming[g];
				}
				ZCR_Traffic.Hold(w, "onelane");
				s_mWaitSince.Set(w, now);
				s_mWaitMaxKmh.Set(w, 0);
				keep.Set(w, true);
				m_iWaits++;
				vector p = w.GetOrigin();
				Print(string.Format("[ZCR][ONELANE] t=%1 side=%2 vehicle=%3 event=wait m=%4 for=%5 dir=%6 bridge=%7,%8 x=%9", now, ZCR_LossLog.SideOf(w),
					ZCR_LossLog.ShortName(w), Math.Round(comingM[q]), ZCR_LossLog.ShortName(first), comingDir[q], Math.Round(b.m_vC[0]), Math.Round(b.m_vC[2]),
					Math.Round(p[0])) + string.Format(" z=%1", Math.Round(p[2])), LogLevel.NORMAL);
			}
		}
		// Held vehicles no longer coming onto a bridge (gone, turned away, got onto it).
		array<IEntity> drop = {};
		foreach (IEntity hv, int heldSince : s_mWaitSince)
		{
			if (!keep.Contains(hv))
				drop.Insert(hv);
		}
		foreach (IEntity d : drop)
		{
			string why = "away";
			if (!d || cars.Find(d) < 0)
				why = "gone";
			Let(d, why, now);
		}
		if (now >= m_iNextSum)
		{
			m_iNextSum = now + 60;
			Print(string.Format("[ZCR][ONELANE_SUM] t=%1 waits=%2 timeouts=%3 turns=%4 bridges=%5 cells=%6 waiting=%7", now, m_iWaits, m_iTimeouts, m_iTurns,
				m_iBridges, s_mCells.Count(), s_mWaitSince.Count()), LogLevel.NORMAL);
		}
	}
}
