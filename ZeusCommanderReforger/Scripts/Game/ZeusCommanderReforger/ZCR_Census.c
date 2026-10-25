// What piles up during a match (25 Oct - Martin: "fps still drops for some reason as time goes by"): the game's own FPS
// line showed its dynamic entities growing 1243 -> 1823 over 20 minutes while the AI count stayed ~225. Every CENSUS_S
// game seconds, every dynamic entity on the map counted by kind - soldiers alive and dead, vehicles intact and wrecked,
// waypoints, AI groups, and the rest by class - in one line:
//   [ZCR][CENSUS] t= total= alive= dead= veh= wrecks= waypoints= groups= ms= top=Class:n,...
// -zcrNoCensus off.
class ZCR_Census
{
	static const int CENSUS_S = 120;
	protected static bool s_bStarted;
	protected static ref map<string, int> s_mCount;
	protected static ref array<vector> s_aSample = {};
	protected static ref map<int, int> s_mLod = new map<int, int>();
	protected static ref set<AIWaypoint> s_mHeld = new set<AIWaypoint>();
	protected static ref array<vector> s_aOrphanAt = {};
	protected static int s_iOrphans;
	protected static int s_iAlive, s_iDead, s_iVeh, s_iWrecks, s_iWaypoints, s_iGroups, s_iTotal;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoCensus"))
			return;
		s_bStarted = true;
		GetGame().GetCallqueue().CallLater(Tick, CENSUS_S * 1000, true);
	}

	protected static bool Count(IEntity e)
	{
		if (!e || e.GetParent())
			return true;   // a soldier's gear, a vehicle's parts: counted with their root
		s_iTotal++;
		ChimeraCharacter c = ChimeraCharacter.Cast(e);
		if (c)
		{
			CharacterControllerComponent controller = c.GetCharacterController();
			if (controller && controller.IsDead())
				s_iDead++;
			else
			{
				s_iAlive++;
				// The soldier's AI level of detail (0 = full; the engine thins out far ones - unless told not to).
				AIControlComponent ai = AIControlComponent.Cast(c.FindComponent(AIControlComponent));
				if (ai && ai.GetAIAgent())
				{
					int lod = ai.GetAIAgent().GetLOD();
					s_mLod.Set(lod, s_mLod.Get(lod) + 1);
				}
			}
			return true;
		}
		if (Vehicle.Cast(e))
		{
			SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(e.FindComponent(SCR_DamageManagerComponent));
			if (damage && damage.GetState() == EDamageState.DESTROYED)
				s_iWrecks++;
			else
				s_iVeh++;
			return true;
		}
		if (AIWaypoint.Cast(e))
		{
			s_iWaypoints++;
			string wp = "wp:" + Prefab(e);
			s_mCount.Set(wp, s_mCount.Get(wp) + 1);
			// A waypoint no group holds any more (25 Oct: Move waypoints grow ~10 a game minute): where, to find who left it.
			if (!s_mHeld.Contains(AIWaypoint.Cast(e)))
			{
				s_iOrphans++;
				if (s_aOrphanAt.Count() < 8)
					s_aOrphanAt.Insert(e.GetOrigin());
			}
			return true;
		}
		if (AIGroup.Cast(e))
		{
			s_iGroups++;
			return true;
		}
		// Generic entities by their prefab (the bulk: 1158 -> 1488 in 11 minutes of the first FPS test).
		string name = e.ClassName();
		if (name == "GenericEntity")
			name = Prefab(e);
		// Where the biggest growing kind sits (25 Oct: Inventory_Virtual_Entity 784 -> 839 in 2 minutes): a few positions.
		if (name == "Inventory_Virtual_Entity" && s_aSample.Count() < 6)
			s_aSample.Insert(e.GetOrigin());
		s_mCount.Set(name, s_mCount.Get(name) + 1);
		return true;
	}

	// "AIWaypoint_Move" from "{...}Prefabs/AI/Waypoints/AIWaypoint_Move.et"; "no_prefab" without one.
	protected static string Prefab(IEntity e)
	{
		if (!e.GetPrefabData())
			return "no_prefab";
		string full = e.GetPrefabData().GetPrefabName();
		int slash = full.LastIndexOf("/");
		if (slash >= 0)
			full = full.Substring(slash + 1, full.Length() - slash - 1);
		full.Replace(".et", "");
		if (full.IsEmpty())
			return "no_prefab";
		return full;
	}

	protected static void Tick()
	{
		int started = System.GetTickCount();
		s_mCount = new map<string, int>();
		s_aSample.Clear();
		s_mLod.Clear();
		s_aOrphanAt.Clear();
		s_iOrphans = 0;
		// Every waypoint some group still has.
		s_mHeld.Clear();
		array<AIAgent> agents = {};
		if (GetGame().GetAIWorld())
			GetGame().GetAIWorld().GetAIAgents(agents);
		foreach (AIAgent a : agents)
		{
			AIGroup g = AIGroup.Cast(a);
			if (!g)
				continue;
			array<AIWaypoint> held = {};
			g.GetWaypoints(held);
			foreach (AIWaypoint hw : held)
				s_mHeld.Insert(hw);
		}
		s_iAlive = 0;
		s_iDead = 0;
		s_iVeh = 0;
		s_iWrecks = 0;
		s_iWaypoints = 0;
		s_iGroups = 0;
		s_iTotal = 0;
		// The whole map (Everon is 12.8 km; Arland 4 km).
		GetGame().GetWorld().QueryEntitiesByAABB(Vector(-2000, -1000, -2000), Vector(16000, 3000, 16000), Count, null, EQueryEntitiesFlags.DYNAMIC);
		// The rest, largest first (top 16).
		string top;
		for (int k; k < 16 && !s_mCount.IsEmpty(); k++)
		{
			string best;
			int most = -1;
			foreach (string name, int n : s_mCount)
			{
				if (n > most)
				{
					most = n;
					best = name;
				}
			}
			top += string.Format("%1:%2,", best, most);
			s_mCount.Remove(best);
		}
		Print(string.Format("[ZCR][CENSUS] t=%1 total=%2 alive=%3 dead=%4 veh=%5 wrecks=%6 waypoints=%7 groups=%8 ms=%9", ZCR_LossLog.Seconds(), s_iTotal,
			s_iAlive, s_iDead, s_iVeh, s_iWrecks, s_iWaypoints, s_iGroups, System.GetTickCount() - started) + " top=" + top, LogLevel.NORMAL);
		string lods;
		for (int l; l <= AIAgent.GetMaxLOD(); l++)
			lods += string.Format("%1:%2,", l, s_mLod.Get(l));
		Print(string.Format("[ZCR][CENSUS] t=%1 lod=%2 max_lod=%3", ZCR_LossLog.Seconds(), lods, AIAgent.GetMaxLOD()), LogLevel.NORMAL);
		string orphans;
		foreach (vector o : s_aOrphanAt)
			orphans += string.Format("%1,%2;", Math.Round(o[0]), Math.Round(o[2]));
		Print(string.Format("[ZCR][CENSUS] t=%1 orphan_waypoints=%2 at=%3", ZCR_LossLog.Seconds(), s_iOrphans, orphans), LogLevel.NORMAL);
		string at;
		foreach (vector v : s_aSample)
			at += string.Format("%1,%2,%3;", Math.Round(v[0]), Math.Round(v[1]), Math.Round(v[2]));
		if (!at.IsEmpty())
			Print(string.Format("[ZCR][CENSUS] t=%1 sample=Inventory_Virtual_Entity at=%2", ZCR_LossLog.Seconds(), at), LogLevel.NORMAL);
	}
}
