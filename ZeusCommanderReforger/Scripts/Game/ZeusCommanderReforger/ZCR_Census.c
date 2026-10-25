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
	protected static int s_iAlive, s_iDead, s_iVeh, s_iWrecks, s_iWaypoints, s_iGroups, s_iTotal;

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
				s_iAlive++;
			return true;
		}
		if (Vehicle.Cast(e))
		{
			SCR_DamageManagerComponent damage = SCR_DamageManagerComponent.Cast(e.FindComponent(SCR_DamageManagerComponent));
			if (damage && damage.GetState() == EDamageState.DESTROYED)
				s_iWrecks++;
			else
				s_iVeh++;
			return true;
		}
		if (AIWaypoint.Cast(e))
		{
			s_iWaypoints++;
			return true;
		}
		if (AIGroup.Cast(e))
		{
			s_iGroups++;
			return true;
		}
		string name = e.ClassName();
		s_mCount.Set(name, s_mCount.Get(name) + 1);
		return true;
	}

	protected static void Tick()
	{
		int started = System.GetTickCount();
		s_mCount = new map<string, int>();
		s_iAlive = 0;
		s_iDead = 0;
		s_iVeh = 0;
		s_iWrecks = 0;
		s_iWaypoints = 0;
		s_iGroups = 0;
		s_iTotal = 0;
		// The whole map (Everon is 12.8 km; Arland 4 km).
		GetGame().GetWorld().QueryEntitiesByAABB(Vector(-2000, -1000, -2000), Vector(16000, 3000, 16000), Count, null, EQueryEntitiesFlags.DYNAMIC);
		// The rest, largest first (top 10).
		string top;
		for (int k; k < 10 && !s_mCount.IsEmpty(); k++)
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
	}
}
