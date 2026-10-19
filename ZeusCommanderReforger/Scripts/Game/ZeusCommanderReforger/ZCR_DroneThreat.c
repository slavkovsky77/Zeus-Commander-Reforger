// Soldiers react to enemy FPV drones (Martin, 19 Oct: "infantry just walks exposed - they can be chill
// with no danger, but with danger from drones they really should run like hell to cover"; Arma 3's
// ZC_fnc_droneThreat). Every second, for every commanders' drone in the air: soldiers on foot of the
// other sides within 250 m of it (an FPV is heard; was 150) react, each at most every 15 s -
//   - under a roof or tree canopy already: stay, crouched;
//   - overhead cover (canopy, a building) within 40 m, the far side from the drone first, each soldier
//     his own spot 6 m from the others: run there;
//   - none: spread out (15-25 m away from the drone, each his own way, 8 m apart), down when it comes again.
// When a drone goes off, the survivors within 40 m scatter 20-35 m, each his own way, into overhead
// cover where there is some - not standing round the bodies waiting for the next one (Arma 3 v50).
// Both sides (the soldiers' own reflex, not a commander's choice); -zcrNoDroneReact turns it off.
// Measured every 10 s: [ZCR][DRONETHREAT] t= side= near= (soldiers within 150 m of an enemy drone)
// covered= (% under a roof or canopy) reacting= (% running to cover now) prone=.
class ZCR_DroneSeen
{
	IEntity m_Drone;
	vector m_vAt;
	string m_sSide;
}

class ZCR_DroneThreat
{
	protected static ref ZCR_DroneThreat s_Instance;
	protected static bool s_bStarted;
	protected static ref map<IEntity, int> s_mReactedAt = new map<IEntity, int>();
	protected static ref map<IEntity, int> s_mRunningUntil = new map<IEntity, int>();
	// Drones in the air, with where each was last seen - kept in a list (a map keyed by the drone loses
	// the entry when the drone is deleted, so the scatter after a hit never ran).
	protected static ref array<ref ZCR_DroneSeen> s_aSeen = {};
	protected static ref array<IEntity> s_aFound = {};
	protected static ref TraceParam s_Trace;
	protected static int s_iNextLog;
	protected static int s_iNextDisperse;
	protected static ref map<IEntity, vector> s_mWas = new map<IEntity, vector>();
	static const float REACT = 250;      // an FPV is heard well before it arrives (was 150)
	protected static ref map<IEntity, int> s_mSpreadAt = new map<IEntity, int>();
	static const int COOLDOWN = 15;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoDroneReact"))
			return;
		s_bStarted = true;
		s_Instance = new ZCR_DroneThreat();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		array<vector> taken = {};
		map<string, int> near = new map<string, int>();
		map<string, int> covered = new map<string, int>();
		map<string, int> running = new map<string, int>();
		map<string, int> prone = new map<string, int>();
		// Drones that went off since the last tick: scatter the survivors round where they were.
		for (int g = s_aSeen.Count() - 1; g >= 0; g--)
		{
			if (s_aSeen[g].m_Drone)
				continue;
			Scatter(s_aSeen[g].m_vAt, s_aSeen[g].m_sSide, now);
			s_aSeen.Remove(g);
		}
		for (int i; i < ZCR_Drones.s_aDrones.Count(); i++)
		{
			IEntity drone = ZCR_Drones.s_aDrones[i];
			if (!drone)
				continue;
			string droneSide = ZCR_Drones.s_aDroneSide[i];
			vector dp = drone.GetOrigin();
			if (dp[1] - GetGame().GetWorld().GetSurfaceY(dp[0], dp[2]) < 2)
				continue;
			ZCR_DroneSeen seen;
			foreach (ZCR_DroneSeen x : s_aSeen)
			{
				if (x.m_Drone == drone)
					seen = x;
			}
			if (!seen)
			{
				seen = new ZCR_DroneSeen();
				seen.m_Drone = drone;
				seen.m_sSide = droneSide;
				s_aSeen.Insert(seen);
			}
			seen.m_vAt = dp;
			s_aFound.Clear();
			GetGame().GetWorld().QueryEntitiesBySphere(dp, REACT, s_Instance.AddMan, null, EQueryEntitiesFlags.DYNAMIC);
			foreach (IEntity e : s_aFound)
			{
				ChimeraCharacter c = ChimeraCharacter.Cast(e);
				string side = ZCR_LossLog.SideOf(e);
				if (!c || c.IsInVehicle() || side == droneSide || side.IsEmpty())
					continue;
				CharacterControllerComponent ctl = c.GetCharacterController();
				if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
					continue;
				near.Set(side, near.Get(side) + 1);
				bool over = Overhead(c.EyePosition(), c);
				if (over)
					covered.Set(side, covered.Get(side) + 1);
				if (s_mRunningUntil.Contains(c) && now < s_mRunningUntil.Get(c))
					running.Set(side, running.Get(side) + 1);
				if (ctl.GetStance() == ECharacterStance.PRONE)
					prone.Set(side, prone.Get(side) + 1);
				if (now - s_mReactedAt.Get(c) < COOLDOWN && s_mReactedAt.Contains(c))
					continue;
				s_mReactedAt.Set(c, now);
				React(c, dp, over, now, taken);
			}
		}
		if (now >= s_iNextDisperse)
		{
			s_iNextDisperse = now + 10;
			Disperse(now);
		}
		if (now >= s_iNextLog)
		{
			s_iNextLog = now + 10;
			foreach (string side, int n : near)
			{
				if (n > 0)
					Print(string.Format("[ZCR][DRONETHREAT] t=%1 side=%2 near=%3 covered=%4 reacting=%5 prone=%6", now, side, n,
						Math.Round(100.0 * covered.Get(side) / n), Math.Round(100.0 * running.Get(side) / n), Math.Round(100.0 * prone.Get(side) / n)), LogLevel.NORMAL);
			}
		}
	}

	protected bool AddMan(IEntity e)
	{
		if (ChimeraCharacter.Cast(e))
			s_aFound.Insert(e);
		return true;
	}

	protected static SCR_AIUtilityComponent Utility(ChimeraCharacter c)
	{
		AIControlComponent control = AIControlComponent.Cast(c.FindComponent(AIControlComponent));
		if (!control || !control.GetControlAIAgent())
			return null;
		return SCR_AIUtilityComponent.Cast(control.GetControlAIAgent().FindComponent(SCR_AIUtilityComponent));
	}

	// Under cover from above, or run to some (each his own spot), or spread out, then get down.
	protected static void React(ChimeraCharacter c, vector from, bool over, int now, array<vector> taken)
	{
		SCR_AIUtilityComponent utility = Utility(c);
		if (!utility)
			return;
		if (over)
		{
			if (utility.m_CombatMoveState)
				utility.m_CombatMoveState.ApplyRequestChangeStanceOutsideCover(ECharacterStance.CROUCH);
			return;
		}
		vector spot;
		if (FindOverhead(c, from, 40, spot, vector.Zero, taken))
		{
			// Above the attack (90) and the cover layer (98): a drone overhead comes first.
			taken.Insert(spot);
			utility.AddAction(new SCR_AIMoveIndividuallyBehavior(utility, null, spot, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_INDIVIDUALLY, 70, null, 1.0));
			s_mRunningUntil.Set(c, now + 12);
			return;
		}
		// No cover near: spread out first - away from the drone, each his own way, 15-25 m, at least
		// 8 m from the others - so one drone can't take the team; down when it comes again.
		if (!s_mSpreadAt.Contains(c) || now - s_mSpreadAt.Get(c) > 40)
		{
			vector away = c.GetOrigin() - from;
			away[1] = 0;
			if (away.Length() < 1)
				away = Vector(1, 0, 0);
			away.Normalize();
			for (int tries; tries < 6; tries++)
			{
				float r = Math.RandomFloat(-80, 80) * Math.DEG2RAD;
				vector dir = Vector(away[0] * Math.Cos(r) - away[2] * Math.Sin(r), 0, away[0] * Math.Sin(r) + away[2] * Math.Cos(r));
				vector run = c.GetOrigin() + dir * Math.RandomFloat(15, 25);
				bool crowded;
				foreach (vector q : taken)
				{
					if (vector.DistanceXZ(q, run) < 8)
						crowded = true;
				}
				if (crowded)
					continue;
				run[1] = GetGame().GetWorld().GetSurfaceY(run[0], run[2]);
				taken.Insert(run);
				utility.AddAction(new SCR_AIMoveIndividuallyBehavior(utility, null, run, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_INDIVIDUALLY, 70, null, 2.0));
				s_mRunningUntil.Set(c, now + 8);
				s_mSpreadAt.Set(c, now);
				return;
			}
		}
		if (utility.m_CombatMoveState)
			utility.m_CombatMoveState.ApplyRequestChangeStanceOutsideCover(ECharacterStance.PRONE);
	}

	// After a drone went off: everyone within 40 m runs 20-35 m off, each his own way.
	protected static void Scatter(vector at, string droneSide, int now)
	{
		s_aFound.Clear();
		GetGame().GetWorld().QueryEntitiesBySphere(at, 40, s_Instance.AddMan, null, EQueryEntitiesFlags.DYNAMIC);
		int n;
		float a0 = Math.RandomFloat(0, 360);
		foreach (int k, IEntity e : s_aFound)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(e);
			if (!c || c.IsInVehicle() || ZCR_LossLog.SideOf(e) == droneSide)
				continue;
			CharacterControllerComponent ctl = c.GetCharacterController();
			if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
				continue;
			SCR_AIUtilityComponent utility = Utility(c);
			if (!utility)
				continue;
			float r = (a0 + k * 70) * Math.DEG2RAD;
			vector aim = c.GetOrigin() + Vector(Math.Cos(r), 0, Math.Sin(r)) * Math.RandomFloat(20, 35);
			vector spot = aim;
			FindOverhead(c, at, 15, spot, aim);
			utility.AddAction(new SCR_AIMoveIndividuallyBehavior(utility, null, spot, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_INDIVIDUALLY, 70, null, 1.0));
			s_mRunningUntil.Set(c, now + 12);
			s_mReactedAt.Set(c, now);
			n++;
		}
		if (n > 0)
			Print(string.Format("[ZCR][DRONETHREAT] t=%1 scatter=%2 at=%3 %4", now, n, Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
	}

	// Nobody waits in the open at a base (Martin, 19 Oct 22:00: "enemy infantry chilling on the base
	// while getting massacred by drones"; teams waiting there for a vehicle, a recruit or an order stood
	// bunched in the field; then "infantry should not stay out in the open, hide in cover, ideally in
	// buildings"). Every 10 s: a soldier on foot who hasn't moved 3 m in 10 s, anywhere, with no enemy
	// known within 300 m (a fight is the game's own business - the cover layer holds it there) and
	// nothing overhead goes to a spot under a roof or canopy within 40 m, at least 6 m from the others
	// sent this round. Both sides. Logs [ZCR][DISPERSE] t= side= idle= open= moved=.
	protected static void Disperse(int now)
	{
		map<IEntity, vector> was = s_mWas;
		s_mWas = new map<IEntity, vector>();
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		array<vector> taken = {};
		map<string, int> idle = new map<string, int>();
		map<string, int> open = new map<string, int>();
		map<string, int> moved = new map<string, int>();
		foreach (AIAgent agent : agents)
		{
			if (!agent)
				continue;
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (!c || c.IsInVehicle())
				continue;
			string side = ZCR_LossLog.SideOf(c);
			if (side != "US" && side != "USSR")
				continue;
			CharacterControllerComponent ctl = c.GetCharacterController();
			if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
				continue;
			vector p = c.GetOrigin();
			s_mWas.Set(c, p);
			vector before;
			if (!was.Find(c, before) || vector.DistanceXZ(before, p) > 3)
				continue;
			if (ZCR_Sampler.KnownEnemiesNear(side, p, 300) > 0)
				continue;
			idle.Set(side, idle.Get(side) + 1);
			if (Overhead(c.EyePosition(), c))
				continue;
			open.Set(side, open.Get(side) + 1);
			SCR_AIUtilityComponent utility = Utility(c);
			vector spot;
			if (!utility || !FindOverhead(c, p, 40, spot, vector.Zero, taken))
				continue;
			taken.Insert(spot);
			utility.AddAction(new SCR_AIMoveIndividuallyBehavior(utility, null, spot, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_INDIVIDUALLY, 10, null, 1.0));
			moved.Set(side, moved.Get(side) + 1);
		}
		foreach (string side, int n : idle)
			Print(string.Format("[ZCR][DISPERSE] t=%1 side=%2 idle=%3 open=%4 moved=%5", now, side, n, open.Get(side), moved.Get(side)), LogLevel.NORMAL);
	}

	// A spot within 'radius' (of 'center', default the soldier) under a roof or canopy, on the navmesh,
	// nearest first and the far side from 'threat' first; none within 6 m of 'avoid'.
	protected static bool FindOverhead(ChimeraCharacter c, vector threat, float radius, out vector spot, vector center = vector.Zero, array<vector> avoid = null)
	{
		AIControlComponent control = AIControlComponent.Cast(c.FindComponent(AIControlComponent));
		AIPathfindingComponent pathfinding;
		if (control && control.GetControlAIAgent())
			pathfinding = AIPathfindingComponent.Cast(control.GetControlAIAgent().FindComponent(AIPathfindingComponent));
		BaseWorld world = GetGame().GetWorld();
		vector here = center;
		if (here == vector.Zero)
			here = c.GetOrigin();
		vector away = here - threat;
		away[1] = 0;
		if (away.Length() < 1)
			away = Vector(1, 0, 0);
		away.Normalize();
		array<float> dists = {0, 6, 12, 18, 24, 30, 36};
		array<float> angles = {0, 45, -45, 90, -90, 135, -135, 180};
		foreach (float d : dists)
		{
			if (d > radius)
				break;
			foreach (float a : angles)
			{
				if (d == 0 && a != 0)
					continue;
				float r = a * Math.DEG2RAD;
				vector dir = Vector(away[0] * Math.Cos(r) - away[2] * Math.Sin(r), 0, away[0] * Math.Sin(r) + away[2] * Math.Cos(r));
				vector p = here + dir * d;
				p[1] = world.GetSurfaceY(p[0], p[2]);
				if (!Overhead(p + Vector(0, 1.2, 0), c))
					continue;
				vector nav = p;
				if (pathfinding && !pathfinding.GetClosestPositionOnNavmesh(p, "2 3 2", nav))
					continue;
				if (vector.DistanceXZ(nav, p) > 2)
					continue;
				bool crowded;
				if (avoid)
				{
					foreach (vector q : avoid)
					{
						if (vector.DistanceXZ(q, nav) < 6)
							crowded = true;
					}
				}
				if (crowded)
					continue;
				spot = nav;
				return true;
			}
		}
		return false;
	}

	// Something above within 15 m: a roof, a tree crown.
	static bool Overhead(vector eye, IEntity self)
	{
		if (!s_Trace)
			s_Trace = new TraceParam();
		s_Trace.Flags = TraceFlags.ENTS | TraceFlags.WORLD;
		s_Trace.TargetLayers = EPhysicsLayerDefs.ViewGeometry | EPhysicsLayerDefs.Foliage | EPhysicsLayerDefs.FireGeometry;
		s_Trace.Exclude = self;
		s_Trace.Start = eye + Vector(0, 0.3, 0);
		s_Trace.End = eye + Vector(0, 15, 0);
		return GetGame().GetWorld().TraceMove(s_Trace, null) < 1.0;
	}
}
