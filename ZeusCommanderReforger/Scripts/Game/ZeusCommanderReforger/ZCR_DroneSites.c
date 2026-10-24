// Drone sites (Martin, 19 Oct: "drone operators like in Arma 3 - or the AI builds drone trucks, a drone
// arsenal at points to launch from; destroy it and that position has no drones"; Arma 3: an operator
// post you could kill to stop the launches). Each side launches FPV teams only from its drone sites:
// a drone truck with a 2-man operator team beside it. One at the main base from the start; a forward
// one is set up at the side's own base nearest the front when its target is over 1.5 km from every
// site (ready 2 minutes later; at most 3 sites). A site is lost when its truck is destroyed or both
// operators are dead: that base launches nothing more; a lost main-base site is rebuilt after 5 min.
// Counter-drone: a side that has seen an enemy site's truck or operators in the last 2 minutes sends
// every third team at it. Logs [ZCR][DRONESITE]; -zcrNoDroneSites: drones from any own base as before.
// Sites move (Martin, 24 Oct 16:05, on 'real drone teams move after a few launches so they're harder to find': "yeah I love
// this"): after MOVE_AFTER launches, MOVE_EVERY_S at one spot, or as soon as the enemy has seen it, a site whose last
// launch is a minute old packs up - the operators get into the truck, drive 300-500 m to clear ground not toward the
// front, get out, take a new post in cover and are ready again SETUP_AFTER_MOVE s later. No launches while it moves.
//   [ZCR][DRONESITE] t= side= move=pack|drive|unload|set|failed_boarding at= why=launches|time|seen ...
// -zcrStaticDroneSites: no moves.
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
	// Moving: 0 set up, 1 boarding, 2 driving, 3 getting out
	int m_iMove;
	int m_iMoveAt;
	int m_iSetAt;
	int m_iLaunches;
	int m_iLastLaunchAt;
	int m_iMoves;
	vector m_vTo;
	string m_sWhy;
	bool m_bDue;            // a move is due: no more launches from here, packing once the last drone is down
	AIWaypoint m_Waypoint;
}

class ZCR_DroneSites
{
	static ref array<ref ZCR_DroneSite> s_aSites = {};
	protected static ref map<string, int> s_mForwardTriedAt = new map<string, int>();
	static const int FIRST_READY = 60;
	static const int SETUP = 120;
	static const int REBUILD = 300;
	static const int MAX_SITES = 3;
	static const float FORWARD_GAP = 1500;
	static const float FORWARD_NEAR = 1200;
	static const int MOVE_AFTER = 3;           // launches from one spot
	static const int MOVE_EVERY_S = 480;       // or this long at one spot
	static const int SETUP_AFTER_MOVE = 60;
	static const int BOARD_S = 90;             // boarding, driving and getting out give up after these
	static const int DRIVE_S = 300;
	static const int UNLOAD_S = 60;

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
			if (!s.m_bLost)
				Move(s, front, now);
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
		// A failed try (no clear ground there) is retried after 2 minutes, not every tick.
		if (at != vector.Zero && (!s_mForwardTriedAt.Contains(side) || now - s_mForwardTriedAt.Get(side) >= 120))
		{
			s_mForwardTriedAt.Set(side, now);
			Create(side, at, front, false, now + SETUP);
		}
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
		s.m_iSetAt = readyAt;
		ZCR_Trace.At("spawn", "drone_site", spot, side);
		s.m_Truck = GetGame().SpawnEntityPrefab(truckRes, GetGame().GetWorld(), params);
		params.Transform[3] = spot + Vector(6, 0, 4);
		s.m_Operators = SCR_AIGroup.Cast(GetGame().SpawnEntityPrefab(teamRes, GetGame().GetWorld(), params));
		// Pilot (goggles, controller, still while he flies) and guard, their post in cover by the truck; tagged on screen.
		if (s.m_Operators)
			ZCR_DroneOperator.Register(s.m_Operators, side, spot + Vector(6, 0, 4), spot);
		s_aSites.Insert(s);
		Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 set_up at=%3 main=%4 ready_in=%5 x=%6 z=%7", ZCR_LossLog.Seconds(), side, s.m_sName, main,
			readyAt - ZCR_LossLog.Seconds(), Math.Round(spot[0]), Math.Round(spot[2])), LogLevel.NORMAL);
		ZCR_Feed.Note(side, string.Format("drone site set up at %1 (drone truck and operators)", s.m_sName));
		return true;
	}

	// The infantry test's drone site (kind "site", Martin 24 Oct: "we could test it again in a simpler scenario"): a site
	// set up at 'at' facing 'front', ready in 20 s; its operator team for the test to follow (null if it couldn't be set up).
	// Tried at 'at', then around it out to 360 m (17:21: no clear launch spot at the first point - no site, the storm over at 30 s).
	static SCR_AIGroup CreateTest(string side, vector at, vector front)
	{
		for (int ring; ring <= 3; ring++)
		{
			for (int k; k < 8; k++)
			{
				if (ring == 0 && k > 0)
					break;
				float r = k * 45 * Math.DEG2RAD;
				vector base = at + Vector(Math.Cos(r), 0, Math.Sin(r)) * (ring * 120);
				base[1] = GetGame().GetWorld().GetSurfaceY(base[0], base[2]);
				int n = s_aSites.Count();
				if (Create(side, base, front, false, ZCR_LossLog.Seconds() + 20) && s_aSites.Count() > n)
					return s_aSites[s_aSites.Count() - 1].m_Operators;
			}
		}
		return null;
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
		ZCR_DroneSite chosen;
		foreach (ZCR_DroneSite s : s_aSites)
		{
			if (s.m_sSide != side || s.m_bLost || now < s.m_iReadyAt)
				continue;
			if (s.m_iMove != 0 || s.m_bDue)
				continue;                      // due to move, packing, driving or unloading: no launches
			float d = vector.DistanceXZ(s.m_vPos, goal);
			if (d < best)
			{
				best = d;
				from = s.m_vLaunch;
				name = s.m_sName;
				found = true;
				chosen = s;
			}
		}
		if (chosen)
		{
			chosen.m_iLaunches++;
			chosen.m_iLastLaunchAt = now;
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
			if (Seen(s, side))
			{
				where = s.m_vPos;
				if (s.m_Truck)
					where = s.m_Truck.GetOrigin();     // moving: where the truck is now
				name = s.m_sName;
				return true;
			}
		}
		return false;
	}

	// Seen by 'by': its truck or an operator in a soldier's sight in the last 3 minutes, or a soldier of theirs within 250 m
	// of it (a truck there can't be missed - perception alone hardly ever lists an empty vehicle: no counter-drone strike in
	// the first matches).
	protected static bool Seen(ZCR_DroneSite s, string by)
	{
		vector at = s.m_vPos;
		if (s.m_Truck)
			at = s.m_Truck.GetOrigin();
		if ((s.m_Truck && ZCR_Sampler.Knows(by, s.m_Truck, 180)) || ZCR_Sampler.OwnNear(by, at, 250))
			return true;
		if (!s.m_Operators)
			return false;
		array<AIAgent> agents = {};
		s.m_Operators.GetAgents(agents);
		foreach (AIAgent a : agents)
		{
			if (a && a.GetControlledEntity() && ZCR_Sampler.Knows(by, a.GetControlledEntity(), 180))
				return true;
		}
		return false;
	}

	protected static string Enemy(string side)
	{
		if (side == "US")
			return "USSR";
		return "US";
	}

	// The move, a step every commander tick: pack (board) -> drive -> unload -> set up.
	protected static void Move(ZCR_DroneSite s, vector front, int now)
	{
		if (System.IsCLIParam("zcrStaticDroneSites") || !s.m_Truck || !s.m_Operators)
			return;
		if (s.m_iMove == 0)
		{
			if (now < s.m_iReadyAt)
				return;                        // still setting up
			string why = s.m_sWhy;
			if (!s.m_bDue)
			{
				why = "";                      // 17:29: the last move's reason kept and it packed up again at once
				if (s.m_iLaunches >= MOVE_AFTER)
					why = "launches";
				else if (now - s.m_iSetAt >= MOVE_EVERY_S)
					why = "time";
				else if (Seen(s, Enemy(s.m_sSide)))
					why = "seen";
				if (why.IsEmpty())
					return;
				// Due: no more launches from here (17:24, the farm-site storm: launches every 35 s never left the minute's
				// pause the move waited for - 8 launches, no move).
				s.m_bDue = true;
				s.m_sWhy = why;
			}
			if (now - s.m_iLastLaunchAt < 60)
				return;                        // its last drone may still be flying
			vector to;
			if (!NewSpot(s, front, to))
			{
				s.m_iSetAt = now;              // nowhere to go: stays, tries again later
				s.m_iLaunches = 0;
				s.m_bDue = false;
				s.m_sWhy = "";
				Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 move=failed at=%3 why=no_spot", now, s.m_sSide, s.m_sName), LogLevel.NORMAL);
				return;
			}
			s.m_vTo = to;
			s.m_sWhy = why;
			s.m_bDue = false;
			s.m_iMove = 1;
			s.m_iMoveAt = now;
			ZCR_DroneOperator.Moving(s.m_Operators, true);
			SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(s.m_Truck.FindComponent(SCR_AIVehicleUsageComponent));
			if (usage && s.m_Operators.GetGroupUtilityComponent())
				s.m_Operators.GetGroupUtilityComponent().AddUsableVehicle(usage);
			Waypoint(s, "{8AD8C82346156494}Prefabs/AI/Waypoints/AIWaypoint_GetInSelected.et", s.m_Truck.GetOrigin(), 25, s.m_Truck);
			Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 move=pack at=%3 why=%4 launches=%5 to=%6 x=%7 z=%8", now, s.m_sSide, s.m_sName, why,
				s.m_iLaunches, Math.Round(vector.DistanceXZ(s.m_vPos, to)), Math.Round(to[0]), Math.Round(to[2])), LogLevel.NORMAL);
			ZCR_Feed.Note(s.m_sSide, string.Format("the drone team at %1 packs up and moves (%2)", s.m_sName, why));
			return;
		}
		int aboard, alive;
		Aboard(s, aboard, alive);
		if (s.m_iMove == 1)
		{
			if (alive > 0 && aboard < alive && now - s.m_iMoveAt < BOARD_S)
				return;
			// Nobody left behind (17:30: 1 of 2 aboard after 90 s and the truck left): the boarding order once more, up to
			// twice as long; then the move is called off where they are.
			if (aboard < alive && now - s.m_iMoveAt < 2 * BOARD_S)
			{
				if (!s.m_Waypoint)
					Waypoint(s, "{8AD8C82346156494}Prefabs/AI/Waypoints/AIWaypoint_GetInSelected.et", s.m_Truck.GetOrigin(), 25, s.m_Truck);
				return;
			}
			if (aboard < alive)
			{
				Settle(s, now, "failed_boarding");
				Waypoint(s, "{C40316EE26846CAB}Prefabs/AI/Waypoints/AIWaypoint_GetOut.et", s.m_Truck.GetOrigin(), 15);   // the ones aboard out again
				return;
			}
			s.m_iMove = 2;
			s.m_iMoveAt = now;
			Waypoint(s, "{750A8D1695BD6998}Prefabs/AI/Waypoints/AIWaypoint_Move.et", s.m_vTo, 15);
			Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 move=drive at=%3 aboard=%4 of=%5", now, s.m_sSide, s.m_sName, aboard, alive), LogLevel.NORMAL);
			return;
		}
		if (s.m_iMove == 2)
		{
			if (vector.DistanceXZ(s.m_Truck.GetOrigin(), s.m_vTo) > 30 && now - s.m_iMoveAt < DRIVE_S)
				return;
			s.m_iMove = 3;
			s.m_iMoveAt = now;
			Waypoint(s, "{C40316EE26846CAB}Prefabs/AI/Waypoints/AIWaypoint_GetOut.et", s.m_Truck.GetOrigin(), 15);
			Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 move=unload at=%3 left=%4", now, s.m_sSide, s.m_sName,
				Math.Round(vector.DistanceXZ(s.m_Truck.GetOrigin(), s.m_vTo))), LogLevel.NORMAL);
			return;
		}
		if (aboard > 0 && now - s.m_iMoveAt < UNLOAD_S)
			return;
		Settle(s, now, "set");
	}

	// Set up where the truck is now: its name, launch spot and the operators' post there; ready SETUP_AFTER_MOVE later.
	protected static void Settle(ZCR_DroneSite s, int now, string how)
	{
		SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(s.m_Truck.FindComponent(SCR_AIVehicleUsageComponent));
		if (usage && s.m_Operators.GetGroupUtilityComponent())
			s.m_Operators.GetGroupUtilityComponent().RemoveUsableVehicle(usage);
		ClearWaypoint(s);
		vector here = s.m_Truck.GetOrigin();
		vector launch;
		if (vector.DistanceXZ(here, s.m_vPos) > 50 && ZCR_Drones.ClearSpot(here, here + (here - s.m_vPos), launch))
		{
			launch[1] = GetGame().GetWorld().GetSurfaceY(launch[0], launch[2]);
			s.m_vPos = here;
			s.m_vLaunch = launch;
			s.m_sName = Name(here);
			s.m_iMoves++;
		}
		s.m_iMove = 0;
		s.m_iLaunches = 0;
		s.m_bDue = false;
		s.m_sWhy = "";
		s.m_iReadyAt = now + SETUP_AFTER_MOVE;
		s.m_iSetAt = s.m_iReadyAt;
		ZCR_DroneOperator.Moving(s.m_Operators, false);
		ZCR_DroneOperator.NewPost(s.m_Operators, s.m_vPos + Vector(6, 0, 4), s.m_vPos);
		Print(string.Format("[ZCR][DRONESITE] t=%1 side=%2 move=%3 at=%4 moves=%5 why=%6 x=%7 z=%8", now, s.m_sSide, how, s.m_sName, s.m_iMoves, s.m_sWhy,
			Math.Round(s.m_vPos[0]), Math.Round(s.m_vPos[2])), LogLevel.NORMAL);
	}

	// Clear ground 300-500 m off, not toward the front (within 100 degrees of straight away from it), not the sea.
	protected static bool NewSpot(ZCR_DroneSite s, vector front, out vector to)
	{
		vector here = s.m_vPos;
		vector away = here - front;
		away[1] = 0;
		if (front == vector.Zero || away.Length() < 1)
			away = Vector(0, 0, -1);
		away.Normalize();
		for (int tries; tries < 8; tries++)
		{
			float r = Math.RandomFloat(-100, 100) * Math.DEG2RAD;
			vector dir = Vector(away[0] * Math.Cos(r) - away[2] * Math.Sin(r), 0, away[0] * Math.Sin(r) + away[2] * Math.Cos(r));
			vector cand = here + dir * Math.RandomFloat(300, 500);
			vector spot;
			if (ZCR_Drones.ClearSpot(cand, cand + dir * 100, spot))
			{
				spot[1] = GetGame().GetWorld().GetSurfaceY(spot[0], spot[2]);
				to = spot;
				return true;
			}
		}
		return false;
	}

	protected static void Aboard(ZCR_DroneSite s, out int aboard, out int alive)
	{
		array<AIAgent> agents = {};
		s.m_Operators.GetAgents(agents);
		foreach (AIAgent a : agents)
		{
			ChimeraCharacter man;
			if (a)
				man = ChimeraCharacter.Cast(a.GetControlledEntity());
			if (!man || !man.GetCharacterController() || man.GetCharacterController().GetLifeState() == ECharacterLifeState.DEAD)
				continue;
			alive++;
			if (man.IsInVehicle() && CompartmentAccessComponent.GetVehicleIn(man) == s.m_Truck)
				aboard++;
		}
	}

	// The team's one order of the move (the previous one taken off); a boarding order gets its vehicle before the team
	// gets the order, as the traffic simulation does it.
	protected static AIWaypoint Waypoint(ZCR_DroneSite s, ResourceName prefab, vector at, float radius, IEntity vehicle = null)
	{
		ClearWaypoint(s);
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = at;
		AIWaypoint w = AIWaypoint.Cast(GetGame().SpawnEntityPrefabEx(prefab, false, params: params));
		if (!w)
			return null;
		SCR_BoardingEntityWaypoint board = SCR_BoardingEntityWaypoint.Cast(w);
		if (board && vehicle)
			board.SetEntity(vehicle);
		w.SetCompletionRadius(radius);
		s.m_Operators.AddWaypoint(w);
		s.m_Waypoint = w;
		return w;
	}

	protected static void ClearWaypoint(ZCR_DroneSite s)
	{
		if (!s.m_Waypoint)
			return;
		if (s.m_Operators)
			s.m_Operators.RemoveWaypoint(s.m_Waypoint);
		RplComponent.DeleteRplEntity(s.m_Waypoint, false);
		s.m_Waypoint = null;
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
			else if (s.m_iMove != 0)
				text += s.m_sName + " moving";
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
