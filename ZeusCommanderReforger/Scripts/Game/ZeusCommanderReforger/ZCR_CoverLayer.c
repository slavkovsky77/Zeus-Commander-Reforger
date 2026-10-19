// A soldier layer like Arma 3's "cover in a firefight" (zeus-commander fn_coverFight.sqf): Reforger's
// AI fights from cover only 1-10% of the time (ZCR_Sampler; Arma 3 with this layer 30-40%).
// Every commander tick, for the side with our strategist: each soldier on foot (not the squad
// leader, who keeps the squad's orders) who knows an enemy within 400 m and has nothing solid
// within 3 m toward it (and no roof) moves to the nearest spot 6-25 m away, preferring the side
// away from the enemy, that is on the navmesh and has cover toward the enemy - at most every 20 s.
// Not in a squad storming its objective (Arma 3: then everyone goes in). The move is the game's
// own individual move at priority 58 + 40 = 98: above shooting a chosen target (90), below the
// danger reactions; he fights from there, and rejoins his squad when it moves on.
// Lab option -zcrCoverLayer (off by default until measured). Logs [ZCR][COVERMOVE] per tick.
class ZCR_CoverLayer
{
	protected static ref map<IEntity, int> s_mMovedAt = new map<IEntity, int>();
	protected static ref TraceParam s_Trace;
	protected static ref array<IEntity> s_aExclude = {};
	protected static const float LEVEL = 40;
	protected static const float RANGE = 400;

	static void Tick(FactionKey side, AICF_FactionState state)
	{
		if (!Replication.IsServer() || !state || !System.IsCLIParam("zcrCoverLayer"))
			return;
		int now = ZCR_LossLog.Seconds();
		int engaged, open, moved;
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
				vector eye = c.EyePosition();
				vector threat = EyeOf(enemy);
				if (Covered(eye, threat, c, enemy) || Roof(eye, c))
					continue;
				open++;
				if (now - s_mMovedAt.Get(c) < 20)
					continue;
				vector spot;
				if (!FindCover(c, agent, threat, enemy, spot))
					continue;
				SCR_AIUtilityComponent utility = SCR_AIUtilityComponent.Cast(agent.FindComponent(SCR_AIUtilityComponent));
				if (!utility)
					continue;
				utility.AddAction(new SCR_AIMoveIndividuallyBehavior(utility, null, spot, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_INDIVIDUALLY, LEVEL, null, 1.0));
				s_mMovedAt.Set(c, now);
				moved++;
			}
		}
		if (engaged > 0)
			Print(string.Format("[ZCR][COVERMOVE] t=%1 side=%2 engaged=%3 open=%4 moved=%5", now, side, engaged, open, moved), LogLevel.NORMAL);
	}

	protected static vector EyeOf(IEntity e)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(e);
		if (c)
			return c.EyePosition();
		return e.GetOrigin() + Vector(0, 1.5, 0);
	}

	protected static IEntity NearestEnemy(IEntity soldier)
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
