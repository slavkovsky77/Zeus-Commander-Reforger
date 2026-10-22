// The lab's settings for JMVehicleAI (jm3009, Workshop 6A8490E1621E7B3C, APL) in the Zeus Commander lab, 22 Oct.
// As shipped, its convoy rule had a lead vehicle wait up to 60 s for any of its side's vehicles behind it, and
// oncoming traffic waited up to 60 s: our separate rides stood in queues (Arland 21 jams in a match, against a
// median of 6 without the mod). Kept: anti-stuck reversing, curve braking, gaps, the gunners' aim and weapon choice.
// Applied once to the settings the mod loaded, on its manager's first tick.
modded class JMVAI_Manager
{
	protected static JMVAI_Settings s_ZcrTuned;

	override protected void Tick()
	{
		JMVAI_Settings s = JMVAI_Settings.Get();
		if (s && s != s_ZcrTuned)
		{
			s_ZcrTuned = s;
			s.m_bConvoyCohesion = false;      // no waiting for the vehicle behind
			s.m_fYieldWaitTime = 15;          // oncoming traffic: wait at most 15 s (60)
			s.m_fTownWaitMax = 10;            // soldiers in a town street: wait at most 10 s (60)
			s.m_bDebugDisplay = false;        // no debug text over the vehicles in the watched game
			s.m_bDebugDrawRoute = false;
			s.m_fLogIntervalSec = 30;
			Print(string.Format("[ZCR][JMVAI_TUNE] convoy_cohesion=%1 yield_wait_s=%2 town_wait_s=%3 anti_stuck=%4 curves=%5 convoy_gap=%6",
				s.m_bConvoyCohesion, s.m_fYieldWaitTime, s.m_fTownWaitMax, s.m_bAntiStuckEnabled, s.m_bCurvesEnabled, s.m_bConvoyEnabled), LogLevel.NORMAL);
		}
		super.Tick();
	}
}
