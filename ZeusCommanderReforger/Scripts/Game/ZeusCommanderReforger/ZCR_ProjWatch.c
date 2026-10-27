// Bullets piling up at the world origin (27 Oct, the first 40-minute watched matches: rifle and machine-gun rounds at
// x 0, z 0, 145 m up, never flying - 84 by game minute 11, 2847 by minute 40, the frame rate sliding as they grow).
// Every 2 game seconds the new ones there, grouped - one line per group:
//   [ZCR][PROJWATCH] t= new= total= shots= n= kind= shot= by= inst= parent= age_s= speed= y=
// The first version (68f8b6a) read the shooter from the round's own record: none, for all 10831 of six matches. So
// every soldier's shots are now recorded as they leave the muzzle (the game's OnProjectileShot; vehicle turrets don't
// raise it): shot=yes - a round he fired, by=who, age_s=how long before it turned up at the origin; shot=no - never
// fired by a soldier. inst= the round's instigator kind, parent= whether it came from another projectile (spall).
// -zcrNoProjWatch off.
class ZCR_ProjWatch
{
	static const float BOX_M = 30;
	static const int KEEP_MS = 30000;   // how long a shot is remembered (real time)
	protected static bool s_bStarted;
	protected static ref ZCR_ProjWatch s_Self;
	protected static ref set<IEntity> s_mSeen = new set<IEntity>();
	protected static ref array<IEntity> s_aFound = {};
	protected static ref set<EntityID> s_mHooked = new set<EntityID>();
	protected static ref map<EntityID, int> s_mShotAt = new map<EntityID, int>();
	protected static ref map<EntityID, string> s_mShotBy = new map<EntityID, string>();
	protected static int s_iShots, s_iShotsAtOrigin;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoProjWatch"))
			return;
		s_bStarted = true;
		s_Self = new ZCR_ProjWatch();
		GetGame().GetCallqueue().CallLater(Tick, 2000, true);
	}

	// Every soldier's shots, from the first tick he is seen.
	protected static void HookSoldiers()
	{
		AIWorld world = GetGame().GetAIWorld();
		if (!world)
			return;
		array<AIAgent> agents = {};
		world.GetAIAgents(agents);
		foreach (AIAgent a : agents)
		{
			if (!a)
				continue;
			IEntity man = a.GetControlledEntity();
			if (!ChimeraCharacter.Cast(man) || s_mHooked.Contains(man.GetID()))
				continue;
			EventHandlerManagerComponent events = EventHandlerManagerComponent.Cast(man.FindComponent(EventHandlerManagerComponent));
			if (!events)
				continue;
			s_Self.Hook(events);
			s_mHooked.Insert(man.GetID());
		}
	}

	protected void Hook(EventHandlerManagerComponent events)
	{
		events.RegisterScriptHandler("OnProjectileShot", this, OnShot, false);
	}

	protected void OnShot(int playerID, BaseWeaponComponent weapon, IEntity projectile)
	{
		if (!projectile)
			return;
		s_iShots++;
		vector at = projectile.GetOrigin();
		if (Math.AbsFloat(at[0]) < BOX_M && Math.AbsFloat(at[2]) < BOX_M)
			s_iShotsAtOrigin++;
		string by = "unknown";
		if (weapon && weapon.GetOwner())
		{
			IEntity man = weapon.GetOwner().GetRootParent();
			ChimeraCharacter c = ChimeraCharacter.Cast(man);
			if (c && c.IsInVehicle())
				by = ZCR_LossLog.ShortName(man) + "@vehicle";
			else if (man)
				by = ZCR_LossLog.ShortName(man);
		}
		s_mShotAt.Set(projectile.GetID(), System.GetTickCount());
		s_mShotBy.Set(projectile.GetID(), by);
	}

	protected static bool Collect(IEntity e)
	{
		if (e && !e.GetParent() && e.ClassName().Contains("Projectile"))
			s_aFound.Insert(e);
		return true;
	}

	protected static void Tick()
	{
		HookSoldiers();
		int now = System.GetTickCount();
		s_aFound.Clear();
		GetGame().GetWorld().QueryEntitiesByAABB(Vector(-BOX_M, -2000, -BOX_M), Vector(BOX_M, 4000, BOX_M), Collect, null, EQueryEntitiesFlags.DYNAMIC);
		set<IEntity> current = new set<IEntity>();
		map<string, int> groups = new map<string, int>();
		map<string, float> ageMin = new map<string, float>();
		map<string, float> ageMax = new map<string, float>();
		map<string, float> speedMax = new map<string, float>();
		map<string, float> yMin = new map<string, float>();
		map<string, float> yMax = new map<string, float>();
		int fresh;
		foreach (IEntity p : s_aFound)
		{
			current.Insert(p);
			if (s_mSeen.Contains(p))
				continue;
			fresh++;
			float age = -1;
			string key = Describe(p, now, age);
			float speed = -1;
			ProjectileMoveComponent move = ProjectileMoveComponent.Cast(p.FindComponent(ProjectileMoveComponent));
			if (move)
				speed = move.GetVelocity().Length();
			float y = p.GetOrigin()[1];
			if (!groups.Contains(key))
			{
				ageMin.Set(key, age);
				ageMax.Set(key, age);
				speedMax.Set(key, speed);
				yMin.Set(key, y);
				yMax.Set(key, y);
			}
			groups.Set(key, groups.Get(key) + 1);
			ageMin.Set(key, Math.Min(ageMin.Get(key), age));
			ageMax.Set(key, Math.Max(ageMax.Get(key), age));
			speedMax.Set(key, Math.Max(speedMax.Get(key), speed));
			yMin.Set(key, Math.Min(yMin.Get(key), y));
			yMax.Set(key, Math.Max(yMax.Get(key), y));
		}
		s_mSeen = current;
		int shots = s_iShots;
		int shotsAtOrigin = s_iShotsAtOrigin;
		s_iShots = 0;
		s_iShotsAtOrigin = 0;
		Forget(now);
		if (fresh == 0)
			return;
		int t = ZCR_LossLog.Seconds();
		foreach (string key, int n : groups)
			Print(string.Format("[ZCR][PROJWATCH] t=%1 new=%2 total=%3 shots=%4 at_origin=%5 n=%6 %7", t, fresh, s_aFound.Count(), shots, shotsAtOrigin,
				n, key) + string.Format(" age_s=%1..%2 speed=%3 y=%4..%5", ageMin.Get(key).ToString(-1, 1), ageMax.Get(key).ToString(-1, 1),
				Math.Round(speedMax.Get(key)), yMin.Get(key).ToString(-1, 2), yMax.Get(key).ToString(-1, 2)), LogLevel.NORMAL);
	}

	// Shots older than KEEP_MS dropped.
	protected static void Forget(int now)
	{
		array<EntityID> old = {};
		foreach (EntityID id, int at : s_mShotAt)
		{
			if (now - at > KEEP_MS)
				old.Insert(id);
		}
		foreach (EntityID id : old)
		{
			s_mShotAt.Remove(id);
			s_mShotBy.Remove(id);
		}
	}

	// "kind= shot= by= inst= parent=" for one projectile; age = seconds since it was fired (-1 if not seen fired).
	protected static string Describe(IEntity p, int now, out float age)
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
		age = -1;
		string shot = "no";
		string by = "-";
		EntityID id = p.GetID();
		if (s_mShotAt.Contains(id))
		{
			shot = "yes";
			by = s_mShotBy.Get(id);
			age = (now - s_mShotAt.Get(id)) / 1000.0;
		}
		string inst = "none";
		string parent = "no";
		BaseProjectileComponent pc = BaseProjectileComponent.Cast(p.FindComponent(BaseProjectileComponent));
		if (pc)
		{
			if (pc.GetInstigator())
				inst = typename.EnumToString(InstigatorType, pc.GetInstigator().GetInstigatorType());
			if (pc.GetParentProjectile())
				parent = "yes";
		}
		return string.Format("kind=%1 shot=%2 by=%3 inst=%4 parent=%5", kind, shot, by, inst, parent);
	}
}
