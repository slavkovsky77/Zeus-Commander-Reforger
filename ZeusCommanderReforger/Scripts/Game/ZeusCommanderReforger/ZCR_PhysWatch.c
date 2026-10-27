// The crash hunt (26 Oct - Martin, note 421: "let's make a sub-lab reproducing the crash and fix it"). The night's crashes
// were the engine asserting on a bad entity matrix (enf_entity.cpp 1656-1672: orientation, position, bounding box), then an
// access violation - and the assert never names the entity. Every WATCH_MS this looks at every dynamic entity that moves
// (vehicles, soldiers, inventory items, drones) and logs the first sign of one going wrong, so the lines before a crash
// name the culprit:
//   [ZCR][PHYS] t= what=nan|wild|spin|falling|high name= kind=vehicle|man|item|drone|other v= av= y= ground= x= z= parent=
// nan: a position that isn't a number; wild: over WILD_MS m/s; spin: over SPIN_RAD rad/s; falling: FALL_M under the ground
// (rifles and a drone controller fell to -34 km last night - "entity out of world bounds"); high: HIGH_M above it.
// Each entity once per kind and 5 s. -zcrPhysFix: an item (not a soldier or vehicle) falling under the ground is deleted
// before it reaches the world's floor. -zcrNoPhysWatch off.
// 27 Oct 03:40: the crash sub-lab crashes in a soldier's get-in or get-out of an APC on a slope (both directions, never on
// the flat apron), so each get-in and get-out a soldier starts is logged too, with the vehicle and its tilt - the lines
// before a battle crash then say which vehicle, how tilted, in or out:
//   [ZCR][GETINOUT] t= what=in|out man= vehicle= seat= pitch= roll= x= z=
class ZCR_PhysWatch
{
	static const int WATCH_MS = 500;
	static const float WILD_MS = 120;      // m/s - an FPV dives at up to 50, bullets aren't watched
	static const float SPIN_RAD = 40;
	static const float FALL_M = 30;
	static const float HIGH_M = 1500;
	protected static bool s_bStarted;
	protected static ref ZCR_PhysWatch s_Instance;
	protected ref map<IEntity, int> m_mLastLog = new map<IEntity, int>();
	protected ref map<IEntity, int> m_mLastMove = new map<IEntity, int>();
	protected int m_iChecked;
	protected int m_iDeleted;
	protected int m_iNextSummary;
	protected ref array<IEntity> m_aDelete = {};

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoPhysWatch"))
			return;
		s_bStarted = true;
		s_Instance = new ZCR_PhysWatch();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, WATCH_MS, true);
	}

	protected void Tick()
	{
		BaseWorld world = GetGame().GetWorld();
		if (!world)
			return;
		m_iChecked = 0;
		m_aDelete.Clear();
		world.QueryEntitiesByAABB(Vector(-2000, -40000, -2000), Vector(16000, 6000, 16000), Check, null, EQueryEntitiesFlags.DYNAMIC);
		foreach (IEntity e : m_aDelete)
		{
			if (e)
			{
				m_iDeleted++;
				RplComponent.DeleteRplEntity(e, false);
			}
		}
		int now = ZCR_LossLog.Seconds();
		if (now >= m_iNextSummary)
		{
			m_iNextSummary = now + 120;
			Print(string.Format("[ZCR][PHYS] t=%1 summary checked=%2 deleted=%3", now, m_iChecked, m_iDeleted), LogLevel.NORMAL);
		}
	}

	protected bool Check(IEntity e)
	{
		if (!e)
			return true;
		ChimeraCharacter soldier = ChimeraCharacter.Cast(e);
		if (soldier)
			GetInOut(soldier);
		if (e.GetParent())
			return true;       // gear and parts move with their root
		string kind;
		if (Vehicle.Cast(e))
			kind = "vehicle";
		else if (ChimeraCharacter.Cast(e))
			kind = "man";
		else if (e.FindComponent(InventoryItemComponent))
			kind = "item";
		else if (e.GetPrefabData() && e.GetPrefabData().GetPrefabName().Contains("Drone"))
			kind = "drone";
		else
			return true;
		m_iChecked++;
		vector p = e.GetOrigin();
		if (p[0] != p[0] || p[1] != p[1] || p[2] != p[2])
		{
			Report(e, kind, "nan", 0, 0, 0);
			return true;
		}
		float ground = GetGame().GetWorld().GetSurfaceY(p[0], p[2]);
		float v, av;
		Physics physics = e.GetPhysics();
		if (physics)
		{
			v = physics.GetVelocity().Length();
			av = physics.GetAngularVelocity().Length();
		}
		if (v != v || av != av)
			Report(e, kind, "nan", v, av, ground);
		else if (v > WILD_MS)
			Report(e, kind, "wild", v, av, ground);
		else if (av > SPIN_RAD)
			Report(e, kind, "spin", v, av, ground);
		else if (p[1] < ground - FALL_M)
		{
			Report(e, kind, "falling", v, av, ground);
			if (kind == "item" && System.IsCLIParam("zcrPhysFix"))
				m_aDelete.Insert(e);
		}
		else if (p[1] > ground + HIGH_M)
			Report(e, kind, "high", v, av, ground);
		return true;
	}

	protected void GetInOut(ChimeraCharacter man)
	{
		CompartmentAccessComponent access = man.GetCompartmentAccessComponent();
		if (!access)
			return;
		string what;
		if (access.IsGettingIn())
			what = "in";
		else if (access.IsGettingOut())
			what = "out";
		else
			return;
		int now = ZCR_LossLog.Seconds();
		int last;
		if (m_mLastMove.Find(man, last) && now - last < 8)
			return;
		m_mLastMove.Set(man, now);
		BaseCompartmentSlot seat = access.GetCompartment();
		IEntity vehicle;
		if (seat)
			vehicle = seat.GetVehicle();
		if (!vehicle)
			vehicle = CompartmentAccessComponent.GetVehicleIn(man);
		string vname = "none";
		string seatType = "none";
		if (seat)
			seatType = typename.EnumToString(ECompartmentType, seat.GetType());
		float pitch, roll;
		vector pos = man.GetOrigin();
		if (vehicle)
		{
			vname = ZCR_LossLog.ShortName(vehicle);
			vector mat[4];
			vehicle.GetWorldTransform(mat);
			vector right = mat[0];
			vector fwd = mat[2];
			pos = mat[3];
			pitch = Math.Asin(Math.Clamp(fwd[1], -1, 1)) * Math.RAD2DEG;
			roll = Math.Asin(Math.Clamp(right[1], -1, 1)) * Math.RAD2DEG;
		}
		Print(string.Format("[ZCR][GETINOUT] t=%1 what=%2 man=%3 vehicle=%4 seat=%5 pitch=%6 roll=%7 x=%8 z=%9", now, what,
			ZCR_LossLog.ShortName(man), vname, seatType, Math.Round(pitch), Math.Round(roll), Math.Round(pos[0]), Math.Round(pos[2])), LogLevel.NORMAL);
	}

	protected void Report(IEntity e, string kind, string what, float v, float av, float ground)
	{
		int now = ZCR_LossLog.Seconds();
		int last;
		if (m_mLastLog.Find(e, last) && now - last < 5)
			return;
		m_mLastLog.Set(e, now);
		vector p = e.GetOrigin();
		string name = ZCR_LossLog.ShortName(e);
		Print(string.Format("[ZCR][PHYS] t=%1 what=%2 name=%3 kind=%4 v=%5 av=%6 y=%7 ground=%8 x=%9", now, what, name, kind,
			Math.Round(v), Math.Round(av), Math.Round(p[1]), Math.Round(ground), Math.Round(p[0])) + string.Format(" z=%1", Math.Round(p[2])), LogLevel.NORMAL);
	}
}
