// What each side is doing now, for the lab app's Live tab (Martin, 21 Oct: "in live it would be nice to see
// current efforts - defend, supply, attack efforts... I am missing supply runs, what are building efforts").
// Every 30 game seconds, one line per side:
//   [ZCR][EFFORTS] t= side= json={"main": base, "attack": [{base, teams, men, riding}], "defend": [...],
//     "hold": [{base, enemies}], "short": [{base, have, max}], "trucks": [{doing, phase, from, to, cargo, step, leg, left, planned}],
//     "build": [{what, base, stage, for, tries}], "sites": [{base, what, pct, for}], "armour": [label]}
// From AI Conflict's team slots (role and target), the bases, its supply trucks and construction orders, the
// side's knowledge of enemies near its bases, and the armour units. Server side; logging only.
// Progress (Martin: "those actions should have visible progresses"): attack/defend "there" = soldiers within 300 m
// of the base; a truck's "step" 1-4 (to load, loading, driving, unloading) and "leg" 0-100 (how far along its
// current drive, from the farthest it was on it); a site's "pct" built.
// Time (Martin: "there could be also time how long is phase is taking"): every item has "for" - game seconds in its
// current phase (an attack on that base, a truck's step, a site search across its retries, a site being built) - and
// a site search "tries" (AI Conflict gives a search ~6 game minutes, then starts a new order for the same thing).
class ZCR_Efforts
{
	protected static int s_iNext;
	protected static ref map<string, int> s_mSince = new map<string, int>();
	protected static ref map<string, int> s_mSeen = new map<string, int>();
	protected static ref map<string, string> s_mStage = new map<string, string>();
	protected static ref map<string, string> s_mToken = new map<string, string>();
	protected static ref map<string, int> s_mTries = new map<string, int>();

	// Game seconds the item has been in this stage; a new stage, or the item gone for over 75 s, starts again.
	protected static int For(string key, string stage, int now)
	{
		int seen;
		if (!s_mSeen.Find(key, seen) || now - seen > 75 || s_mStage.Get(key) != stage)
		{
			s_mSince.Set(key, now);
			s_mStage.Set(key, stage);
		}
		s_mSeen.Set(key, now);
		return now - s_mSince.Get(key);
	}

	// How many orders (tokens) the item has had since its stage began.
	protected static int Tries(string key, string token, bool fresh)
	{
		if (fresh || !s_mTries.Contains(key))
		{
			s_mTries.Set(key, 1);
			s_mToken.Set(key, token);
		}
		else if (s_mToken.Get(key) != token)
		{
			s_mTries.Set(key, s_mTries.Get(key) + 1);
			s_mToken.Set(key, token);
		}
		return s_mTries.Get(key);
	}

	static void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		if (now < s_iNext)
			return;
		s_iNext = now + 30;
		Log("US", now);
		Log("USSR", now);
	}

	protected static string J(string s)
	{
		s.Replace("\\", "\\\\");
		s.Replace("\"", "'");
		return "\"" + s + "\"";
	}

	protected static void Log(string side, int now)
	{
		// Teams by role and target base.
		map<string, int> attackTeams = new map<string, int>();
		map<string, int> attackMen = new map<string, int>();
		map<string, int> attackRiding = new map<string, int>();
		map<string, int> defendTeams = new map<string, int>();
		map<string, int> defendMen = new map<string, int>();
		map<string, int> attackThere = new map<string, int>();
		map<string, int> defendThere = new map<string, int>();
		AICF_FactionState state = ZCR_Strategist.s_mStates.Get(side);
		if (state)
		{
			for (int s; s < state.GetSlotCount(); s++)
			{
				AICF_GroupSlot slot = state.GetSlot(s);
				if (!slot || !slot.GetGroup() || !slot.GetTargetBase())
					continue;
				int men = AICF_GroupRuntime.CountAliveAgents(slot.GetGroup());
				if (men <= 0)
					continue;
				string base = ZCR_Strategist.BaseName(slot.GetTargetBase());
				int there = 0;
				if (slot.GetTargetBase().GetOwner())
					there = MenNear(slot.GetGroup(), slot.GetTargetBase().GetOwner().GetOrigin(), 300);
				if (slot.GetRole() == AICF_EGroupRole.ATTACK)
				{
					attackThere.Set(base, attackThere.Get(base) + there);
					attackTeams.Set(base, attackTeams.Get(base) + 1);
					attackMen.Set(base, attackMen.Get(base) + men);
					attackRiding.Set(base, attackRiding.Get(base) + AICF_GroupRuntime.CountAliveAgentsInAnyVehicle(slot.GetGroup()));
				}
				else
				{
					defendThere.Set(base, defendThere.Get(base) + there);
					defendTeams.Set(base, defendTeams.Get(base) + 1);
					defendMen.Set(base, defendMen.Get(base) + men);
				}
			}
		}
		string attack;
		string defend;
		foreach (string base, int teams : attackTeams)
			attack += string.Format(",{\"base\":%1,\"teams\":%2,\"men\":%3,\"riding\":%4,\"there\":%5,", J(base), teams, attackMen.Get(base), attackRiding.Get(base), attackThere.Get(base)) +
				string.Format("\"for\":%1}", For(side + "|attack|" + base, "attack", now));
		foreach (string base, int teams : defendTeams)
			defend += string.Format(",{\"base\":%1,\"teams\":%2,\"men\":%3,\"there\":%4,\"for\":%5}", J(base), teams, defendMen.Get(base), defendThere.Get(base),
				For(side + "|defend|" + base, "defend", now));
		// The side's bases: enemies known near (hold), short of supplies (resupply).
		string hold;
		string low;
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		array<SCR_MilitaryBaseComponent> bases = {};
		if (system)
			system.GetBases(bases);
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent cb = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!cb || !cb.GetOwner() || !cb.GetFaction() || cb.GetFaction().GetFactionKey() != side)
				continue;
			int near = ZCR_Sampler.KnownEnemiesNear(side, cb.GetOwner().GetOrigin(), 400);
			if (near > 0)
				hold += string.Format(",{\"base\":%1,\"enemies\":%2}", J(ZCR_Strategist.BaseName(cb)), near);
			float max = cb.GetSuppliesMax();
			if (max > 0 && cb.GetSupplies() < 0.4 * max)
				low += string.Format(",{\"base\":%1,\"have\":%2,\"max\":%3}", J(ZCR_Strategist.BaseName(cb)), Math.Round(cb.GetSupplies()), Math.Round(max));
		}
		// Supply trucks on a job.
		string trucks;
		array<ref AICF_TruckView> views = {};
		AICF_LogisticsDepotRegistry.AICF_Trucks(views);
		foreach (AICF_TruckView t : views)
		{
			if (t.m_sSide != side)
				continue;
			string doing = ZCR_Director.TruckDoing(t);
			if (doing.IsEmpty() || t.m_sPhase == "IDLE_AT_DEPOT")
				continue;
			string from = "";
			string to = "";
			if (t.m_From)
				from = ZCR_Strategist.BaseName(t.m_From);
			if (t.m_To)
				to = ZCR_Strategist.BaseName(t.m_To);
			trucks += string.Format(",{\"doing\":%1,\"phase\":%2,\"from\":%3,\"to\":%4,\"cargo\":%5,", J(doing), J(t.m_sPhase), J(from), J(to), Math.Round(t.m_fCargo)) +
				string.Format("\"step\":%1,\"leg\":%2,\"left\":%3,\"planned\":%4,\"for\":%5}", Step(t.m_sPhase), Leg(t), Left(t), Math.Round(Planned(t)),
				For(string.Format("%1|truck|%2|%3|%4", side, t.m_Vehicle, from, to), t.m_sPhase, now));
		}
		// Engineers: AI Conflict's construction orders (choosing a site / building).
		string build;
		array<SCR_CampaignMilitaryBaseComponent> obases = {};
		array<string> what = {};
		array<bool> building = {};
		array<string> tokens = {};
		AICF_ConstructionPlanner.AICF_Orders(side, obases, what, building);
		AICF_ConstructionPlanner.AICF_OrderTokens(side, tokens);
		for (int i; i < obases.Count(); i++)
		{
			string stage = "choosing a site";
			if (building[i])
				stage = "building";
			string orderBase = ZCR_Strategist.BaseName(obases[i]);
			string orderKey = side + "|build|" + orderBase + "|" + what[i];
			int took = For(orderKey, stage, now);
			string token = "";
			if (i < tokens.Count())
				token = tokens[i];
			int tries = Tries(orderKey, token, took == 0);
			build += string.Format(",{\"what\":%1,\"base\":%2,\"stage\":%3,\"for\":%4,\"tries\":%5}", J(what[i]), J(orderBase), J(stage), took, tries);
		}
		// Building sites going up (the builders' targets), with their progress.
		string sites;
		array<SCR_CampaignBuildingCompositionComponent> targets = {};
		array<Faction> owners = {};
		AICF_BaseBuilderService.AICF_Sites(targets, owners);
		for (int si; si < targets.Count(); si++)
		{
			SCR_CampaignBuildingCompositionComponent site = targets[si];
			if (!site || !site.GetOwner() || !owners[si] || owners[si].GetFactionKey() != side)
				continue;
			int pct = -1;
			SCR_CampaignBuildingLayoutComponent layout = site.GetCompositionLayout();
			if (layout && layout.GetToBuildValue() > 0)
				pct = Math.Round(100 * layout.GetCurrentBuildValue() / layout.GetToBuildValue());
			string kind = "building";
			if (site.GetOwner().GetPrefabData())
				kind = ZCR_Director.BuildingKind(site.GetOwner().GetPrefabData().GetPrefabName());
			string siteBase = NearestBase(site.GetOwner().GetOrigin());
			sites += string.Format(",{\"base\":%1,\"what\":%2,\"pct\":%3,\"for\":%4}", J(siteBase), J(kind), pct,
				For(string.Format("%1|site|%2", side, site.GetOwner()), "building", now));
		}
		// Armour units.
		string armour;
		array<vector> at = {};
		array<string> sides = {};
		array<string> labels = {};
		ZCR_Armour.List(at, sides, labels);
		for (int k; k < labels.Count(); k++)
		{
			if (sides[k] != side)
				continue;
			array<string> parts = {};
			labels[k].Split("|", parts, false);
			armour += "," + J(parts[parts.Count() - 1]);
		}
		string main = "";
		ZCR_StrategicPlan plan = ZCR_StrategicPlan.Get(side);
		if (plan && plan.GetMainEffort() >= 0 && ZCR_Strategist.s_mNodeName.Contains(plan.GetMainEffort()))
			main = ZCR_Strategist.s_mNodeName.Get(plan.GetMainEffort());
		string json = string.Format("{\"main\":%1,\"attack\":[%2],\"defend\":[%3],\"hold\":[%4],\"short\":[%5],", J(main), Strip(attack), Strip(defend), Strip(hold), Strip(low));
		json += string.Format("\"trucks\":[%1],\"build\":[%2],\"sites\":[%3],\"armour\":[%4]}", Strip(trucks), Strip(build), Strip(sites), Strip(armour));
		Print(string.Format("[ZCR][EFFORTS] t=%1 side=%2 json=%3", now, side, json), LogLevel.NORMAL);
	}

	// Soldiers of the group alive within radius of the spot.
	protected static int MenNear(SCR_AIGroup group, vector at, float radius)
	{
		array<AIAgent> agents = {};
		group.GetAgents(agents);
		int n;
		foreach (AIAgent agent : agents)
		{
			IEntity e = agent.GetControlledEntity();
			if (e && AICF_GroupRuntime.IsAliveCharacter(e) && vector.DistanceXZ(e.GetOrigin(), at) <= radius)
				n++;
		}
		return n;
	}

	protected static int Step(string phase)
	{
		if (phase == "TO_SOURCE")
			return 1;
		if (phase == "LOADING")
			return 2;
		if (phase == "TO_DESTINATION")
			return 3;
		if (phase == "UNLOADING")
			return 4;
		return 0;
	}

	// Metres (straight line) to the base the truck is driving to; -1 while not driving.
	protected static int Left(AICF_TruckView t)
	{
		if (!t.m_Vehicle)
			return -1;
		SCR_CampaignMilitaryBaseComponent goal;
		if (t.m_sPhase == "TO_SOURCE")
			goal = t.m_From;
		else if (t.m_sPhase == "TO_DESTINATION")
			goal = t.m_To;
		if (!goal || !goal.GetOwner())
			return -1;
		return Math.Round(vector.DistanceXZ(t.m_Vehicle.GetOrigin(), goal.GetOwner().GetOrigin()));
	}

	// The load the truck is to carry: the planned amount, else what it can hold.
	protected static float Planned(AICF_TruckView t)
	{
		if (t.m_fPlanned > 0)
			return t.m_fPlanned;
		return t.m_fCapacity;
	}

	// How far along its current drive a truck is: 100 - the distance left in % of the most it had left on this leg.
	protected static ref map<IEntity, float> s_mLegMax = new map<IEntity, float>();
	protected static ref map<IEntity, string> s_mLegPhase = new map<IEntity, string>();

	protected static int Leg(AICF_TruckView t)
	{
		if (!t.m_Vehicle)
			return 0;
		SCR_CampaignMilitaryBaseComponent goal;
		if (t.m_sPhase == "TO_SOURCE")
			goal = t.m_From;
		else if (t.m_sPhase == "TO_DESTINATION")
			goal = t.m_To;
		else
			return 100;
		if (!goal || !goal.GetOwner())
			return 0;
		float left = vector.DistanceXZ(t.m_Vehicle.GetOrigin(), goal.GetOwner().GetOrigin());
		if (s_mLegPhase.Get(t.m_Vehicle) != t.m_sPhase || !s_mLegMax.Contains(t.m_Vehicle))
		{
			s_mLegPhase.Set(t.m_Vehicle, t.m_sPhase);
			s_mLegMax.Set(t.m_Vehicle, left);
		}
		float most = Math.Max(s_mLegMax.Get(t.m_Vehicle), left);
		s_mLegMax.Set(t.m_Vehicle, most);
		if (most < 1)
			return 100;
		return Math.ClampInt(Math.Round(100 * (1 - left / most)), 0, 100);
	}

	protected static string NearestBase(vector at)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		array<SCR_MilitaryBaseComponent> bases = {};
		if (system)
			system.GetBases(bases);
		string name = "";
		float best = 1e9;
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent cb = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!cb || !cb.GetOwner())
				continue;
			float d = vector.DistanceXZ(cb.GetOwner().GetOrigin(), at);
			if (d < best)
			{
				best = d;
				name = ZCR_Strategist.BaseName(cb);
			}
		}
		return name;
	}

	// A list built as ",a,b" without its first comma.
	protected static string Strip(string list)
	{
		if (list.IsEmpty())
			return "";
		return list.Substring(1, list.Length() - 1);
	}
}
