// Zeus Commander x DCO_AI bridge - loaded only together with DCO (lab/reforger.py adds it whenever DCO is loaded).
// DCO is the tactical layer, our commander the strategic one (Martin, 24 Oct 2026). Our orders become DCO's own
// per-group switches (its public SCR_AIGroup.DCO_SetFeatureOff; nothing of DCO is changed or copied):
//   storming - the squad pushes: DCO's contact drills (contact SOP, break contact, ambush drill) and its overmatch
//              reaction off for that squad; back on when it stops storming. (Infantry sub-lab, 24 Oct: with all of DCO's
//              extras on, attacks stall - 2 of 6 positions taken; with them turned down the attackers pushed through.)
modded class ZCR_Tactical
{
	static const int STORM_OFF = DCO_EGroupFeature.CONTACT_DRILLS | DCO_EGroupFeature.OVERMATCH;

	override string Layer()
	{
		if (System.IsCLIParam("zcrStormPush"))
			return "dco-push";
		return "dco";
	}

	// Squad detail (24 Oct: DCO's own profiler - 4.8 ms a frame, 29% of a 60-FPS frame with 157 soldiers; its advice: set
	// background squads to Light): every commander tick, a squad with no enemy its side knows of within 800 m gets DCO's
	// Light detail, one near the enemy full detail. -zcrNoDcoLod off.
	//   [ZCR][DCOLOD] t= faction= light= full=          (every 60 s)
	static const float CALM_M = 800;
	protected ref map<string, int> m_mLodLogAt = new map<string, int>();

	override void Tend(string faction, AICF_FactionState state)
	{
		if (!state || System.IsCLIParam("zcrNoDcoLod"))
			return;
		int lightOff = DCO_GroupFeatures.PresetOff(DCO_EGroupDetail.LIGHT);
		int light, full;
		for (int i; i < state.GetSlotCount(); i++)
		{
			AICF_GroupSlot slot = state.GetSlot(i);
			if (!slot || !slot.GetGroup())
				continue;
			SCR_AIGroup g = slot.GetGroup();
			array<AIAgent> agents = {};
			g.GetAgents(agents);
			if (agents.IsEmpty() || !agents[0] || !agents[0].GetControlledEntity())
				continue;
			vector at = agents[0].GetControlledEntity().GetOrigin();
			int want = 0;
			if (ZCR_Sampler.KnownEnemiesNear(faction, at, CALM_M) == 0)
			{
				want = lightOff;
				light++;
			}
			else
				full++;
			if (System.IsCLIParam("zcrStormPush") && (g.DCO_GetFeatureOff() & STORM_OFF) == STORM_OFF)
				want = want | STORM_OFF;
			if (g.DCO_GetFeatureOff() != want)
				g.DCO_SetFeatureOff(want, "zeus_commander_lod");
		}
		int now = ZCR_LossLog.Seconds();
		if (now >= m_mLodLogAt.Get(faction))
		{
			m_mLodLogAt.Set(faction, now + 60);
			Print(string.Format("[ZCR][DCOLOD] t=%1 faction=%2 light=%3 full=%4", now, faction, light, full), LogLevel.NORMAL);
		}
	}

	// The drone operators stay at their post (24 Oct 15:40, the village storm: the pilot 26-60 m off it between and even
	// during flights): every one of DCO's group features off for the team - contact drills, overmatch, CQB, explosion
	// reactions, rearm, ... (DCO's own per-group switch).
	static const int ALL_FEATURES = 4095;

	override void HoldStill(SCR_AIGroup group)
	{
		if (group)
			group.DCO_SetFeatureOff(ALL_FEATURES, "zeus_commander_operator");
	}

	// Only with -zcrStormPush (24 Oct 12:00: the push experiment failed - storming squads without DCO's drills died in the
	// open, 1 of 4 positions taken), so matches run plain DCO; the hook stays for the next idea.
	override void SetStorming(SCR_AIGroup group, bool storming)
	{
		if (!group || !System.IsCLIParam("zcrStormPush"))
			return;
		int off = group.DCO_GetFeatureOff();
		if (storming)
			off = off | STORM_OFF;
		else
			off = off & ~STORM_OFF;
		group.DCO_SetFeatureOff(off, "zeus_commander");
	}
}
