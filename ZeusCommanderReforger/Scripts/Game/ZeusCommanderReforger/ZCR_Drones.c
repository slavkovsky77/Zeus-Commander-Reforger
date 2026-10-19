// FPV drone teams for the commanders (-zcrDrones on the server; needs Martin's FPV AI Drones and
// Realistic Combat Drones loaded). A team of 4 AI-flown FPVs starts at the side's own base nearest
// its target and flies there with a Move waypoint; the drones go for enemy soldiers within 200 m
// (anti-infantry) or vehicles (anti-vehicle - only where the side has seen an enemy vehicle near
// the target: anti-vehicle teams sent to FIA bases hovered there and were lost, 12 of 68 drones).
// Teams start from a clear spot 40-120 m from the base - open sky, nothing within 12 m, level
// ground (from 30 m off the centre, drones hit barracks, trees and a transformer at take-off).
// Drone warfare doctrine (Martin, review note 118: modern combat, heavy drone use): a side with our
// strategist sends its teams where the plan says (drone <base>: prep fire on the objective while
// gathering, pressure during the assault and storm) - a team every 90 s, up to 3 in the air
// (-zcrDroneTempo / -zcrDroneMax). A side on AI Conflict alone gets a baseline too, so both sides
// use drones: every 4 minutes, up to 2, at the base most of its attack squads are sent to.
// The hunt (both sides): every other launch goes for the biggest group of enemy soldiers the side
// has seen in the last minute (5 or more within 100 m, within 2.5 km of its bases) - drones hunt
// the enemy's soldiers, not only the bases, so spacing and cover matter.
// Uses the mod's Game Master teams by prefab only, so this addon still runs without the mod
// (the prefab doesn't load and nothing happens).
class ZCR_Drones
{
	protected static ref map<FactionKey, int> s_mNextAt = new map<FactionKey, int>();
	protected static ref map<FactionKey, int> s_mCount = new map<FactionKey, int>();
	protected static ref array<SCR_AIGroup> s_aTeams = {};
	protected static ref array<string> s_aTeamSide = {};
	// The drones of each team, for the camera director: [team index] -> drones found after launch.
	static ref array<IEntity> s_aDrones = {};
	static ref array<string> s_aDroneSide = {};
	static int s_iFoundAt = -1;   // when the last team's drones were found in the air (the director cuts to them)

	protected static const ResourceName WAYPOINT = "{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et";

	protected static ResourceName Team(FactionKey side, bool antiVehicle)
	{
		if (side == "US")
		{
			if (antiVehicle)
				return "{95E48E607C658B95}PrefabsEditable/FPVAI/E_FPVAI_Station_AT_US.et";
			return "{1BBD52E7242E274A}PrefabsEditable/FPVAI/E_FPVAI_Station_AP_US.et";
		}
		if (antiVehicle)
			return "{05E96855EDE1A606}PrefabsEditable/FPVAI/E_FPVAI_Station_AT_USSR.et";
		return "{116F0030E01EB0DB}PrefabsEditable/FPVAI/E_FPVAI_Station_AP_USSR.et";
	}

	protected static int CliInt(string name, int fallback)
	{
		string value;
		if (System.GetCLIParam(name, value) && !value.IsEmpty())
			return value.ToInt();
		return fallback;
	}

	// Called by the strategist after each plan (server): the doctrine's drone targets, else the
	// main effort when it is a base we don't hold.
	static void OnPlan(FactionKey side, ZCR_StrategicPlan plan, bool fromStrategist)
	{
		if (!Replication.IsServer() || !System.IsCLIParam("zcrDrones") || !fromStrategist)
			return;
		int target = -1;
		foreach (int t : plan.GetDroneTargets())
		{
			if (ZCR_Strategist.s_mNodePos.Contains(t) && ZCR_Strategist.s_mNodeOwner.Get(t) != side)
			{
				target = t;
				break;
			}
		}
		if (target < 0)
		{
			target = plan.GetMainEffort();
			if (target < 0 || ZCR_Strategist.s_mNodeOwner.Get(target) == side)
				return;
		}
		Launch(side, target, CliInt("zcrDroneTempo", 90), CliInt("zcrDroneMax", 3), "doctrine");
	}

	// AI Conflict's side (no strategist): a baseline - every 4 min, up to 2, at the base most of
	// its attack squads are sent to.
	static void Baseline(FactionKey side, AICF_FactionState state, AICF_ObjectiveGraph graph)
	{
		if (!Replication.IsServer() || !System.IsCLIParam("zcrDrones") || !state || !graph)
			return;
		int now = ZCR_LossLog.Seconds();
		int next;
		if (s_mNextAt.Find(side, next) && now < next)
			return;
		map<int, int> votes = new map<int, int>();
		for (int s; s < state.GetSlotCount(); s++)
		{
			AICF_GroupSlot slot = state.GetSlot(s);
			if (!slot || slot.GetRole() != AICF_EGroupRole.ATTACK || !slot.GetTargetBase())
				continue;
			for (int i = 0; i < graph.GetNodeCount(); i++)
			{
				AICF_ObjectiveNode node = graph.GetNode(i);
				if (node && node.GetBase() == slot.GetTargetBase())
				{
					votes.Set(i, votes.Get(i) + 1);
					break;
				}
			}
		}
		int target = -1;
		int most;
		foreach (int node, int n : votes)
		{
			if (n > most && ZCR_Strategist.s_mNodeOwner.Get(node) != side && ZCR_Strategist.s_mNodePos.Contains(node))
			{
				most = n;
				target = node;
			}
		}
		if (target < 0)
			return;
		Launch(side, target, 240, 2, "baseline");
	}

	protected static ref map<FactionKey, int> s_mLaunches = new map<FactionKey, int>();
	protected static ref map<SCR_AIGroup, vector> s_mTeamGoal = new map<SCR_AIGroup, vector>();
	protected static ref map<SCR_AIGroup, int> s_mTeamGoalAt = new map<SCR_AIGroup, int>();
	protected static ref map<SCR_AIGroup, int> s_mTeamNo = new map<SCR_AIGroup, int>();

	// Drones stuck in the air (Martin: "drones get stuck in the air and don't move"; Arma 3 note 53):
	// a team hovering at its goal for a minute with nothing to hit gets a new goal - the nearest enemy
	// its side has seen in the last minute, within 1.2 km; with none, after 2.5 minutes its drones
	// are called home (removed). The drone mod's group station follows the team's waypoint.
	// Logs [ZCR][DRONES] ... retarget / home.
	static void Tend(FactionKey side)
	{
		int now = ZCR_LossLog.Seconds();
		for (int i = s_aTeams.Count() - 1; i >= 0; i--)
		{
			SCR_AIGroup team = s_aTeams[i];
			if (!team || s_aTeamSide[i] != side || !s_mTeamGoal.Contains(team))
				continue;
			int since = now - s_mTeamGoalAt.Get(team);
			if (since < 60)
				continue;
			vector goal = s_mTeamGoal.Get(team);
			array<IEntity> hovering = {};
			for (int k; k < s_aDrones.Count(); k++)
			{
				IEntity d = s_aDrones[k];
				if (!d || s_aDroneSide[k] != side)
					continue;
				vector p = d.GetOrigin();
				if (vector.DistanceXZ(p, goal) < 200 && p[1] - GetGame().GetWorld().GetSurfaceY(p[0], p[2]) > 3)
					hovering.Insert(d);
			}
			if (hovering.IsEmpty())
				continue;
			vector enemy;
			if (ZCR_Sampler.NearestKnown(side, goal, 1200, enemy) && vector.DistanceXZ(enemy, goal) > 80)
			{
				SetGoal(team, enemy, now);
				Print(string.Format("[ZCR][DRONES] t=%1 side=%2 team=%3 retarget hovering=%4 after=%5 to=%6 %7 distance=%8", now, side, s_mTeamNo.Get(team),
					hovering.Count(), since, Math.Round(enemy[0]), Math.Round(enemy[2]), Math.Round(vector.DistanceXZ(enemy, goal))), LogLevel.NORMAL);
				ZCR_Feed.Note(side, string.Format("drone team %1 had nothing to hit - on to enemies seen %2 m away", s_mTeamNo.Get(team), Math.Round(vector.DistanceXZ(enemy, goal))));
			}
			else if (since >= 150)
			{
				foreach (IEntity d : hovering)
					SCR_EntityHelper.DeleteEntityAndChildren(d);
				s_mTeamGoalAt.Set(team, now);
				Print(string.Format("[ZCR][DRONES] t=%1 side=%2 team=%3 home hovering=%4 after=%5", now, side, s_mTeamNo.Get(team), hovering.Count(), since), LogLevel.NORMAL);
				ZCR_Feed.Note(side, string.Format("drone team %1: nothing to hit for 2.5 min - called home", s_mTeamNo.Get(team)));
			}
		}
	}

	// A team's goal: its waypoints replaced by one Move waypoint there.
	protected static void SetGoal(SCR_AIGroup team, vector goal, int now)
	{
		array<AIWaypoint> old = {};
		team.GetWaypoints(old);
		foreach (AIWaypoint w : old)
			team.RemoveWaypoint(w);
		Resource wpRes = Resource.Load(WAYPOINT);
		if (wpRes && wpRes.IsValid())
		{
			EntitySpawnParams wpParams = new EntitySpawnParams();
			wpParams.TransformMode = ETransformMode.WORLD;
			wpParams.Transform[3] = goal;
			AIWaypoint wp = AIWaypoint.Cast(GetGame().SpawnEntityPrefab(wpRes, GetGame().GetWorld(), wpParams));
			if (wp)
				team.AddWaypoint(wp);
		}
		s_mTeamGoal.Set(team, goal);
		s_mTeamGoalAt.Set(team, now);
	}

	protected static void Launch(FactionKey side, int target, int tempo, int maxUp, string why)
	{
		vector goal;
		if (!ZCR_Strategist.s_mNodePos.Find(target, goal))
			return;
		string goalName = ZCR_Strategist.s_mNodeName.Get(target);
		int now = ZCR_LossLog.Seconds();
		// The hunt: every other launch at the enemy soldiers seen in the field, when there are enough.
		if (s_mLaunches.Get(side) % 2 == 1)
		{
			vector cluster;
			int seen = ZCR_Sampler.KnownCluster(side, cluster);
			if (seen >= 5 && NearestOwn(side, cluster) <= 2500)
			{
				goal = cluster;
				goalName = string.Format("%1 enemy soldiers seen near %2", seen, ZCR_Strategist.s_mNodeName.Get(Nearest(cluster)));
				why = "hunt";
			}
		}
		// Counter-drone: every third launch at an enemy drone site this side has seen (ZCR_DroneSites).
		if (ZCR_DroneSites.On() && s_mLaunches.Get(side) % 3 == 2)
		{
			vector site;
			string siteName;
			if (ZCR_DroneSites.KnownEnemySite(side, site, siteName))
			{
				goal = site;
				goalName = "the enemy drone site at " + siteName;
				why = "counter-drone";
			}
		}
		int next;
		if (s_mNextAt.Find(side, next) && now < next)
			return;
		if (Active(side) >= maxUp)
			return;
		vector from;
		float best = 1e9;
		if (ZCR_DroneSites.On())
		{
			// From the side's ready drone site nearest the objective - none ready, no drones.
			string fromName;
			if (!ZCR_DroneSites.LaunchFrom(side, goal, from, fromName))
			{
				s_mNextAt.Set(side, now + 30);
				return;
			}
			best = vector.DistanceXZ(from, goal);
		}
		else
		{
			// Our base nearest the objective.
			foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
			{
				if ((why != "hunt" && node == target) || ZCR_Strategist.s_mNodeOwner.Get(node) != side)
					continue;
				float d = vector.DistanceXZ(pos, goal);
				if (d < best)
				{
					best = d;
					from = pos;
				}
			}
		}
		if (best > 4000)
			return;
		int n = s_mCount.Get(side) + 1;
		bool antiVehicle = ZCR_Sampler.KnownVehiclesNear(side, goal, 300) > 0;
		Resource res = Resource.Load(Team(side, antiVehicle));
		if (!res || !res.IsValid())
		{
			Print("[ZCR][DRONES] the FPV AI Drones mod is not loaded - no drone teams", LogLevel.WARNING);
			s_mNextAt.Set(side, now + 100000);
			return;
		}
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		vector at;
		if (!ClearSpot(from, goal, at))
		{
			// No clear spot: no team (19 Oct: launched at the harbour base's own centre, the drones
			// killed 57 of the side's own soldiers there).
			s_mNextAt.Set(side, now + tempo);
			Print(string.Format("[ZCR][DRONES] t=%1 side=%2 no clear launch spot near %3 - no team", now, side, ZCR_Strategist.s_mNodeName.Get(Nearest(from))), LogLevel.NORMAL);
			ZCR_Feed.Note(side, "no clear drone launch spot - no team");
			return;
		}
		at[1] = GetGame().GetWorld().GetSurfaceY(at[0], at[2]);
		params.Transform[3] = at;
		SCR_AIGroup team = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(res, GetGame().GetWorld(), params));
		if (!team)
			return;
		Resource wpRes = Resource.Load(WAYPOINT);
		if (wpRes && wpRes.IsValid())
		{
			EntitySpawnParams wpParams = new EntitySpawnParams();
			wpParams.TransformMode = ETransformMode.WORLD;
			wpParams.Transform[3] = goal;
			AIWaypoint wp = AIWaypoint.Cast(GetGame().SpawnEntityPrefab(wpRes, GetGame().GetWorld(), wpParams));
			if (wp)
				team.AddWaypoint(wp);
		}
		s_aTeams.Insert(team);
		s_aTeamSide.Insert(side);
		s_mTeamGoal.Set(team, goal);
		s_mTeamGoalAt.Set(team, now);
		s_mTeamNo.Set(team, n);
		s_mCount.Set(side, n);
		s_mNextAt.Set(side, now + tempo);
		s_mLaunches.Set(side, s_mLaunches.Get(side) + 1);
		string kind = "anti-infantry";
		if (antiVehicle)
			kind = "anti-vehicle";
		ZCR_Feed.Note(side, string.Format("drone team %1 (%2) to %3", n, kind, goalName));
		Print(string.Format("[ZCR][DRONES] t=%1 side=%2 team=%3 kind=%4 from=%5 to=%6 distance=%7 why=%8", now, side, n, kind,
			ZCR_Strategist.s_mNodeName.Get(Nearest(from)), goalName, Math.Round(best), why), LogLevel.NORMAL);
		Find(at, side);
	}

	protected static ref TraceParam s_Trace;

	// A launch spot near the base: 40-250 m from it, toward the goal first; open sky (nothing within
	// 40 m above), nothing within 12 m around at 1-3 m height, level ground, not the sea. None: false.
	static bool ClearSpot(vector base, vector goal, out vector spot)
	{
		BaseWorld world = GetGame().GetWorld();
		vector toward = goal - base;
		toward[1] = 0;
		if (toward.Length() > 1)
			toward.Normalize();
		else
			toward = Vector(1, 0, 0);
		array<float> dists = {40, 60, 80, 100, 120, 160, 200, 250};
		array<float> angles = {0, 45, -45, 90, -90, 135, -135, 180};
		foreach (float d : dists)
		{
			foreach (float a : angles)
			{
				float r = a * Math.DEG2RAD;
				vector dir = Vector(toward[0] * Math.Cos(r) - toward[2] * Math.Sin(r), 0, toward[0] * Math.Sin(r) + toward[2] * Math.Cos(r));
				vector p = base + dir * d;
				p[1] = world.GetSurfaceY(p[0], p[2]);
				if (Clear(world, p))
				{
					spot = p;
					return true;
				}
			}
		}
		return false;
	}

	protected static bool Clear(BaseWorld world, vector p)
	{
		// Not in the water: the sea is level too (19 Oct, Arland: 60 US drones launched into the
		// harbour beside its main base and were lost).
		if (world.IsOcean() && p[1] < world.GetOceanBaseHeight() + 1.0)
			return false;
		if (!s_Trace)
			s_Trace = new TraceParam();
		s_Trace.Flags = TraceFlags.ENTS | TraceFlags.WORLD;
		s_Trace.TargetLayers = 0;
		s_Trace.LayerMask = 0xffffffff;
		s_Trace.Exclude = null;
		// Open sky.
		s_Trace.Start = p + Vector(0, 1, 0);
		s_Trace.End = p + Vector(0, 40, 0);
		if (world.TraceMove(s_Trace, null) < 1.0)
			return false;
		// Nothing around, at 1 and 3 m, in 8 directions.
		for (int i = 0; i < 8; i++)
		{
			float r = i * 45 * Math.DEG2RAD;
			vector dir = Vector(Math.Cos(r), 0, Math.Sin(r));
			foreach (float h : {1.0, 3.0})
			{
				s_Trace.Start = p + Vector(0, h, 0);
				s_Trace.End = p + Vector(0, h, 0) + dir * 12;
				if (world.TraceMove(s_Trace, null) < 1.0)
					return false;
			}
		}
		// Level ground: the four corners 4 m out within 1.5 m of the centre.
		foreach (vector o : {Vector(4, 0, 0), Vector(-4, 0, 0), Vector(0, 0, 4), Vector(0, 0, -4)})
		{
			if (Math.AbsFloat(world.GetSurfaceY(p[0] + o[0], p[2] + o[2]) - p[1]) > 1.5)
				return false;
		}
		return true;
	}

	protected static float NearestOwn(FactionKey side, vector at)
	{
		float best = 1e9;
		foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
		{
			if (ZCR_Strategist.s_mNodeOwner.Get(node) == side)
				best = Math.Min(best, vector.DistanceXZ(pos, at));
		}
		return best;
	}

	protected static int Nearest(vector at)
	{
		int bestNode = -1;
		float best = 1e9;
		foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
		{
			float d = vector.DistanceXZ(at, pos);
			if (d < best)
			{
				best = d;
				bestNode = node;
			}
		}
		return bestNode;
	}

	// For the watch panel: teams launched so far, and drones in the air now.
	static int Launched(FactionKey side)
	{
		return s_mCount.Get(side);
	}

	static int InAir(FactionKey side)
	{
		int n;
		for (int i; i < s_aDrones.Count(); i++)
		{
			if (s_aDrones[i] && s_aDroneSide[i] == side)
				n++;
		}
		return n;
	}

	protected static int Active(FactionKey side)
	{
		int n;
		for (int i = s_aTeams.Count() - 1; i >= 0; i--)
		{
			if (!s_aTeams[i])
			{
				s_aTeams.Remove(i);
				s_aTeamSide.Remove(i);
				continue;
			}
			if (s_aTeamSide[i] == side)
				n++;
		}
		return n;
	}

	protected static ref array<ref ZCR_DroneFinder> s_aFinders = {};

	protected static void Find(vector at, string side)
	{
		ZCR_DroneFinder finder = new ZCR_DroneFinder();
		finder.m_vAt = at;
		finder.m_sSide = side;
		s_aFinders.Insert(finder);
		GetGame().GetCallqueue().CallLater(finder.Run, 1500, false);
	}
}

// Finds a just-launched team's drones near where it was spawned (entity queries need object
// methods), for the camera director's drone shots.
class ZCR_DroneFinder
{
	vector m_vAt;
	string m_sSide;
	ref array<IEntity> m_aFound = {};

	bool Add(IEntity e)
	{
		m_aFound.Insert(e);
		return true;
	}

	void Run()
	{
		GetGame().GetWorld().QueryEntitiesBySphere(m_vAt, 200, Add, null, EQueryEntitiesFlags.DYNAMIC);
		int n;
		foreach (IEntity e : m_aFound)
		{
			if (!e || !e.GetPrefabData() || e.GetRootParent() != e)
				continue;
			string name = e.GetPrefabData().GetPrefabName();
			name.ToLower();
			if (name.Contains("fpv") || name.Contains("drone"))
			{
				ZCR_Drones.s_aDrones.Insert(e);
				ZCR_Drones.s_aDroneSide.Insert(m_sSide);
				n++;
			}
		}
		if (n > 0)
			ZCR_Drones.s_iFoundAt = ZCR_LossLog.Seconds();
		Print(string.Format("[ZCR][DRONES] t=%1 side=%2 drones_found=%3 entities_near=%4", ZCR_LossLog.Seconds(), m_sSide, n, m_aFound.Count()), LogLevel.NORMAL);
	}
}
