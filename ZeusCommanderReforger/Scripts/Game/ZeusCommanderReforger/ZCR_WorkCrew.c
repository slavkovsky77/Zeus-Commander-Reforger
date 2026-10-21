// Work crews (Martin, 20 Oct: "I really would like to see free guys who are not attacking or defending
// build much more!"). AI Conflict has one builder per base; idle soldiers near a site join him: up to
// CREW soldiers of the same side, on foot, within PICK_M of a composition being built, standing still,
// with no enemy known within 300 m and their team not waiting for or boarding a vehicle. Each takes a
// spot just outside the composition's footprint (inside it the game won't finish the build) and adds
// VALUE build points every 3 s - the builder's shovel adds 10. They leave when the site is done, an
// enemy is known near or their team moves on (over LEAVE_M away).
// Logs every 30 s: [ZCR][CREW] t= side= sites= crew= points=. -zcrNoWorkCrew turns it off.
class ZCR_WorkCrew
{
	static const int CREW = 4;
	static const float PICK_M = 120;
	static const float LEAVE_M = 160;
	static const int VALUE = 5;

	protected static ref ZCR_WorkCrew s_Instance;
	protected ref map<IEntity, SCR_CampaignBuildingCompositionComponent> m_mSite = new map<IEntity, SCR_CampaignBuildingCompositionComponent>();
	protected ref map<IEntity, int> m_mSlot = new map<IEntity, int>();
	protected ref map<IEntity, int> m_mOrderedAt = new map<IEntity, int>();
	protected ref map<IEntity, vector> m_mWas = new map<IEntity, vector>();
	protected ref map<string, int> m_mPoints = new map<string, int>();
	protected int m_iNextLog;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer() || System.IsCLIParam("zcrNoWorkCrew"))
			return;
		s_Instance = new ZCR_WorkCrew();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 3000, true);
	}

	// How many soldiers work with the builder at this site.
	static int CrewAt(SCR_CampaignBuildingCompositionComponent site)
	{
		int n;
		if (!s_Instance)
			return 0;
		foreach (IEntity member, SCR_CampaignBuildingCompositionComponent onSite : s_Instance.m_mSite)
		{
			if (member && onSite == site)
				n++;
		}
		return n;
	}

	// The soldier is on a work crew (the cover layer leaves him there).
	static bool Busy(IEntity soldier)
	{
		return s_Instance && soldier && s_Instance.m_mSite.Contains(soldier);
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		array<SCR_CampaignBuildingCompositionComponent> sites = {};
		array<Faction> factions = {};
		AICF_BaseBuilderService.AICF_Sites(sites, factions);

		// Who stood still since the last tick (3 s).
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		map<IEntity, vector> was = m_mWas;
		m_mWas = new map<IEntity, vector>();
		map<IEntity, AIAgent> agentOf = new map<IEntity, AIAgent>();
		foreach (AIAgent a : agents)
		{
			if (a && a.GetControlledEntity())
			{
				m_mWas.Set(a.GetControlledEntity(), a.GetControlledEntity().GetOrigin());
				agentOf.Set(a.GetControlledEntity(), a);
			}
		}

		// Crew members who are done.
		array<IEntity> leave = {};
		foreach (IEntity soldier, SCR_CampaignBuildingCompositionComponent onSite : m_mSite)
		{
			if (!soldier || !onSite || !sites.Contains(onSite) || !Fit(soldier, agentOf.Get(soldier), onSite, LEAVE_M, false))
				leave.Insert(soldier);
		}
		if (m_mSite.Contains(null))
			leave.Insert(null);
		foreach (IEntity gone : leave)
		{
			m_mSite.Remove(gone);
			m_mSlot.Remove(gone);
			m_mOrderedAt.Remove(gone);
		}

		map<string, int> crewCount = new map<string, int>();
		foreach (int i, SCR_CampaignBuildingCompositionComponent site : sites)
		{
			if (!site || !site.GetOwner() || !factions[i])
				continue;
			string side = factions[i].GetFactionKey();
			IEntity siteEntity = site.GetOwner();
			vector center = siteEntity.GetOrigin();
			vector mins, maxs;
			siteEntity.GetWorldBounds(mins, maxs);
			float ring = Math.Clamp(0.5 * vector.DistanceXZ(mins, maxs) + 2, 3, 9);

			// The crew on this site and its free slots.
			array<IEntity> crew = {};
			array<bool> slotTaken = {false, false, false, false};
			foreach (IEntity member, SCR_CampaignBuildingCompositionComponent memberSite : m_mSite)
			{
				if (member && memberSite == site)    // a member deleted this tick (a body cleared) is skipped
				{
					crew.Insert(member);
					slotTaken[m_mSlot.Get(member)] = true;
				}
			}
			// Fill up from idle soldiers of this side nearby.
			if (crew.Count() < CREW)
			{
				foreach (AIAgent agent : agents)
				{
					if (crew.Count() >= CREW)
						break;
					IEntity e = agent.GetControlledEntity();
					vector before;
					if (!e || m_mSite.Contains(e) || ZCR_LossLog.SideOf(e) != side || !was.Find(e, before) || vector.DistanceXZ(before, e.GetOrigin()) > 1.5)
						continue;
					if (!Fit(e, agent, site, PICK_M, true))
						continue;
					int slot = slotTaken.Find(false);
					if (slot < 0)
						break;
					slotTaken[slot] = true;
					m_mSite.Set(e, site);
					m_mSlot.Set(e, slot);
					crew.Insert(e);
				}
			}
			// Each to his spot round the footprint; at the spot, work.
			int working;
			foreach (IEntity member : crew)
			{
				if (!member)
					continue;
				float angle = (m_mSlot.Get(member) * 90 + 45) * Math.DEG2RAD;
				vector spot = center + Vector(Math.Cos(angle) * ring, 0, Math.Sin(angle) * ring);
				spot[1] = GetGame().GetWorld().GetSurfaceY(spot[0], spot[2]);
				if (vector.DistanceXZ(member.GetOrigin(), spot) > 2.5)
				{
					int ordered;
					if (!m_mOrderedAt.Find(member, ordered) || now - ordered >= 9)
					{
						SCR_AIUtilityComponent utility = Utility(agentOf.Get(member));
						if (utility)
							ZCR_Reserved.Add(utility, new SCR_AIMoveIndividuallyBehavior(utility, null, spot, SCR_AIActionBase.PRIORITY_BEHAVIOR_MOVE_INDIVIDUALLY, 8, null, 1.0));
						m_mOrderedAt.Set(member, now);
					}
					continue;
				}
				working++;
			}
			crewCount.Set(side, crewCount.Get(side) + crew.Count());
			if (working == 0)
				continue;
			// The layout may be finished (and deleted) by this call - nothing touches it afterwards.
			SCR_CampaignBuildingLayoutComponent layout = site.GetCompositionLayout();
			if (layout && layout.GetToBuildValue() > 0 && layout.GetCurrentBuildValue() < layout.GetToBuildValue())
			{
				layout.AddBuildingValue(VALUE * working);
				m_mPoints.Set(side, m_mPoints.Get(side) + VALUE * working);
			}
		}

		if (now >= m_iNextLog)
		{
			m_iNextLog = now + 30;
			array<string> sides = {"US", "USSR"};
			foreach (string s : sides)
			{
				int n;
				foreach (Faction f : factions)
				{
					if (f && f.GetFactionKey() == s)
						n++;
				}
				Print(string.Format("[ZCR][CREW] t=%1 side=%2 sites=%3 crew=%4 points=%5", now, s, n, crewCount.Get(s), m_mPoints.Get(s)), LogLevel.NORMAL);
			}
		}
	}

	// On foot, alive, within 'radius' of the site, no enemy known within 300 m, the team not mounting.
	protected bool Fit(IEntity soldier, AIAgent agent, SCR_CampaignBuildingCompositionComponent site, float radius, bool picking)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(soldier);
		if (!c || !agent || c.IsInVehicle() || !site.GetOwner())
			return false;
		CharacterControllerComponent ctl = c.GetCharacterController();
		if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
			return false;
		string side = ZCR_LossLog.SideOf(c);
		vector p = c.GetOrigin();
		if (vector.DistanceXZ(p, site.GetOwner().GetOrigin()) > radius)
			return false;
		if (ZCR_Sampler.KnownEnemiesNear(side, p, 300) > 0)
			return false;
		if (ZCR_DroneThreat.Mounting(agent, side))
			return false;
		return true;
	}

	protected SCR_AIUtilityComponent Utility(AIAgent agent)
	{
		if (!agent)
			return null;
		return SCR_AIUtilityComponent.Cast(agent.FindComponent(SCR_AIUtilityComponent));
	}
}
