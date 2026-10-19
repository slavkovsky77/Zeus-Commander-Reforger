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
	protected static const int ZCR_COMMIT_MIN_ALIVE = 6;

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
		if (underCapture)
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
