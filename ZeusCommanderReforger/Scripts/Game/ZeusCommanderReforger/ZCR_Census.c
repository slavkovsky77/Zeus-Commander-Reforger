// What piles up during a match (25 Oct - Martin: "fps still drops for some reason as time goes by"): the game's own FPS
// line showed its dynamic entities growing 1243 -> 1823 over 20 minutes while the AI count stayed ~225. Every CENSUS_S
// game seconds, every dynamic entity on the map counted by kind - soldiers alive and dead, vehicles intact and wrecked,
// waypoints, AI groups, and the rest by class - in one line:
//   [ZCR][CENSUS] t= total= alive= dead= veh= wrecks= waypoints= groups= ms= top=Class:n,...
// -zcrNoCensus off.
class ZCR_Census
{
	static const int CENSUS_S = 120;
	protected static bool s_bStarted;
	protected static ref map<string, int> s_mCount;
	protected static ref array<vector> s_aSample = {};
	protected static ref map<int, int> s_mLod = new map<int, int>();
	protected static ref set<AIWaypoint> s_mHeld = new set<AIWaypoint>();
	protected static ref array<vector> s_aOrphanAt = {};
	protected static int s_iOrphans;
	protected static int s_iAlive, s_iDead, s_iVeh, s_iWrecks, s_iWaypoints, s_iGroups, s_iTotal;
	protected static int s_iProj, s_iProjGround, s_iProjStill;
	protected static ref map<string, int> s_mFlying = new map<string, int>();   // rounds away from the origin: parent/instigator
	// Intact vehicles (27 Oct: 14 at the start of a 40-minute match, 52 at its end; the census count that follows the
	// frame rate most closely): crewed or empty, physics awake or asleep, the empty ones by prefab.
	protected static int s_iVehCrewed, s_iVehAwake, s_iVehEmptyAwake;
	protected static ref map<string, int> s_mVehEmpty = new map<string, int>();
	protected static ref map<string, int> s_mProjKind = new map<string, int>();
	protected static ref map<string, int> s_mProjCell = new map<string, int>();
	protected static ref array<string> s_aProjAt = {};

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || System.IsCLIParam("zcrNoCensus"))
			return;
		s_bStarted = true;
		GetGame().GetCallqueue().CallLater(Tick, CENSUS_S * 1000, true);
	}

	protected static bool Count(IEntity e)
	{
		if (!e || e.GetParent())
			return true;   // a soldier's gear, a vehicle's parts: counted with their root
		s_iTotal++;
		ChimeraCharacter c = ChimeraCharacter.Cast(e);
		if (c)
		{
			CharacterControllerComponent controller = c.GetCharacterController();
			if (controller && controller.IsDead())
				s_iDead++;
			else
			{
				s_iAlive++;
				// The soldier's AI level of detail (0 = full; the engine thins out far ones - unless told not to).
				AIControlComponent ai = AIControlComponent.Cast(c.FindComponent(AIControlComponent));
				if (ai && ai.GetAIAgent())
				{
					int lod = ai.GetAIAgent().GetLOD();
					s_mLod.Set(lod, s_mLod.Get(lod) + 1);
				}
			}
			return true;
		}
		if (Vehicle.Cast(e))
		{
			SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(e.FindComponent(SCR_DamageManagerComponent));
			if (damage && damage.GetState() == EDamageState.DESTROYED)
				s_iWrecks++;
			else
			{
				s_iVeh++;
				CountVehicle(e);
			}
			return true;
		}
		if (AIWaypoint.Cast(e))
		{
			s_iWaypoints++;
			string wp = "wp:" + Prefab(e);
			s_mCount.Set(wp, s_mCount.Get(wp) + 1);
			// A waypoint no group holds any more (25 Oct: Move waypoints grow ~10 a game minute): where, to find who left it.
			if (!s_mHeld.Contains(AIWaypoint.Cast(e)))
			{
				s_iOrphans++;
				if (s_aOrphanAt.Count() < 8)
					s_aOrphanAt.Insert(e.GetOrigin());
			}
			return true;
		}
		if (AIGroup.Cast(e))
		{
			s_iGroups++;
			return true;
		}
		// Generic entities by their prefab (the bulk: 1158 -> 1488 in 11 minutes of the first FPS test).
		string name = e.ClassName();
		if (name == "GenericEntity")
			name = Prefab(e);
		// Projectiles (27 Oct: 50 -> 733 alive at once between game minutes 20 and 33 of a 40-minute match, in every
		// longer run): by prefab, how many lie on the ground or stand still, the 100 m squares they pile up in, a few samples.
		if (name.Contains("Projectile"))
			CountProjectile(e);
		// Where the biggest growing kind sits (25 Oct: Inventory_Virtual_Entity 784 -> 839 in 2 minutes): a few positions.
		if (name == "Inventory_Virtual_Entity" && s_aSample.Count() < 6)
			s_aSample.Insert(e.GetOrigin());
		s_mCount.Set(name, s_mCount.Get(name) + 1);
		return true;
	}

	protected static void CountVehicle(IEntity e)
	{
		bool crewed;
		BaseCompartmentManagerComponent seatsOf = BaseCompartmentManagerComponent.Cast(e.FindComponent(BaseCompartmentManagerComponent));
		if (seatsOf)
		{
			array<BaseCompartmentSlot> seats = {};
			seatsOf.GetCompartments(seats);
			foreach (BaseCompartmentSlot seat : seats)
			{
				if (seat && seat.GetOccupant())
				{
					crewed = true;
					break;
				}
			}
		}
		Physics phys = e.GetPhysics();
		bool awake = phys && phys.IsActive();
		if (crewed)
			s_iVehCrewed++;
		if (awake)
			s_iVehAwake++;
		if (!crewed)
		{
			string kind = Prefab(e);
			s_mVehEmpty.Set(kind, s_mVehEmpty.Get(kind) + 1);
			if (awake)
				s_iVehEmptyAwake++;
		}
	}

	protected static void CountProjectile(IEntity e)
	{
		s_iProj++;
		string kind = Prefab(e);
		s_mProjKind.Set(kind, s_mProjKind.Get(kind) + 1);
		vector p = e.GetOrigin();
		float h = p[1] - GetGame().GetWorld().GetSurfaceY(p[0], p[2]);
		if (h < 2)
			s_iProjGround++;
		float speed = -1;
		Physics phys = e.GetPhysics();
		if (phys)
		{
			speed = phys.GetVelocity().Length();
			if (speed < 1)
				s_iProjStill++;
		}
		// The control for PROJWATCH (27 Oct: every round at the origin came from a parent projectile): the rounds anywhere
		// else, by whether they have a parent projectile and an instigator.
		if (Math.AbsFloat(p[0]) > 30 || Math.AbsFloat(p[2]) > 30)
		{
			BaseProjectileComponent pc = BaseProjectileComponent.Cast(e.FindComponent(BaseProjectileComponent));
			string fk = "no_component";
			if (pc)
			{
				fk = "parent=no";
				if (pc.GetParentProjectile())
					fk = "parent=yes";
				if (pc.GetInstigator())
					fk += "/inst=" + typename.EnumToString(InstigatorType, pc.GetInstigator().GetInstigatorType());
				else
					fk += "/inst=null";
			}
			s_mFlying.Set(fk, s_mFlying.Get(fk) + 1);
		}
		string cell = string.Format("%1,%2", Math.Floor(p[0] / 100) * 100 + 50, Math.Floor(p[2] / 100) * 100 + 50);
		s_mProjCell.Set(cell, s_mProjCell.Get(cell) + 1);
		if (s_aProjAt.Count() < 6)
			s_aProjAt.Insert(string.Format("%1:%2,%3,h%4,v%5", kind, Math.Round(p[0]), Math.Round(p[2]), Math.Round(h), Math.Round(speed)));
	}

	// The n largest entries of a count map, "key:n,..." (removes them from the map).
	protected static string Largest(map<string, int> counts, int n, string sep)
	{
		string res;
		for (int k; k < n && !counts.IsEmpty(); k++)
		{
			string best;
			int most = -1;
			foreach (string key, int c : counts)
			{
				if (c > most)
				{
					most = c;
					best = key;
				}
			}
			res += string.Format("%1:%2%3", best, most, sep);
			counts.Remove(best);
		}
		return res;
	}

	static string PrefabName(IEntity e)
	{
		return Prefab(e);
	}

	// "AIWaypoint_Move" from "{...}Prefabs/AI/Waypoints/AIWaypoint_Move.et"; "no_prefab" without one.
	protected static string Prefab(IEntity e)
	{
		if (!e.GetPrefabData())
			return "no_prefab";
		string full = e.GetPrefabData().GetPrefabName();
		int slash = full.LastIndexOf("/");
		if (slash >= 0)
			full = full.Substring(slash + 1, full.Length() - slash - 1);
		full.Replace(".et", "");
		if (full.IsEmpty())
			return "no_prefab";
		return full;
	}

	protected static void Tick()
	{
		int started = System.GetTickCount();
		s_mCount = new map<string, int>();
		s_aSample.Clear();
		s_mLod.Clear();
		s_aOrphanAt.Clear();
		s_iOrphans = 0;
		s_iProj = 0;
		s_iProjGround = 0;
		s_iProjStill = 0;
		s_mProjKind.Clear();
		s_mProjCell.Clear();
		s_aProjAt.Clear();
		s_mFlying.Clear();
		s_iVehCrewed = 0;
		s_iVehAwake = 0;
		s_iVehEmptyAwake = 0;
		s_mVehEmpty.Clear();
		// Every waypoint some group still has.
		s_mHeld.Clear();
		array<AIAgent> agents = {};
		if (GetGame().GetAIWorld())
			GetGame().GetAIWorld().GetAIAgents(agents);
		foreach (AIAgent a : agents)
		{
			AIGroup g = AIGroup.Cast(a);
			if (!g)
				continue;
			array<AIWaypoint> held = {};
			g.GetWaypoints(held);
			foreach (AIWaypoint hw : held)
				s_mHeld.Insert(hw);
		}
		s_iAlive = 0;
		s_iDead = 0;
		s_iVeh = 0;
		s_iWrecks = 0;
		s_iWaypoints = 0;
		s_iGroups = 0;
		s_iTotal = 0;
		// The whole map (Everon is 12.8 km; Arland 4 km).
		GetGame().GetWorld().QueryEntitiesByAABB(Vector(-2000, -1000, -2000), Vector(16000, 3000, 16000), Count, null, EQueryEntitiesFlags.DYNAMIC);
		// The rest, largest first (top 16).
		string top;
		for (int k; k < 16 && !s_mCount.IsEmpty(); k++)
		{
			string best;
			int most = -1;
			foreach (string name, int n : s_mCount)
			{
				if (n > most)
				{
					most = n;
					best = name;
				}
			}
			top += string.Format("%1:%2,", best, most);
			s_mCount.Remove(best);
		}
		Print(string.Format("[ZCR][CENSUS] t=%1 total=%2 alive=%3 dead=%4 veh=%5 wrecks=%6 waypoints=%7 groups=%8 ms=%9", ZCR_LossLog.Seconds(), s_iTotal,
			s_iAlive, s_iDead, s_iVeh, s_iWrecks, s_iWaypoints, s_iGroups, System.GetTickCount() - started) + " top=" + top, LogLevel.NORMAL);
		// (Largest() into a local first: concatenated straight into the Format result, the Format part was lost.)
		string emptyKinds = Largest(s_mVehEmpty, 8, ",");
		string vehLine = string.Format("[ZCR][CENSUS] t=%1 vehicles=%2 crewed=%3 awake=%4 empty_awake=%5 empty_kinds=", ZCR_LossLog.Seconds(), s_iVeh,
			s_iVehCrewed, s_iVehAwake, s_iVehEmptyAwake);
		Print(vehLine + emptyKinds, LogLevel.NORMAL);
		string lods;
		for (int l; l <= AIAgent.GetMaxLOD(); l++)
			lods += string.Format("%1:%2,", l, s_mLod.Get(l));
		Print(string.Format("[ZCR][CENSUS] t=%1 lod=%2 max_lod=%3", ZCR_LossLog.Seconds(), lods, AIAgent.GetMaxLOD()), LogLevel.NORMAL);
		string orphans;
		foreach (vector o : s_aOrphanAt)
			orphans += string.Format("%1,%2;", Math.Round(o[0]), Math.Round(o[2]));
		Print(string.Format("[ZCR][CENSUS] t=%1 orphan_waypoints=%2 at=%3", ZCR_LossLog.Seconds(), s_iOrphans, orphans), LogLevel.NORMAL);
		string at;
		foreach (vector v : s_aSample)
			at += string.Format("%1,%2,%3;", Math.Round(v[0]), Math.Round(v[1]), Math.Round(v[2]));
		if (!at.IsEmpty())
			Print(string.Format("[ZCR][CENSUS] t=%1 sample=Inventory_Virtual_Entity at=%2", ZCR_LossLog.Seconds(), at), LogLevel.NORMAL);
		if (s_iProj > 0)
		{
			string samples;
			foreach (string s : s_aProjAt)
				samples += s + ";";
			string kinds = Largest(s_mProjKind, 6, ",");
			string cells = Largest(s_mProjCell, 5, ";");
			string away = Largest(s_mFlying, 6, ",");
			string projLine = string.Format("[ZCR][CENSUS] t=%1 projectiles=%2 ground=%3 still=%4 kinds=%5 cells=%6 at=%7", ZCR_LossLog.Seconds(), s_iProj,
				s_iProjGround, s_iProjStill, kinds, cells, samples);
			Print(projLine + " away=" + away, LogLevel.NORMAL);
		}
	}
}
