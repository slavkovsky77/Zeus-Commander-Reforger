// Arma 3's doctrine at the squad-role level: AI Conflict splits each side 6 ATTACK and 4 DEFEND
// squads for the whole match, and a DEFEND squad never joins an attack. While nothing threatens
// us, the strategist's plan says how many DEFEND squads join the main effort (commit 0-2); they go
// back to DEFEND as soon as the plan says fewer, or one of our bases is being captured.
// A role change takes AI Conflict's own path for a commander's role change
// (RequestPlayerGroupConfiguration): the new role, then a fresh strategic order for the squad.
// Logs [ZCR][COMMIT] for the lab. Server only.
modded class AICF_MatchController
{
	protected static ref map<string, ref array<int>> s_mZCRCommitted;
	protected static ref map<string, int> s_mZCRHoldUntil;
	protected static const int ZCR_COMMIT_MIN_ALIVE = 6;
	protected static const int ZCR_COMMIT_COOLDOWN = 180;   // s after a capture threat before committing again

	void ZCR_CommitDefenders(SCR_CampaignFaction faction, AICF_FactionState state, int commit, bool underCapture)
	{
		if (!Replication.IsServer() || !faction || !state)
			return;
		if (!s_mZCRCommitted)
			s_mZCRCommitted = new map<string, ref array<int>>();
		string key = faction.GetFactionKey();
		array<int> committed;
		if (!s_mZCRCommitted.Find(key, committed) || !committed)
		{
			committed = {};
			s_mZCRCommitted.Set(key, committed);
		}
		// A base of ours being captured: everyone back, and no commit for a while - a capture
		// flickering on and off would otherwise turn the squads round every tick.
		if (!s_mZCRHoldUntil)
			s_mZCRHoldUntil = new map<string, int>();
		int now = ZCR_LossLog.Seconds();
		if (underCapture)
			s_mZCRHoldUntil.Set(key, now + ZCR_COMMIT_COOLDOWN);
		int holdUntil;
		if (s_mZCRHoldUntil.Find(key, holdUntil) && now < holdUntil)
			commit = 0;
		// Release: back to DEFEND, the last committed first.
		while (committed.Count() > commit)
		{
			int slotId = committed[committed.Count() - 1];
			committed.Remove(committed.Count() - 1);
			ZCR_SetRole(faction, state, state.GetSlot(slotId), AICF_EGroupRole.DEFEND, "ZCR_RELEASE");
		}
		// Commit: the strongest combat-ready DEFEND squads, on foot and with their own order.
		while (committed.Count() < commit)
		{
			AICF_GroupSlot best;
			int bestAlive;
			for (int i = 0; i < state.GetSlotCount(); i++)
			{
				AICF_GroupSlot slot = state.GetSlot(i);
				if (!slot || slot.GetRole() != AICF_EGroupRole.DEFEND || !slot.IsCombatReady())
					continue;
				if (m_VehicleCoordinator && (m_VehicleCoordinator.IsControllingMovement(slot) ||
					m_VehicleCoordinator.IsRestorePending(slot) || m_VehicleCoordinator.IsInfantryOrderSuspended(slot)))
					continue;
				int alive = AICF_GroupRuntime.CountAliveAgents(slot.GetGroup());
				if (alive > bestAlive)
				{
					best = slot;
					bestAlive = alive;
				}
			}
			if (!best || bestAlive < ZCR_COMMIT_MIN_ALIVE)
				return;
			if (!ZCR_SetRole(faction, state, best, AICF_EGroupRole.ATTACK, "ZCR_COMMIT"))
				return;
			committed.Insert(best.GetSlotId());
		}
	}

	// Arma 3's teams ride to the drop-off (review note 85): AI Conflict's own commander never gives
	// infantry squads a vehicle (only a player can make a squad motorized), so a march of 1-1.3 km to
	// the next objective took 7-18 minutes. With motorize on, the doctrine side's attack squads become
	// truck squads the way a player's choice would make them; AI Conflict's vehicle system then
	// brings a truck for routes over 400 m and drops them 150 m short. Off: back to infantry.
	// Which objective a squad was given its vehicle for ("faction:slot" -> base).
	protected ref map<string, SCR_CampaignMilitaryBaseComponent> m_mZcrRideFor = new map<string, SCR_CampaignMilitaryBaseComponent>();

	// Motorize, for the long marches only: a squad still at its main base (within 250 m) whose
	// objective is over 1 km away gets a vehicle (light first - Martin: "not only trucks and APCs";
	// AI Conflict's light transport, the US M998, the USSR UAZ-452, its truck when the squad doesn't
	// fit; -zcrMotorizeTruck for trucks only) and keeps it until its objective changes. Squads out in
	// the field stay on foot: walking back to the vehicle spawn site timed out 10 trips of 12
	// (19 Oct probe, SPAWN_SITE_APPROACH_TIMEOUT).
	void ZCR_Motorize(SCR_CampaignFaction faction, AICF_FactionState state, bool motorize)
	{
		if (!Replication.IsServer() || !faction || !state)
			return;
		AICF_EGroupUnitType ride = AICF_EGroupUnitType.MOTORIZED_LIGHT;
		if (System.IsCLIParam("zcrMotorizeTruck"))
			ride = AICF_EGroupUnitType.MOTORIZED_TRUCK;
		vector home;
		if (faction.GetMainBase() && faction.GetMainBase().GetOwner())
			home = faction.GetMainBase().GetOwner().GetOrigin();
		for (int i = 0; i < state.GetSlotCount(); i++)
		{
			AICF_GroupSlot slot = state.GetSlot(i);
			if (!slot || slot.GetRole() != AICF_EGroupRole.ATTACK)
				continue;
			if (slot.GetState() == AICF_EGroupSlotState.SPAWNING)
				continue;
			string key = faction.GetFactionKey() + ":" + slot.GetSlotId();
			SCR_CampaignMilitaryBaseComponent target = slot.GetTargetBase();
			AICF_EGroupUnitType want = AICF_EGroupUnitType.INFANTRY;
			if (motorize && target && slot.GetUnitType() != AICF_EGroupUnitType.INFANTRY && m_mZcrRideFor.Get(key) == target)
				continue;                                       // riding to this objective already
			if (motorize && target && home != vector.Zero && target.GetOwner())
			{
				IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(slot.GetGroup());
				vector goal = target.GetOwner().GetOrigin();
				if (leader && vector.DistanceXZ(leader.GetOrigin(), home) < 250 && vector.DistanceXZ(home, goal) > 1000)
					want = ride;
			}
			if (slot.GetUnitType() == want)
				continue;
			if (!state.ApplyCommanderConfiguration(slot.GetSlotId(), slot.GetRole(), want, slot.GetDesiredSize()))
				continue;
			if (want != AICF_EGroupUnitType.INFANTRY)
				m_mZcrRideFor.Set(key, target);
			else
				m_mZcrRideFor.Remove(key);
			bool admission;
			if (slot.IsCombatReady())
			{
				slot.TouchCommanderConfiguration();
				if (want != AICF_EGroupUnitType.INFANTRY && m_VehicleCoordinator)
					admission = m_VehicleCoordinator.RequestExplicitVehicleAdmission(slot, faction, "ZCR_MOTORIZE");
			}
			Print(string.Format("[ZCR][MOTORIZE] t=%1 faction=%2 slot=%3 type=%4 ready=%5 admission=%6",
				ZCR_LossLog.Seconds(), faction.GetFactionKey(), slot.GetSlotId(), typename.EnumToString(AICF_EGroupUnitType, want),
				slot.IsCombatReady(), admission), LogLevel.NORMAL);
		}
	}

	protected bool ZCR_SetRole(SCR_CampaignFaction faction, AICF_FactionState state, AICF_GroupSlot slot, AICF_EGroupRole role, string reason)
	{
		if (!slot || slot.GetRole() == role)
			return false;
		if (slot.HasPendingOrderRecovery())
			SupersedePendingOrderRecovery(slot, faction, reason);
		if (!state.ApplyCommanderConfiguration(slot.GetSlotId(), role, slot.GetUnitType(), slot.GetDesiredSize()))
			return false;
		bool ordered;
		if (slot.IsCombatReady())
		{
			m_OrderPlanner.ClearOrder(slot);
			ordered = AssignFactionStrategicOrder(slot, faction, reason);
		}
		Print(string.Format("[ZCR][COMMIT] t=%1 faction=%2 slot=%3 role=%4 alive=%5 ordered=%6 reason=%7",
			ZCR_LossLog.Seconds(), faction.GetFactionKey(), slot.GetSlotId(), typename.EnumToString(AICF_EGroupRole, role),
			AICF_GroupRuntime.CountAliveAgents(slot.GetGroup()), ordered, reason), LogLevel.NORMAL);
		return true;
	}
}
