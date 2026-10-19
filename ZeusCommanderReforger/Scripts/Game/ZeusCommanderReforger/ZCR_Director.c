// The camera director for watched lab matches (server side), as on Arma 3 (ac-lab lab/director.sqf):
// the server knows every unit, so it picks each shot and tells the watching game where to look
// (ZCR_Watch draws it). Runs only on a lab server started with -zcrWatchServer, once a player
// connects.
//
// Shots, about 18 s each, the busiest first:
//   capture   a base changed hands in the last 40 s
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
		int now = ZCR_LossLog.Seconds();
		WatchCaptures(now);
		if (now >= m_iShotEnd)
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

		if (capture >= 0)
		{
			target = m_aCapturePos[capture];
			label = m_aCaptureText[capture];
			key = "capture" + capture;
			back = 260;
			height = 300;
			m_aCaptureAt[capture] = -1000;
		}
		else if (!planSide.IsEmpty())
		{
			ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(planSide);
			m_mPlanShown.Set(planSide, plan.GetMainEffort());
			target = ZCR_Strategist.s_mNodePos.Get(plan.GetMainEffort());
			label = string.Format("%1 COMMANDER (%2): %3", planSide, plan.GetSource(), plan.GetIntent());
			key = "plan" + planSide;
			back = 500;
			height = 600;
		}
		else if (m_bLastWasFight && best >= 0)
		{
			// Close-up in the fight just shown, alternating the side.
			array<IEntity> pool = {};
			string want = "US";
			if (m_iShot % 2 == 0)
				want = "USSR";
			foreach (IEntity e : m_aMen)
			{
				if (vector.DistanceXZ(e.GetOrigin(), m_vLastFight) < 300 && ZCR_LossLog.SideOf(e) == want)
					pool.Insert(e);
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
				label = string.Format("CLOSE-UP: %1 %2 %3", ZCR_LossLog.SideOf(follow), ZCR_LossLog.ShortName(follow), Near(target));
				key = "close";
				back = 38;
				height = 30;
				duration = 14;
			}
		}
		bool hotTurn = m_iShot % 5 == 0;
		if (key.IsEmpty() && !hotTurn && best >= 0)
		{
			target = centres[best];
			int lostUS = LossesNear(target, 500, now - 60, "US");
			int lostUSSR = LossesNear(target, 500, now - 60, "USSR");
			label = string.Format("FIGHT %1 - US %2 v USSR %3 within 400 m", Near(target), us[best], ussr[best]);
			if (lostUS + lostUSSR > 0)
				label += string.Format(" - lost in the last minute: US %1, USSR %2", lostUS, lostUSSR);
			key = string.Format("fight%1_%2", Math.Round(target[0] / 250), Math.Round(target[2] / 250));
			back = 200;
			height = 230;
			m_vLastFight = target;
		}
		if (key.IsEmpty() && !hotTurn && !m_aMoving.IsEmpty())
		{
			// Nobody fighting: follow someone on the move, alternating the side; in a vehicle, the
			// vehicle (the Arma 3 director followed APCs carrying troops).
			array<IEntity> movers = {};
			string wanted = "US";
			if (m_iShot % 2 == 0)
				wanted = "USSR";
			foreach (IEntity e : m_aMoving)
			{
				if (ZCR_LossLog.SideOf(e) == wanted)
					movers.Insert(e);
			}
			if (movers.IsEmpty())
				movers.Copy(m_aMoving);
			IEntity mover = movers.GetRandomElement();
			IEntity root = mover.GetRootParent();
			follow = mover;
			string what = "soldier";
			if (root && Vehicle.Cast(root))
			{
				follow = root;
				what = ZCR_LossLog.ShortName(root);
			}
			target = follow.GetOrigin();
			label = string.Format("%1 %2 on the move %3", ZCR_LossLog.SideOf(mover), what, Near(target));
			key = "move";
			back = 90;
			height = 80;
			duration = 16;
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
		m_bLastWasFight = key.StartsWith("fight");
		if (key == m_sLastKey)
			m_iRepeats++;
		else
			m_iRepeats = 0;
		m_sLastKey = key;
		m_iShotEnd = now + duration;

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
		SCR_BaseGameMode gameMode = SCR_BaseGameMode.Cast(GetGame().GetGameMode());
		if (gameMode)
			gameMode.ZCR_SendShot(target, back, height, followId, label, duration);
		Print(string.Format("[ZCR][CAM] t=%1 shot=%2 kind=%3 men=%4 moving=%5 fights=%6 label=%7", now, m_iShot, key, m_aMen.Count(), m_aMoving.Count(), centres.Count(), label), LogLevel.NORMAL);
		SendOverlay(now);
	}

	protected string Score()
	{
		map<string, int> held = new map<string, int>();
		foreach (SCR_CampaignMilitaryBaseComponent base, string owner : m_mOwners)
			held.Set(owner, held.Get(owner) + 1);
		return string.Format("bases US %1 | USSR %2 | FIA %3", held.Get("US"), held.Get("USSR"), held.Get("FIA"));
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
		foreach (SCR_CampaignMilitaryBaseComponent base, string owner : m_mOwners)
			markers += Marker("B", base.GetOwner().GetOrigin() + Vector(0, 40, 0), Colour(owner), 1, ZCR_Strategist.BaseName(base));
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
		string panel;
		foreach (string side : MAIN_SIDES)
		{
			ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(side);
			string intent = plan.GetIntent();
			string source = plan.GetSource();
			if (intent.IsEmpty())
			{
				intent = "AI Conflict's own commander decides";
				source = "AI Conflict";
			}
			panel += string.Format("%1 commander (%2): %3\n", side, source, intent);
		}
		panel += string.Format("%1 | lost in the last 2 min: US %2, USSR %3 | game time %4",
			Score(), LossesNear(vector.Zero, 1e9, now - 120, "US"), LossesNear(vector.Zero, 1e9, now - 120, "USSR"), Clock(now));
		SCR_BaseGameMode gameMode = SCR_BaseGameMode.Cast(GetGame().GetGameMode());
		if (gameMode)
			gameMode.ZCR_SendOverlay(panel, markers);
	}
}
