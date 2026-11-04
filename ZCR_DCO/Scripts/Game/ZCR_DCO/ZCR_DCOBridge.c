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

	// Riders stay mounted (3 Nov, note 520 - Martin: "could we override dco 400m dismount?"; a lab arm, -zcrRideStayMounted):
	// DCO's 400-m rule never fires on AI Conflict's rides (0 of 185 get-out orders in the probe battle); what throws a riding
	// team out is DCO's shot reaction (passengers, any enemy shot within 700 m) and the game's vehicle combat (everyone, the
	// driver too, an enemy group within 200 m - 550 m when it shoots), both checked by DCO's own gate on every get-out. While
	// a squad has a man aboard a vehicle it gets DCO's per-squad exit rule 'ordered or damaged' through DCO's API
	// (vehicleExit = ORDERED | DAMAGED; a burning or wrecked vehicle can always be left), DCO's global rule again once it is
	// on foot. AI Conflict's own unloading gets its men out directly, past that gate, so drop points still work.
	//   [ZCR][STAYMOUNTED] t= faction= mounted= set=        (every 60 s)
	static const int MOUNTED_EXIT = DCO_EVehicleExit.ORDERED | DCO_EVehicleExit.DAMAGED;
	protected ref map<string, int> m_mMountLogAt = new map<string, int>();

	protected void StayMounted(string faction, AICF_FactionState state)
	{
		int mounted, changed;
		for (int i; i < state.GetSlotCount(); i++)
		{
			AICF_GroupSlot slot = state.GetSlot(i);
			if (!slot || !slot.GetGroup())
				continue;
			SCR_AIGroup g = slot.GetGroup();
			array<AIAgent> agents = {};
			g.GetAgents(agents);
			bool aboard;
			foreach (AIAgent a : agents)
			{
				if (!a || !a.GetControlledEntity())
					continue;
				IEntity v = CompartmentAccessComponent.GetVehicleIn(a.GetControlledEntity());
				if (!v)
					continue;
				SCR_AIVehicleUsageComponent usage = SCR_AIVehicleUsageComponent.Cast(v.FindComponent(SCR_AIVehicleUsageComponent));
				if (usage && usage.GetVehicleType() == EAIVehicleType.STATIC_WEAPON)
					continue;
				aboard = true;
				break;
			}
			int want = -1;
			if (aboard)
			{
				want = MOUNTED_EXIT;
				mounted++;
			}
			if (Math.Round(DCO_API.GetSquadSetting(g, "vehicleExit")) != want)
			{
				DCO_API.SetSquadSetting("zeus_commander", g, "vehicleExit", want);
				changed++;
			}
		}
		int now = ZCR_LossLog.Seconds();
		if (now >= m_mMountLogAt.Get(faction))
		{
			m_mMountLogAt.Set(faction, now + 60);
			Print(string.Format("[ZCR][STAYMOUNTED] t=%1 faction=%2 mounted=%3 set=%4", now, faction, mounted, changed), LogLevel.NORMAL);
		}
	}

	// Relentless near the point (5 Nov - Martin, watching the town battle: "what I am still missing: infantry to push from one
	// building to another and gradually storming the point - i saw them stuck in one house; they should react to drones ...
	// but they should definitely move"; -zcrStormRelentless): in DCO's attack logic a soldier in cover in the balanced posture
	// waits 10-20 s x cover_hold_mul 2 between bounds and never bounds while endangered in the last 4 s - under fire and
	// drones, never. An attack squad within RELENTLESS_M of the one-point battle's point gets DCO's aggressive posture
	// (DCO_SetPostureOverride - relentless: it bounds from cover every 0.5 s, its drills and cover choice still DCO's), back to
	// automatic when it leaves.   [ZCR][RELENTLESS] t= faction= on= off=      (every 60 s)
	static const float RELENTLESS_M = 500;
	protected ref map<string, int> m_mRelentlessLogAt = new map<string, int>();

	protected void Relentless(string faction, AICF_FactionState state)
	{
		SCR_CampaignMilitaryBaseComponent point = ZCR_OnePoint.Base();
		if (!point || !point.GetOwner())
			return;
		vector at = point.GetOwner().GetOrigin();
		int on, off;
		for (int i; i < state.GetSlotCount(); i++)
		{
			AICF_GroupSlot slot = state.GetSlot(i);
			if (!slot || !slot.GetGroup())
				continue;
			SCR_AIGroup g = slot.GetGroup();
			SCR_AIGroupUtilityComponent gu = SCR_AIGroupUtilityComponent.Cast(g.FindComponent(SCR_AIGroupUtilityComponent));
			if (!gu)
				continue;
			IEntity leader = AICF_GroupRuntime.ResolveAliveLeader(g);
			bool want = leader && slot.GetRole() == AICF_EGroupRole.ATTACK && vector.DistanceXZ(leader.GetOrigin(), at) <= RELENTLESS_M;
			if (want)
			{
				on++;
				if (gu.DCO_GetPostureOverride() != DCO_GroupTactics.AGGRESIVE)
					gu.DCO_SetPostureOverride(DCO_GroupTactics.AGGRESIVE);
			}
			else if (gu.DCO_GetPostureOverride() == DCO_GroupTactics.AGGRESIVE)
			{
				gu.DCO_SetPostureOverride(DCO_GroupTactics.AUTOMATIC);
				off++;
			}
		}
		int now = ZCR_LossLog.Seconds();
		if (now >= m_mRelentlessLogAt.Get(faction))
		{
			m_mRelentlessLogAt.Set(faction, now + 60);
			Print(string.Format("[ZCR][RELENTLESS] t=%1 faction=%2 on=%3 off=%4", now, faction, on, off), LogLevel.NORMAL);
		}
	}

	override void Tend(string faction, AICF_FactionState state)
	{
		if (state && System.IsCLIParam("zcrStormRelentless"))
			Relentless(faction, state);
		if (state && System.IsCLIParam("zcrRideStayMounted"))
			StayMounted(faction, state);
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
