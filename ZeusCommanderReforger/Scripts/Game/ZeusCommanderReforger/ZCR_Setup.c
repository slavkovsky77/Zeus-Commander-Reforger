// A test scenario with only the two armies (Martin, 19 Oct: "for testing I'd like no FIA bases at the
// start - we'd iterate faster with just two factions against each other"). -zcrNoFIA: at the start
// every base FIA holds goes to one of the two sides - the half nearer the US main base to the US, the
// rest to the USSR (sorted by how much nearer, so the split is even) - and the bases in the middle
// are the front from the first minute. Server only; logs [ZCR][SETUP] per base.
class ZCR_Setup
{
	protected static bool s_bDone;

	static void NoFIA()
	{
		if (s_bDone || !Replication.IsServer() || !System.IsCLIParam("zcrNoFIA"))
			return;
		FactionManager fm = GetGame().GetFactionManager();
		if (!fm)
			return;
		SCR_CampaignFaction us = SCR_CampaignFaction.Cast(fm.GetFactionByKey("US"));
		SCR_CampaignFaction ussr = SCR_CampaignFaction.Cast(fm.GetFactionByKey("USSR"));
		if (!us || !ussr || !us.GetMainBase() || !ussr.GetMainBase() || !us.GetMainBase().GetOwner() || !ussr.GetMainBase().GetOwner())
			return;
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return;
		vector homeUS = us.GetMainBase().GetOwner().GetOrigin();
		vector homeUSSR = ussr.GetMainBase().GetOwner().GetOrigin();
		array<SCR_MilitaryBaseComponent> all = {};
		system.GetBases(all);
		// FIA's bases, by how much nearer the US main base they are (most US-ward first).
		array<SCR_CampaignMilitaryBaseComponent> fia = {};
		array<float> lean = {};
		foreach (SCR_MilitaryBaseComponent b : all)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || base.IsHQ() || !base.GetFaction() || base.GetFaction().GetFactionKey() != "FIA")
				continue;
			vector at = base.GetOwner().GetOrigin();
			float l = vector.DistanceXZ(at, homeUS) - vector.DistanceXZ(at, homeUSSR);
			int i;
			while (i < lean.Count() && lean[i] < l)
				i++;
			lean.InsertAt(l, i);
			fia.InsertAt(base, i);
		}
		if (fia.IsEmpty())
			return;
		s_bDone = true;
		int half = (fia.Count() + 1) / 2;
		foreach (int k, SCR_CampaignMilitaryBaseComponent base : fia)
		{
			SCR_CampaignFaction side = ussr;
			if (k < half)
				side = us;
			base.SetFaction(side);
			Print(string.Format("[ZCR][SETUP] t=%1 no_fia base=%2 to=%3", ZCR_LossLog.Seconds(), ZCR_Strategist.BaseName(base), side.GetFactionKey()), LogLevel.NORMAL);
		}
		// FIA soldiers already out (ambient patrols spawned near the camera before this): removed.
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		int removed;
		foreach (AIAgent agent : agents)
		{
			IEntity e;
			if (agent)
				e = agent.GetControlledEntity();
			if (e && ChimeraCharacter.Cast(e) && ZCR_LossLog.SideOf(e) == "FIA")
			{
				SCR_EntityHelper.DeleteEntityAndChildren(e);
				removed++;
			}
		}
		Print(string.Format("[ZCR][SETUP] t=%1 no_fia removed_fia_soldiers=%2", ZCR_LossLog.Seconds(), removed), LogLevel.NORMAL);
	}
}

// -zcrNoFIA: the base game's ambient FIA patrols (spawned near any player - the watch camera too)
// don't spawn (Martin: "why do I still see green guys?" - 85 FIA lost in the first two-army match).
modded class SCR_AmbientPatrolSpawnPointComponent
{
	override void SpawnPatrol()
	{
		if (System.IsCLIParam("zcrNoFIA"))
		{
			SCR_FactionAffiliationComponent comp = SCR_FactionAffiliationComponent.Cast(GetOwner().FindComponent(SCR_FactionAffiliationComponent));
			Faction f;
			if (comp)
			{
				f = comp.GetAffiliatedFaction();
				if (!f)
					f = comp.GetDefaultAffiliatedFaction();
			}
			if (!f || f.GetFactionKey() == "FIA")
				return;
		}
		super.SpawnPatrol();
	}
}
