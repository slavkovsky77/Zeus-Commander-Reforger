// -zcrCoverScan "step,radius" (lab, 23 Oct evening): what cover the ground offers, for the infantry sub-lab (Martin:
// "move to DCO - some infantry tests that I would like to watch"). For every land point of a step-m grid over the map:
// the buildings, trees and walls / fences / rocks / hedges within radius m. Points with any of it are logged:
//   [ZCR][COVERSCAN] x= z= buildings= trees= walls= h=
//   [ZCR][COVERSCAN] done points= logged=
class ZCR_CoverScan
{
	protected int m_iBuildings;
	protected int m_iTrees;
	protected int m_iWalls;

	static void Start()
	{
		string spec;
		if (!Replication.IsServer() || !System.GetCLIParam("zcrCoverScan", spec) || spec.IsEmpty())
			return;
		GetGame().GetCallqueue().CallLater(Scan, 5000, false, spec);
	}

	protected bool Add(IEntity e)
	{
		if (!e)
			return true;
		if (Building.Cast(e))
		{
			m_iBuildings++;
			return true;
		}
		if (BaseTree.Cast(e))
		{
			m_iTrees++;
			return true;
		}
		EntityPrefabData data = e.GetPrefabData();
		if (!data)
			return true;
		string name = data.GetPrefabName();
		name.ToLower();
		if (name.Contains("wall") || name.Contains("fence") || name.Contains("rock") || name.Contains("stone") || name.Contains("hedge")
			|| name.Contains("sandbag") || name.Contains("bush"))
			m_iWalls++;
		return true;
	}

	protected static void Scan(string spec)
	{
		array<string> p = {};
		spec.Split(",", p, true);
		float step = 100;
		float radius = 40;
		if (p.Count() > 0)
			step = Math.Max(25, p[0].ToFloat());
		if (p.Count() > 1)
			radius = Math.Clamp(p[1].ToFloat(), 10, 100);
		BaseWorld world = GetGame().GetWorld();
		vector mins, maxs;
		world.GetBoundBox(mins, maxs);
		ZCR_CoverScan counter = new ZCR_CoverScan();
		int points, logged;
		for (float x = mins[0] + step; x < maxs[0] - step; x += step)
		{
			for (float z = mins[2] + step; z < maxs[2] - step; z += step)
			{
				float y = world.GetSurfaceY(x, z);
				if (y < world.GetOceanBaseHeight() + 2)
					continue;
				points++;
				counter.m_iBuildings = 0;
				counter.m_iTrees = 0;
				counter.m_iWalls = 0;
				world.QueryEntitiesBySphere(Vector(x, y, z), radius, counter.Add, null, EQueryEntitiesFlags.ALL);
				if (counter.m_iBuildings + counter.m_iTrees + counter.m_iWalls == 0)
					continue;
				logged++;
				Print(string.Format("[ZCR][COVERSCAN] x=%1 z=%2 buildings=%3 trees=%4 walls=%5 h=%6", Math.Round(x), Math.Round(z), counter.m_iBuildings,
					counter.m_iTrees, counter.m_iWalls, Math.Round(y)), LogLevel.NORMAL);
			}
		}
		Print(string.Format("[ZCR][COVERSCAN] done points=%1 logged=%2 step=%3 radius=%4", points, logged, step, radius), LogLevel.NORMAL);
	}
}
