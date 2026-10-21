// A soldier layer like Arma 3's "cover in a firefight" (zeus-commander fn_coverFight.sqf): Reforger's
// AI fights from cover only 1-10% of the time (ZCR_Sampler; Arma 3 with this layer 30-40%).
// Every commander tick, for the side with our strategist: each soldier on foot (not the squad
// leader, who keeps the squad's orders) who knows an enemy within 400 m and has nothing solid
// within 3 m toward it (and no roof) moves to the nearest spot 6-25 m away, preferring the side
// away from the enemy, that is on the navmesh and has cover toward the enemy - at most every 20 s.
// Not in a squad storming its objective (Arma 3: then everyone goes in). The move is the game's
// own individual move at priority 58 + 40 = 98: above shooting a chosen target (90), below the
// danger reactions; he fights from there, crouched (the cover is measured at eye height), and
// rejoins his squad when it moves on. With no covered spot within 25 m he goes prone (Arma 3: in the
// open he lies down) - both through the game's own combat-move stance request.
// On by default from r9 (probe: from cover 1.4-6.7% -> 11.6%, the attack as fast); -zcrNoCoverLayer
// turns it off for an A/B. Logs [ZCR][COVERMOVE] per tick.
// r10 - work with the game's own cover system instead of against it (second probe: 11.6% -> 5.3%):
//   - a soldier in the game's own cover, or on his way to it, is left alone (before, one exposed to
//     shoot over his cover could be sent away from it, and our stance request cancelled his move);
//   - in the game's attack he holds his cover at least 20 s before moving on (the game: 5 s; Arma 3:
//     20 s) - modded SCR_AICombatMoveLogic_Attack below;
//   - a soldier in the open in the game's attack asks the game's own cover search for cover within
//     25 m (a cover point the game knows how to fight from, so he holds it); others as before.
//   [ZCR][COVERMOVE] adds native= (in or moving to the game's cover), asked= (sent to it), and the
//   outcome of the previous tick's asks: found= / nocover=.
class ZCR_CoverLayer
{
	// Martin (19 Oct 23:35): "reckless soldiers" - in the 23:22 match gunfire kills happened at a median
	// of 6 m: the game's attack closes on a seen enemy until 15 m. Soldiers now hold at 60 m from an
	// enemy seen in the last 15 s and fight from there (-zcrStandoff), except within 150 m of an
	// enemy-held base, where the objective has to be cleared.
	static float Standoff()
	{
		string value;
		if (System.GetCLIParam("zcrStandoff", value) && !value.IsEmpty())
			return value.ToFloat();
		return 60;
	}

	static bool NearEnemyBase(IEntity soldier)
	{
		string side = ZCR_LossLog.SideOf(soldier);
		vector at = soldier.GetOrigin();
		foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
		{
			string owner = ZCR_Strategist.s_mNodeOwner.Get(node);
			if (!owner.IsEmpty() && owner != side && vector.DistanceXZ(pos, at) < 150)
				return true;
		}
		return false;
	}

	protected static ref map<IEntity, int> s_mMovedAt = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mHold = new map<IEntity, int>();
	protected static ref map<IEntity, ref SCR_AICombatMoveRequest_Move> s_mAsked = new map<IEntity, ref SCR_AICombatMoveRequest_Move>();
	static const float HOLD_IN_COVER = 20;
	protected static ref TraceParam s_Trace;
	protected static ref array<IEntity> s_aExclude = {};
	protected static const float LEVEL = 40;
	protected static const float RANGE = 400;

	static void Tick(FactionKey side, AICF_FactionState state)
	{
		if (!Replication.IsServer() || !state || System.IsCLIParam("zcrNoCoverLayer"))
			return;
		int now = ZCR_LossLog.Seconds();
		int engaged, open, moved, prone, inGame, asked, found, nocover;
		// How the last asks went.
		foreach (IEntity asker, SCR_AICombatMoveRequest_Move last : s_mAsked)
		{
			if (!last || last.m_eState == SCR_EAICombatMoveRequestState.EXECUTING)
				continue;
			if (last.m_eState == SCR_EAICombatMoveRequestState.SUCCESS)
				found++;
			else if (last.m_eFailReason == SCR_EAICombatMoveRequestFailReason.COVER_NOT_FOUND)
				nocover++;
		}
		s_mAsked.Clear();
		for (int s; s < state.GetSlotCount(); s++)
		{
			AICF_GroupSlot slot = state.GetSlot(s);
			if (!slot || !slot.GetGroup())
				continue;
			if (slot.GetTargetBase() && ZCR_Storm.IsStormed(side, slot.GetTargetBase()))
				continue;
			IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(slot.GetGroup());
			array<AIAgent> agents = {};
			slot.GetGroup().GetAgents(agents);
			// Close to the enemy and still advancing: the squad bounds (ZCR_Bound), not cover-to-cover alone.
			if (ZCR_Bound.Tick(slot, side, leader, agents, now))
				continue;
			foreach (AIAgent agent : agents)
			{
				ChimeraCharacter c;
				if (agent)
					c = ChimeraCharacter.Cast(agent.GetControlledEntity());
				if (!c || c == leader || c.IsInVehicle())
					continue;
				CharacterControllerComponent ctl = c.GetCharacterController();
				if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
					continue;
				IEntity enemy = NearestEnemy(c);
				if (!enemy)
					continue;
				engaged++;
				SCR_AIUtilityComponent utility = SCR_AIUtilityComponent.Cast(agent.FindComponent(SCR_AIUtilityComponent));
				if (!utility)
					continue;
				s_mHold.Set(c, now);
				// In the game's own cover, or on his way to it: leave him be.
				SCR_AICombatMoveState cm = utility.m_CombatMoveState;
				if (cm && (cm.m_bInCover || cm.IsMovingToCover()))
				{
					inGame++;
					continue;
				}
				vector eye = c.EyePosition();
				vector threat = EyeOf(enemy);
				if (Covered(eye, threat, c, enemy) || Roof(eye, c))
					continue;
				open++;
				if (now - s_mMovedAt.Get(c) < 20)
					continue;
				// In the game's attack: its own cover search, within 25 m.
				if (cm && SCR_AIAttackBehavior.Cast(utility.GetCurrentAction()) && !cm.IsExecutingRequest())
				{
					SCR_AICombatMoveRequest_Move rq = CoverRequest(c, threat);
					cm.ApplyNewRequest(rq);
					s_mAsked.Set(c, rq);
					s_mMovedAt.Set(c, now);
					asked++;
					continue;
				}
				vector spot;
				if (!FindCover(c, agent, threat, enemy, spot))
				{
					// Nothing to get behind: lie down and fight from there.
					if (utility.m_CombatMoveState && ctl.GetStance() != ECharacterStance.PRONE)
					{
						utility.m_CombatMoveState.ApplyRequestChangeStanceOutsideCover(ECharacterStance.PRONE);
						s_mMovedAt.Set(c, now);
						prone++;
					}
					continue;
				}
				ZCR_Reserved.Add(utility, new SCR_AIMoveIndividuallyBehavior(utility, null, spot, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_INDIVIDUALLY, LEVEL, null, 1.0));
				if (utility.m_CombatMoveState)
					utility.m_CombatMoveState.ApplyRequestChangeStanceOutsideCover(ECharacterStance.CROUCH);
				s_mMovedAt.Set(c, now);
				moved++;
			}
		}
		if (engaged > 0)
			Print(string.Format("[ZCR][COVERMOVE] t=%1 side=%2 engaged=%3 open=%4 moved=%5 prone=%6 native=%7 asked=%8", now, side, engaged, open, moved, prone, inGame, asked)
				+ string.Format(" found=%1 nocover=%2", found, nocover), LogLevel.NORMAL);
	}

	// A soldier of a side with our strategist, in a fight in the last 20 s and not storming: he holds
	// the game's cover longer (modded SCR_AICombatMoveLogic_Attack).
	static bool Holds(IEntity soldier)
	{
		if (!soldier || !s_mHold.Contains(soldier))
			return false;
		return ZCR_LossLog.Seconds() - s_mHold.Get(soldier) <= 20;
	}

	// The game's own combat move to cover near him (like its "leave useless cover" request): cover
	// within 25 m of where he is, from which he can see the enemy, crouched; fails if there is none.
	protected static SCR_AICombatMoveRequest_Move CoverRequest(ChimeraCharacter c, vector threat)
	{
		SCR_AICombatMoveRequest_Move rq = new SCR_AICombatMoveRequest_Move();
		rq.m_eReason = SCR_EAICombatMoveReason.STANDARD;
		rq.m_vTargetPos = threat;
		rq.m_vMovePos = c.GetOrigin();
		rq.m_bTryFindCover = true;
		rq.m_bUseCoverSearchDirectivity = false;
		rq.m_bCheckCoverVisibility = true;
		rq.m_bFailIfNoCover = true;
		rq.m_eStanceMoving = ECharacterStance.CROUCH;
		rq.m_eStanceEnd = ECharacterStance.CROUCH;
		rq.m_eMovementType = EMovementType.RUN;
		rq.m_eDirection = SCR_EAICombatMoveDirection.ANYWHERE;
		rq.m_fCoverSearchSectorHalfAngleRad = -1.0;
		rq.m_bAimAtTarget = SCR_AICombatMoveUtils.IsAimingAndMovementPossible(rq.m_eStanceMoving, rq.m_eMovementType);
		rq.m_bAimAtTargetEnd = true;
		rq.m_fCoverSearchDistMin = 0;
		rq.m_fCoverSearchDistMax = 25;
		return rq;
	}

	// Of the soldiers on foot, whether he is in the game's own cover (for [ZCR][EXPOSURE]).
	static bool InGameCover(IEntity soldier)
	{
		AIControlComponent control = AIControlComponent.Cast(soldier.FindComponent(AIControlComponent));
		if (!control || !control.GetControlAIAgent())
			return false;
		SCR_AIUtilityComponent utility = SCR_AIUtilityComponent.Cast(control.GetControlAIAgent().FindComponent(SCR_AIUtilityComponent));
		return utility && utility.m_CombatMoveState && utility.m_CombatMoveState.m_bInCover;
	}

	static vector EyeOf(IEntity e)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(e);
		if (c)
			return c.EyePosition();
		return e.GetOrigin() + Vector(0, 1.5, 0);
	}

	static IEntity NearestEnemy(IEntity soldier)
	{
		PerceptionComponent perception = PerceptionComponent.Cast(soldier.FindComponent(PerceptionComponent));
		if (!perception)
			return null;
		array<BaseTarget> targets = {};
		perception.GetTargetsList(targets, ETargetCategory.ENEMY);
		IEntity best;
		float bestDistance = RANGE;
		foreach (BaseTarget t : targets)
		{
			if (!t || !t.GetTargetEntity())
				continue;
			float d = vector.Distance(soldier.GetOrigin(), t.GetTargetEntity().GetOrigin());
			if (d < bestDistance)
			{
				bestDistance = d;
				best = t.GetTargetEntity();
			}
		}
		return best;
	}

	// A spot within 25 m with cover toward the threat, on the navmesh, nearest first; candidates
	// away from the enemy come first at each distance.
	protected static bool FindCover(ChimeraCharacter c, AIAgent agent, vector threat, IEntity enemy, out vector spot)
	{
		AIPathfindingComponent pathfinding = AIPathfindingComponent.Cast(agent.FindComponent(AIPathfindingComponent));
		BaseWorld world = GetGame().GetWorld();
		vector here = c.GetOrigin();
		vector away = here - threat;
		away[1] = 0;
		if (away.Length() < 1)
			return false;
		away.Normalize();
		array<float> dists = {6, 10, 15, 20, 25};
		array<float> angles = {0, 35, -35, 70, -70, 110, -110};
		foreach (float d : dists)
		{
			foreach (float a : angles)
			{
				float r = a * Math.DEG2RAD;
				vector dir = Vector(away[0] * Math.Cos(r) - away[2] * Math.Sin(r), 0, away[0] * Math.Sin(r) + away[2] * Math.Cos(r));
				vector p = here + dir * d;
				p[1] = world.GetSurfaceY(p[0], p[2]);
				vector nav = p;
				if (pathfinding && !pathfinding.GetClosestPositionOnNavmesh(p, "2 3 2", nav))
					continue;
				if (vector.DistanceXZ(nav, p) > 2)
					continue;
				vector eye = nav + Vector(0, 1.0, 0);   // crouched behind it
				if (Covered(eye, threat, c, enemy))
				{
					spot = nav;
					return true;
				}
			}
		}
		return false;
	}

	// A spot within 20 m of 'center' with cover toward the threat, on the navmesh, nearest first (the
	// bounding's next cover).
	static bool CoverAround(ChimeraCharacter c, AIAgent agent, vector center, vector threat, IEntity enemy, out vector spot)
	{
		AIPathfindingComponent pathfinding = AIPathfindingComponent.Cast(agent.FindComponent(AIPathfindingComponent));
		BaseWorld world = GetGame().GetWorld();
		array<float> dists = {0, 5, 10, 15, 20};
		for (int k; k < dists.Count(); k++)
		{
			int n = 1;
			if (dists[k] > 0)
				n = 8;
			for (int i; i < n; i++)
			{
				float r = i * 45 * Math.DEG2RAD;
				vector p = center + Vector(Math.Cos(r), 0, Math.Sin(r)) * dists[k];
				p[1] = world.GetSurfaceY(p[0], p[2]);
				vector nav = p;
				if (pathfinding && !pathfinding.GetClosestPositionOnNavmesh(p, "2 3 2", nav))
					continue;
				if (vector.DistanceXZ(nav, p) > 2)
					continue;
				if (Covered(nav + Vector(0, 1.0, 0), threat, c, enemy))
				{
					spot = nav;
					return true;
				}
			}
		}
		return false;
	}

	protected static bool Covered(vector eye, vector threat, IEntity self, IEntity other)
	{
		vector dir = threat - eye;
		if (dir.Length() < 0.5)
			return false;
		dir.Normalize();
		return Trace(eye, eye + dir * 3, self, other, TraceFlags.ENTS | TraceFlags.WORLD, EPhysicsLayerDefs.FireGeometry | EPhysicsLayerDefs.Terrain);
	}

	protected static bool Roof(vector eye, IEntity self)
	{
		return Trace(eye + Vector(0, 0.3, 0), eye + Vector(0, 15, 0), self, null, TraceFlags.ENTS, EPhysicsLayerDefs.FireGeometry);
	}

	protected static bool Trace(vector from, vector to, IEntity self, IEntity other, TraceFlags flags, int layers)
	{
		if (!s_Trace)
		{
			s_Trace = new TraceParam();
			s_Trace.ExcludeArray = s_aExclude;
		}
		s_aExclude.Clear();
		if (self)
			s_aExclude.Insert(self);
		if (other)
		{
			s_aExclude.Insert(other);
			if (other.GetRootParent() && other.GetRootParent() != other)
				s_aExclude.Insert(other.GetRootParent());
		}
		s_Trace.TargetLayers = layers;
		s_Trace.Flags = flags;
		s_Trace.Start = from;
		s_Trace.End = to;
		return GetGame().GetWorld().TraceMove(s_Trace, null) < 1.0;
	}
}

// The game's attack moves a soldier on after 5 s in cover when he isn't under fire (20 s when he is);
// ours hold it at least 20 s (Arma 3's cover layer), so they fight from it.
modded class SCR_AICombatMoveLogic_Attack
{
	// Hold at the standoff from a seen enemy instead of closing to 15 m (ZCR_CoverLayer.Standoff).
	override protected bool MoveToNextPosCondition()
	{
		if (m_Target && m_MyEntity && m_fTargetDist < ZCR_CoverLayer.Standoff() && m_Target.GetTimeSinceSeen() < 15
			&& !ZCR_CoverLayer.NearEnemyBase(m_MyEntity))
			return false;
		return super.MoveToNextPosCondition();
	}

	protected override float ResolveStoppedWaitTime(bool inCover, EAIThreatState threat, EWeaponType weaponType)
	{
		float wait = super.ResolveStoppedWaitTime(inCover, threat, weaponType);
		// Bounding: the half that covers stays where it is and shoots while the other half moves.
		if (ZCR_Bound.Holds(m_MyEntity))
			return 1000;
		if (inCover && ZCR_CoverLayer.Holds(m_MyEntity))
			return Math.Max(wait, ZCR_CoverLayer.HOLD_IN_COVER);
		return wait;
	}
}
