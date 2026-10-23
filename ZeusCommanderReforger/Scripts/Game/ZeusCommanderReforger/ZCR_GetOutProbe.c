// Lab probe (23 Oct night): who orders a vehicle crew out. Test cars lost their drivers with no failed move logged - the
// first car at B in every watched run (review note 314) and 4 of 6 cars on the Everon exit in one headless run. The game
// orders crews out from six places (a failed group move, fire damage aboard, a target reaction, a failed get-in, gunners
// leaving a turret, the group's own get-out activity). -zcrGetOutProbe logs each order with the script stack that made it:
//   [ZCR][GETOUT] t= kind=soldier|group vehicle= x= z= priority= in_activity= stack=
class ZCR_GetOutProbe
{
	protected static int s_iOn = -1;

	static bool On()
	{
		if (s_iOn < 0)
		{
			s_iOn = 0;
			if (System.IsCLIParam("zcrGetOutProbe"))
				s_iOn = 1;
		}
		return s_iOn == 1;
	}

	static void Log(string kind, IEntity vehicle, float priority, bool inActivity)
	{
		string stack;
		Debug.DumpStack(stack);
		stack.Replace("\n", " < ");
		stack.Replace("\t", "");
		if (stack.Length() > 700)
			stack = stack.Substring(0, 700);
		vector at = vehicle.GetOrigin();
		Print(string.Format("[ZCR][GETOUT] t=%1 kind=%2 vehicle=%3 x=%4 z=%5 priority=%6 in_activity=%7 stack=%8", ZCR_LossLog.Seconds(), kind,
			ZCR_LossLog.ShortName(vehicle), Math.Round(at[0]), Math.Round(at[2]), priority, inActivity, stack), LogLevel.NORMAL);
	}
}

// -zcrDoorProbe "x,z;...": every 30 s each door within 40 m of the points (gates on a test track): prefab, place, how open.
// -zcrOpenDoors also opens them (is a closed gate what jams the Everon base exit?).
//   [ZCR][DOOR] t= at= door= x= z= open=
class ZCR_DoorProbe
{
	protected static ref ZCR_DoorProbe s_Instance;
	protected ref array<vector> m_aPoints = {};
	protected ref array<IEntity> m_aFound = {};

	static void Start()
	{
		string spec;
		if (s_Instance || !Replication.IsServer() || !System.GetCLIParam("zcrDoorProbe", spec) || spec.IsEmpty())
			return;
		s_Instance = new ZCR_DoorProbe();
		array<string> parts = {};
		spec.Split(";", parts, true);
		foreach (string p : parts)
		{
			array<string> xz = {};
			p.Split(",", xz, true);
			if (xz.Count() >= 2)
				s_Instance.m_aPoints.Insert(Vector(xz[0].ToFloat(), 0, xz[1].ToFloat()));
		}
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, false);   // a first look (and opening) at once
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 30000, true);
	}

	protected bool Add(IEntity e)
	{
		if (e && e.FindComponent(DoorComponent))
			m_aFound.Insert(e);
		return true;
	}

	protected void Tick()
	{
		BaseWorld world = GetGame().GetWorld();
		foreach (vector p : m_aPoints)
		{
			p[1] = world.GetSurfaceY(p[0], p[2]);
			m_aFound.Clear();
			world.QueryEntitiesBySphere(p, 40, Add, null, EQueryEntitiesFlags.ALL);
			foreach (IEntity e : m_aFound)
			{
				DoorComponent door = DoorComponent.Cast(e.FindComponent(DoorComponent));
				vector at = e.GetOrigin();
				string name = "";
				IEntity named = e;
				while (named && name.IsEmpty())
				{
					if (named.GetPrefabData())
						name = named.GetPrefabData().GetPrefabName();
					named = named.GetParent();
				}
				int slash = name.LastIndexOf("/");
				if (slash >= 0)
					name = name.Substring(slash + 1, name.Length() - slash - 1);
				Print(string.Format("[ZCR][DOOR] t=%1 at=%2,%3 door=%4 x=%5 z=%6 open=%7", ZCR_LossLog.Seconds(), Math.Round(p[0]), Math.Round(p[2]),
					name, Math.Round(at[0]), Math.Round(at[2]), Math.Round(door.GetNormalizedDoorState() * 100) / 100), LogLevel.NORMAL);
				if (System.IsCLIParam("zcrOpenDoors") && Math.AbsFloat(door.GetNormalizedDoorState()) < 0.5)
					door.SetControlValue(1, RplId.Invalid());
			}
		}
	}
}

// The group's get-out activity (a failed move orders the whole group out through it).
modded class SCR_AIGetOutActivity
{
	void SCR_AIGetOutActivity(SCR_AIGroupUtilityComponent utility, AIWaypoint relatedWaypoint, IEntity vehicle, SCR_AIBoardingParameters boardingParameters = null, float priority = PRIORITY_ACTIVITY_GET_OUT, float priorityLevel = PRIORITY_LEVEL_NORMAL)
	{
		if (utility && vehicle && ZCR_GetOutProbe.On())
			ZCR_GetOutProbe.Log("group", vehicle, priority, relatedWaypoint != null);
	}
}
