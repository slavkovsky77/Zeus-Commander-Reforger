// Navmesh probe (23 Oct night): does the watched game (a listen server, the camera somewhere) have the vehicle navmesh
// where its AI vehicles drive? In watched test-track runs the first car spawned 1.2 km from the camera never moved and
// its crew got out 11 s later - in every watched run, never headless. Lab only, inert without the switches:
//   -zcrNavProbe "x,z;x,z;..."  every 30 s: each point's vehicle-navmesh tile (loaded / requested / valid), and how many
//                               AI-driven vehicles stand on a tile that isn't loaded
//                               [ZCR][NAVTILE] t= at= loaded= requested= valid=  /  [ZCR][NAVCARS] t= driven= unloaded=
//   -zcrLoadTiles               also ask for every probe point's tile and the tiles along the lines between them (100 m apart)
class ZCR_NavProbe
{
	protected static ref ZCR_NavProbe s_Instance;
	protected ref array<vector> m_aPoints = {};
	protected int m_iNext = 5;

	static void Start()
	{
		string spec;
		if (s_Instance || !Replication.IsServer() || !System.GetCLIParam("zcrNavProbe", spec) || spec.IsEmpty())
			return;
		s_Instance = new ZCR_NavProbe();
		array<string> parts = {};
		spec.Split(";", parts, true);
		foreach (string p : parts)
		{
			array<string> xz = {};
			p.Split(",", xz, true);
			if (xz.Count() >= 2)
				s_Instance.m_aPoints.Insert(Vector(xz[0].ToFloat(), 0, xz[1].ToFloat()));
		}
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 1000, true);
	}

	protected static NavmeshWorldComponent Navmesh()
	{
		AIWorld world = GetGame().GetAIWorld();
		if (!world)
			return null;
		return world.GetNavmeshWorldComponent("BTRlike");
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		if (now < m_iNext)
			return;
		m_iNext = now + 30;
		NavmeshWorldComponent nav = Navmesh();
		if (!nav)
		{
			Print(string.Format("[ZCR][NAVTILE] t=%1 navmesh=none", now), LogLevel.NORMAL);
			return;
		}
		BaseWorld world = GetGame().GetWorld();
		bool load = System.IsCLIParam("zcrLoadTiles");
		for (int i = 0; i < m_aPoints.Count(); i++)
		{
			vector p = m_aPoints[i];
			p[1] = world.GetSurfaceY(p[0], p[2]);
			if (load)
			{
				nav.LoadTileIn(p);
				if (i + 1 < m_aPoints.Count())
				{
					vector q = m_aPoints[i + 1];
					float len = vector.DistanceXZ(p, q);
					for (float d = 100; d < len; d += 100)
					{
						vector r = p + (q - p) * (d / len);
						r[1] = world.GetSurfaceY(r[0], r[2]);
						nav.LoadTileIn(r);
					}
				}
			}
			Print(string.Format("[ZCR][NAVTILE] t=%1 at=%2,%3 loaded=%4 requested=%5 valid=%6", now, Math.Round(p[0]), Math.Round(p[2]),
				nav.IsTileLoaded(p), nav.IsTileRequested(p), nav.IsTileValid(p)), LogLevel.NORMAL);
		}
		array<IEntity> cars = {};
		ZCR_Driving.DrivenNow(cars);
		int unloaded;
		foreach (IEntity c : cars)
		{
			if (c && !nav.IsTileLoaded(c.GetOrigin()))
				unloaded++;
		}
		Print(string.Format("[ZCR][NAVCARS] t=%1 driven=%2 unloaded=%3", now, cars.Count(), unloaded), LogLevel.NORMAL);
	}
}
