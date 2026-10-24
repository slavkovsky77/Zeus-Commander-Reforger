// The camera director for watched lab matches (server side), as on Arma 3 (ac-lab lab/director.sqf):
// the server knows every unit, so it picks each shot and tells the watching game where to look
// (ZCR_Watch draws it). Runs only on a lab server started with -zcrWatchServer, once a player
// connects.
//
// Shots, about 18 s each, the busiest first:
//   capture   a base changed hands in the last 40 s
//   storm     a side storms a base (ZCR_Storm) - in the last 40 s
//   plan      a commander changed its plan: its main effort, with the commander's intent
//   fight     soldiers of both sides within ~300 m of each other; losses there count double
//   close-up  after a fight shot: one soldier of that fight, followed, from 40 m
//   hot zone  every 5th shot, and when nothing goes on: the towns where the match is decided,
//             not too high (at most ~3 km across)
// The same spot loses interest after three shots in a row.
// Drawn over every shot (sent every 3 s): bases with their owner's colour, a trail of growing
// squares from each side's troops to its main effort, losses of the last 90 s in side colours,
// and the fights; a panel with both commanders' intent, bases held and recent losses.
class ZCR_Director
{
	protected static ref ZCR_Director s_Instance;
	protected static ref array<string> MAIN_SIDES = {"US", "USSR"};

	protected ref array<int> m_aWatchers = {};
	protected int m_iShot;
	protected int m_iShotEnd;
	protected int m_iDroneCutAt = -1;   // the drone launch the camera last cut to
	protected bool m_bDroneNow;
	protected IEntity m_FollowedDrone;
	protected int m_iDroneGoneAt = -1;
	protected int m_iDroneShotAt;
	protected int m_iNextOverlay;
	protected string m_sLastKey;
	protected int m_iRepeats;
	protected vector m_vLastFight;
	protected bool m_bLastWasFight;
	protected ref map<SCR_CampaignMilitaryBaseComponent, string> m_mOwners = new map<SCR_CampaignMilitaryBaseComponent, string>();
	protected ref array<string> m_aCaptureText = {};
	protected ref array<vector> m_aCapturePos = {};
	protected ref array<int> m_aCaptureAt = {};
	protected ref map<string, int> m_mPlanShown = new map<string, int>();
	// The last scan: soldiers of the two main sides.
	protected ref array<IEntity> m_aMen = {};
	protected ref array<IEntity> m_aScan = {};
	// Where each soldier was at the last scan: who is on the move.
	protected ref map<IEntity, vector> m_mLastPos = new map<IEntity, vector>();
	protected ref array<IEntity> m_aMoving = {};
	// The watcher's controls (phone buttons, as on Arma 3 - ac-lab lab/director.sqf): LOCK or a
	// picked unit holds the camera (AUTO off), CLOSER / WIDER zoom every shot, PREV SHOT goes back.
	protected bool m_bHold;
	protected bool m_bLocked;
	protected float m_fZoom = 1;
	protected string m_sForce;
	protected int m_iSpotUntil;
	protected vector m_vShown;
	protected float m_fShownBack;
	protected float m_fShownHeight;
	protected IEntity m_ShownFollow;
	protected string m_sShownLabel;
	protected vector m_vFollowLast;
	protected string m_sFollowSide;
	protected ref array<vector> m_aHistTarget = {};
	protected ref array<float> m_aHistBack = {};
	protected ref array<float> m_aHistHeight = {};
	protected ref array<IEntity> m_aHistFollow = {};
	protected ref array<string> m_aHistLabel = {};
	protected ref array<IEntity> m_aGroupLeaders = {};
	protected int m_iGroupsAt = -1000;

	static void AddWatcher(int playerId)
	{
		if (!Replication.IsServer())
			return;
		if (!s_Instance)
		{
			s_Instance = new ZCR_Director();
			GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
			Print("[ZCR][DIRECTOR] started", LogLevel.NORMAL);
		}
		if (!s_Instance.m_aWatchers.Contains(playerId))
			s_Instance.m_aWatchers.Insert(playerId);
		s_Instance.m_iShotEnd = 0;
	}

	static string Colour(string side)
	{
		if (side == "US")
			return "0.35 0.62 1";
		if (side == "USSR")
			return "1 0.35 0.3";
		if (side == "FIA")
			return "0.4 0.85 0.4";
		return "0.9 0.9 0.9";
	}

	protected static bool Alive(IEntity entity)
	{
		ChimeraCharacter character = ChimeraCharacter.Cast(entity);
		if (!character)
			return false;
		CharacterControllerComponent controller = character.GetCharacterController();
		return controller && !controller.IsDead();
	}

	protected bool OnFound(IEntity entity)
	{
		if (Alive(entity))
			m_aScan.Insert(entity);
		return true;
	}

	protected bool OnlyCharacters(IEntity entity)
	{
		return ChimeraCharacter.Cast(entity) != null;
	}

	protected void Scan()
	{
		// The soldiers of both AI Conflict armies, squad by squad (a whole-map sphere query
		// returned nothing).
		m_aScan.Clear();
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
					if (agent && Alive(agent.GetControlledEntity()))
						m_aScan.Insert(agent.GetControlledEntity());
				}
			}
		}
		m_aMen.Clear();
		m_aMoving.Clear();
		map<IEntity, vector> seen = new map<IEntity, vector>();
		foreach (IEntity e : m_aScan)
		{
			string side = ZCR_LossLog.SideOf(e);
			if (side != "US" && side != "USSR")
				continue;
			m_aMen.Insert(e);
			vector before;
			if (m_mLastPos.Find(e, before) && vector.DistanceXZ(before, e.GetOrigin()) > 25)
				m_aMoving.Insert(e);
			seen.Set(e, e.GetOrigin());
		}
		m_mLastPos = seen;
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("director");   // ZCR_Cost: our scripts' share of the frame time
		// Lab (22 Oct, crash hunt): -zcrNoDirector - the camera stays where it starts, no shots across the map.
		if (System.IsCLIParam("zcrNoDirector"))
			return;
		int now = ZCR_LossLog.Seconds();
		WatchCaptures(now);
		// FPV teams hit 8-20 s after launch - too quick for the shot rhythm: cut to them at once.
		// (Not while the camera stays on a drone's impact - a new team cut it away at once.)
		bool onImpact = m_sLastKey == "drone" && m_iDroneGoneAt >= 0 && now - m_iDroneGoneAt < 8;
		if (!m_bHold && !onImpact && ZCR_Drones.s_iFoundAt > m_iDroneCutAt && LiveDrone())
		{
			m_iDroneCutAt = ZCR_Drones.s_iFoundAt;
			m_bDroneNow = true;
			m_iShotEnd = 0;
		}
		// A drone followed to the end (Martin: "I could watch it until it reaches its target"): the shot
		// lasts while it flies, up to 2 minutes (one that hovers with nothing to hit is left then).
		if (m_sLastKey == "drone" && m_FollowedDrone && now - m_iDroneShotAt < 120 && m_iShotEnd < now + 2)
			m_iShotEnd = now + 2;
		// The followed drone has hit: the camera stays on the impact 8 game seconds - 4 at 2x (Martin:
		// wait 2-3 s on the explosion to see what happened, it was too fast), then on.
		if (m_sLastKey == "drone" && !m_FollowedDrone && m_iDroneShotAt > 0 && m_iShotEnd > 0)
		{
			if (m_iDroneGoneAt < 0)
			{
				m_iDroneGoneAt = now;
				m_iShotEnd = now + 8;
			}
			else if (now - m_iDroneGoneAt >= 8)
			{
				m_iShotEnd = 0;
				m_iDroneShotAt = 0;
			}
		}
		// A tap on the picture holds the camera there for 30 s.
		if (m_iSpotUntil > 0 && now >= m_iSpotUntil)
		{
			m_iSpotUntil = 0;
			if (!m_bLocked)
			{
				m_bHold = false;
				m_iShotEnd = 0;
			}
		}
		// A picked unit that falls: the nearest of his side nearby takes over (Arma 3: his squad).
		if (m_bHold && m_ShownFollow && ChimeraCharacter.Cast(m_ShownFollow) && !Alive(m_ShownFollow))
			FollowNearest(now);
		if (m_ShownFollow)
			m_vFollowLast = m_ShownFollow.GetOrigin();
		if (!m_bHold && now >= m_iShotEnd)
			NextShot(now);
		if (now >= m_iNextOverlay)
		{
			m_iNextOverlay = now + 3;
			SendOverlay(now);
		}
	}

	protected void WatchCaptures(int now)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return;
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base)
				continue;
			string owner;
			if (base.GetFaction())
				owner = base.GetFaction().GetFactionKey();
			string before;
			if (m_mOwners.Find(base, before) && before != owner)
			{
				string text = string.Format("CAPTURE: %1 takes %2 from %3", owner, ZCR_Strategist.BaseName(base), before);
				m_aCaptureText.Insert(text);
				m_aCapturePos.Insert(base.GetOwner().GetOrigin());
				m_aCaptureAt.Insert(now);
			}
			m_mOwners.Set(base, owner);
		}
	}

	// The panel's event feed: captures, storms, drone teams - the last three, newest first.
	protected static ref array<string> s_aNotes = {};

	static void Note(string text)
	{
		s_aNotes.InsertAt(Clock(ZCR_LossLog.Seconds()) + " " + text, 0);
		while (s_aNotes.Count() > 3)
			s_aNotes.Remove(3);
	}

	protected int m_iSpeedTick = -1;
	protected int m_iSpeedT;

	// " (2x)" when the game runs faster than the clock (the Diag Menu's time multiplier, solo).
	protected string Speed(int now)
	{
		int tick = System.GetTickCount();
		if (m_iSpeedTick < 0)
		{
			m_iSpeedTick = tick;
			m_iSpeedT = now;
			return "";
		}
		float real = (tick - m_iSpeedTick) / 1000.0;
		if (real < 20)
			return "";
		float x = (now - m_iSpeedT) / real;
		if (x < 1.2)
			return "";
		return string.Format("  (%1x speed)", Math.Round(x * 10) / 10);
	}

	// One side's panel: who commands, bases and soldiers, the plan, what its squads do now, drones,
	// the latest decisions.
	protected string SidePanel(string side, int now)
	{
		if (LabTest())
			return TestPanel(side);
		ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(side);
		string source = plan.GetSource();
		string intent = plan.GetIntent();
		if (intent.IsEmpty())
		{
			// No plan yet: our doctrine before its first plan (a minute in), or AI Conflict alone
			// (Martin, 23:17: "AI Conflict alone vs AI Conflict alone? wtf" - it was the first minute).
			string bridge;
			if (System.GetCLIParam("zcrBridge" + side, bridge) && bridge.StartsWith("http"))
			{
				source = "phased";
				intent = "first plan a minute into the match";
			}
			else
			{
				source = "AI Conflict";
				intent = "AI Conflict's own commander decides";
			}
		}
		string name = "BLUFOR";
		if (side == "USSR")
			name = "OPFOR";
		int held, men;
		foreach (SCR_CampaignMilitaryBaseComponent base, string owner : m_mOwners)
		{
			if (owner == side)
				held++;
		}
		foreach (IEntity e : m_aMen)
		{
			if (e && ZCR_LossLog.SideOf(e) == side)
				men++;
		}
		// Arma 3's panel: the side in its colour and bold, grey section labels, coloured decisions.
		string br = "<br/>";
		string text = "<b>" + ZCR_Feed.SideCol(side, side + "  " + name) + "</b>  " + Commander(source) + br;
		text += string.Format("%1 bases  -  %2 soldiers  -  lost %3 in the last 2 min", held, men, LossesNear(vector.Zero, 1e9, now - 120, side)) + br;
		text += ZCR_Feed.Col(ZCR_Feed.GREY, "PLAN") + br + "  " + ZCR_Feed.Col(ZCR_Feed.YELLOW, intent) + br;
		text += ZCR_Feed.Col(ZCR_Feed.GREY, "NOW DOING") + br + ZCR_Feed.NowText(side) + br;
		text += ZCR_Feed.Col(ZCR_Feed.GREY, "GOALS") + br + ZCR_Goals.Text(side, m_mOwners) + br;
		text += ZCR_Feed.Col(ZCR_Feed.GREY, "DRONES") + string.Format("  %1 teams sent, %2 in the air", ZCR_Drones.Launched(side), ZCR_Drones.InAir(side)) + br;
		if (ZCR_DroneSites.On())
			text += "  sites: " + ZCR_DroneSites.Text(side) + br;
		text += ZCR_Feed.Col(ZCR_Feed.GREY, "SUPPLIES") + ZCR_Logistics.Text(side, now, m_mOwners) + br;
		text += ZCR_Feed.Col(ZCR_Feed.GREY, "LATEST DECISIONS") + br + ZCR_Feed.Latest(side);
		return text;
	}

	// A lab test (no commander at all - AI Conflict is off): the panels say what the test is (Martin, 23 Oct 22:20,
	// watching the DCO storm: "what is that? AI Conflict alone against AI Conflict alone?").
	protected static bool LabTest()
	{
		return System.IsCLIParam("aicfOff") && (System.IsCLIParam("zcrGunTest") || System.IsCLIParam("zcrDriveTest") || System.IsCLIParam("zcrTrafficSim"));
	}

	// -zcrTestTitle from the runner: the sub-lab's names for the track and the setup (underscores for spaces).
	protected static string TestTitle()
	{
		string title;
		if (!System.GetCLIParam("zcrTestTitle", title) || title.IsEmpty())
			return "a small test scenario";
		title.Replace("_", " ");
		return title;
	}

	protected string TestPanel(string side)
	{
		string name = "BLUFOR";
		if (side == "USSR")
			name = "OPFOR";
		string br = "<br/>";
		string ai = "the game's own soldier AI";
		typename dco = String("DCO_Log").ToType();
		if (dco)
			ai = "the DCO_AI mod";
		string text = "<b>" + ZCR_Feed.SideCol(side, side + "  " + name) + "</b>  LAB TEST - no commander" + br;
		text += ZCR_Feed.Col(ZCR_Feed.GREY, "SOLDIERS") + "  " + ai + br;
		array<IEntity> units = {};
		array<string> labels = {};
		ZCR_DriveTest.Units(units, labels);
		ZCR_GunTest.Units(units, labels);
		ZCR_TrafficSim.Units(units, labels);
		string mine = string.Format(": %1 ", side);
		int shown;
		foreach (string l : labels)
		{
			if (!l.Contains(mine) || shown >= 6)
				continue;
			text += "  " + l + br;
			shown++;
		}
		return text;
	}

	// Who is commanding, in plain words.
	protected static string Commander(string source)
	{
		if (source.Contains("llm"))
			return "our doctrine + Gemini";
		if (source == "AI Conflict")
			return "AI Conflict alone";
		return "our doctrine";
	}

	protected static string Clock(int seconds)
	{
		int m = seconds / 60;
		int s = seconds % 60;
		if (s < 10)
			return string.Format("%1:0%2", m, s);
		return string.Format("%1:%2", m, s);
	}

	protected string Near(vector at)
	{
		string best;
		float bestDistance = 1e9;
		foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
		{
			float d = vector.DistanceXZ(at, pos);
			if (d < bestDistance)
			{
				bestDistance = d;
				best = ZCR_Strategist.s_mNodeName.Get(node);
				// Whose: both sides' main bases have the same name on Everon.
				string owner = ZCR_Strategist.s_mNodeOwner.Get(node);
				if (!owner.IsEmpty())
					best += " (" + owner + ")";
			}
		}
		if (best.IsEmpty())
			return "";
		if (bestDistance < 500)
			return "at " + best;
		return "near " + best;
	}

	protected int LossesNear(vector at, float radius, int since, string side)
	{
		int n;
		for (int i; i < ZCR_LossLog.s_aRecentPos.Count(); i++)
		{
			if (ZCR_LossLog.s_aRecentAt[i] < since)
				continue;
			if (!side.IsEmpty() && ZCR_LossLog.s_aRecentSide[i] != side)
				continue;
			if (vector.DistanceXZ(at, ZCR_LossLog.s_aRecentPos[i]) < radius)
				n++;
		}
		return n;
	}

	// The fights: 250 m cells with both sides within the cell and its neighbours.
	// Each: [score, centre, us, ussr]
	protected void Fights(int now, out array<float> scores, out array<vector> centres, out array<int> us, out array<int> ussr)
	{
		scores = {};
		centres = {};
		us = {};
		ussr = {};
		map<string, ref array<IEntity>> cells = new map<string, ref array<IEntity>>();
		foreach (IEntity e : m_aMen)
		{
			vector p = e.GetOrigin();
			string key = string.Format("%1_%2", Math.Floor(p[0] / 250), Math.Floor(p[2] / 250));
			array<IEntity> cell;
			if (!cells.Find(key, cell))
			{
				cell = {};
				cells.Set(key, cell);
			}
			cell.Insert(e);
		}
		foreach (string key, array<IEntity> cell : cells)
		{
			array<string> parts = {};
			key.Split("_", parts, true);
			int cx = parts[0].ToInt();
			int cz = parts[1].ToInt();
			int nUS, nUSSR;
			vector at;
			foreach (IEntity e : cell)
				at += e.GetOrigin();
			at = at / cell.Count();
			for (int dx = -1; dx <= 1; dx++)
			{
				for (int dz = -1; dz <= 1; dz++)
				{
					array<IEntity> other;
					if (!cells.Find(string.Format("%1_%2", cx + dx, cz + dz), other))
						continue;
					foreach (IEntity e : other)
					{
						if (ZCR_LossLog.SideOf(e) == "US")
							nUS++;
						else
							nUSSR++;
					}
				}
			}
			if (Math.Min(nUS, nUSSR) == 0)
				continue;
			scores.Insert(Math.Min(nUS, nUSSR) + 1.5 * LossesNear(at, 400, now - 60, ""));
			centres.Insert(at);
			us.Insert(nUS);
			ussr.Insert(nUSSR);
		}
	}

	protected void NextShot(int now)
	{
		// The driving test track (-zcrDriveTest): only its cars move - follow them (near the trap first).
		if (ZCR_DriveTest.Active())
		{
			string carLabel;
			IEntity car = ZCR_DriveTest.CameraCar(carLabel);
			if (car)
			{
				Show(car.GetOrigin(), 30, 14, car, carLabel, false);
				m_iShotEnd = now + 25;
				return;
			}
		}
		if (ZCR_GunTest.Active())
		{
			string gunLabel;
			IEntity gunUnit = ZCR_GunTest.CameraUnit(gunLabel);
			if (gunUnit && ZCR_DroneOperator.IsOperator(gunUnit))
			{
				// Close enough to see the goggles and the controller (Martin, 24 Oct 15:32).
				Show(gunUnit.GetOrigin(), 9, 3, gunUnit, gunLabel, false);
				m_iShotEnd = now + 15;
				return;
			}
			if (gunUnit)
			{
				Show(gunUnit.GetOrigin(), 40, 18, gunUnit, gunLabel, false);
				m_iShotEnd = now + 20;
				return;
			}
		}
		if (ZCR_TrafficSim.Active())
		{
			string simLabel;
			IEntity simCar = ZCR_TrafficSim.CameraCar(simLabel);
			if (simCar)
			{
				Show(simCar.GetOrigin(), 30, 14, simCar, simLabel, false);
				m_iShotEnd = now + 25;
				return;
			}
		}
		string force = m_sForce;   // "action": the best fight now; "front": the hot zone
		m_sForce = "";
		m_iShot++;
		Scan();
		vector target;
		float back = 220;
		float height = 260;
		IEntity follow;
		string label;
		string key;
		int duration = 18;

		array<float> scores;
		array<vector> centres;
		array<int> us, ussr;
		Fights(now, scores, centres, us, ussr);
		int best = -1;
		for (int i; i < scores.Count(); i++)
		{
			float s = scores[i];
			if (vector.DistanceXZ(centres[i], m_vLastFight) < 250 && m_iRepeats >= 2)
				s *= 0.3;
			if (best < 0 || s > scores[best])
				best = i;
		}

		// A capture not yet shown.
		int capture = -1;
		for (int c; c < m_aCaptureAt.Count(); c++)
		{
			if (now - m_aCaptureAt[c] <= 40)
				capture = c;
		}
		// A plan change not yet shown.
		string planSide;
		array<string> planOrder = {"USSR", "US"};
		foreach (string side : planOrder)
		{
			// Only when the main effort moves to another base (a replan to the same base is no news).
			ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(side);
			int shown = -1;
			if (!m_mPlanShown.Find(side, shown))
				shown = -1;
			if (plan.GetMainEffort() >= 0 && plan.GetMainEffort() != shown && ZCR_Strategist.s_mNodePos.Contains(plan.GetMainEffort()))
			{
				planSide = side;
				break;
			}
		}

		IEntity armour;
		string armourLabel;
		IEntity truck;
		string truckLabel;
		vector siteAt;
		string siteLabel;
		if (force.IsEmpty() && capture >= 0)
		{
			target = m_aCapturePos[capture];
			label = m_aCaptureText[capture];
			key = "capture" + capture;
			back = 260;
			height = 300;
			m_aCaptureAt[capture] = -1000;
		}
		else if (force.IsEmpty() && ZCR_Storm.PendingEvent(now) >= 0)
		{
			// A storm: the climax of an assault - close, and close-ups follow it like a fight.
			int storm = ZCR_Storm.PendingEvent(now);
			target = ZCR_Storm.s_aEventPos[storm];
			label = ZCR_Storm.s_aEventText[storm];
			key = "assault-storm" + storm;
			back = 80;
			height = 60;
			m_vLastFight = target;
			ZCR_Storm.s_aEventAt[storm] = -1000;
		}
		else if (force.IsEmpty() && !planSide.IsEmpty())
		{
			ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(planSide);
			m_mPlanShown.Set(planSide, plan.GetMainEffort());
			target = ZCR_Strategist.s_mNodePos.Get(plan.GetMainEffort());
			label = string.Format("%1 COMMANDER (%2): %3", planSide, plan.GetSource(), plan.GetIntent());
			key = "plan" + planSide;
			back = 500;
			height = 600;
		}
		else if (force.IsEmpty() && (m_bDroneNow || m_iShot % 3 == 1) && LiveDrone())
		{
			// An FPV drone on its way: followed until it hits (Martin on Arma 3: "I didn't see the
			// finish of the FPV attack").
			follow = LiveDrone();
			target = follow.GetOrigin();
			label = string.Format("%1 FPV DRONE on its way %2", m_sDroneSide, Near(target));
			key = "drone";
			// Close behind it (the camera now looks at the drone itself, at its height).
			back = 16;
			height = 6;
			duration = 30;
		}
		else if (force.IsEmpty() && m_iShot % 4 == 2 && RidingVehicle())
		{
			// A vehicle with soldiers in it, on the move (Martin: "I didn't notice any usage of cars").
			follow = RidingVehicle();
			target = follow.GetOrigin();
			label = string.Format("%1 %2%3 WITH %4 ABOARD %5", m_sRideSide, VehicleName(follow), TeamTag(follow), m_iRideMen, Near(target));
			key = "ride";
			back = 25;
			height = 9;
			duration = 20;
		}
		else if (force.IsEmpty() && m_iShot % 6 == 0 && ZCR_Armour.Pick(Turn("US", "USSR"), armour, armourLabel))
		{
			// A tank or IFV of ours going in (Martin, 21 Oct: "make AI use them also for combat").
			follow = armour;
			target = armour.GetOrigin();
			label = armourLabel + " " + Near(target);
			key = "armour";
			back = 30;
			height = 12;
			duration = 20;
		}
		else if (force.IsEmpty() && m_iShot % 6 == 3 && SupplyTruck(truck, truckLabel))
		{
			// A supply truck on the road with what it carries (Martin, 21 Oct: "it should be seen on
			// vehicles during the game if they carry supplies and how much").
			follow = truck;
			target = truck.GetOrigin();
			label = truckLabel;
			key = "truck";
			back = 25;
			height = 10;
			duration = 20;
		}
		else if (force.IsEmpty() && m_iShot % 6 == 5 && BuildSite(siteAt, siteLabel))
		{
			// A building going up, the builder and his crew at it (Martin: "I am not seeing defences
			// being built by anybody").
			target = siteAt;
			label = siteLabel;
			key = "build";
			back = 30;
			height = 14;
			duration = 16;
		}
		else if (force.IsEmpty() && m_bLastWasFight && best >= 0)
		{
			// Close-up in the fight just shown, alternating the side.
			array<IEntity> pool = {};
			string want = Turn("US", "USSR");
			// Someone actually in the fight first (knows an enemy within 400 m) - Martin: "watch the
			// fight closer, zoom in for a while".
			foreach (IEntity e : m_aMen)
			{
				if (vector.DistanceXZ(e.GetOrigin(), m_vLastFight) < 300 && ZCR_LossLog.SideOf(e) == want && ZCR_CoverLayer.NearestEnemy(e))
					pool.Insert(e);
			}
			if (pool.IsEmpty())
			{
				foreach (IEntity e : m_aMen)
				{
					if (vector.DistanceXZ(e.GetOrigin(), m_vLastFight) < 300 && ZCR_LossLog.SideOf(e) == want)
						pool.Insert(e);
				}
			}
			if (pool.IsEmpty())
			{
				foreach (IEntity e : m_aMen)
				{
					if (vector.DistanceXZ(e.GetOrigin(), m_vLastFight) < 300)
						pool.Insert(e);
				}
			}
			if (!pool.IsEmpty())
			{
				follow = pool.GetRandomElement();
				target = follow.GetOrigin();
				label = string.Format("CLOSE-UP: %1 %2%3 %4", ZCR_LossLog.SideOf(follow), ZCR_LossLog.Role(follow), TeamTag(follow), Near(target));
				key = "close";
				back = 14;
				height = 7;
				duration = 20;
			}
		}
		bool hotTurn = force == "front" || (force.IsEmpty() && m_iShot % 5 == 0);
		if (key.IsEmpty() && !hotTurn && best >= 0)
		{
			target = centres[best];
			int lostUS = LossesNear(target, 500, now - 60, "US");
			int lostUSSR = LossesNear(target, 500, now - 60, "USSR");
			label = string.Format("FIGHT %1 - US %2 v USSR %3 within 400 m", Near(target), us[best], ussr[best]);
			if (lostUS + lostUSSR > 0)
				label += string.Format(" - lost in the last minute: US %1, USSR %2", lostUS, lostUSSR);
			key = string.Format("fight%1_%2", Math.Round(target[0] / 250), Math.Round(target[2] / 250));
			back = 60;
			height = 45;
			duration = 22;
			m_vLastFight = target;
		}
		if (key.IsEmpty() && !hotTurn)
		{
			// An assault (Arma 3's attack shot): soldiers of a side within 300 m of a base they don't
			// hold - an FIA garrison or the enemy's - and the more so with losses there in the last
			// minute. Most of the early fighting is against FIA, whose soldiers aren't in the lists.
			string bestSide;
			int bestNode = -1;
			float bestScore;
			int bestCount;
			foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
			{
				string owner = ZCR_Strategist.s_mNodeOwner.Get(node);
				foreach (string side : MAIN_SIDES)
				{
					if (owner == side || (!m_sFocus.IsEmpty() && side != m_sFocus))
						continue;
					int n;
					foreach (IEntity e : m_aMen)
					{
						if (ZCR_LossLog.SideOf(e) == side && vector.DistanceXZ(e.GetOrigin(), pos) < 300)
							n++;
					}
					if (n < 4)
						continue;
					float sc = n + 3 * LossesNear(pos, 400, now - 60, "");
					if (vector.DistanceXZ(pos, m_vLastFight) < 250 && m_iRepeats >= 2)
						sc *= 0.3;
					if (sc > bestScore)
					{
						bestScore = sc;
						bestNode = node;
						bestSide = side;
						bestCount = n;
					}
				}
			}
			if (bestNode >= 0)
			{
				target = ZCR_Strategist.s_mNodePos.Get(bestNode);
				string holder = ZCR_Strategist.s_mNodeOwner.Get(bestNode);
				label = string.Format("%1 ASSAULT on %2 (%3) - %4 soldiers within 300 m", bestSide, ZCR_Strategist.s_mNodeName.Get(bestNode), holder, bestCount);
				int lost = LossesNear(target, 400, now - 60, "");
				if (lost > 0)
					label += string.Format(" - %1 lost there in the last minute", lost);
				key = "assault" + bestNode;
				back = 70;
				height = 55;
				duration = 22;
				m_vLastFight = target;
			}
		}
		if (key.IsEmpty() && !hotTurn && !m_aMoving.IsEmpty())
		{
			// Nobody fighting: follow someone on the move, alternating the side; in a vehicle, the
			// vehicle (the Arma 3 director followed APCs carrying troops).
			array<IEntity> movers = {};
			string wanted = Turn("US", "USSR");
			foreach (IEntity e : m_aMoving)
			{
				if (ZCR_LossLog.SideOf(e) == wanted)
					movers.Insert(e);
			}
			if (movers.IsEmpty())
				movers.Copy(m_aMoving);
			// Out in the field, not walking around a base: the one farthest from any base.
			IEntity mover = movers.GetRandomElement();
			float farthest = -1;
			foreach (IEntity e : movers)
			{
				float nearest = 1e9;
				foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
					nearest = Math.Min(nearest, vector.DistanceXZ(e.GetOrigin(), pos));
				if (nearest > farthest)
				{
					farthest = nearest;
					mover = e;
				}
			}
			IEntity root = mover.GetRootParent();
			follow = mover;
			string what = ZCR_LossLog.Role(mover);
			if (root && Vehicle.Cast(root))
			{
				follow = root;
				what = ZCR_LossLog.ShortName(root);
			}
			target = follow.GetOrigin();
			label = string.Format("%1 %2%3 on the move %4", ZCR_LossLog.SideOf(mover), what, TeamTag(mover), Near(target));
			key = "move";
			back = 90;
			height = 80;
			duration = 16;
		}
		if (key.IsEmpty() && force != "front" && m_sLastKey == "hot")
		{
			// The hot zone again: one side's objective instead, the sides in turn (Arma 3's
			// objective shot) - the quiet first minutes otherwise show the same view over and over.
			string side = Turn("US", "USSR");
			for (int k = 0; k < 2 && key.IsEmpty(); k++)
			{
				ZCR_StrategicPlan sidePlan = ZCR_StrategicPlan.Get(side);
				int node = sidePlan.GetMainEffort();
				if (node >= 0 && ZCR_Strategist.s_mNodePos.Contains(node))
				{
					target = ZCR_Strategist.s_mNodePos.Get(node);
					string intent = sidePlan.GetIntent();
					if (intent.Length() > 100)
						intent = intent.Substring(0, 100) + "...";
					string what = "OBJECTIVE";
					if (ZCR_Strategist.s_mNodeOwner.Get(node) == side)
						what = "STAGING";   // gathering at its own base before the attack
					label = string.Format("%1 %2: %3 (%4) - %5", side, what, ZCR_Strategist.s_mNodeName.Get(node), ZCR_Strategist.s_mNodeOwner.Get(node), intent);
					key = "objective" + side;
					back = 350;
					height = 260;
				}
				if (side == "US")
					side = "USSR";
				else
					side = "US";
			}
		}
		if (key.IsEmpty())
		{
			// Hot zone: the main efforts and the fights, at most ~3 km across.
			array<vector> spots = {};
			foreach (string side : MAIN_SIDES)
			{
				ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(side);
				if (plan.GetMainEffort() >= 0 && ZCR_Strategist.s_mNodePos.Contains(plan.GetMainEffort()))
					spots.Insert(ZCR_Strategist.s_mNodePos.Get(plan.GetMainEffort()));
			}
			for (int f; f < centres.Count() && f < 4; f++)
				spots.Insert(centres[f]);
			if (spots.IsEmpty())
			{
				foreach (IEntity e : m_aMen)
					spots.Insert(e.GetOrigin());
			}
			vector lo = "1e9 0 1e9";
			vector hi = "-1e9 0 -1e9";
			foreach (vector p : spots)
			{
				lo[0] = Math.Min(lo[0], p[0]);
				lo[2] = Math.Min(lo[2], p[2]);
				hi[0] = Math.Max(hi[0], p[0]);
				hi[2] = Math.Max(hi[2], p[2]);
			}
			if (spots.IsEmpty())
			{
				lo = Vector(5000, 0, 5000);
				hi = Vector(7000, 0, 7000);
			}
			float width = Math.Min(2200, Math.Max(800, Math.Max(hi[0] - lo[0], hi[2] - lo[2]) + 500));
			target = (lo + hi) * 0.5;
			back = width * 0.5;
			height = width * 0.55;
			label = string.Format("HOT ZONE %1 - %2", Near(target), Score());
			key = "hot";
		}
		m_bLastWasFight = key.StartsWith("fight") || key.StartsWith("assault");
		if (key == m_sLastKey)
			m_iRepeats++;
		else
			m_iRepeats = 0;
		m_sLastKey = key;
		m_iShotEnd = now + duration;
		m_bDroneNow = false;
		m_FollowedDrone = null;
		m_iDroneGoneAt = -1;
		if (key == "drone")
		{
			m_FollowedDrone = follow;
			m_iDroneShotAt = now;
		}

		Show(target, back, height, follow, label, true);
		Print(string.Format("[ZCR][CAM] t=%1 shot=%2 kind=%3 men=%4 moving=%5 fights=%6 label=%7", now, m_iShot, key, m_aMen.Count(), m_aMoving.Count(), centres.Count(), label), LogLevel.NORMAL);
		SendOverlay(now);
	}

	// Fly the watchers' cameras to a shot (zoomed as they asked) and move their observers there.
	protected void Show(vector target, float back, float height, IEntity follow, string label, bool remember)
	{
		m_vShown = target;
		m_fShownBack = back;
		m_fShownHeight = height;
		m_ShownFollow = follow;
		m_sShownLabel = label;
		if (follow)
		{
			m_vFollowLast = follow.GetOrigin();
			m_sFollowSide = ZCR_LossLog.SideOf(follow);
		}
		if (remember)
		{
			m_aHistTarget.Insert(target);
			m_aHistBack.Insert(back);
			m_aHistHeight.Insert(height);
			m_aHistFollow.Insert(follow);
			m_aHistLabel.Insert(label);
			if (m_aHistTarget.Count() > 30)
			{
				m_aHistTarget.RemoveOrdered(0);
				m_aHistBack.RemoveOrdered(0);
				m_aHistHeight.RemoveOrdered(0);
				m_aHistFollow.RemoveOrdered(0);
				m_aHistLabel.RemoveOrdered(0);
			}
		}
		RplId followId = RplId.Invalid();
		if (follow)
		{
			RplComponent rpl = RplComponent.Cast(follow.FindComponent(RplComponent));
			if (rpl)
				followId = rpl.Id();
		}
		foreach (int playerId : m_aWatchers)
		{
			PlayerController controller = GetGame().GetPlayerManager().GetPlayerController(playerId);
			if (!controller)
				continue;
			ObserversSystem observers = ObserversSystem.Cast(GetGame().GetWorld().FindSystem(ObserversSystem));
			if (observers)
				observers.InsertObserverMP(controller.GetRplIdentity(), target[0], target[2], null);
		}
		string shown = label;
		if (m_bLocked)
			shown = "LOCKED - " + label;
		SCR_BaseGameMode gameMode = SCR_BaseGameMode.Cast(GetGame().GetGameMode());
		if (gameMode)
			gameMode.ZCR_SendShot(target, back * m_fZoom, height * m_fZoom, followId, shown, 18);
		SendOverlay(ZCR_LossLog.Seconds());
	}

	// A watcher's button or tap (ZCR_WatchControls on his game, through his player controller).
	static void Command(int playerId, string cmd, vector pos)
	{
		if (s_Instance && s_Instance.m_aWatchers.Contains(playerId))
			s_Instance.DoCommand(cmd, pos);
	}

	protected void DoCommand(string cmd, vector pos)
	{
		int now = ZCR_LossLog.Seconds();
		Print(string.Format("[ZCR][CAMUI] t=%1 cmd=%2 x=%3 z=%4", now, cmd, Math.Round(pos[0]), Math.Round(pos[2])), LogLevel.NORMAL);
		if (cmd == "next")
		{
			m_iSpotUntil = 0;
			if (!StepTest(now, 1))
				NextShot(now);
		}
		else if (cmd == "prev")
		{
			// In a lab test: the test's unit before.
			if (StepTest(now, -1))
				return;
			// The scene before: its unit if still alive, else its place.
			if (m_aHistTarget.Count() < 2)
				return;
			int last = m_aHistTarget.Count() - 1;
			m_aHistTarget.Remove(last);
			m_aHistBack.Remove(last);
			m_aHistHeight.Remove(last);
			m_aHistFollow.Remove(last);
			m_aHistLabel.Remove(last);
			last--;
			IEntity f = m_aHistFollow[last];
			if (f && ChimeraCharacter.Cast(f) && !Alive(f))
				f = null;
			m_bHold = true;
			m_iShotEnd = now + 18;
			Show(m_aHistTarget[last], m_aHistBack[last], m_aHistHeight[last], f, "BACK: " + m_aHistLabel[last], false);
		}
		else if (cmd == "lock")
		{
			m_bLocked = !m_bLocked;
			m_bHold = m_bLocked;
			if (!m_bHold)
				m_iShotEnd = 0;
			else
				Show(m_vShown, m_fShownBack, m_fShownHeight, m_ShownFollow, m_sShownLabel, false);
		}
		else if (cmd == "auto")
		{
			m_bLocked = false;
			m_bHold = false;
			m_fZoom = 1;
			m_iSpotUntil = 0;
			m_iShotEnd = 0;
		}
		else if (cmd == "closer" || cmd == "wider")
		{
			if (cmd == "closer")
				m_fZoom = Math.Max(0.3, m_fZoom * 0.6);
			else
				m_fZoom = Math.Min(3, m_fZoom * 1.65);
			Show(m_vShown, m_fShownBack, m_fShownHeight, m_ShownFollow, m_sShownLabel, false);
		}
		else if (cmd == "action" || cmd == "overview")
		{
			m_iSpotUntil = 0;
			m_sForce = "action";
			if (cmd == "overview")
				m_sForce = "front";
			NextShot(now);
		}
		else if (cmd.StartsWith("side-"))
		{
			m_sFocus = cmd.Substring(5, cmd.Length() - 5);
			Print(string.Format("[ZCR][CAMUI] t=%1 side focus %2", now, m_sFocus), LogLevel.NORMAL);
		}
		else if (cmd.StartsWith("kind-"))
		{
			m_sKind = cmd.Substring(5, cmd.Length() - 5);
			m_iGroupsAt = -1000;
			Print(string.Format("[ZCR][CAMUI] t=%1 step through %2", now, m_sKind), LogLevel.NORMAL);
			StepGroup(now, 1);
		}
		else if (cmd == "point+" || cmd == "point-")
		{
			int pdir = 1;
			if (cmd == "point-")
				pdir = -1;
			StepPoint(now, pdir);
		}
		else if (cmd == "group+" || cmd == "group-")
		{
			// Out of free look, so the camera goes to the picked unit (25 Oct - Martin: "next/prev vehicles didn't work
			// on the test": they picked cars 13 and 14 while free look kept the camera where it was).
			if (ZCR_Watch.IsFree())
				ZCR_Watch.SetFree(false);
			int dir = 1;
			if (cmd == "group-")
				dir = -1;
			if (!StepTest(now, dir))
				StepGroup(now, dir);
		}
		else if (cmd == "report")
			Report(now);
		else if (cmd == "tap")
			Tap(now, pos);
	}

	// Lab tests (the drive track, the guns test, the traffic and supply runs): PREV / NEXT step through the test's own
	// units (Martin, 23 Oct: "next/prev vehicle doesn't work here on these integration tests" - they stepped through the
	// commander's teams, which a test hasn't got).
	protected int m_iTestTurn;

	protected bool StepTest(int now, int dir)
	{
		array<IEntity> units = {};
		array<string> labels = {};
		ZCR_DriveTest.Units(units, labels);
		ZCR_GunTest.Units(units, labels);
		ZCR_TrafficSim.Units(units, labels);
		if (units.IsEmpty())
			return false;
		m_iTestTurn = (m_iTestTurn + dir + units.Count()) % units.Count();
		IEntity u = units[m_iTestTurn];
		m_bHold = true;
		m_iShotEnd = now + 25;
		Show(u.GetOrigin(), 30, 14, u, string.Format("%1 (%2 of %3)", labels[m_iTestTurn], m_iTestTurn + 1, units.Count()), false);
		return true;
	}

	protected int m_iPoint = -1;
	protected string m_sFocus;          // SIDE button: "" both sides, "US" or "USSR" only
	protected string m_sKind = "teams"; // what PREV / NEXT steps through: teams, vehicles, drones
	protected string m_sRideSide;
	protected int m_iRideMen;
	protected ref map<IEntity, AICF_GroupSlot> m_mLeaderSlot = new map<IEntity, AICF_GroupSlot>();
	protected vector m_vTeamGoal;
	protected string m_sTeamGoal;

	// REPORT (Martin: "when I report an issue, mark the timestamp and the unit I'm looking at, so you
	// have the logs and don't guess"): what the camera shows now, written to the log as [ZCR][REPORT]
	// lines - the shot, the followed unit (side, role, stance, moving, cover, overhead, in a vehicle),
	// its team's goal, enemies its side knows near it, drones in the air near it, soldiers around.
	// lab/report.py gathers these with the log around them and a frame from the recording.
	protected int m_iReports;

	protected void Report(int now)
	{
		m_iReports++;
		int n = m_iReports;
		vector at = m_vShown;
		IEntity f = m_ShownFollow;
		if (f)
			at = f.GetOrigin();
		Print(string.Format("[ZCR][REPORT] n=%1 t=%2 clock=%3 shot=%4 at=%5 %6 label=%7", n, now, Clock(now), m_iShot, Math.Round(at[0]), Math.Round(at[2]), m_sShownLabel), LogLevel.NORMAL);
		if (f)
		{
			string kind = "entity";
			ChimeraCharacter c = ChimeraCharacter.Cast(f);
			string extra = "";
			if (c)
			{
				kind = "soldier";
				CharacterControllerComponent ctl = c.GetCharacterController();
				if (ctl)
					extra = string.Format(" stance=%1", typename.EnumToString(ECharacterStance, ctl.GetStance()));
				extra += string.Format(" vehicle=%1 role=%2 team=%3", c.IsInVehicle(), ZCR_LossLog.Role(f), TeamKey(f));
				extra += ZCR_Sampler.DeathState(f, ZCR_CoverLayer.NearestEnemy(f));
			}
			else if (ZCR_Drones.s_aDrones.Contains(f))
				kind = "drone";
			else if (Vehicle.Cast(f))
				kind = "vehicle " + VehicleName(f);
			Print(string.Format("[ZCR][REPORT] n=%1 followed=%2 side=%3 at=%4 %5 height=%6%7", n, kind, ZCR_LossLog.SideOf(f), Math.Round(at[0]), Math.Round(at[2]),
				Math.Round(at[1] - GetGame().GetWorld().GetSurfaceY(at[0], at[2])), extra), LogLevel.NORMAL);
			AICF_GroupSlot slot = m_mLeaderSlot.Get(f);
			if (slot)
				Print(string.Format("[ZCR][REPORT] n=%1 team slot=%2 men=%3 goal=%4", n, slot.GetSlotId(), AICF_GroupRuntime.CountAliveAgents(slot.GetGroup()), TeamGoal(slot, f)), LogLevel.NORMAL);
		}
		// Around the spot: soldiers per side within 150 m, enemies known, drones near.
		map<string, int> men = new map<string, int>();
		foreach (IEntity e : m_aMen)
		{
			if (e && vector.DistanceXZ(e.GetOrigin(), at) < 150)
				men.Set(ZCR_LossLog.SideOf(e), men.Get(ZCR_LossLog.SideOf(e)) + 1);
		}
		int drones;
		for (int k; k < ZCR_Drones.s_aDrones.Count(); k++)
		{
			IEntity d = ZCR_Drones.s_aDrones[k];
			if (d && vector.DistanceXZ(d.GetOrigin(), at) < 300)
				drones++;
		}
		Print(string.Format("[ZCR][REPORT] n=%1 around US=%2 USSR=%3 known_enemies_US=%4 known_enemies_USSR=%5 drones_within_300=%6", n, men.Get("US"), men.Get("USSR"),
			ZCR_Sampler.KnownEnemiesNear("US", at, 300), ZCR_Sampler.KnownEnemiesNear("USSR", at, 300), drones), LogLevel.NORMAL);
		ZCR_Feed.Note("US", string.Format("REPORT %1 marked at %2", n, Clock(now)));
	}

	// "team A3" - AI Conflict's slot key of the soldier's team (Martin: "messages should contain IDs of
	// units or groups so I can see it and report it to you"). A vehicle: the team of someone aboard.
	protected string TeamKey(IEntity e)
	{
		if (!e)
			return "";
		IEntity who = e;
		if (!ChimeraCharacter.Cast(e))
		{
			who = null;
			foreach (IEntity m : m_aMen)
			{
				if (m && m.GetRootParent() == e)
				{
					who = m;
					break;
				}
			}
			if (!who)
				return "";
		}
		AIControlComponent control = AIControlComponent.Cast(who.FindComponent(AIControlComponent));
		if (!control || !control.GetControlAIAgent())
			return "";
		AIGroup group = control.GetControlAIAgent().GetParentGroup();
		if (!group)
			return "";
		foreach (FactionKey faction, AICF_FactionState state : ZCR_Strategist.s_mStates)
		{
			for (int s; state && s < state.GetSlotCount(); s++)
			{
				AICF_GroupSlot slot = state.GetSlot(s);
				if (slot && slot.GetGroup() == group)
					return "team " + slot.GetSlotKey();
			}
		}
		return "";
	}

	// " (team A3)" or "".
	protected string TeamTag(IEntity e)
	{
		string key = TeamKey(e);
		if (key.IsEmpty())
			return "";
		return " (" + key + ")";
	}

	// "ATTACK Farm - 450 m to go - riding", from AI Conflict's own order for the team.
	protected string TeamGoal(AICF_GroupSlot slot, IEntity leader)
	{
		m_vTeamGoal = vector.Zero;
		m_sTeamGoal = "";
		if (!slot)
			return "";
		string role = typename.EnumToString(AICF_EGroupRole, slot.GetRole());
		string text = role;
		SCR_CampaignMilitaryBaseComponent target = slot.GetTargetBase();
		if (target && target.GetOwner())
		{
			m_vTeamGoal = target.GetOwner().GetOrigin();
			m_sTeamGoal = ZCR_Strategist.BaseName(target);
			text += string.Format(" %1 - %2 m to go", m_sTeamGoal, Math.Round(vector.DistanceXZ(leader.GetOrigin(), m_vTeamGoal)));
		}
		string posture = slot.GetOperationalPosture();
		if (posture == "INFANTRY_MUSTER")
			text += " - gathering at base";
		ChimeraCharacter c = ChimeraCharacter.Cast(leader);
		if (c && c.IsInVehicle())
			text += " - riding";
		return text;
	}


	// A vehicle of the side in turn (or the focus side) with soldiers in it, moving over 4 m/s.
	protected IEntity RidingVehicle()
	{
		string want = Turn("US", "USSR");
		map<IEntity, int> aboard = new map<IEntity, int>();
		foreach (IEntity e : m_aMen)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(e);
			if (!c || !c.IsInVehicle() || ZCR_LossLog.SideOf(e) != want)
				continue;
			IEntity v = e.GetRootParent();
			if (!v || v == e)
				continue;
			Physics phys = v.GetPhysics();
			if (!phys || phys.GetVelocity().Length() < 4)
				continue;
			aboard.Set(v, aboard.Get(v) + 1);
		}
		IEntity best;
		int most;
		foreach (IEntity v, int n : aboard)
		{
			if (n > most)
			{
				most = n;
				best = v;
			}
		}
		m_sRideSide = want;
		m_iRideMen = most;
		return best;
	}

	// Vehicles with US or USSR soldiers in them, and drones in the air, nearest the camera first.
	protected void Movers(array<IEntity> into)
	{
		array<float> dist = {};
		array<IEntity> seen = {};
		if (m_sKind == "drones")
		{
			for (int k; k < ZCR_Drones.s_aDrones.Count(); k++)
			{
				IEntity d = ZCR_Drones.s_aDrones[k];
				if (!d || (!m_sFocus.IsEmpty() && ZCR_Drones.s_aDroneSide[k] != m_sFocus))
					continue;
				vector p = d.GetOrigin();
				if (p[1] - GetGame().GetWorld().GetSurfaceY(p[0], p[2]) < 3)
					continue;
				seen.Insert(d);
			}
		}
		else
		{
			foreach (IEntity e : m_aMen)
			{
				ChimeraCharacter c = ChimeraCharacter.Cast(e);
				if (!c || !c.IsInVehicle())
					continue;
				string side = ZCR_LossLog.SideOf(e);
				if ((side != "US" && side != "USSR") || (!m_sFocus.IsEmpty() && side != m_sFocus))
					continue;
				IEntity v = e.GetRootParent();
				if (v && v != e && !seen.Contains(v))
					seen.Insert(v);
			}
		}
		foreach (IEntity e : seen)
		{
			float d = vector.DistanceXZ(e.GetOrigin(), m_vShown);
			int at = 0;
			while (at < dist.Count() && dist[at] < d)
				at++;
			dist.InsertAt(d, at);
			into.InsertAt(e, at);
		}
	}

	protected static string VehicleName(IEntity v)
	{
		if (!v || !v.GetPrefabData())
			return "vehicle";
		string name = v.GetPrefabData().GetPrefabName();
		int slash = name.LastIndexOf("/");
		if (slash >= 0)
			name = name.Substring(slash + 1, name.Length() - slash - 1);
		name.Replace(".et", "");
		name.Replace("_", " ");
		return name;
	}

	// The side a shot keeps to: the focus, else the sides in turn.
	protected string Turn(string a, string b)
	{
		if (!m_sFocus.IsEmpty())
			return m_sFocus;
		if (m_iShot % 2 == 0)
			return b;
		return a;
	}

	// NEXT / PREV POINT (Martin: "switch between points, so I can watch one point"): the bases in turn;
	// the camera stays over the one shown (locked) until AUTO.
	protected void StepPoint(int now, int dir)
	{
		array<int> nodes = {};
		foreach (int node, vector pos : ZCR_Strategist.s_mNodePos)
		{
			// One side: its own bases and the one it attacks.
			if (!m_sFocus.IsEmpty() && ZCR_Strategist.s_mNodeOwner.Get(node) != m_sFocus && node != ZCR_StrategicPlan.Get(m_sFocus).GetMainEffort())
				continue;
			int at = 0;
			while (at < nodes.Count() && nodes[at] < node)
				at++;
			nodes.InsertAt(node, at);
		}
		if (nodes.IsEmpty())
			return;
		int i = nodes.Find(m_iPoint);
		if (i < 0)
		{
			i = 0;
			if (dir < 0)
				i = nodes.Count() - 1;
		}
		else
			i = (i + dir + nodes.Count()) % nodes.Count();
		m_iPoint = nodes[i];
		vector at = ZCR_Strategist.s_mNodePos.Get(m_iPoint);
		int us, ussr;
		foreach (IEntity e : m_aMen)
		{
			if (!e || vector.DistanceXZ(e.GetOrigin(), at) > 300)
				continue;
			string side = ZCR_LossLog.SideOf(e);
			if (side == "US")
				us++;
			else if (side == "USSR")
				ussr++;
		}
		m_bHold = true;
		m_bLocked = true;
		m_iSpotUntil = 0;
		string label = string.Format("LOCKED - POINT %1 (%2) - within 300 m: US %3, USSR %4", ZCR_Strategist.s_mNodeName.Get(m_iPoint),
			ZCR_Strategist.s_mNodeOwner.Get(m_iPoint), us, ussr);
		Show(at, 180, 150, null, label, true);
		Print(string.Format("[ZCR][CAMUI] t=%1 point %2", now, ZCR_Strategist.s_mNodeName.Get(m_iPoint)), LogLevel.NORMAL);
	}

	// NEXT / PREV GROUP: every team on the map, the two sides in turn (Martin: "I can only switch between
	// the US groups" - it took those within 700 m of the camera), each side nearest first; follow the leader.
	protected void StepGroup(int now, int dir)
	{
		// Teams change slowly; vehicles and drones come and go (a drone lives a minute or two).
		int keep = 40;
		if (m_sKind != "teams")
			keep = 5;
		if (now - m_iGroupsAt > keep || m_aGroupLeaders.IsEmpty() || !m_aGroupLeaders.Contains(m_ShownFollow))
		{
			m_iGroupsAt = now;
			m_aGroupLeaders.Clear();
			if (m_sKind != "teams")
				Movers(m_aGroupLeaders);
			array<ref array<IEntity>> bySide = {};
			foreach (FactionKey faction, AICF_FactionState state : ZCR_Strategist.s_mStates)
			{
				if (m_sKind != "teams" || (!m_sFocus.IsEmpty() && faction != m_sFocus))
					continue;
				array<IEntity> leaders = {};
				array<float> dist = {};
				for (int s; state && s < state.GetSlotCount(); s++)
				{
					AICF_GroupSlot slot = state.GetSlot(s);
					if (!slot || !slot.GetGroup())
						continue;
					IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(slot.GetGroup());
					if (!leader)
						continue;
					m_mLeaderSlot.Set(leader, slot);
					float d = vector.DistanceXZ(leader.GetOrigin(), m_vShown);
					int at = 0;
					while (at < dist.Count() && dist[at] < d)
						at++;
					dist.InsertAt(d, at);
					leaders.InsertAt(leader, at);
				}
				bySide.Insert(leaders);
			}
			for (int k; k < 40; k++)
			{
				foreach (array<IEntity> leaders : bySide)
				{
					if (k < leaders.Count())
						m_aGroupLeaders.Insert(leaders[k]);
				}
			}
		}
		if (m_aGroupLeaders.IsEmpty())
		{
			Print(string.Format("[ZCR][CAMUI] no %1", m_sKind), LogLevel.NORMAL);
			string none = string.Format("NO %1 NOW", m_sKind);
			none.ToUpper();
			Show(m_vShown, 120, 90, null, none, true);
			return;
		}
		int n = m_aGroupLeaders.Count();
		int i = m_aGroupLeaders.Find(m_ShownFollow);
		if (i < 0)
		{
			i = 0;
			if (dir < 0)
				i = n - 1;
		}
		else
			i = (i + dir + n) % n;
		IEntity leader = m_aGroupLeaders[i];
		m_bHold = true;
		m_bLocked = true;
		m_iSpotUntil = 0;
		if (m_sKind == "drones")
		{
			int k = ZCR_Drones.s_aDrones.Find(leader);
			string droneSide;
			if (k >= 0)
				droneSide = ZCR_Drones.s_aDroneSide[k];
			Show(leader.GetOrigin(), 16, 6, leader, string.Format("FOLLOWING DRONE %1 OF %2: %3 FPV of drone team %4 %5", i + 1, n, droneSide, ZCR_Drones.TeamNo(leader), Near(leader.GetOrigin())), true);
			return;
		}
		if (m_sKind == "vehicles")
		{
			Show(leader.GetOrigin(), 30, 14, leader, string.Format("FOLLOWING VEHICLE %1 OF %2: %3 %4%5 %6", i + 1, n, ZCR_LossLog.SideOf(leader), VehicleName(leader), TeamTag(leader), Near(leader.GetOrigin())), true);
			return;
		}
		AICF_GroupSlot slot = m_mLeaderSlot.Get(leader);
		int men = 1;
		if (slot)
			men = AICF_GroupRuntime.CountAliveAgents(slot.GetGroup());
		string key = "team";
		if (slot)
			key = "team " + slot.GetSlotKey();
		Show(leader.GetOrigin(), 60, 45, leader, string.Format("FOLLOWING TEAM %1 OF %2: %3 %4 (%5 men) %6 - %7", i + 1, n,
			ZCR_LossLog.SideOf(leader), key, men, Near(leader.GetOrigin()), TeamGoal(slot, leader)), true);
	}

	// A tap on the picture: the soldier or vehicle there is followed (AUTO off until another pick);
	// anywhere else the camera flies there for 30 s.
	protected void Tap(int now, vector pos)
	{
		IEntity best;
		float bestDistance = 40;
		foreach (IEntity e : m_aMen)
		{
			if (!e || !Alive(e))
				continue;
			float d = vector.DistanceXZ(e.GetOrigin(), pos);
			if (d < bestDistance)
			{
				bestDistance = d;
				best = e;
			}
		}
		if (best)
		{
			IEntity root = best.GetRootParent();
			IEntity follow = best;
			string what = ZCR_LossLog.Role(best) + TeamTag(best);
			if (root && Vehicle.Cast(root))
			{
				follow = root;
				what = ZCR_LossLog.ShortName(root);
			}
			m_bHold = true;
			m_bLocked = true;
			m_iSpotUntil = 0;
			Show(follow.GetOrigin(), 45, 32, follow, string.Format("FOLLOWING %1 %2 %3", ZCR_LossLog.SideOf(best), what, Near(follow.GetOrigin())), true);
			return;
		}
		m_bHold = true;
		m_iSpotUntil = now + 30;
		Show(pos, 160, 140, null, "HERE " + Near(pos), true);
	}

	protected void FollowNearest(int now)
	{
		IEntity best;
		float bestDistance = 150;
		foreach (IEntity e : m_aMen)
		{
			if (!e || !Alive(e) || ZCR_LossLog.SideOf(e) != m_sFollowSide)
				continue;
			float d = vector.DistanceXZ(e.GetOrigin(), m_vFollowLast);
			if (d < bestDistance)
			{
				bestDistance = d;
				best = e;
			}
		}
		if (best)
			Show(best.GetOrigin(), 45, 32, best, string.Format("FOLLOWING %1 %2%3 %4 (the one followed fell)", m_sFollowSide, ZCR_LossLog.Role(best), TeamTag(best), Near(best.GetOrigin())), false);
		else
			Show(m_vFollowLast, 80, 60, null, "THE ONE FOLLOWED FELL " + Near(m_vFollowLast), false);
	}

	protected string m_sDroneSide;

	// A drone of the commanders' FPV teams still flying (deleted once it has hit).
	protected IEntity LiveDrone()
	{
		for (int i = ZCR_Drones.s_aDrones.Count() - 1; i >= 0; i--)
		{
			IEntity d = ZCR_Drones.s_aDrones[i];
			if (!d)
			{
				ZCR_Drones.s_aDrones.Remove(i);
				ZCR_Drones.s_aDroneSide.Remove(i);
				continue;
			}
			// In the air: well above the ground.
			vector p = d.GetOrigin();
			if (p[1] - GetGame().GetWorld().GetSurfaceY(p[0], p[2]) > 5 && (m_sFocus.IsEmpty() || ZCR_Drones.s_aDroneSide[i] == m_sFocus))
			{
				m_sDroneSide = ZCR_Drones.s_aDroneSide[i];
				return d;
			}
		}
		return null;
	}

	protected string Score()
	{
		if (LabTest())
			return "LAB TEST: " + TestTitle();
		map<string, int> held = new map<string, int>();
		foreach (SCR_CampaignMilitaryBaseComponent base, string owner : m_mOwners)
			held.Set(owner, held.Get(owner) + 1);
		return string.Format("bases US %1 | USSR %2 | FIA %3", held.Get("US"), held.Get("USSR"), held.Get("FIA"));
	}

	// A supply truck to show: one on the road (to load or with its cargo), the sides in turn.
	protected bool SupplyTruck(out IEntity truck, out string label)
	{
		array<ref AICF_TruckView> trucks = {};
		AICF_LogisticsDepotRegistry.AICF_Trucks(trucks);
		string want = Turn("US", "USSR");
		AICF_TruckView pick;
		foreach (AICF_TruckView t : trucks)
		{
			if (!t.m_Vehicle || (t.m_sPhase != "TO_SOURCE" && t.m_sPhase != "TO_DESTINATION" && t.m_sPhase != "LOADING" && t.m_sPhase != "UNLOADING"))
				continue;
			if (!pick || (t.m_sSide == want && pick.m_sSide != want))
				pick = t;
		}
		if (!pick)
			return false;
		truck = pick.m_Vehicle;
		label = string.Format("%1 SUPPLY TRUCK %2 - %3/%4 supplies aboard %5", pick.m_sSide, TruckDoing(pick), Math.Round(pick.m_fCargo), Math.Round(pick.m_fCapacity), Near(truck.GetOrigin()));
		return true;
	}

	// A building going up to show: the one with the biggest crew, then the most progress.
	protected bool BuildSite(out vector at, out string label)
	{
		array<SCR_CampaignBuildingCompositionComponent> sites = {};
		array<Faction> factions = {};
		AICF_BaseBuilderService.AICF_Sites(sites, factions);
		int best = -1;
		int bestCrew = -1;
		foreach (int i, SCR_CampaignBuildingCompositionComponent site : sites)
		{
			if (!site || !site.GetOwner() || !factions[i])
				continue;
			int crew = ZCR_WorkCrew.CrewAt(site);
			if (crew > bestCrew)
			{
				best = i;
				bestCrew = crew;
			}
		}
		if (best < 0)
			return false;
		IEntity e = sites[best].GetOwner();
		string what = "A BUILDING";
		if (e.GetPrefabData())
			what = BuildingKind(e.GetPrefabData().GetPrefabName());
		at = e.GetOrigin();
		label = string.Format("%1 ENGINEERS BUILDING %2 %3 - builder and crew of %4", factions[best].GetFactionKey(), what, Near(at), bestCrew);
		return true;
	}

	protected static string BaseLabel(SCR_CampaignMilitaryBaseComponent base, string run, string build)
	{
		float max = base.GetSuppliesMax();
		float have = base.GetSupplies();
		string name = ZCR_Strategist.BaseName(base);
		string brief = string.Format("%1  %2/%3", name, Math.Round(have), Math.Round(max));
		string full = string.Format("%1  %2/%3 supplies", name, Math.Round(have), Math.Round(max));
		if (AICF_SupplyDepots.Is(base))
		{
			brief += "  DEPOT";
			full += string.Format(" - SUPPLY DEPOT +%1/min", AICF_SupplyDepots.IncomePerMinute());
		}
		else if (max > 0 && have < 0.6 * max)
			full += " - asks for supplies";
		if (!run.IsEmpty())
		{
			brief += "  - truck coming";
			full += " - " + run;
		}
		if (!build.IsEmpty())
		{
			brief += "  - building";
			full += " - building " + build;
		}
		return brief + "|" + full;
	}

	// The point's supply level as a dot colour: green 60%+ (AI Conflict asks for trucks below 60%), amber
	// 30-60%, red under 30%.
	protected static string SupplyColour(SCR_CampaignMilitaryBaseComponent base)
	{
		float max = base.GetSuppliesMax();
		float share = 1;
		if (max > 0)
			share = base.GetSupplies() / max;
		if (share >= 0.6)
			return "0.25 0.85 0.35";
		if (share >= 0.3)
			return "0.95 0.72 0.15";
		return "0.92 0.22 0.15";
	}

	// Supply runs heading to each point (a truck going to load for it, loading, on the way or unloading) and
	// what is being built at each point (sites within 350 m).
	static void BaseTasks(map<SCR_CampaignMilitaryBaseComponent, string> runs, map<SCR_CampaignMilitaryBaseComponent, string> builds)
	{
		array<ref AICF_TruckView> trucks = {};
		AICF_LogisticsDepotRegistry.AICF_Trucks(trucks);
		foreach (AICF_TruckView t : trucks)
		{
			if (!t.m_To || (t.m_sPhase != "TO_SOURCE" && t.m_sPhase != "LOADING" && t.m_sPhase != "TO_DESTINATION" && t.m_sPhase != "UNLOADING"))
				continue;
			string what = string.Format("%1 truck %2", t.m_sSide, TruckDoing(t));
			if (runs.Contains(t.m_To))
				what = runs.Get(t.m_To) + ", " + what;
			runs.Set(t.m_To, what);
		}
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return;
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		array<SCR_CampaignBuildingCompositionComponent> sites = {};
		array<Faction> factions = {};
		AICF_BaseBuilderService.AICF_Sites(sites, factions);
		foreach (SCR_CampaignBuildingCompositionComponent site : sites)
		{
			if (!site || !site.GetOwner())
				continue;
			SCR_CampaignMilitaryBaseComponent nearest;
			float best = 350;
			foreach (SCR_MilitaryBaseComponent b : bases)
			{
				SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
				if (!base || !base.GetOwner())
					continue;
				float d = vector.DistanceXZ(base.GetOwner().GetOrigin(), site.GetOwner().GetOrigin());
				if (d < best)
				{
					best = d;
					nearest = base;
				}
			}
			if (!nearest)
				continue;
			string what = SiteText(site);
			if (builds.Contains(nearest))
				what = builds.Get(nearest) + ", " + what;
			builds.Set(nearest, what);
		}
	}

	// "BUNKER 45%".
	protected static string SiteText(SCR_CampaignBuildingCompositionComponent site)
	{
		string what = "building";
		EntityPrefabData data = site.GetOwner().GetPrefabData();
		if (data)
			what = BuildingKind(data.GetPrefabName());
		SCR_CampaignBuildingLayoutComponent layout = site.GetCompositionLayout();
		if (layout && layout.GetToBuildValue() > 0)
			what += string.Format(" %1", Math.Round(100 * layout.GetCurrentBuildValue() / layout.GetToBuildValue())) + "%";
		return what;
	}

	// Supply trucks with what they carry and do, finished fortifications, and buildings going up with their
	// work crews (Martin, 21 Oct: "it should be seen on vehicles if they are carrying supplies and how
	// much"; "I am not seeing defences being built by anybody").
	protected static string LogisticsMarkers()
	{
		string markers;
		array<ref AICF_TruckView> trucks = {};
		AICF_LogisticsDepotRegistry.AICF_Trucks(trucks);
		foreach (AICF_TruckView t : trucks)
		{
			string doing = TruckDoing(t);
			if (!t.m_Vehicle || doing.IsEmpty())
				continue;
			markers += Marker("S", t.m_Vehicle.GetOrigin() + Vector(0, 7, 0), Colour(t.m_sSide), 1,
				string.Format("TRUCK %1|%2 SUPPLY TRUCK %3/%4 - %5", Math.Round(t.m_fCargo), t.m_sSide, Math.Round(t.m_fCargo), Math.Round(t.m_fCapacity), doing));
		}
		// Armour units (ZCR_Armour): what each tank / IFV is doing.
		array<vector> armourAt = {};
		array<string> armourSide = {};
		array<string> armourLabel = {};
		ZCR_Armour.List(armourAt, armourSide, armourLabel);
		foreach (int a, vector armourPos : armourAt)
			markers += Marker("A", armourPos + Vector(0, 8, 0), Colour(armourSide[a]), 1, armourLabel[a]);
		array<IEntity> forts = {};
		array<string> sides = {};
		array<string> kinds = {};
		AICF_Fortifications.List(forts, sides, kinds);
		foreach (int i, IEntity f : forts)
			markers += Marker("F", f.GetOrigin() + Vector(0, 5, 0), Colour(sides[i]), 1, kinds[i] + "|" + sides[i] + " " + kinds[i]);
		array<SCR_CampaignBuildingCompositionComponent> sites = {};
		array<Faction> factions = {};
		AICF_BaseBuilderService.AICF_Sites(sites, factions);
		foreach (int k, SCR_CampaignBuildingCompositionComponent site : sites)
		{
			if (!site || !site.GetOwner() || !factions[k])
				continue;
			string progress = "";
			SCR_CampaignBuildingLayoutComponent layout = site.GetCompositionLayout();
			if (layout && layout.GetToBuildValue() > 0)
				progress = string.Format(" %1", Math.Round(100 * layout.GetCurrentBuildValue() / layout.GetToBuildValue())) + "%";
			string what = "building";
			EntityPrefabData data = site.GetOwner().GetPrefabData();
			if (data)
				what = BuildingKind(data.GetPrefabName());
			markers += Marker("C", site.GetOwner().GetOrigin() + Vector(0, 8, 0), Colour(factions[k].GetFactionKey()), 1,
				string.Format("%1%2|%3 BUILDING %1%2 - crew %4", what, progress, factions[k].GetFactionKey(), ZCR_WorkCrew.CrewAt(site) + 1));
		}
		return markers;
	}

	static string TruckDoing(AICF_TruckView t)
	{
		string from = "?";
		if (t.m_From)
			from = ZCR_Strategist.BaseName(t.m_From);
		string to = "?";
		if (t.m_To)
			to = ZCR_Strategist.BaseName(t.m_To);
		switch (t.m_sPhase)
		{
			case "IDLE_AT_DEPOT": return "parked at its depot";
			case "SPAWN_PENDING": return "getting ready";
			case "DRIVER_READY": return "getting ready";
			case "TO_SOURCE": return "to load at " + from;
			case "LOADING": return "loading at " + from;
			case "TO_DESTINATION": return string.Format("taking %1 to %2", Math.Round(t.m_fCargo), to);
			case "UNLOADING": return "unloading at " + to;
			case "RETURN_HOME": return "back to its depot";
			case "WAIT_RETRY": return "waiting";
		}
		return "";
	}

	static string BuildingKind(string prefab)
	{
		if (prefab.Contains("LivingArea"))
			return "BARRACKS";
		if (prefab.Contains("VehicleMaintenance"))
			return "VEHICLE DEPOT";
		if (prefab.Contains("AmmoStorage"))
			return "ARMORY";
		return AICF_Fortifications.Kind(prefab);
	}

	protected static string Marker(string kind, vector at, string colour, float size, string text)
	{
		float y = GetGame().GetWorld().GetSurfaceY(at[0], at[2]);
		return string.Format("%1;%2;%3;%4;%5;%6;%7\n", kind, Math.Round(at[0]), Math.Round(y), Math.Round(at[2]), colour, size, text);
	}

	protected void SendOverlay(int now)
	{
		string markers;
		// Bases, in their owner's colour.
		// Bases with their supplies (Martin, 21 Oct: "I should see on the map overview the state of the
		// supplies"): stock/storage, "asks for supplies" below AI Conflict's request level (60%), and AI
		// Conflict's supply depots - "SUPPLY DEPOT", green while neutral (FIA's colour), any side loads there.
		// Martin, 21 Oct: "make clear over the points how many supplies are there, and the current supply and
		// fortification tasks - a details button so the GUI is not overfilled". Each point: its supply number and
		// a dot by level (green 60%+, amber 30-60%, red under 30%), "truck coming" while a supply run heads there,
		// "building" while a site goes up there; DETAILS (watch buttons) shows the full text.
		map<SCR_CampaignMilitaryBaseComponent, string> runs = new map<SCR_CampaignMilitaryBaseComponent, string>();
		map<SCR_CampaignMilitaryBaseComponent, string> builds = new map<SCR_CampaignMilitaryBaseComponent, string>();
		BaseTasks(runs, builds);
		foreach (SCR_CampaignMilitaryBaseComponent base, string owner : m_mOwners)
		{
			vector at = base.GetOwner().GetOrigin() + Vector(0, 40, 0);
			markers += Marker("B", at, Colour(owner), 1, BaseLabel(base, runs.Get(base), builds.Get(base)));
			markers += Marker("Y", at, SupplyColour(base), 1, "");
		}
		markers += LogisticsMarkers();
		// The followed team's goal.
		if (m_vTeamGoal != vector.Zero && m_ShownFollow && m_mLeaderSlot.Contains(m_ShownFollow))
			markers += Marker("G", m_vTeamGoal + Vector(0, 60, 0), Colour(ZCR_LossLog.SideOf(m_ShownFollow)), 1, "TEAM GOAL: " + m_sTeamGoal);
		// Losses of the last 90 s, fading.
		for (int i; i < ZCR_LossLog.s_aRecentPos.Count(); i++)
		{
			int age = now - ZCR_LossLog.s_aRecentAt[i];
			if (age <= 90)
				markers += Marker("L", ZCR_LossLog.s_aRecentPos[i], Colour(ZCR_LossLog.s_aRecentSide[i]), 1 - age / 120.0, "");
		}
		// Each side's main effort: a trail of growing squares from its troops to the objective.
		foreach (string side : MAIN_SIDES)
		{
			ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(side);
			vector goal;
			if (plan.GetMainEffort() < 0 || !ZCR_Strategist.s_mNodePos.Find(plan.GetMainEffort(), goal))
				continue;
			vector from;
			int n;
			foreach (IEntity e : m_aMen)
			{
				if (ZCR_LossLog.SideOf(e) == side && vector.DistanceXZ(e.GetOrigin(), goal) < 4000)
				{
					from += e.GetOrigin();
					n++;
				}
			}
			if (n == 0)
				continue;
			from = from / n;
			float length = vector.DistanceXZ(from, goal);
			if (length < 150)
				continue;
			int steps = Math.Ceil(length / 120);
			if (steps > 24)
				steps = 24;
			for (int s = 1; s <= steps; s++)
			{
				float f = s / (steps + 1.0);
				markers += Marker("T", from + (goal - from) * f + Vector(0, 25, 0), Colour(side), 0.4 + 0.8 * f, "");
			}
			markers += Marker("G", goal + Vector(0, 70, 0), Colour(side), 1, side + " MAIN EFFORT");
		}
		// The panels (Martin: "left and right side for BLUFOR and OPFOR like in Arma 3, like live
		// logs"): a slim top line with the score and time, the US (BLUFOR) on the left and the USSR
		// (OPFOR) on the right - who commands, its plan, what its squads do now, drones, its latest
		// decisions - and the lab's measures along the bottom.
		string top = "<b>" + Score() + "</b>     game time " + Clock(now) + ZCR_Feed.Col(ZCR_Feed.YELLOW, Speed(now));
		string left = SidePanel("US", now);
		string right = SidePanel("USSR", now);
		string bottom;
		foreach (int i, string side : MAIN_SIDES)
		{
			if (i > 0)
				bottom += "        |        ";
			bottom += ZCR_Feed.SideCol(side, "<b>" + side + "</b>") + ZCR_Feed.Col(ZCR_Feed.RED, string.Format(" lost %1", ZCR_Feed.s_mLostFire.Get(side) + ZCR_Feed.s_mLostOther.Get(side)))
				+ string.Format(" (by fire %1, no killer - drones, blasts %2)", ZCR_Feed.s_mLostFire.Get(side), ZCR_Feed.s_mLostOther.Get(side));
			if (ZCR_Feed.s_mCover.Contains(side))
				bottom += string.Format(" - in cover %1%", ZCR_Feed.s_mCover.Get(side));
			if (ZCR_Feed.s_mAtBase.Contains(side))
				bottom += string.Format(" - at main base %1%", ZCR_Feed.s_mAtBase.Get(side));
			if (ZCR_Feed.s_mStacked.Contains(side))
				bottom += string.Format(" - stacked %1%", ZCR_Feed.s_mStacked.Get(side));
		}
		SCR_BaseGameMode gameMode = SCR_BaseGameMode.Cast(GetGame().GetGameMode());
		if (gameMode)
			gameMode.ZCR_SendOverlay(top, left, right, bottom, markers);
	}
}
