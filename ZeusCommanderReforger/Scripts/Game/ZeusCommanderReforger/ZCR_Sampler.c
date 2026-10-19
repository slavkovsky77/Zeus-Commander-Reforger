// The Arma 3 lab's soldier measurements (Zeus Commander's fn_recorder) for Reforger's US and USSR
// soldiers, with the same definitions so the two engine pages compare:
//   [ZCR][CROWD] t= side= men= near= stacked= field= field_stacked=   every 30 s: soldiers on foot,
//       the average number of friends within 25 m, the % with 6 or more (stacked); and the same for
//       the soldiers in the field - over 200 m from their own main base, where AI Conflict gathers
//       its recruits one by one
//   [ZCR][EXPOSURE] t= side= engaged= covered= prone=  every 30 s: of the soldiers on foot who know
//       an enemy within 300 m, the % with something solid within 3 m toward the nearest one, or a
//       roof overhead (covered), and the % lying down
//   on each soldier's death, added to [ZCR][LOSS]: stance, moving (over 3 km/h in the last 5 s),
//       covered (something solid within 3 m toward the killer; "-" with no killer), roof, foot.
// Unlike Arma 3's check, the ground counts as cover too (a crest between him and the enemy).
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
		if (killer && killer != victim)
		{
			vector to = killer.GetOrigin() + Vector(0, 1.5, 0);
			ChimeraCharacter kc = ChimeraCharacter.Cast(killer);
			if (kc)
				to = kc.EyePosition();
			covered = s_Instance.Blocked(st.m_vEye, to, victim, killer).ToString();
		}
		return string.Format(" stance=%1 moving=%2 covered=%3 roof=%4 foot=%5",
			typename.EnumToString(ECharacterStance, st.m_iStance), st.m_bMoving, covered,
			s_Instance.Roof(st.m_vEye, victim), !st.m_bInVehicle);
	}

	void Sample()
	{
		int now = ZCR_LossLog.Seconds();
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
				if (home == vector.Zero || vector.DistanceXZ(e.GetOrigin(), home) > 200)
				{
					field++;
					if (friends >= STACKED_FRIENDS)
						fieldStacked++;
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
				if (Blocked(st.m_vEye, to, e, enemy) || Roof(st.m_vEye, e))
					covered++;
				if (st.m_iStance == ECharacterStance.PRONE)
					prone++;
			}
			int fieldPct = -1;
			if (field > 0)
				fieldPct = Math.Round(100.0 * fieldStacked / field);
			Print(string.Format("[ZCR][CROWD] t=%1 side=%2 men=%3 near=%4 stacked=%5 field=%6 field_stacked=%7", now, side, men.Count(),
				Math.Round(10.0 * near / men.Count()) / 10.0, Math.Round(100.0 * stacked / men.Count()), field, fieldPct), LogLevel.NORMAL);
			if (engaged > 0)
				Print(string.Format("[ZCR][EXPOSURE] t=%1 side=%2 engaged=%3 covered=%4 prone=%5", now, side, engaged,
					Math.Round(100.0 * covered / engaged), Math.Round(100.0 * prone / engaged)), LogLevel.NORMAL);
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

	// Something solid within 3 m of the eye on the line toward 'to' (fire geometry or ground).
	protected bool Blocked(vector eye, vector to, IEntity self, IEntity other)
	{
		vector dir = to - eye;
		if (dir.Length() < 0.5)
			return false;
		dir.Normalize();
		return Trace(eye, eye + dir * COVER_RANGE, self, other, TraceFlags.ENTS | TraceFlags.WORLD);
	}

	protected bool Roof(vector eye, IEntity self)
	{
		return Trace(eye + Vector(0, 0.3, 0), eye + Vector(0, ROOF_RANGE, 0), self, null, TraceFlags.ENTS);
	}

	protected bool Trace(vector from, vector to, IEntity self, IEntity other, TraceFlags flags)
	{
		if (!m_Trace)
		{
			m_Trace = new TraceParam();
			m_Trace.TargetLayers = EPhysicsLayerDefs.FireGeometry;
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
		m_Trace.Flags = flags | TraceFlags.ANY_CONTACT;
		m_Trace.Start = from;
		m_Trace.End = to;
		return GetGame().GetWorld().TraceMove(m_Trace, null) < 1.0;
	}
}
