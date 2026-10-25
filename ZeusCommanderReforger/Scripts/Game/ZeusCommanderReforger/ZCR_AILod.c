// AI level of detail by distance from the director camera (25 Oct night - Martin: "find out why FPS drops like that").
// In our watched matches nobody plays: the engine, which thins out AI far from the players, left every soldier at LOD 0 -
// full detail - wherever he was (census: 81 of 85 soldiers on foot at LOD 0, the scale goes to 10), and at 3x the game
// simulates them three times a frame: 57 fps at 1x, 49 at 2x, 41-44 at 3x, falling as the AI count grows. Here every
// 2 s each AI agent (soldiers, and groups by their leader) gets a LOD by its distance from the camera: full detail
// within 400 m, then 2, 4 and 6 - never the max (10), which switches the AI off (AI Conflict keeps its squads below it
// so they can still capture). -zcrAILod on (a lab test first).
//   [ZCR][AILOD] t= agents= changed= lod0= lod2= lod4= lod6=   (every 30 s)
class ZCR_AILod
{
	protected static bool s_bStarted;
	protected static int s_iLogAt;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || !System.IsCLIParam("zcrAILod"))
			return;
		s_bStarted = true;
		GetGame().GetCallqueue().CallLater(Tick, 2000, true);
	}

	static int LodFor(float metres)
	{
		if (metres < 400)
			return 0;
		if (metres < 900)
			return 2;
		if (metres < 1600)
			return 4;
		return 6;
	}

	protected static void Tick()
	{
		vector cam;
		if (!ZCR_Watch.CameraPos(cam))
			return;
		AIWorld world = GetGame().GetAIWorld();
		if (!world)
			return;
		array<AIAgent> agents = {};
		world.GetAIAgents(agents);
		int changed;
		int count0, count2, count4, count6;
		foreach (AIAgent a : agents)
		{
			if (!a || a.GetLOD() == AIAgent.GetMaxLOD())
				continue;   // switched off by the engine or AI Conflict: left alone
			IEntity e = a.GetControlledEntity();
			if (!e)
			{
				SCR_AIGroup g = SCR_AIGroup.Cast(a);
				if (g)
					e = g.GetLeaderEntity();
			}
			if (!e)
				continue;
			int lod = LodFor(vector.Distance(e.GetOrigin(), cam));
			if (a.GetLOD() != lod)
			{
				a.SetLOD(lod);
				changed++;
			}
			if (lod == 0)
				count0++;
			else if (lod == 2)
				count2++;
			else if (lod == 4)
				count4++;
			else
				count6++;
		}
		int now = ZCR_LossLog.Seconds();
		if (now >= s_iLogAt)
		{
			s_iLogAt = now + 30;
			Print(string.Format("[ZCR][AILOD] t=%1 agents=%2 changed=%3 lod0=%4 lod2=%5 lod4=%6 lod6=%7", now, agents.Count(), changed, count0, count2, count4,
				count6), LogLevel.NORMAL);
		}
	}
}
