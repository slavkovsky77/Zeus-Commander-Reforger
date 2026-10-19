// The Arma 3 lab's soldier measurements (Zeus Commander's fn_recorder) for Reforger's US and USSR
// soldiers, with the same definitions so the two engine pages compare:
//   [ZCR][CROWD] t= side= men= near= stacked= field= field_stacked=   every 30 s: soldiers on foot,
//       the average number of friends within 25 m, the % with 6 or more (stacked); and the same for
//       the soldiers in the field - over 200 m from their own main base, where AI Conflict gathers
//       its recruits one by one
//   [ZCR][EXPOSURE] t= side= engaged= covered= prone=  every 30 s: of the soldiers on foot who know
//       an enemy within 300 m, the % with something solid within 3 m toward the nearest one, or a
//       roof overhead (covered), and the % lying down
//       ... ground= object= above=: what the cover is - toward the enemy the ground (a crest) or an
//       object (building, wall, rock, tree trunk, vehicle), and overhead a roof or tree canopy
//       (hides him from a drone; a crest does not)
//   ... field_above= on [ZCR][CROWD]: % of the soldiers in the field under a roof or canopy
//   on each soldier's death, added to [ZCR][LOSS]: stance, moving (over 3 km/h in the last 5 s),
//       covered (something solid within 3 m toward the killer; "-" with no killer), roof, foot,
//       cover= (ground/building/tree/vehicle/object/none toward the killer), above= (roof/canopy/none).
// Unlike Arma 3's check, the ground counts as cover too (a crest between him and the enemy).
// Also each side's knowledge (Arma 3: "the AI never cheats on what it knows"): every enemy one of
// its soldiers has seen, with where he was last seen, for 60 s - KnownEnemiesNear for the report.
// Server only; started by the first commander tick.
class ZCR_SoldierState
{
	vector m_vPos;
	vector m_vEye;
	int m_iAt;
	int m_iStance;
	bool m_bMoving;
	bool m_bInVehicle;
	string m_sSide;
}

class ZCR_Sampler
{
	protected static ref ZCR_Sampler s_Instance;
	protected ref map<IEntity, ref ZCR_SoldierState> m_mState = new map<IEntity, ref ZCR_SoldierState>();
	// side -> enemy -> where and when last seen
	protected ref map<string, ref map<IEntity, vector>> m_mKnownPos = new map<string, ref map<IEntity, vector>>();
	protected ref map<string, ref map<IEntity, int>> m_mKnownAt = new map<string, ref map<IEntity, int>>();
	protected int m_iNextMeasure;
	protected ref TraceParam m_Trace;
	protected ref array<IEntity> m_aExclude = {};
	protected static const float MOVING_MPS = 0.83;      // 3 km/h, Arma 3's "moving"
	protected static const float ENGAGED_RANGE = 300;
	protected static const float COVER_RANGE = 3;
	protected static const float ROOF_RANGE = 15;
	protected static const float CROWD_RANGE = 25;
	protected static const int STACKED_FRIENDS = 6;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer())
			return;
		s_Instance = new ZCR_Sampler();
		GetGame().GetCallqueue().CallLater(s_Instance.Sample, 5000, true);
	}

	// " stance=... moving=... covered=... roof=... foot=..." for the loss line; "" if unknown.
	static string DeathState(IEntity victim, IEntity killer)
	{
		if (!s_Instance || !ChimeraCharacter.Cast(victim))
			return "";
		ZCR_SoldierState st;
		if (!s_Instance.m_mState.Find(victim, st) || !st)
			return "";
		string covered = "-";
		string cover = "-";
		if (killer && killer != victim)
		{
			vector to = killer.GetOrigin() + Vector(0, 1.5, 0);
			ChimeraCharacter kc = ChimeraCharacter.Cast(killer);
			if (kc)
				to = kc.EyePosition();
			cover = s_Instance.CoverToward(st.m_vEye, to, victim, killer);
			covered = (cover != "none").ToString();
		}
		string above = s_Instance.Above(st.m_vEye, victim);
		return string.Format(" stance=%1 moving=%2 covered=%3 roof=%4 foot=%5 cover=%6 above=%7",
			typename.EnumToString(ECharacterStance, st.m_iStance), st.m_bMoving, covered,
			above == "roof", !st.m_bInVehicle, cover, above);
	}

	// Enemies this side has seen within the last 60 s within 'radius' of 'at' (alive).
	static int KnownEnemiesNear(string side, vector at, float radius)
	{
		if (!s_Instance)
			return -1;
		map<IEntity, vector> pos;
		map<IEntity, int> when;
		if (!s_Instance.m_mKnownPos.Find(side, pos) || !s_Instance.m_mKnownAt.Find(side, when))
			return 0;
		int now = ZCR_LossLog.Seconds();
		int n;
		foreach (IEntity e, vector p : pos)
		{
			if (!e || now - when.Get(e) > 60)
				continue;
			ChimeraCharacter c = ChimeraCharacter.Cast(e);
			if (c && c.GetCharacterController() && c.GetCharacterController().GetLifeState() == ECharacterLifeState.DEAD)
				continue;
			if (vector.DistanceXZ(p, at) <= radius)
				n++;
		}
		return n;
	}

	protected void Learn(string side, IEntity soldier, int now)
	{
		PerceptionComponent perception = PerceptionComponent.Cast(soldier.FindComponent(PerceptionComponent));
		if (!perception)
			return;
		map<IEntity, vector> pos;
		map<IEntity, int> when;
		if (!m_mKnownPos.Find(side, pos))
		{
			pos = new map<IEntity, vector>();
			m_mKnownPos.Set(side, pos);
		}
		if (!m_mKnownAt.Find(side, when))
		{
			when = new map<IEntity, int>();
			m_mKnownAt.Set(side, when);
		}
		array<BaseTarget> targets = {};
		perception.GetTargetsList(targets, ETargetCategory.ENEMY);
		foreach (BaseTarget target : targets)
		{
			if (!target || !target.GetTargetEntity() || target.GetTimeSinceSeen() > 30)
				continue;
			pos.Set(target.GetTargetEntity(), target.GetLastSeenPosition());
			when.Set(target.GetTargetEntity(), now);
		}
	}

	protected void Forget(int now)
	{
		foreach (string side, map<IEntity, int> when : m_mKnownAt)
		{
			map<IEntity, vector> pos = m_mKnownPos.Get(side);
			array<IEntity> old = {};
			foreach (IEntity e, int t : when)
			{
				if (!e || now - t > 60)
					old.Insert(e);
			}
			foreach (IEntity e : old)
			{
				when.Remove(e);
				if (pos)
					pos.Remove(e);
			}
		}
	}

	void Sample()
	{
		int now = ZCR_LossLog.Seconds();
		Forget(now);
		map<IEntity, ref ZCR_SoldierState> next = new map<IEntity, ref ZCR_SoldierState>();
		foreach (FactionKey faction, AICF_FactionState state : ZCR_Strategist.s_mStates)
		{
			if (!state)
				continue;
			for (int s; s < state.GetSlotCount(); s++)
			{
				AICF_GroupSlot slot = state.GetSlot(s);
				if (!slot || !slot.GetGroup())
					continue;
				array<AIAgent> agents = {};
				slot.GetGroup().GetAgents(agents);
				foreach (AIAgent agent : agents)
				{
					ChimeraCharacter c;
					if (agent)
						c = ChimeraCharacter.Cast(agent.GetControlledEntity());
					if (!c)
						continue;
					CharacterControllerComponent ctl = c.GetCharacterController();
					if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
						continue;
					ZCR_SoldierState st;
					if (!m_mState.Find(c, st) || !st)
					{
						st = new ZCR_SoldierState();
						st.m_vPos = c.GetOrigin();
						st.m_iAt = now;
					}
					float dt = Math.Max(1, now - st.m_iAt);
					st.m_bMoving = vector.DistanceXZ(st.m_vPos, c.GetOrigin()) / dt > MOVING_MPS;
					st.m_vPos = c.GetOrigin();
					st.m_iAt = now;
					st.m_vEye = c.EyePosition();
					st.m_iStance = ctl.GetStance();
					st.m_bInVehicle = c.IsInVehicle();
					st.m_sSide = faction;
					next.Set(c, st);
					Learn(faction, c, now);
				}
			}
		}
		m_mState = next;
		if (now >= m_iNextMeasure)
		{
			m_iNextMeasure = now + 30;
			Measure(now);
		}
	}

	protected void Measure(int now)
	{
		array<string> sides = {"US", "USSR"};
		foreach (string side : sides)
		{
			array<IEntity> men = {};
			foreach (IEntity e, ZCR_SoldierState st : m_mState)
			{
				if (e && st && st.m_sSide == side && !st.m_bInVehicle)
					men.Insert(e);
			}
			if (men.IsEmpty())
				continue;
			int near;
			int stacked;
			int field;
			int fieldStacked;
			int fieldAbove;
			int byGround;
			int byObject;
			int byAbove;
			vector home = MainBase(side);
			int engaged;
			int covered;
			int prone;
			foreach (IEntity e : men)
			{
				int friends;
				foreach (IEntity o : men)
				{
					if (o != e && vector.DistanceSq(o.GetOrigin(), e.GetOrigin()) < CROWD_RANGE * CROWD_RANGE)
						friends++;
				}
				near += friends;
				if (friends >= STACKED_FRIENDS)
					stacked++;
				ZCR_SoldierState me = m_mState.Get(e);
				string over = Above(me.m_vEye, e);
				if (home == vector.Zero || vector.DistanceXZ(e.GetOrigin(), home) > 200)
				{
					field++;
					if (friends >= STACKED_FRIENDS)
						fieldStacked++;
					if (over != "none")
						fieldAbove++;
				}
				IEntity enemy = NearestEnemy(e);
				if (!enemy)
					continue;
				engaged++;
				ZCR_SoldierState st = m_mState.Get(e);
				vector to = enemy.GetOrigin() + Vector(0, 1.5, 0);
				ChimeraCharacter ec = ChimeraCharacter.Cast(enemy);
				if (ec)
					to = ec.EyePosition();
				string kind = CoverToward(st.m_vEye, to, e, enemy);
				if (kind == "ground")
					byGround++;
				else if (kind != "none")
					byObject++;
				if (over != "none")
					byAbove++;
				if (kind != "none" || over == "roof")
					covered++;
				if (st.m_iStance == ECharacterStance.PRONE)
					prone++;
			}
			int fieldPct = -1;
			int fieldAbovePct = -1;
			if (field > 0)
			{
				fieldPct = Math.Round(100.0 * fieldStacked / field);
				fieldAbovePct = Math.Round(100.0 * fieldAbove / field);
			}
			Print(string.Format("[ZCR][CROWD] t=%1 side=%2 men=%3 near=%4 stacked=%5 field=%6 field_stacked=%7 field_above=%8", now, side, men.Count(),
				Math.Round(10.0 * near / men.Count()) / 10.0, Math.Round(100.0 * stacked / men.Count()), field, fieldPct, fieldAbovePct), LogLevel.NORMAL);
			if (engaged > 0)
				Print(string.Format("[ZCR][EXPOSURE] t=%1 side=%2 engaged=%3 covered=%4 prone=%5 ground=%6 object=%7 above=%8", now, side, engaged,
					Math.Round(100.0 * covered / engaged), Math.Round(100.0 * prone / engaged), Math.Round(100.0 * byGround / engaged),
					Math.Round(100.0 * byObject / engaged), Math.Round(100.0 * byAbove / engaged)), LogLevel.NORMAL);
		}
	}

	protected vector MainBase(string side)
	{
		FactionManager fm = GetGame().GetFactionManager();
		if (!fm)
			return vector.Zero;
		SCR_CampaignFaction faction = SCR_CampaignFaction.Cast(fm.GetFactionByKey(side));
		if (!faction || !faction.GetMainBase() || !faction.GetMainBase().GetOwner())
			return vector.Zero;
		return faction.GetMainBase().GetOwner().GetOrigin();
	}

	// The nearest enemy this soldier knows of within 300 m (his own perception).
	protected IEntity NearestEnemy(IEntity soldier)
	{
		PerceptionComponent perception = PerceptionComponent.Cast(soldier.FindComponent(PerceptionComponent));
		if (!perception)
			return null;
		array<BaseTarget> targets = {};
		perception.GetTargetsList(targets, ETargetCategory.ENEMY);
		IEntity best;
		float bestDistance = ENGAGED_RANGE;
		foreach (BaseTarget target : targets)
		{
			if (!target || !target.GetTargetEntity())
				continue;
			float d = vector.Distance(soldier.GetOrigin(), target.GetTargetEntity().GetOrigin());
			if (d < bestDistance)
			{
				bestDistance = d;
				best = target.GetTargetEntity();
			}
		}
		return best;
	}

	// What stands within 3 m of the eye on the line toward 'to' (fire geometry or ground):
	// ground, building, tree, vehicle, object (walls, rocks, sandbags) or none.
	protected string CoverToward(vector eye, vector to, IEntity self, IEntity other)
	{
		vector dir = to - eye;
		if (dir.Length() < 0.5)
			return "none";
		dir.Normalize();
		// Terrain is on its own layer: without it a crest never counted (ground=0 in every sample).
		if (!Trace(eye, eye + dir * COVER_RANGE, self, other, TraceFlags.ENTS | TraceFlags.WORLD, EPhysicsLayerDefs.FireGeometry | EPhysicsLayerDefs.Terrain))
			return "none";
		return Kind(m_Trace.TraceEnt);
	}

	// What is over his head within 15 m on what blocks sight - a roof or tree canopy hides him
	// from a drone: roof, canopy, object or none.
	protected string Above(vector eye, IEntity self)
	{
		int layers = EPhysicsLayerDefs.ViewGeometry | EPhysicsLayerDefs.Foliage | EPhysicsLayerDefs.FireGeometry;
		if (!Trace(eye + Vector(0, 0.3, 0), eye + Vector(0, ROOF_RANGE, 0), self, null, TraceFlags.ENTS, layers))
			return "none";
		string kind = Kind(m_Trace.TraceEnt);
		if (kind == "building")
			return "roof";
		if (kind == "tree")
			return "canopy";
		return "object";
	}

	protected static string Kind(IEntity hit)
	{
		if (!hit || GenericTerrainEntity.Cast(hit))
			return "ground";
		IEntity root = hit.GetRootParent();
		if (!root)
			root = hit;
		if (BaseTree.Cast(root) || BaseTree.Cast(hit))
			return "tree";
		if (BaseBuilding.Cast(root) || BaseBuilding.Cast(hit))
			return "building";
		if (Vehicle.Cast(root))
			return "vehicle";
		return "object";
	}

	protected bool Trace(vector from, vector to, IEntity self, IEntity other, TraceFlags flags, int layers)
	{
		if (!m_Trace)
		{
			m_Trace = new TraceParam();
			m_Trace.ExcludeArray = m_aExclude;
		}
		m_aExclude.Clear();
		if (self)
		{
			m_aExclude.Insert(self);
			if (self.GetRootParent() && self.GetRootParent() != self)
				m_aExclude.Insert(self.GetRootParent());
		}
		if (other)
		{
			m_aExclude.Insert(other);
			if (other.GetRootParent() && other.GetRootParent() != other)
				m_aExclude.Insert(other.GetRootParent());
		}
		m_Trace.TargetLayers = layers;
		m_Trace.Flags = flags;
		m_Trace.Start = from;
		m_Trace.End = to;
		m_Trace.TraceEnt = null;
		return GetGame().GetWorld().TraceMove(m_Trace, null) < 1.0;
	}
}
