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
