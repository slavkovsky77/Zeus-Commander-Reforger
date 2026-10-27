// Bullets piling up at the world origin (27 Oct, the first 40-minute watched matches: rifle and machine-gun rounds at
// x 0, z 0, 145 m up, never flying - 84 by game minute 11, 2847 by minute 40, the frame rate sliding as they grow).
// Every 2 game seconds the new ones there, grouped by who fired them: the shooter, alive or dead, the vehicle and seat
// he sits in, where he is - one line per group:
//   [ZCR][PROJWATCH] t= new= total= n= kind= shooter= state= vehicle= seat= x= z=
// -zcrNoProjWatch off.
class ZCR_ProjWatch
{
	static const float BOX_M = 30;
	protected static bool s_bStarted;
	protected static ref set<IEntity> s_mSeen = new set<IEntity>();
	protected static ref array<IEntity> s_aFound = {};

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoProjWatch"))
			return;
		s_bStarted = true;
		GetGame().GetCallqueue().CallLater(Tick, 2000, true);
	}

	protected static bool Collect(IEntity e)
	{
		if (e && !e.GetParent() && e.ClassName().Contains("Projectile"))
			s_aFound.Insert(e);
		return true;
	}

	protected static void Tick()
	{
		s_aFound.Clear();
		GetGame().GetWorld().QueryEntitiesByAABB(Vector(-BOX_M, -2000, -BOX_M), Vector(BOX_M, 4000, BOX_M), Collect, null, EQueryEntitiesFlags.DYNAMIC);
		set<IEntity> now = new set<IEntity>();
		map<string, int> groups = new map<string, int>();
		int fresh;
		foreach (IEntity p : s_aFound)
		{
			now.Insert(p);
			if (s_mSeen.Contains(p))
				continue;
			fresh++;
			string key = Describe(p);
			groups.Set(key, groups.Get(key) + 1);
		}
		s_mSeen = now;
		if (fresh == 0)
			return;
		int t = ZCR_LossLog.Seconds();
		foreach (string key, int n : groups)
			Print(string.Format("[ZCR][PROJWATCH] t=%1 new=%2 total=%3 n=%4 %5", t, fresh, s_aFound.Count(), n, key), LogLevel.NORMAL);
	}

	// "kind= shooter= state= vehicle= seat= x= z=" for one projectile.
	protected static string Describe(IEntity p)
	{
		string kind = "no_prefab";
		if (p.GetPrefabData())
		{
			kind = p.GetPrefabData().GetPrefabName();
			int slash = kind.LastIndexOf("/");
			if (slash >= 0)
				kind = kind.Substring(slash + 1, kind.Length() - slash - 1);
			kind.Replace(".et", "");
		}
		IEntity who;
		BaseProjectileComponent pc = BaseProjectileComponent.Cast(p.FindComponent(BaseProjectileComponent));
		if (pc && pc.GetInstigator())
			who = pc.GetInstigator().GetInstigatorEntity();
		if (!who)
			return string.Format("kind=%1 shooter=none state=- vehicle=- seat=- x=- z=-", kind);
		string state = "-";
		string vname = "-";
		string seatType = "-";
		ChimeraCharacter man = ChimeraCharacter.Cast(who);
		if (man)
		{
			CharacterControllerComponent controller = man.GetCharacterController();
			if (controller && controller.IsDead())
				state = "dead";
			else
				state = "alive";
			if (man.IsInVehicle())
			{
				CompartmentAccessComponent access = man.GetCompartmentAccessComponent();
				BaseCompartmentSlot seat;
				if (access)
					seat = access.GetCompartment();
				if (seat)
				{
					seatType = typename.EnumToString(ECompartmentType, seat.GetType());
					if (seat.GetVehicle())
						vname = ZCR_LossLog.ShortName(seat.GetVehicle());
				}
				else
					seatType = "unknown";
			}
		}
		vector at = who.GetOrigin();
		return string.Format("kind=%1 shooter=%2 state=%3 vehicle=%4 seat=%5 x=%6 z=%7", kind, ZCR_LossLog.ShortName(who), state, vname, seatType,
			Math.Round(at[0]), Math.Round(at[2]));
	}
}
