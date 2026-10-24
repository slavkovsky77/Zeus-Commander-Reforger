// Small-arms fire at drones (Martin, 20 Oct 02:25: "implement defense against drones - infantry reacts
// with small-arms fire like in reality", important). Every second, for each enemy drone in the air:
// up to 3 soldiers on foot within 120 m of it who can see it (machine gunners first, then the nearest)
// fire at it - the game's own suppress behaviour, aimed at a small sphere moved onto the drone each
// second, so they really turn and shoot (crouched or prone: the danger layer keeps them down). The rest
// keep reacting as before (down, cover). Rifle fire at a small fast drone rarely hits: each shooter with
// a line of sight has a 3% chance a second to bring it down (6% for a machine gunner, x1.5 under 50 m);
// a hit drone is destroyed through its damage component (deleted if it has none) and logged.
// No fire into friends (24 Oct, drone storm at the farm: 3 of 9 US soldiers shot by their own team leader firing at
// a drone over the squad and diving on the squad leader): a soldier holds fire - and stops a running burst - while a
// friend is within 8 m of the drone or near his line of fire (1.5 m from it at the muzzle, widening to the 4-m sphere
// the burst is aimed into); the next soldier in line who has a clear shot fires instead.
// Measured: [ZCR][ANTIDRONE] t= side= shot_down= by= distance= at each hit, and every 30 s
// t= side= shooters= drones_engaged= shot_down_total= held_friend=. Both sides; -zcrNoAntiDrone turns it off.
class ZCR_AntiDroneTarget
{
	IEntity m_Drone;
	ref ZCR_SafeSphere m_Volume;
}

class ZCR_AntiDrone
{
	protected static ref ZCR_AntiDrone s_Instance;
	protected static bool s_bStarted;
	protected ref array<ref ZCR_AntiDroneTarget> m_aTargets = {};
	protected ref map<IEntity, int> m_mFiringUntil = new map<IEntity, int>();
	protected ref map<IEntity, SCR_AISuppressBehavior> m_mBurst = new map<IEntity, SCR_AISuppressBehavior>();
	protected ref map<string, int> m_mHeld = new map<string, int>();
	protected ref map<string, int> m_mShotDown = new map<string, int>();
	protected ref map<string, int> m_mShooters = new map<string, int>();
	protected ref map<string, int> m_mEngaged = new map<string, int>();
	protected ref array<IEntity> m_aFound = {};
	protected ref TraceParam m_Trace;
	protected int m_iNextLog;
	static const float RANGE = 120;
	static const int SHOOTERS = 3;
	static const float SPHERE_M = 4;
	static const float FRIEND_NEAR_M = 8;
	static const float FRIEND_LINE_M = 1.5;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoAntiDrone"))
			return;
		s_bStarted = true;
		s_Instance = new ZCR_AntiDrone();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	protected bool AddMan(IEntity e)
	{
		if (ChimeraCharacter.Cast(e))
			m_aFound.Insert(e);
		return true;
	}

	// A fixed sphere at the drone for each burst - never moved: the game picks a point in the volume,
	// then its height range there, and a sphere moved in between left the point outside - a negative
	// square root, a NaN, and the diagnostic build stopped (probe 20 Oct 02:42).
	protected ZCR_AntiDroneTarget Target(IEntity drone, vector at)
	{
		ZCR_AntiDroneTarget t = new ZCR_AntiDroneTarget();
		t.m_Drone = drone;
		t.m_Volume = new ZCR_SafeSphere(at, SPHERE_M);
		m_aTargets.Insert(t);
		return t;
	}

	protected void Tick()
	{
		ZCR_CostScope cost = new ZCR_CostScope("antidrone");   // ZCR_Cost: our scripts' share of the frame time
		int now = ZCR_LossLog.Seconds();
		BaseWorld world = GetGame().GetWorld();
		// Old bursts' spheres: kept only while referenced by a running behaviour (they are refs there).
		m_aTargets.Clear();
		for (int i; i < ZCR_Drones.s_aDrones.Count(); i++)
		{
			IEntity drone = ZCR_Drones.s_aDrones[i];
			if (!drone)
				continue;
			string droneSide = ZCR_Drones.s_aDroneSide[i];
			vector dp = drone.GetOrigin();
			if (dp[1] - world.GetSurfaceY(dp[0], dp[2]) < 3)
				continue;
			// Who can see it: soldiers of the other sides on foot within range, machine gunners first.
			m_aFound.Clear();
			world.QueryEntitiesBySphere(dp, RANGE, AddMan, null, EQueryEntitiesFlags.DYNAMIC);
			array<ChimeraCharacter> shooters = {};
			array<float> order = {};
			foreach (IEntity e : m_aFound)
			{
				ChimeraCharacter c = ChimeraCharacter.Cast(e);
				string side = ZCR_LossLog.SideOf(e);
				if (!c || c.IsInVehicle() || side == droneSide || (side != "US" && side != "USSR"))
					continue;
				CharacterControllerComponent ctl = c.GetCharacterController();
				if (!ctl || ctl.GetLifeState() != ECharacterLifeState.ALIVE)
					continue;
				if (!Sees(world, c.EyePosition(), dp, c, drone))
					continue;
				float d = vector.Distance(c.EyePosition(), dp);
				float rank = d;
				if (IsGunner(c))
					rank -= 1000;
				int at = 0;
				while (at < order.Count() && order[at] < rank)
					at++;
				order.InsertAt(rank, at);
				shooters.InsertAt(c, at);
			}
			if (shooters.IsEmpty())
				continue;
			ZCR_AntiDroneTarget target = Target(drone, dp);
			bool down;
			string by;
			float byDist;
			string side = ZCR_LossLog.SideOf(shooters[0]);
			int fired;
			for (int k; k < shooters.Count() && fired < SHOOTERS; k++)
			{
				ChimeraCharacter c = shooters[k];
				if (FriendInFire(c, side, c.EyePosition(), dp))
				{
					m_mHeld.Set(side, m_mHeld.Get(side) + 1);
					StopBurst(c);
					continue;
				}
				fired++;
				m_mShooters.Set(side, m_mShooters.Get(side) + 1);
				// The game's suppress behaviour at the drone, a 3 s burst re-aimed while it is near.
				if (!m_mFiringUntil.Contains(c) || now >= m_mFiringUntil.Get(c))
				{
					SCR_AIUtilityComponent utility = ZCR_DroneThreat.UtilityOf(c);
					if (utility)
					{
						SCR_AISuppressBehavior burst = new SCR_AISuppressBehavior(utility, null, target.m_Volume, 3, 3, 80);
						ZCR_Reserved.Add(utility, burst);
						m_mBurst.Set(c, burst);
					}
					m_mFiringUntil.Set(c, now + 3);
				}
				float d = vector.Distance(c.EyePosition(), dp);
				float chance = 0.03;
				if (IsGunner(c))
					chance = 0.06;
				if (d < 50)
					chance *= 1.5;
				if (!down && Math.RandomFloat01() < chance)
				{
					down = true;
					by = ZCR_LossLog.Role(c);
					byDist = d;
				}
			}
			if (fired > 0)
				m_mEngaged.Set(side, m_mEngaged.Get(side) + 1);
			if (down)
			{
				m_mShotDown.Set(side, m_mShotDown.Get(side) + 1);
				Print(string.Format("[ZCR][ANTIDRONE] t=%1 side=%2 shot_down=1 drone_side=%3 by=%4 distance=%5 x=%6 z=%7", now, side, droneSide, by, Math.Round(byDist),
					Math.Round(dp[0]), Math.Round(dp[2])), LogLevel.NORMAL);
				ZCR_Feed.Note(side, string.Format("%1 shot down an enemy drone at %2 m", by, Math.Round(byDist)));
				Destroy(drone);
			}
		}
		if (now >= m_iNextLog)
		{
			m_iNextLog = now + 30;
			array<string> sides = {"US", "USSR"};
			foreach (string s : sides)
			{
				if (m_mShooters.Get(s) > 0 || m_mShotDown.Get(s) > 0 || m_mHeld.Get(s) > 0)
					Print(string.Format("[ZCR][ANTIDRONE] t=%1 side=%2 shooters=%3 drones_engaged=%4 shot_down_total=%5 held_friend=%6", now, s, m_mShooters.Get(s),
						m_mEngaged.Get(s), m_mShotDown.Get(s), m_mHeld.Get(s)), LogLevel.NORMAL);
				m_mShooters.Set(s, 0);
				m_mEngaged.Set(s, 0);
				m_mHeld.Set(s, 0);
			}
		}
	}

	// A friend of the shooter's side (alive or down, not the shooter) near the drone or near the line from the eye to it.
	protected bool FriendInFire(ChimeraCharacter shooter, string side, vector eye, vector dp)
	{
		vector line = dp - eye;
		float len2 = line.LengthSq();
		foreach (IEntity e : m_aFound)
		{
			ChimeraCharacter f = ChimeraCharacter.Cast(e);
			if (!f || f == shooter || ZCR_LossLog.SideOf(f) != side)
				continue;
			CharacterControllerComponent ctl = f.GetCharacterController();
			if (!ctl || ctl.GetLifeState() == ECharacterLifeState.DEAD)
				continue;
			vector p = f.GetOrigin() + vector.Up;
			if (vector.Distance(p, dp) < FRIEND_NEAR_M)
				return true;
			if (len2 < 1)
				continue;
			float along = vector.Dot(p - eye, line) / len2;
			if (along <= 0 || along >= 1)
				continue;
			if (vector.Distance(p, eye + line * along) < FRIEND_LINE_M + SPHERE_M * along)
				return true;
		}
		return false;
	}

	// The shooter's running burst ends at once (the game's suppress behaviour would keep firing for its 3 s).
	protected void StopBurst(ChimeraCharacter c)
	{
		SCR_AISuppressBehavior burst = m_mBurst.Get(c);
		if (burst && burst.GetActionState() == EAIActionState.RUNNING)
			burst.Fail();
		m_mBurst.Remove(c);
		m_mFiringUntil.Remove(c);
	}

	protected static bool IsGunner(ChimeraCharacter c)
	{
		string role = ZCR_LossLog.Role(c);
		role.ToLower();
		return role.Contains("machine") || role.Contains("mg") || role.Contains("automatic");
	}

	protected bool Sees(BaseWorld world, vector eye, vector dp, IEntity self, IEntity drone)
	{
		if (!m_Trace)
			m_Trace = new TraceParam();
		m_Trace.Flags = TraceFlags.ENTS | TraceFlags.WORLD;
		m_Trace.TargetLayers = EPhysicsLayerDefs.ViewGeometry | EPhysicsLayerDefs.Foliage;
		m_Trace.Exclude = self;
		m_Trace.Start = eye;
		m_Trace.End = dp;
		float f = world.TraceMove(m_Trace, null);
		return f >= 0.97 || (m_Trace.TraceEnt && m_Trace.TraceEnt.GetRootParent() == drone);
	}

	// Brought down: its damage component destroys it (the drone's own code sees it), else it is removed.
	protected static void Destroy(IEntity drone)
	{
		SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(drone.FindComponent(SCR_DamageManagerComponent));
		if (damage && !damage.IsDestroyed())
		{
			ZCR_Trace.Ent("destroy", drone, "shot_down");
			damage.SetHealthScaled(0);
			if (damage.IsDestroyed())
				return;
		}
		ZCR_Trace.Ent("delete", drone, "shot_down");
		RplComponent.DeleteRplEntity(drone, false);
	}
}

// The game's suppression sphere takes sqrt(r^2 - d^2) for a point the suppression picked near its edge;
// a hair outside the sphere that is NaN and the diagnostic build stops (BadFloat in GetYRange: the
// watched match of 20 Oct 13:00, and 05:16 before - moving the sphere was only part of it). Clamped at 0.
class ZCR_SafeSphere : SCR_AISuppressionVolumeSphere
{
	override protected void GetYRange(vector position, out float minY, out float maxY)
	{
		vector centerPos = GetCenterPosition();
		float distToCenter2D = vector.DistanceXZ(centerPos, position);
		float maxDist = Math.Sqrt(Math.Max(0, (m_fRadius * m_fRadius) - (distToCenter2D * distToCenter2D)));
		maxY = centerPos[1] + maxDist;
		minY = centerPos[1] - maxDist;
	}
}
