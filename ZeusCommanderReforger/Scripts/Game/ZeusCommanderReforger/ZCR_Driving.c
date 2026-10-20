// AI drivers' speed (Martin, 20 Oct: "cars are weirdly wiggling - goes left, right"; the logs of 20 Oct:
// 230 of 342 vehicles lost were crashes - the killer their own driver at 1 m - 191 of them at two places on
// the main bases' exit roads, ~500 m east of the US base and ~300 m north-east of the USSR base).
// The game's own cruise-speed limit for an AI driver (AICarMovementComponent.SetCruiseSpeed - its scenario
// framework's "set vehicle cruise speed" action) on every vehicle an AI drives: -zcrCruiseSpeed (km/h;
// default 0 = the game's own speed). A/B 20 Oct, 0 v 50 km/h: AI drivers run a median 12 km/h, at most 62,
// and the vehicles still blew up at the same places - the world's minefields across the exit roads (removed
// by our AI Conflict, AICF_RoadMines), not speed.
// Measured every 30 s: [ZCR][DRIVE] t= side= driven= median_kmh= max_kmh= over60= limit=, and a vehicle's
// last speed on its [ZCR][LOSS] line (kmh=).
class ZCR_Driving
{
	protected static ref ZCR_Driving s_Instance;
	protected static ref map<IEntity, float> s_mSpeed = new map<IEntity, float>();
	protected static ref map<IEntity, int> s_mSeen = new map<IEntity, int>();
	protected float m_fLimit = 0;
	protected int m_iNextLog;
	protected int m_iNextClean;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer())
			return;
		s_Instance = new ZCR_Driving();
		string value;
		if (System.GetCLIParam("zcrCruiseSpeed", value) && !value.IsEmpty())
			s_Instance.m_fLimit = value.ToFloat();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 2000, true);
	}

	// " kmh=NN" for a vehicle seen driven in the last minute, else "".
	static string Note(IEntity victim)
	{
		float kmh;
		if (!Vehicle.Cast(victim) || !s_mSpeed.Find(victim, kmh))
			return "";
		return string.Format(" kmh=%1", Math.Round(kmh));
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		map<string, ref array<float>> speeds = new map<string, ref array<float>>();
		foreach (AIAgent agent : agents)
		{
			if (!agent)
				continue;
			ChimeraCharacter c = ChimeraCharacter.Cast(agent.GetControlledEntity());
			if (!c || !c.IsInVehicle())
				continue;
			CompartmentAccessComponent access = c.GetCompartmentAccessComponent();
			if (!access)
				continue;
			PilotCompartmentSlot seat = PilotCompartmentSlot.Cast(access.GetCompartment());
			if (!seat)
				continue;
			IEntity v = seat.GetVehicle();
			if (!v || !v.GetPhysics())
				continue;
			float kmh = v.GetPhysics().GetVelocity().Length() * 3.6;
			s_mSpeed.Set(v, kmh);
			s_mSeen.Set(v, now);
			if (m_fLimit > 0)
			{
				AICarMovementComponent car = AICarMovementComponent.Cast(v.FindComponent(AICarMovementComponent));
				if (car)
					car.SetCruiseSpeed(m_fLimit);
			}
			string side = ZCR_LossLog.SideOf(c);
			if (!speeds.Contains(side))
				speeds.Set(side, {});
			speeds.Get(side).Insert(kmh);
		}
		if (now >= m_iNextLog)
		{
			m_iNextLog = now + 30;
			array<string> sides = {"US", "USSR"};
			foreach (string side : sides)
			{
				array<float> s = speeds.Get(side);
				if (!s || s.IsEmpty())
				{
					Print(string.Format("[ZCR][DRIVE] t=%1 side=%2 driven=0 limit=%3", now, side, m_fLimit), LogLevel.NORMAL);
					continue;
				}
				s.Sort();
				int over;
				foreach (float k : s)
				{
					if (k > 60)
						over++;
				}
				Print(string.Format("[ZCR][DRIVE] t=%1 side=%2 driven=%3 median_kmh=%4 max_kmh=%5 over60=%6 limit=%7",
					now, side, s.Count(), Math.Round(s[s.Count() / 2]), Math.Round(s[s.Count() - 1]), over, m_fLimit), LogLevel.NORMAL);
			}
		}
		if (now >= m_iNextClean)
		{
			m_iNextClean = now + 60;
			map<IEntity, float> speed = new map<IEntity, float>();
			map<IEntity, int> seen = new map<IEntity, int>();
			foreach (IEntity e, int at : s_mSeen)
			{
				if (e && now - at < 60)
				{
					speed.Set(e, s_mSpeed.Get(e));
					seen.Set(e, at);
				}
			}
			s_mSpeed = speed;
			s_mSeen = seen;
		}
	}
}
