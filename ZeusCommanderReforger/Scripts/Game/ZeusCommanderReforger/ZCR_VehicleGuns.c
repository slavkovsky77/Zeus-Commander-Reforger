// [ZCR][VEHGUNS] (22 Oct, Martin: "measure the use of guns and weapons of vehicles - that's important"): the shots fired
// from vehicle turrets (armour, armed rides) and from static guns (tripod MGs), by side, one line a side a minute with
// the match's totals so far:
//   [ZCR][VEHGUNS] t=600 side=US shots=412 gunners=3 vehicles=2 manned=4 static_shots=30 MACHINEGUN=380 CANNON=32
// empty= manned turrets with every gun at 0 rounds now, empty_s= turret-seconds spent so (all match): AI gunners fire
// their first magazine and never reload (AI Turret Reload Fix, Workshop 72DB162D129C40D9, says so; 22 Oct).
// Kills by turret gunners are tagged on [ZCR][LOSS] (turret=<vehicle>).
// Shots are read from the ammunition: each manned turret's weapons are checked every second, a drop in the loaded
// magazine is shots, a new or fuller magazine a reload. (The game's OnProjectileShot event reports no AI turret
// shots - 0 on the gunner, the turret and the vehicle in a 12-minute test with 9 targets engaged.)
class ZCR_VehicleGuns
{
	protected static ref ZCR_VehicleGuns s_Instance;
	protected static ref map<BaseWeaponComponent, int> s_mAmmo = new map<BaseWeaponComponent, int>();
	protected static ref map<BaseWeaponComponent, BaseMagazineComponent> s_mMagazine = new map<BaseWeaponComponent, BaseMagazineComponent>();
	protected static ref map<string, int> s_mShots = new map<string, int>();        // side -> shots from vehicles
	protected static ref map<string, int> s_mStatic = new map<string, int>();       // side -> shots from static guns
	protected static ref map<string, int> s_mByType = new map<string, int>();       // "side|type" -> shots
	protected static ref map<string, ref set<IEntity>> s_mGunners = new map<string, ref set<IEntity>>();   // who fired
	protected static ref map<string, ref set<IEntity>> s_mVehicles = new map<string, ref set<IEntity>>();  // from what
	protected static ref map<string, int> s_mManned = new map<string, int>();
	protected static ref map<string, int> s_mEmpty = new map<string, int>();        // side -> manned turrets empty now
	protected static ref map<string, int> s_mEmptySeconds = new map<string, int>(); // side -> turret-seconds empty
	protected static ref set<TurretControllerComponent> s_EmptyNow = new set<TurretControllerComponent>();
	// Turrets seen with rounds loaded: only those count as run dry (a BTR-70's commander turret never holds any).
	protected static ref set<TurretControllerComponent> s_HadAmmo = new set<TurretControllerComponent>();
	protected int m_iLogAt;

	static void Start()
	{
		if (s_Instance || !Replication.IsServer())
			return;
		s_Instance = new ZCR_VehicleGuns();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	static BaseCompartmentSlot TurretSeat(IEntity e)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(e);
		if (!c || !c.IsInVehicle())
			return null;
		CompartmentAccessComponent access = c.GetCompartmentAccessComponent();
		if (!access || !access.GetCompartment() || access.GetCompartment().GetType() != ECompartmentType.TURRET)
			return null;
		return access.GetCompartment();
	}

	// " turret=<vehicle>" for a kill by a gunner in a vehicle turret or a static gun, else "".
	static string Note(IEntity killer)
	{
		BaseCompartmentSlot seat = TurretSeat(killer);
		if (!seat)
			return "";
		return " turret=" + ZCR_LossLog.ShortName(seat.GetVehicle());
	}

	// A vehicle that drives (wheels or tracks), not a static gun on a tripod.
	protected static bool Drives(IEntity v)
	{
		return v && (v.FindComponent(VehicleWheeledSimulation) || v.FindComponent(VehicleTrackedSimulation));
	}

	protected void Tick()
	{
		s_mManned.Clear();
		s_mEmpty.Clear();
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		foreach (AIAgent agent : agents)
		{
			if (!agent)
				continue;
			IEntity gunner = agent.GetControlledEntity();
			BaseCompartmentSlot seat = TurretSeat(gunner);
			if (!seat)
				continue;
			TurretControllerComponent turret = TurretControllerComponent.Cast(seat.GetController());
			if (!turret || !turret.GetWeaponManager())
				continue;
			string side = ZCR_LossLog.SideOf(gunner);
			s_mManned.Set(side, s_mManned.Get(side) + 1);
			IEntity vehicle = seat.GetVehicle();
			array<BaseWeaponComponent> weapons = {};
			turret.GetWeaponManager().GetWeapons(weapons);
			int loaded;
			foreach (BaseWeaponComponent weapon : weapons)
			{
				if (!weapon)
					continue;
				BaseMagazineComponent magazine = weapon.GetCurrentMagazine();
				int ammo = -1;
				if (magazine)
					ammo = magazine.GetAmmoCount();
				else if (weapon.GetCurrentMuzzle())
					ammo = weapon.GetCurrentMuzzle().GetAmmoCount();
				if (ammo < 0)
					continue;
				if (ammo > 0)
					loaded++;
				int was;
				bool known = s_mAmmo.Find(weapon, was);
				bool sameMagazine = s_mMagazine.Get(weapon) == magazine;
				s_mAmmo.Set(weapon, ammo);
				s_mMagazine.Set(weapon, magazine);
				if (!known || !sameMagazine || ammo >= was)
					continue;
				Shot(side, gunner, vehicle, weapon, was - ammo);
			}
			if (loaded > 0)
				s_HadAmmo.Insert(turret);
			if (loaded == 0 && !weapons.IsEmpty() && s_HadAmmo.Contains(turret))
			{
				s_mEmpty.Set(side, s_mEmpty.Get(side) + 1);
				s_mEmptySeconds.Set(side, s_mEmptySeconds.Get(side) + 1);
				// [ZCR][VEHGUNS_EMPTY] once each time a manned gun runs dry: what it is and the rounds it could reload from.
				if (!s_EmptyNow.Contains(turret))
				{
					s_EmptyNow.Insert(turret);
					Print(string.Format("[ZCR][VEHGUNS_EMPTY] t=%1 side=%2 vehicle=%3 static=%4 weapon=%5 spare_mags=%6", ZCR_LossLog.Seconds(), side,
						ZCR_LossLog.ShortName(vehicle), !Drives(vehicle), ZCR_LossLog.ShortName(weapons[0].GetOwner()), SpareMagazines(turret)), LogLevel.NORMAL);
				}
			}
			else
				s_EmptyNow.RemoveItem(turret);
		}

		int now = ZCR_LossLog.Seconds();
		if (now - m_iLogAt < 60)
			return;
		m_iLogAt = now;
		array<string> sides = {"US", "USSR"};
		foreach (string side : sides)
		{
			string types;
			foreach (string key, int n : s_mByType)
			{
				if (key.StartsWith(side + "|"))
					types += string.Format(" %1=%2", key.Substring(side.Length() + 1, key.Length() - side.Length() - 1), n);
			}
			int gunners, vehicles;
			if (s_mGunners.Contains(side))
				gunners = s_mGunners.Get(side).Count();
			if (s_mVehicles.Contains(side))
				vehicles = s_mVehicles.Get(side).Count();
			Print(string.Format("[ZCR][VEHGUNS] t=%1 side=%2 shots=%3 gunners=%4 vehicles=%5 manned=%6 static_shots=%7 empty=%8 empty_s=%9", now, side, s_mShots.Get(side),
				gunners, vehicles, s_mManned.Get(side), s_mStatic.Get(side), s_mEmpty.Get(side), s_mEmptySeconds.Get(side)) + types, LogLevel.NORMAL);
		}
	}

	// Loaded magazines in the turret's own storage (what AI Turret Reload Fix reloads from).
	protected static int SpareMagazines(TurretControllerComponent turret)
	{
		InventoryStorageManagerComponent inv = turret.GetInventoryManager();
		if (!inv)
			return -1;
		array<IEntity> items = {};
		inv.GetItems(items);
		int n;
		foreach (IEntity item : items)
		{
			BaseMagazineComponent mag;
			if (item)
				mag = BaseMagazineComponent.Cast(item.FindComponent(BaseMagazineComponent));
			if (mag && mag.GetAmmoCount() > 0)
				n++;
		}
		return n;
	}

	protected static void Shot(string side, IEntity gunner, IEntity vehicle, BaseWeaponComponent weapon, int rounds)
	{
		if (!Drives(vehicle))
		{
			s_mStatic.Set(side, s_mStatic.Get(side) + rounds);
			return;
		}
		s_mShots.Set(side, s_mShots.Get(side) + rounds);
		string kind = typename.EnumToString(EWeaponType, weapon.GetWeaponType());
		kind.Replace("WT_", "");
		string key = side + "|" + kind;
		s_mByType.Set(key, s_mByType.Get(key) + rounds);
		if (!s_mGunners.Contains(side))
			s_mGunners.Set(side, new set<IEntity>());
		s_mGunners.Get(side).Insert(gunner);
		if (!s_mVehicles.Contains(side))
			s_mVehicles.Set(side, new set<IEntity>());
		s_mVehicles.Get(side).Insert(vehicle);
	}
}
