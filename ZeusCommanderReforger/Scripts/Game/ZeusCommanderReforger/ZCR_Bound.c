// Bounding (Arma 3's fn_bound, Martin's remark 69: "real players move from cover to cover when the
// enemy is close, really careful"): an attacking squad of the side with our strategist, with an enemy
// known within 350 m and still over 40 m from its objective, splits in two halves. One half stays
// where it is and shoots (the game's attack logic doesn't walk it on), the other moves, crouched, to
// the next cover 35-60 m closer to the objective - each soldier his own spot with cover toward the
// threat (none: the aim point itself). When the movers are in (within 4 m of their spots) or after
// 15 s, the halves swap. Nobody crosses open ground while nobody covers him. Not while storming (then
// everyone goes in). Also spreads the squad: two halves 35-60 m apart instead of one bunch.
// -zcrBound turns it on (A/B first). Logs [ZCR][BOUND] per swap.
// First probe (19 Oct): USSR lost 46 (14 without), exchange 0.43 - squads bounded with the enemy 14 m
// away (halves sent 35-60 m on, past him) and down to 2 men. Now only with the enemy 60-350 m away and
// 4 or more men, and no bound ends nearer than 30 m to him; closer, the cover layer fights.
class ZCR_BoundState
{
	int m_iHalf = 1;
	int m_iSince = -1000000;
	ref array<IEntity> m_aMovers = {};
	ref array<vector> m_aSpots = {};
}

class ZCR_Bound
{
	protected static ref map<SCR_AIGroup, ref ZCR_BoundState> s_mState = new map<SCR_AIGroup, ref ZCR_BoundState>();
	protected static ref map<IEntity, int> s_mHolding = new map<IEntity, int>();
	static const float RANGE = 350;
	static const float CLOSE = 60;
	static const int MIN_MEN = 4;
	static const int SWAP = 15;

	static bool On()
	{
		return System.IsCLIParam("zcrBound");
	}

	// In the half that covers: the game's attack logic keeps him where he is.
	static bool Holds(IEntity soldier)
	{
		if (!soldier || !s_mHolding.Contains(soldier))
			return false;
		return ZCR_LossLog.Seconds() <= s_mHolding.Get(soldier);
	}

	protected static vector Objective(SCR_CampaignMilitaryBaseComponent base)
	{
		array<SCR_SeizingComponent> points = {};
		base.GetCapturePoints(points);
		if (!points.IsEmpty() && points[0] && points[0].GetOwner())
			return points[0].GetOwner().GetOrigin();
		return base.GetOwner().GetOrigin();
	}

	protected static void End(SCR_AIGroup group, array<AIAgent> agents)
	{
		if (!s_mState.Contains(group))
			return;
		s_mState.Remove(group);
		foreach (AIAgent agent : agents)
		{
			if (agent && agent.GetControlledEntity())
				s_mHolding.Remove(agent.GetControlledEntity());
		}
	}

	// Per squad, from the cover layer's tick: true when the squad bounds (the cover layer leaves it).
	static bool Tick(AICF_GroupSlot slot, FactionKey side, IEntity leader, array<AIAgent> agents, int now)
	{
		if (!On())
			return false;
		SCR_AIGroup group = slot.GetGroup();
		SCR_CampaignMilitaryBaseComponent base = slot.GetTargetBase();
		if (!base || slot.GetRole() != AICF_EGroupRole.ATTACK || !leader)
		{
			End(group, agents);
			return false;
		}
		vector dest = Objective(base);
		IEntity enemy = ZCR_CoverLayer.NearestEnemy(leader);
		float enemyAt = 1e9;
		if (enemy)
			enemyAt = vector.DistanceXZ(enemy.GetOrigin(), leader.GetOrigin());
		if (vector.DistanceXZ(leader.GetOrigin(), dest) < 40 || enemyAt > RANGE || enemyAt < CLOSE)
		{
			End(group, agents);
			return false;
		}
		array<ChimeraCharacter> men = {};
		array<AIAgent> theirs = {};
		foreach (AIAgent agent : agents)
		{
			ChimeraCharacter man;
			if (agent)
				man = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (!man || man.IsInVehicle())
				continue;
			CharacterControllerComponent ctl = man.GetCharacterController();
			if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
				continue;
			men.Insert(man);
			theirs.Insert(agent);
		}
		if (men.Count() < MIN_MEN)
		{
			End(group, agents);
			return false;
		}
		ZCR_BoundState st = s_mState.Get(group);
		if (!st)
		{
			st = new ZCR_BoundState();
			s_mState.Set(group, st);
		}
		vector threat = ZCR_CoverLayer.EyeOf(enemy);
		bool arrived = true;
		for (int i; i < st.m_aMovers.Count(); i++)
		{
			IEntity m = st.m_aMovers[i];
			if (m && vector.DistanceXZ(m.GetOrigin(), st.m_aSpots[i]) > 4)
				arrived = false;
		}
		if (arrived || now - st.m_iSince > SWAP)
		{
			// Swap: the other half moves now.
			st.m_iHalf = 1 - st.m_iHalf;
			st.m_aMovers.Clear();
			st.m_aSpots.Clear();
			int covered;
			for (int j; j < men.Count(); j++)
			{
				if (j % 2 != st.m_iHalf)
					continue;
				ChimeraCharacter mover = men[j];
				vector from = mover.GetOrigin();
				vector to = dest - from;
				to[1] = 0;
				float left = to.Length() - 15;
				if (left <= 5)
					continue;
				to.Normalize();
				float step = Math.Min(35 + Math.RandomFloat(0, 25), left);
				// Never nearer than 30 m to the enemy.
				step = Math.Min(step, vector.DistanceXZ(from, enemy.GetOrigin()) - 30);
				if (step < 10)
					continue;
				vector aim = from + to * step;
				aim[1] = GetGame().GetWorld().GetSurfaceY(aim[0], aim[2]);
				vector spot = aim;
				if (ZCR_CoverLayer.CoverAround(mover, theirs[j], aim, threat, enemy, spot))
					covered++;
				else
					spot = aim;
				SCR_AIUtilityComponent utility = SCR_AIUtilityComponent.Cast(theirs[j].FindComponent(SCR_AIUtilityComponent));
				if (!utility)
					continue;
				utility.AddAction(new SCR_AIMoveIndividuallyBehavior(utility, null, spot, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_INDIVIDUALLY, 40, null, 1.0));
				if (utility.m_CombatMoveState)
					utility.m_CombatMoveState.ApplyRequestChangeStanceOutsideCover(ECharacterStance.CROUCH);
				st.m_aMovers.Insert(mover);
				st.m_aSpots.Insert(spot);
			}
			st.m_iSince = now;
			Print(string.Format("[ZCR][BOUND] t=%1 side=%2 slot=%3 half=%4 movers=%5 covered=%6 men=%7 to_objective=%8 enemy_m=%9", now, side,
				slot.GetSlotId(), st.m_iHalf, st.m_aMovers.Count(), covered, men.Count(), Math.Round(vector.DistanceXZ(leader.GetOrigin(), dest)),
				Math.Round(vector.DistanceXZ(enemy.GetOrigin(), leader.GetOrigin()))), LogLevel.NORMAL);
		}
		// The other half covers.
		for (int k; k < men.Count(); k++)
		{
			if (k % 2 != st.m_iHalf)
				s_mHolding.Set(men[k], now + SWAP + 5);
			else
				s_mHolding.Remove(men[k]);
		}
		return true;
	}
}
