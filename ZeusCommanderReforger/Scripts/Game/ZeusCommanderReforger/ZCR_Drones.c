// FPV drone teams for the commander (-zcrDrones on the server; needs Martin's FPV AI Drones and
// Realistic Combat Drones loaded). A side whose strategist is attacking - its main effort is a base
// it doesn't hold - gets a team of 4 AI-flown FPVs at its own base nearest the objective, sent to
// the objective with a Move waypoint: the drones fly there and go for enemy soldiers within 200 m
// (anti-infantry) or vehicles (anti-vehicle, every third team). At most two teams a side in the
// air, one new team every 4 minutes. A side on AI Conflict alone gets none.
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

	// Called by the strategist after each plan (server).
	static void OnPlan(FactionKey side, ZCR_StrategicPlan plan, bool fromStrategist)
	{
		if (!Replication.IsServer() || !System.IsCLIParam("zcrDrones") || !fromStrategist)
			return;
		int target = plan.GetMainEffort();
		vector goal;
		if (target < 0 || !ZCR_Strategist.s_mNodePos.Find(target, goal))
			return;
		// Attacking: the main effort is not ours.
		if (ZCR_Strategist.s_mNodeOwner.Get(target) == side)
			return;
		int now = ZCR_LossLog.Seconds();
		int next;
		if (s_mNextAt.Find(side, next) && now < next)
			return;
		if (Active(side) >= 2)
			return;
		// Our base nearest the objective.
		vector from;
		float best = 1e9;
		foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
		{
			if (node == target || ZCR_Strategist.s_mNodeOwner.Get(node) != side)
				continue;
			float d = vector.DistanceXZ(pos, goal);
			if (d < best)
			{
				best = d;
				from = pos;
			}
		}
		if (best > 4000)
			return;
		int n = s_mCount.Get(side) + 1;
		bool antiVehicle = n % 3 == 0;
		Resource res = Resource.Load(Team(side, antiVehicle));
		if (!res || !res.IsValid())
		{
			Print("[ZCR][DRONES] the FPV AI Drones mod is not loaded - no drone teams", LogLevel.WARNING);
			s_mNextAt.Set(side, now + 100000);
			return;
		}
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		vector at = from + Vector(30, 0, 30);
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
		s_mCount.Set(side, n);
		s_mNextAt.Set(side, now + 240);
		string kind = "anti-infantry";
		if (antiVehicle)
			kind = "anti-vehicle";
		Print(string.Format("[ZCR][DRONES] t=%1 side=%2 team=%3 kind=%4 from=%5 to=%6 distance=%7", now, side, n, kind,
			ZCR_Strategist.s_mNodeName.Get(Nearest(from)), ZCR_Strategist.s_mNodeName.Get(target), Math.Round(best)), LogLevel.NORMAL);
		Find(at, side);
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
		Print(string.Format("[ZCR][DRONES] t=%1 side=%2 drones_found=%3 entities_near=%4", ZCR_LossLog.Seconds(), m_sSide, n, m_aFound.Count()), LogLevel.NORMAL);
	}
}
