// Drone sites (Martin, 19 Oct: "drone operators like in Arma 3 - or the AI builds drone trucks, a drone
// arsenal at points to launch from; destroy it and that position has no drones"; Arma 3: an operator
// post you could kill to stop the launches). Each side launches FPV teams only from its drone sites:
// a drone truck with a 2-man operator team beside it. One at the main base from the start; a forward
// one is set up at the side's own base nearest the front when its target is over 1.5 km from every
// site (ready 2 minutes later; at most 3 sites). A site is lost when its truck is destroyed or both
// operators are dead: that base launches nothing more; a lost main-base site is rebuilt after 5 min.
// Counter-drone: a side that has seen an enemy site's truck or operators in the last 2 minutes sends
// every third team at it. Logs [ZCR][DRONESITE]; -zcrNoDroneSites: drones from any own base as before.
class ZCR_DroneSite
{
	string m_sSide;
	string m_sName;
	vector m_vPos;
	vector m_vLaunch;       // where its teams start: clear ground chosen once, 40+ m from the truck
	bool m_bMain;
	SCR_AIGroup m_Operators;
	IEntity m_Truck;
	int m_iReadyAt;
	bool m_bLost;
	int m_iLostAt;
}

class ZCR_DroneSites
{
	static ref array<ref ZCR_DroneSite> s_aSites = {};
	static const int FIRST_READY = 60;
	static const int SETUP = 120;
	static const int REBUILD = 300;
	static const int MAX_SITES = 3;
	static const float FORWARD_GAP = 1500;
	static const float FORWARD_NEAR = 1200;

	static bool On()
	{
		return !System.IsCLIParam("zcrNoDroneSites");
	}

	protected static ResourceName Truck(string side)
	{
		if (side == "USSR")
			return "{1BABF6B33DA0AEB6}Prefabs/Vehicles/Wheeled/Ural4320/Ural4320_command.et";
		return "{36BDCC88B17B3BFA}Prefabs/Vehicles/Wheeled/M923A1/M923A1_command.et";
	}

	protected static ResourceName Operators(string side)
	{
		if (side == "USSR")
			return "{CB58D90EA14430AD}Prefabs/Groups/OPFOR/Group_USSR_SentryTeam.et";
		return "{3BF36BDEEB33AEC9}Prefabs/Groups/BLUFOR/Group_US_SentryTeam.et";
	}

	// Every commander tick, per side: losses, rebuilding, the main and the forward site.
	// 'front': where the side's drones go now (its plan's main effort, or AI Conflict's main target).
	static void Tick(string side, vector front)
	{
		if (!On() || !Replication.IsServer())
			return;
		int now = ZCR_LossLog.Seconds();
		bool hasMain;
		int alive;
		foreach (ZCR_DroneSite s : s_aSites)
		{
			if (s.m_sSide != side)
				continue;
			if (!s.m_bLost && Destroyed(s))
			{
				s.m_bLost = true;
				s.m_iLostAt = now;
				Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 lost at=%3 main=%4", now, side, s.m_sName, s.m_bMain), LogLevel.NORMAL);
				ZCR_Feed.Note(side, string.Format("LOST the drone site at %1 - no drones from there", s.m_sName));
			}
			if (s.m_bMain && (!s.m_bLost || now - s.m_iLostAt < REBUILD))
				hasMain = true;
			if (!s.m_bLost)
				alive++;
		}
		// The main base's site: from the start, and again 5 minutes after it was lost.
		SCR_CampaignFaction faction = SCR_CampaignFaction.Cast(GetGame().GetFactionManager().GetFactionByKey(side));
		if (!hasMain && faction && faction.GetMainBase() && faction.GetMainBase().GetOwner())
		{
			int ready = now + FIRST_READY;
			bool rebuilt;
			foreach (ZCR_DroneSite s : s_aSites)
			{
				if (s.m_sSide == side && s.m_bMain)
					rebuilt = true;
			}
			if (rebuilt)
				ready = now + SETUP;
			if (Create(side, faction.GetMainBase().GetOwner().GetOrigin(), front, true, ready))
				alive++;
		}
		// A forward site: the front is far from every site and the side holds a base near it.
		if (front == vector.Zero || alive >= MAX_SITES)
			return;
		float nearestSite = 1e9;
		foreach (ZCR_DroneSite s : s_aSites)
		{
			if (s.m_sSide == side && !s.m_bLost)
				nearestSite = Math.Min(nearestSite, vector.DistanceXZ(s.m_vPos, front));
		}
		if (nearestSite <= FORWARD_GAP)
			return;
		vector at;
		float best = FORWARD_NEAR;
		foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
		{
			if (ZCR_Strategist.s_mNodeOwner.Get(node) != side)
				continue;
			float d = vector.DistanceXZ(pos, front);
			if (d < best && d > 150)
			{
				best = d;
				at = pos;
			}
		}
		if (at != vector.Zero)
			Create(side, at, front, false, now + SETUP);
	}

	protected static bool Destroyed(ZCR_DroneSite s)
	{
		if (!s.m_Truck)
			return true;
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(s.m_Truck.FindComponent(SCR_DamageManagerComponent));
		if (damage && damage.IsDestroyed())
			return true;
		if (!s.m_Operators || AICF_GroupRuntime.CountAliveAgents(s.m_Operators) == 0)
			return ZCR_LossLog.Seconds() > s.m_iReadyAt;      // the team spawns a moment after the group
		return false;
	}

	// A site at a base: the truck on clear ground 40-250 m from it on the side away from the front,
	// the operators beside it.
	protected static bool Create(string side, vector base, vector front, bool main, int readyAt)
	{
		vector away = base + (base - front);
		if (front == vector.Zero)
			away = base + Vector(0, 0, -100);
		vector spot;
		if (!ZCR_Drones.ClearSpot(base, away, spot))
		{
			Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 no clear spot near %3", ZCR_LossLog.Seconds(), side, Name(base)), LogLevel.NORMAL);
			return false;
		}
		spot[1] = GetGame().GetWorld().GetSurfaceY(spot[0], spot[2]);
		// The launch spot, chosen once (a search at every launch failed at the harbour base and,
		// later in the match, by the truck - 19 Oct probe).
		vector launch;
		if (!ZCR_Drones.ClearSpot(spot, away, launch))
		{
			Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 no clear launch spot near %3", ZCR_LossLog.Seconds(), side, Name(base)), LogLevel.NORMAL);
			return false;
		}
		launch[1] = GetGame().GetWorld().GetSurfaceY(launch[0], launch[2]);
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = spot;
		Resource truckRes = Resource.Load(Truck(side));
		Resource teamRes = Resource.Load(Operators(side));
		if (!truckRes || !truckRes.IsValid() || !teamRes || !teamRes.IsValid())
			return false;
		ZCR_DroneSite s = new ZCR_DroneSite();
		s.m_sSide = side;
		s.m_sName = Name(base);
		if (main)
			s.m_sName = "Main Operating Base";        // the base list may not be in yet at the start
		s.m_vPos = spot;
		s.m_vLaunch = launch;
		s.m_bMain = main;
		s.m_iReadyAt = readyAt;
		s.m_Truck = GetGame().SpawnEntityPrefab(truckRes, GetGame().GetWorld(), params);
		params.Transform[3] = spot + Vector(6, 0, 4);
		s.m_Operators = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(teamRes, GetGame().GetWorld(), params));
		s_aSites.Insert(s);
		Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 set_up at=%3 main=%4 ready_in=%5 x=%6 z=%7", ZCR_LossLog.Seconds(), side, s.m_sName, main,
			readyAt - ZCR_LossLog.Seconds(), Math.Round(spot[0]), Math.Round(spot[2])), LogLevel.NORMAL);
		ZCR_Feed.Note(side, string.Format("drone site set up at %1 (drone truck and operators)", s.m_sName));
		return true;
	}

	protected static string Name(vector at)
	{
		string name = "the field";
		float best = 1e9;
		foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
		{
			float d = vector.DistanceXZ(pos, at);
			if (d < best)
			{
				best = d;
				name = ZCR_Strategist.s_mNodeName.Get(node);
			}
		}
		return name;
	}

	// The ready site nearest the goal, or false (no drones).
	static bool LaunchFrom(string side, vector goal, out vector from, out string name)
	{
		int now = ZCR_LossLog.Seconds();
		float best = 1e9;
		bool found;
		foreach (ZCR_DroneSite s : s_aSites)
		{
			if (s.m_sSide != side || s.m_bLost || now < s.m_iReadyAt)
				continue;
			float d = vector.DistanceXZ(s.m_vPos, goal);
			if (d < best)
			{
				best = d;
				from = s.m_vLaunch;
				name = s.m_sName;
				found = true;
			}
		}
		return found;
	}

	// Counter-drone: an enemy site this side has seen (its truck or an operator) in the last 2 minutes.
	static bool KnownEnemySite(string side, out vector where, out string name)
	{
		foreach (ZCR_DroneSite s : s_aSites)
		{
			if (s.m_sSide == side || s.m_bLost)
				continue;
			bool seen = s.m_Truck && ZCR_Sampler.Knows(side, s.m_Truck, 120);
			if (!seen && s.m_Operators)
			{
				array<AIAgent> agents = {};
				s.m_Operators.GetAgents(agents);
				foreach (AIAgent a : agents)
				{
					if (a && a.GetControlledEntity() && ZCR_Sampler.Knows(side, a.GetControlledEntity(), 120))
						seen = true;
				}
			}
			if (seen)
			{
				where = s.m_vPos;
				name = s.m_sName;
				return true;
			}
		}
		return false;
	}

	// For the panel: "Main Operating Base ready, Farm in 1:20, Levie lost".
	static string Text(string side)
	{
		int now = ZCR_LossLog.Seconds();
		string text;
		foreach (ZCR_DroneSite s : s_aSites)
		{
			if (s.m_sSide != side)
				continue;
			if (!text.IsEmpty())
				text += ", ";
			if (s.m_bLost)
				text += s.m_sName + " lost";
			else if (now < s.m_iReadyAt)
				text += s.m_sName + " ready in " + ZCR_Feed.Clock(s.m_iReadyAt - now);
			else
				text += s.m_sName + " ready";
		}
		if (text.IsEmpty())
			return "none yet";
		return text;
	}
}
