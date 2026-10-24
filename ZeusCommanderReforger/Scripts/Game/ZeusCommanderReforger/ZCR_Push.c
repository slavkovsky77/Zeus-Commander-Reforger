// A vehicle moved by a physics push instead of a teleport (22 Oct, Martin: "try more"). Our back-offs (a jammed
// vehicle backs 8 m) and park-asides (an abandoned blocker moved off the road) cut the jams to 2.0 and the long stops
// to 2.8 a match, but they teleported the vehicle, and hand moves came with crashes. JMVehicleAI (jm3009, Workshop
// 6A8490E1621E7B3C, APL) showed the way: its anti-stuck sets the vehicle's velocity a few times a second for a couple
// of seconds - the AI driver doesn't override physics, no transform jumps, replication sees an ordinary moving
// vehicle. Here the vehicle slides at 2.5 m/s (9 km/h) towards the spot, its heading kept, then the AI drives again.
// [ZCR][PUSH] t= vehicle= why= m= moved_m= s= x= z= when one ends. -zcrTeleportMoves goes back to the teleport.
class ZCR_PushJob
{
	Vehicle m_Vehicle;
	vector m_vDir;
	vector m_vFrom;
	float m_fDistance;
	int m_iStartMs;
	int m_iEndMs;
	string m_sWhy;
}

class ZCR_Push
{
	static const float SPEED = 2.5;        // m/s
	static const int TICK_MS = 100;
	protected static ref ZCR_Push s_Instance;
	protected static ref array<ref ZCR_PushJob> s_aJobs = {};

	static bool Busy(IEntity vehicle)
	{
		foreach (ZCR_PushJob job : s_aJobs)
		{
			if (job.m_Vehicle == vehicle)
				return true;
		}
		return false;
	}

	// Pushes the vehicle towards the spot (its heading kept). False if it can't be pushed now.
	static bool Start(Vehicle vehicle, vector at, string why)
	{
		if (!vehicle || !vehicle.GetPhysics() || Busy(vehicle))
			return false;
		vector from = vehicle.GetOrigin();
		vector dir = at - from;
		dir[1] = 0;
		float distance = dir.Length();
		if (distance < 0.5 || distance > 30)
			return false;
		dir.Normalize();
		if (!s_Instance)
		{
			s_Instance = new ZCR_Push();
			GetGame().GetCallqueue().CallLater(s_Instance.Tick, TICK_MS, true);
		}
		ZCR_PushJob job = new ZCR_PushJob();
		job.m_Vehicle = vehicle;
		job.m_vDir = dir;
		job.m_vFrom = from;
		job.m_fDistance = distance;
		// World (game) time: the watched game runs 3x and its physics with it, so the push covers the same metres.
		job.m_iStartMs = NowMs();
		job.m_iEndMs = job.m_iStartMs + Math.Min(8000, (distance / SPEED + 0.3) * 1000);
		job.m_sWhy = why;
		s_aJobs.Insert(job);
		vehicle.GetPhysics().SetActive(ActiveState.ACTIVE);
		return true;
	}

	protected static int NowMs()
	{
		BaseWorld world = GetGame().GetWorld();
		if (!world)
			return 0;
		return world.GetWorldTime();
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("push");   // ZCR_Cost: our scripts' share of the frame time
		int now = NowMs();
		for (int i = s_aJobs.Count() - 1; i >= 0; i--)
		{
			ZCR_PushJob job = s_aJobs[i];
			Vehicle v = job.m_Vehicle;
			Physics physics;
			if (v)
				physics = v.GetPhysics();
			vector up;
			if (v)
				up = v.GetTransformAxis(1);
			bool done = !physics || now >= job.m_iEndMs || up[1] < 0.5;
			if (!done && v)
			{
				vector moved = v.GetOrigin() - job.m_vFrom;
				moved[1] = 0;
				done = moved.Length() >= job.m_fDistance;
			}
			if (done)
			{
				if (physics)
					physics.SetAngularVelocity(vector.Zero);
				if (v)
				{
					vector moved = v.GetOrigin() - job.m_vFrom;
					moved[1] = 0;
					Print(string.Format("[ZCR][PUSH] t=%1 vehicle=%2 why=%3 m=%4 moved_m=%5 s=%6 x=%7 z=%8", ZCR_LossLog.Seconds(), ZCR_LossLog.ShortName(v), job.m_sWhy,
						Math.Round(job.m_fDistance), Math.Round(moved.Length() * 10) / 10, Math.Round((now - job.m_iStartMs) / 100) / 10,
						Math.Round(v.GetOrigin()[0]), Math.Round(v.GetOrigin()[2])), LogLevel.NORMAL);
				}
				s_aJobs.Remove(i);
				continue;
			}
			vector velocity = physics.GetVelocity();
			vector push = job.m_vDir * SPEED;
			push[1] = velocity[1];    // gravity and the ground stay the physics' own
			physics.SetVelocity(push);
			physics.SetAngularVelocity(vector.Zero);
		}
	}
}
