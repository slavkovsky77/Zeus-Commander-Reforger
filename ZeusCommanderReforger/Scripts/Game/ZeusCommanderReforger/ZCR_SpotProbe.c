// -zcrProbeSpots x,z;x,z;... (lab only): what is at a map spot - every entity within 25 m (prefab or class,
// distance, height) and the terrain height around it, 20 s and again 120 s into the match. Written for the
// two places where AI vehicles catch fire on the main bases' exit roads (20 Oct: 191 of 230 crashes).
class ZCR_SpotProbe
{
	protected static int s_iDone;
	protected static ref array<string> s_aLines;

	static void Tick()
	{
		if (s_iDone >= 2 || !System.IsCLIParam("zcrProbeSpots"))
			return;
		int now = ZCR_LossLog.Seconds();
		if ((s_iDone == 0 && now < 20) || (s_iDone == 1 && now < 120))
			return;
		s_iDone++;
		string value;
		System.GetCLIParam("zcrProbeSpots", value);
		array<string> spots = {};
		value.Split(";", spots, true);
		BaseWorld world = GetGame().GetWorld();
		foreach (string spot : spots)
		{
			array<string> xz = {};
			spot.Split(",", xz, true);
			if (xz.Count() < 2)
				continue;
			vector at = Vector(xz[0].ToFloat(), 0, xz[1].ToFloat());
			at[1] = world.GetSurfaceY(at[0], at[2]);
			string heights;
			for (int dx = -20; dx <= 20; dx += 10)
			{
				for (int dz = -20; dz <= 20; dz += 10)
					heights += string.Format("%1,", Math.Round(world.GetSurfaceY(at[0] + dx, at[2] + dz)));
				heights += "|";
			}
			Print(string.Format("[ZCR][SPOT] t=%1 at=%2 %3 ground=%4 heights(x-20..+20 rows, z-20..+20)=%5 ocean=%6", now, Math.Round(at[0]), Math.Round(at[2]), Math.Round(at[1]), heights, world.GetOceanBaseHeight()), LogLevel.NORMAL);
			s_aLines = {};
			world.QueryEntitiesBySphere(at, 25, Collect, null, EQueryEntitiesFlags.ALL);
			foreach (string line : s_aLines)
				Print(string.Format("[ZCR][SPOT] t=%1 at=%2 %3 %4", now, Math.Round(at[0]), Math.Round(at[2]), line), LogLevel.NORMAL);
		}
	}

	protected static bool Collect(IEntity e)
	{
		if (!e || s_aLines.Count() > 80)
			return true;
		string name = e.ClassName();
		EntityPrefabData data = e.GetPrefabData();
		if (data && data.GetPrefabName())
			name = data.GetPrefabName();
		vector p = e.GetOrigin();
		s_aLines.Insert(string.Format("entity=%1 x=%2 y=%3 z=%4 parent=%5", name, Math.Round(p[0]), Math.Round(p[1] * 10) / 10, Math.Round(p[2]), e.GetParent() != null));
		return true;
	}
}
