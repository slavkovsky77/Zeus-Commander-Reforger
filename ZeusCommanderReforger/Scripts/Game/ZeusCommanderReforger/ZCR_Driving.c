// AI drivers' speed (Martin, 20 Oct: "cars are weirdly wiggling - goes left, right"; the logs of 20 Oct:
// 230 of 342 vehicles lost were crashes - the killer their own driver at 1 m - 191 of them at two places on
// the main bases' exit roads, ~500 m east of the US base and ~300 m north-east of the USSR base).
// The game's own cruise-speed limit for an AI driver (AICarMovementComponent.SetCruiseSpeed - its scenario
// framework's "set vehicle cruise speed" action) on every vehicle an AI drives: -zcrCruiseSpeed (km/h;
// default 0 = the game's own speed). A/B 20 Oct, 0 v 50 km/h: AI drivers run a median 12 km/h, at most 62,
// and the vehicles still blew up at the same places - the world's minefields across the exit roads (removed
// by our AI Conflict, AICF_RoadMines), not speed.
// Measured every 30 s: [ZCR][DRIVE] t= side= driven= median_kmh= max_kmh= over60= limit= stuck= jammed=, and a
// vehicle's last speed on its [ZCR][LOSS] line (kmh=).
// Stuck and jammed vehicles (Martin, 21 Oct: "AI crashed into vehicles, they crash and crash, they deadlock
// themselves" - a T-72 and a supply truck nose to nose in a rock gap 2 min, cars bumping at the main base): a
// driven vehicle that hasn't moved 3 m for STUCK_S game seconds is stuck; with another vehicle within JAM_M it is
// jammed (a deadlock). Logged once when it starts and when it ends:
//   [ZCR][JAM] t= side= vehicle= other= other_side= x= z= (jammed) / [ZCR][STUCKVEH] t= side= vehicle= x= z=
//   [ZCR][UNJAM] t= side= vehicle= stuck_s= (moving again or gone)
// A soldier killed with no killer next to a moving vehicle of his side (6 m, over 2 km/h) gets runover=<vehicle> on
// his [ZCR][LOSS] line (Martin's /bad 21:03: the T-72 ran over its medic and machine gunner).
class ZCR_Driving
{
	protected static ref ZCR_Driving s_Instance;
	protected static ref map<IEntity, float> s_mSpeed = new map<IEntity, float>();
	protected static ref map<IEntity, int> s_mSeen = new map<IEntity, int>();
	protected static ref map<IEntity, vector> s_mMark = new map<IEntity, vector>();
	protected static ref map<IEntity, int> s_mMarkAt = new map<IEntity, int>();
	protected static ref map<IEntity, string> s_mStuck = new map<IEntity, string>();     // "" not stuck, "STUCK", "JAM"
	protected static ref map<IEntity, string> s_mSide = new map<IEntity, string>();
	protected static ref array<IEntity> s_aNear;
	static const int STUCK_S = 45;
	static const float JAM_M = 10;
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

	// " runover=<vehicle>" for a soldier killed with no killer next to a moving vehicle of his side, else "".
	static string RunOver(IEntity victim, IEntity killer)
	{
		if (!ChimeraCharacter.Cast(victim) || (killer && killer != victim))
			return "";
		string side = ZCR_LossLog.SideOf(victim);
		foreach (IEntity v, float kmh : s_mSpeed)
		{
			if (!v || kmh < 2 || s_mSide.Get(v) != side)
				continue;
			if (vector.DistanceXZ(v.GetOrigin(), victim.GetOrigin()) <= 6)
				return " runover=" + ZCR_LossLog.ShortName(v);
		}
		return "";
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
			s_mSide.Set(v, side);
			Watch(v, side, now);
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
				int stuckN, jamN;
				foreach (IEntity sv, string state : s_mStuck)
				{
					if (!sv || s_mSide.Get(sv) != side)
						continue;
					if (state == "STUCK")
						stuckN++;
					else if (state == "JAM")
						jamN++;
				}
				// The moving ones (over 3 km/h): how fast the AI drives when it drives - waiting at a pad or loading isn't driving.
				array<float> moving = {};
				foreach (float mk : s)
				{
					if (mk > 3)
						moving.Insert(mk);
				}
				int movingKmh = -1;
				if (!moving.IsEmpty())
					movingKmh = Math.Round(moving[moving.Count() / 2]);
				Print(string.Format("[ZCR][DRIVE] t=%1 side=%2 driven=%3 median_kmh=%4 max_kmh=%5 over60=%6 limit=%7",
					now, side, s.Count(), Math.Round(s[s.Count() / 2]), Math.Round(s[s.Count() - 1]), over, m_fLimit) +
					string.Format(" stuck=%1 jammed=%2 moving_kmh=%3", stuckN, jamN, movingKmh), LogLevel.NORMAL);
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
			// Vehicles no longer driven (driver out or dead, wreck gone): a stuck one ends there.
			array<IEntity> gone = {};
			foreach (IEntity sv, string state : s_mStuck)
			{
				if (!sv || !seen.Contains(sv))
					gone.Insert(sv);
			}
			foreach (IEntity g : gone)
			{
				if (g && !s_mStuck.Get(g).IsEmpty())
					Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 stuck_s=%4 ended=not_driven", now, s_mSide.Get(g), ZCR_LossLog.ShortName(g),
						now - s_mMarkAt.Get(g)), LogLevel.NORMAL);
				s_mStuck.Remove(g);
				s_mMark.Remove(g);
				s_mMarkAt.Remove(g);
			}
		}
	}

	// Stuck / jammed bookkeeping for one driven vehicle (every 2 s).
	protected static void Watch(IEntity v, string side, int now)
	{
		vector at = v.GetOrigin();
		vector mark;
		if (!s_mMark.Find(v, mark) || vector.DistanceXZ(at, mark) > 3)
		{
			string was = s_mStuck.Get(v);
			if (!was.IsEmpty())
				Print(string.Format("[ZCR][UNJAM] t=%1 side=%2 vehicle=%3 stuck_s=%4 ended=moving", now, side, ZCR_LossLog.ShortName(v), now - s_mMarkAt.Get(v)), LogLevel.NORMAL);
			s_mMark.Set(v, at);
			s_mMarkAt.Set(v, now);
			s_mStuck.Set(v, "");
			return;
		}
		if (now - s_mMarkAt.Get(v) < STUCK_S || !s_mStuck.Get(v).IsEmpty())
			return;
		IEntity other = OtherVehicleNear(v, JAM_M);
		if (other)
		{
			s_mStuck.Set(v, "JAM");
			string otherSide = ZCR_LossLog.SideOf(other);
			if (otherSide.IsEmpty())
				otherSide = "none";
			Print(string.Format("[ZCR][JAM] t=%1 side=%2 vehicle=%3 other=%4 other_side=%5 x=%6 z=%7", now, side, ZCR_LossLog.ShortName(v),
				ZCR_LossLog.ShortName(other), otherSide, Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
		}
		else
		{
			s_mStuck.Set(v, "STUCK");
			Print(string.Format("[ZCR][STUCKVEH] t=%1 side=%2 vehicle=%3 x=%4 z=%5", now, side, ZCR_LossLog.ShortName(v), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
		}
	}

	protected static IEntity OtherVehicleNear(IEntity v, float radius)
	{
		s_aNear = {};
		GetGame().GetWorld().QueryEntitiesBySphere(v.GetOrigin(), radius, CollectVehicle, null, EQueryEntitiesFlags.DYNAMIC);
		foreach (IEntity e : s_aNear)
		{
			if (e != v && e.GetRootParent() != v)
				return e;
		}
		return null;
	}

	protected static bool CollectVehicle(IEntity e)
	{
		if (Vehicle.Cast(e))
			s_aNear.Insert(e);
		return true;
	}
}
