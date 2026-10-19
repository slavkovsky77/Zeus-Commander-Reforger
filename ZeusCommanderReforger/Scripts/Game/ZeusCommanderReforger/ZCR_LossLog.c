// Every soldier and vehicle lost, one log line each, for the lab (lab/metrics.py):
//   [ZCR][LOSS] t=312 victim=Character_US_Rifleman side=US kind=man killer_side=USSR
//               killer_kind=vehicle relation=KILLED_BY_ENEMY_AI distance=240 x=4512 z=7120
// t is seconds of game time. Registered once by the first strategist (server only).
class ZCR_LossLog
{
	protected static ref ZCR_LossLog s_Instance;
	// The losses of the last minutes, for the camera director (server): where, when, whose.
	static ref array<vector> s_aRecentPos = {};
	static ref array<int> s_aRecentAt = {};
	static ref array<string> s_aRecentSide = {};

	static void Register()
	{
		if (s_Instance || !Replication.IsServer())
			return;
		SCR_BaseGameMode gameMode = SCR_BaseGameMode.Cast(GetGame().GetGameMode());
		if (!gameMode)
			return;
		s_Instance = new ZCR_LossLog();
		gameMode.GetOnControllableDestroyed().Insert(s_Instance.OnDestroyed);
		Print("[ZCR][LOSS_LOG] registered", LogLevel.NORMAL);
	}

	static int Seconds()
	{
		BaseWorld world = GetGame().GetWorld();
		if (!world)
			return 0;
		return Math.Round(world.GetWorldTime() / 1000);
	}

	static string SideOf(IEntity entity)
	{
		if (!entity)
			return "";
		FactionAffiliationComponent affiliation = FactionAffiliationComponent.Cast(entity.FindComponent(FactionAffiliationComponent));
		if (!affiliation || !affiliation.GetAffiliatedFaction())
			return "";
		return affiliation.GetAffiliatedFaction().GetFactionKey();
	}

	static string KindOf(IEntity entity)
	{
		if (!entity)
			return "none";
		if (ChimeraCharacter.Cast(entity))
			return "man";
		if (Vehicle.Cast(entity))
			return "vehicle";
		return "other";
	}

	// The prefab's file name without folders and extension: "Character_US_Rifleman".
	// For captions: "squad leader", "machine gunner"... from the prefab name; vehicles keep theirs.
	static string Role(IEntity entity)
	{
		string name = ShortName(entity);
		if (!ChimeraCharacter.Cast(entity))
			return name;
		array<string> keys = {"_SL", "_TL", "_MG", "_AMG", "_AR", "_GL", "_LAT", "_AT", "_Medic", "_RTO", "_Sniper", "_Marksman", "_Engineer", "_Officer", "_Crew", "_Rifleman", "_Partisan"};
		array<string> roles = {"squad leader", "team leader", "machine gunner", "assistant gunner", "autorifleman", "grenadier", "AT rifleman", "AT specialist", "medic", "radio operator", "sniper", "marksman", "engineer", "officer", "crewman", "rifleman", "partisan"};
		for (int i = 0; i < keys.Count(); i++)
		{
			if (name.Contains(keys[i]))
				return roles[i];
		}
		return "soldier";
	}

	static string ShortName(IEntity entity)
	{
		if (!entity || !entity.GetPrefabData())
			return "?";
		string name = entity.GetPrefabData().GetPrefabName();
		int slash = name.LastIndexOf("/");
		if (slash >= 0)
			name = name.Substring(slash + 1, name.Length() - slash - 1);
		int dot = name.LastIndexOf(".");
		if (dot > 0)
			name = name.Substring(0, dot);
		return name;
	}

	void OnDestroyed(notnull SCR_InstigatorContextData data)
	{
		IEntity victim = data.GetVictimEntity();
		if (!victim)
			return;
		IEntity killer = data.GetKillerEntity();
		vector at = victim.GetOrigin();
		int distance = -1;
		if (killer)
			distance = Math.Round(vector.Distance(at, killer.GetOrigin()));
		if (ChimeraCharacter.Cast(victim) || Vehicle.Cast(victim))
		{
			s_aRecentPos.Insert(at);
			s_aRecentAt.Insert(Seconds());
			s_aRecentSide.Insert(SideOf(victim));
			if (s_aRecentPos.Count() > 400)
			{
				s_aRecentPos.RemoveOrdered(0);
				s_aRecentAt.RemoveOrdered(0);
				s_aRecentSide.RemoveOrdered(0);
			}
		}
		string killerName = "none";
		if (killer)
			killerName = ShortName(killer);
		Print(string.Format("[ZCR][LOSS] t=%1 victim=%2 side=%3 kind=%4 killer_side=%5 killer_kind=%6 relation=%7 distance=%8 x=%9",
			Seconds(), ShortName(victim), SideOf(victim), KindOf(victim), SideOf(killer), KindOf(killer),
			typename.EnumToString(SCR_ECharacterDeathStatusRelations, data.GetVictimKillerRelation()), distance,
			string.Format("%1 z=%2 killer=%3%4", Math.Round(at[0]), Math.Round(at[2]), killerName, ZCR_Sampler.DeathState(victim, killer))), LogLevel.NORMAL);
	}
}
