// Bullets piling up at the world origin (27 Oct, the first 40-minute watched matches: rifle and machine-gun rounds at
// x 0, z 0, 145 m up, never flying - 84 by game minute 11, 2847 by minute 40, the frame rate sliding as they grow).
// Every 2 game seconds the new ones there, grouped - one line per group:
//   [ZCR][PROJWATCH] t= new= total= shots= n= kind= shot= by= inst= parent= age_s= speed= y=
// The first version (68f8b6a) read the shooter from the round's own record: none, for all 10831 of six matches. So
// every soldier's shots are now recorded as they leave the muzzle (the game's OnProjectileShot; vehicle turrets don't
// raise it): shot=yes - a round he fired, by=who, age_s=how long before it turned up at the origin; shot=no - never
// fired by a soldier. inst= the round's instigator kind, parent= whether it came from another projectile (spall).
// Match 10 (4b4100e): all 113 had a parent projectile, and no shot was recorded (immediate handlers never ran). So
// now the parent: pkind= its prefab, pat= origin (within BOX_M of it) / away / gone, pby= who fired it; the shot hook
// delayed as the fork's (hooked= soldiers). The census counts the same for rounds in flight elsewhere (the control).
// Match 11 (e875423): the "parent" is the round itself; every one sits at exactly 0,0,0, speed 0, no instigator - made
// and never launched (the game's own ballistics, not a script of ours or the mods'). Do they cost frames, and can they
// go? -zcrProjSweepAt <game s>: all of them deleted once at that time (FPS before/after in the same match);
// -zcrProjSweep: every tick, the ones still there from the previous tick. One line per sweep:
//   [ZCR][PROJSWEEP] t= mode= deleted= mask= flags=
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
	protected static int s_iSweepAt = -1;
	protected static bool s_bSweepEvery, s_bSwept;

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoProjWatch"))
			return;
		s_bStarted = true;
		s_Self = new ZCR_ProjWatch();
		string value;
		if (System.GetCLIParam("zcrProjSweepAt", value) && !value.IsEmpty())
			s_iSweepAt = value.ToInt();
		s_bSweepEvery = System.IsCLIParam("zcrProjSweep");
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
		events.RegisterScriptHandler("OnProjectileShot", this, OnShot, true);
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
		Sweep(current);
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
			Print(string.Format("[ZCR][PROJWATCH] t=%1 new=%2 total=%3 shots=%4 at_origin=%5 hooked=%6 n=%7 %8", t, fresh, s_aFound.Count(), shots,
				shotsAtOrigin, s_mHooked.Count(), n, key) + string.Format(" age_s=%1..%2 speed=%3 y=%4..%5", ageMin.Get(key).ToString(-1, 1), ageMax.Get(key).ToString(-1, 1),
				Math.Round(speedMax.Get(key)), yMin.Get(key).ToString(-1, 2), yMax.Get(key).ToString(-1, 2)), LogLevel.NORMAL);
	}

	// The rounds at the origin deleted: all once at -zcrProjSweepAt, or with -zcrProjSweep the ones there since the last
	// tick (a round in flight passes through the box in a fraction of a second; these never move).
	protected static void Sweep(set<IEntity> current)
	{
		string mode;
		int t = ZCR_LossLog.Seconds();
		if (s_iSweepAt >= 0 && !s_bSwept && t >= s_iSweepAt)
		{
			mode = "once";
			s_bSwept = true;
		}
		else if (s_bSweepEvery)
			mode = "every";
		else
			return;
		array<IEntity> doomed = {};
		foreach (IEntity p : s_aFound)
		{
			if (!p || p.IsDeleted() || (mode == "every" && !s_mSeen.Contains(p)))
				continue;
			vector at = p.GetOrigin();
			if (at.Length() > 0.01)
				continue;   // only the ones at exactly 0,0,0
			ProjectileMoveComponent move = ProjectileMoveComponent.Cast(p.FindComponent(ProjectileMoveComponent));
			if (move && move.GetVelocity().Length() > 0.01)
				continue;
			doomed.Insert(p);
		}
		if (doomed.IsEmpty())
			return;
		string mask = string.Format("%1", doomed[0].GetEventMask());
		string flags = string.Format("%1", doomed[0].GetFlags());
		foreach (IEntity p : doomed)
		{
			current.RemoveItem(p);
			SCR_EntityHelper.DeleteEntityAndChildren(p);
		}
		Print(string.Format("[ZCR][PROJSWEEP] t=%1 mode=%2 deleted=%3 mask=%4 flags=%5", t, mode, doomed.Count(), mask, flags), LogLevel.NORMAL);
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
		string pkind = "-";
		string pat = "-";
		string pby = "-";
		BaseProjectileComponent pc = BaseProjectileComponent.Cast(p.FindComponent(BaseProjectileComponent));
		if (pc)
		{
			if (pc.GetInstigator())
				inst = typename.EnumToString(InstigatorType, pc.GetInstigator().GetInstigatorType());
			IEntity pp = pc.GetParentProjectile();
			if (pp)
			{
				parent = "yes";
				if (pp == p)
					parent = "self";
				pkind = ZCR_Census.PrefabName(pp);
				vector at = pp.GetOrigin();
				pat = "away";
				if (pp.IsDeleted())
					pat = "gone";
				else if (Math.AbsFloat(at[0]) < BOX_M && Math.AbsFloat(at[2]) < BOX_M)
					pat = "origin";
				BaseProjectileComponent ppc = BaseProjectileComponent.Cast(pp.FindComponent(BaseProjectileComponent));
				if (ppc && ppc.GetInstigator() && ppc.GetInstigator().GetInstigatorEntity())
					pby = ZCR_LossLog.ShortName(ppc.GetInstigator().GetInstigatorEntity());
				else if (ppc && ppc.GetInstigator())
					pby = typename.EnumToString(InstigatorType, ppc.GetInstigator().GetInstigatorType());
			}
		}
		return string.Format("kind=%1 shot=%2 by=%3 inst=%4 parent=%5 pkind=%6 pat=%7 pby=%8", kind, shot, by, inst, parent, pkind, pat, pby);
	}
}
