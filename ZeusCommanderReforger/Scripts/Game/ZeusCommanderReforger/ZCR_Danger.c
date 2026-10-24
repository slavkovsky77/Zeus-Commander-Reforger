// Danger awareness (Martin, 20 Oct 01:10: "by reckless soldiers I mean they don't care about danger").
// Every 2 s each soldier on foot of the two sides gets a danger level from the game's own threat state
// (shots near him, hits - SCR_AIThreatSystem), what his side knows (the nearest enemy seen in the last
// minute), friends lost near him in the last 30 s and enemy drones in the air near him:
//   HIGH   - THREATENED, an enemy within 150 m, a friend lost within 100 m in the last 2 minutes (a
//            kill zone), or a drone within 150 m:
//            never standing - crouched or prone (the game's stance setting at COMMANDING level; the drone
//            reaction's prone is at SCENARIO level and wins)
//   MEDIUM - ALERTED, an enemy within 400 m, or a drone within 250 m: crouched while not moving
//   LOW    - none of that: no limit (marching at a jog, at ease at a base far from the front).
// The game's own combat movement still decides where to go; this only takes away standing up in danger.
// Measured every 30 s: [ZCR][DANGER] t= side= high= medium= high_standing= medium_standing= (% standing
// of the soldiers at that level). -zcrNoDanger turns it off.
class ZCR_Danger
{
	protected static ref ZCR_Danger s_Instance;
	protected static bool s_bStarted;
	protected ref map<IEntity, vector> m_mWas = new map<IEntity, vector>();
	protected ref map<IEntity, int> m_mLimit = new map<IEntity, int>();      // 0 none, 1 crouched or prone
	protected int m_iNextLog;
	static const int HIGH = 2;
	static const int MEDIUM = 1;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoDanger"))
			return;
		s_bStarted = true;
		s_Instance = new ZCR_Danger();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 2000, true);
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		map<IEntity, vector> was = m_mWas;
		m_mWas = new map<IEntity, vector>();
		map<string, int> high = new map<string, int>();
		map<string, int> medium = new map<string, int>();
		map<string, int> highStanding = new map<string, int>();
		map<string, int> mediumStanding = new map<string, int>();
		foreach (AIAgent agent : agents)
		{
			if (!agent)
				continue;
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (!c || c.IsInVehicle())
				continue;
			string side = ZCR_LossLog.SideOf(c);
			if (side != "US" && side != "USSR")
				continue;
			CharacterControllerComponent ctl = c.GetCharacterController();
			if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
				continue;
			vector p = c.GetOrigin();
			m_mWas.Set(c, p);
			vector before;
			bool moving = was.Find(c, before) && vector.DistanceXZ(before, p) > 2;
			SCR_AIUtilityComponent utility = SCR_AIUtilityComponent.Cast(agent.FindComponent(SCR_AIUtilityComponent));
			int level = Level(c, side, p, utility, now);
			bool standing = ctl.GetStance() == ECharacterStance.STAND;
			if (level == HIGH)
			{
				high.Set(side, high.Get(side) + 1);
				if (standing)
					highStanding.Set(side, highStanding.Get(side) + 1);
			}
			else if (level == MEDIUM)
			{
				medium.Set(side, medium.Get(side) + 1);
				if (standing)
					mediumStanding.Set(side, mediumStanding.Get(side) + 1);
			}
			bool limit = level == HIGH || (level == MEDIUM && !moving);
			Apply(agent, c, limit);
		}
		if (now >= m_iNextLog)
		{
			m_iNextLog = now + 30;
			array<string> sides = {"US", "USSR"};
			foreach (string s : sides)
			{
				int h = high.Get(s);
				int m = medium.Get(s);
				int hs = -1;
				int ms = -1;
				if (h > 0)
					hs = Math.Round(100.0 * highStanding.Get(s) / h);
				if (m > 0)
					ms = Math.Round(100.0 * mediumStanding.Get(s) / m);
				Print(string.Format("[ZCR][DANGER] t=%1 side=%2 high=%3 medium=%4 high_standing=%5 medium_standing=%6", now, s, h, m, hs, ms), LogLevel.NORMAL);
			}
		}
	}

	// -zcrDangerDronesOnly (24 Oct, DCO as the tactical layer): only enemy drones count - DCO decides the fighting stance
	// and knows nothing about drones (the first DCO matches, this layer off: 83-100% of drone victims died standing).
	protected static float DroneDist(string side, vector p)
	{
		float droneDist = 1e9;
		for (int k; k < ZCR_Drones.s_aDrones.Count(); k++)
		{
			IEntity d = ZCR_Drones.s_aDrones[k];
			if (!d || ZCR_Drones.s_aDroneSide[k] == side)
				continue;
			vector dp = d.GetOrigin();
			if (dp[1] - GetGame().GetWorld().GetSurfaceY(dp[0], dp[2]) < 2)
				continue;
			droneDist = Math.Min(droneDist, vector.DistanceXZ(dp, p));
		}
		return droneDist;
	}

	protected int Level(ChimeraCharacter c, string side, vector p, SCR_AIUtilityComponent utility, int now)
	{
		if (System.IsCLIParam("zcrDangerDronesOnly"))
		{
			float near = DroneDist(side, p);
			if (near < 150)
				return HIGH;
			if (near < 250)
				return MEDIUM;
			return 0;
		}
		EAIThreatState threat = EAIThreatState.SAFE;
		if (utility && utility.m_ThreatSystem)
			threat = utility.m_ThreatSystem.GetState();
		if (threat == EAIThreatState.THREATENED)
			return HIGH;
		vector enemy;
		float enemyDist = 1e9;
		if (ZCR_Sampler.NearestKnown(side, p, 400, enemy))
			enemyDist = vector.DistanceXZ(enemy, p);
		if (enemyDist < 150)
			return HIGH;
		// A friend lost near in the last 2 minutes - a kill zone (Martin 02:02: the next team walked into
		// the spot where the previous one had been killed).
		for (int i = ZCR_LossLog.s_aRecentPos.Count() - 1; i >= 0; i--)
		{
			if (now - ZCR_LossLog.s_aRecentAt[i] > 120)
				break;
			if (ZCR_LossLog.s_aRecentSide[i] == side && vector.DistanceXZ(ZCR_LossLog.s_aRecentPos[i], p) < 100)
				return HIGH;
		}
		float droneDist = 1e9;
		for (int k; k < ZCR_Drones.s_aDrones.Count(); k++)
		{
			IEntity d = ZCR_Drones.s_aDrones[k];
			if (!d || ZCR_Drones.s_aDroneSide[k] == side)
				continue;
			vector dp = d.GetOrigin();
			if (dp[1] - GetGame().GetWorld().GetSurfaceY(dp[0], dp[2]) < 2)
				continue;
			droneDist = Math.Min(droneDist, vector.DistanceXZ(dp, p));
		}
		if (droneDist < 150)
			return HIGH;
		if (threat == EAIThreatState.ALERTED || enemyDist < 400 || droneDist < 250)
			return MEDIUM;
		return 0;
	}

	// Crouched or prone only (min PRONE, max CROUCH), or no limit - changed only when it changes.
	protected void Apply(AIAgent agent, ChimeraCharacter c, bool limit)
	{
		int want = 0;
		if (limit)
			want = 1;
		if (m_mLimit.Get(c) == want)
			return;
		SCR_AICharacterSettingsComponent settings = SCR_AICharacterSettingsComponent.Cast(agent.FindComponent(SCR_AICharacterSettingsComponent));
		if (!settings)
			return;
		if (limit)
			settings.AddCharacterSetting(SCR_AICharacterStanceSetting_Range.Create(SCR_EAISettingOrigin.COMMANDING, SCR_EAIBehaviorCause.ALWAYS, ECharacterStance.PRONE, ECharacterStance.CROUCH), false, true);
		else
			settings.RemoveSettingsOfTypeAndOrigin(SCR_AICharacterStanceSettingBase, SCR_EAISettingOrigin.COMMANDING);
		m_mLimit.Set(c, want);
	}
}
