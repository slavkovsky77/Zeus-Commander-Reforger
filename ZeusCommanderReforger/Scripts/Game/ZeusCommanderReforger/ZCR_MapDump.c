// Lab: -zcrMapDump - read the map once (24 Oct night, plan page M1 https://claude.ai/artifact/EAVqib8JhtDtkVxGB3KKSV;
// Martin: "supply lines should be planned up front... trucks follow precomputed routes", review note 394). Writes into
// $profile:zcr/ (lab/mapdump.py copies them to lab/maps/<map>/):
//   map_roads.jsonl    every road: {"w": width, "p": [[x, z], ...]}
//   map_objects.jsonl  every standing object but trees and plants: {"n": prefab, "c": class, "x", "z", "yaw",
//                      "sx", "sz", "h"} - walls, fences, buildings, props, rocks (size from its bounds, metres)
//   map_trees.json     trees and bushes per 25 m cell: {"cell": 25, "trees": {"ix,iz": n}, "bushes": {...}}
//   map_meta.json      the world, its bounds, the counts
// The world is read in 256 m squares, 5 s after the start; objects crossing squares are kept once.
//   [ZCR][MAPDUMP] roads= objects= trees= bushes= ms=
class ZCR_MapDump
{
	static const float CHUNK = 256;
	static const float CELL = 25;
	protected static ref array<IEntity> s_aFound = {};

	static void Start()
	{
		if (!Replication.IsServer() || !System.IsCLIParam("zcrMapDump"))
			return;
		GetGame().GetCallqueue().CallLater(Run, 5000, false);
	}

	protected static bool Add(IEntity e)
	{
		if (e)
			s_aFound.Insert(e);
		return true;
	}

	protected static string N(float v)
	{
		return (Math.Round(v * 10) / 10).ToString();
	}

	protected static void Run()
	{
		int started = System.GetTickCount();
		BaseWorld world = GetGame().GetWorld();
		vector wmin, wmax;
		world.GetBoundBox(wmin, wmax);
		FileIO.MakeDirectory("$profile:zcr");

		// Roads.
		int roadCount;
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		FileHandle roadsFile = FileIO.OpenFile("$profile:zcr/map_roads.jsonl", FileMode.WRITE);
		if (aiWorld && aiWorld.GetRoadNetworkManager() && roadsFile)
		{
			map<string, bool> seen = new map<string, bool>();
			for (float x = wmin[0]; x < wmax[0]; x += CHUNK)
			{
				for (float z = wmin[2]; z < wmax[2]; z += CHUNK)
				{
					array<BaseRoad> roads = {};
					aiWorld.GetRoadNetworkManager().GetRoadsInAABB(Vector(x, -500, z), Vector(x + CHUNK, 2000, z + CHUNK), roads);
					foreach (BaseRoad road : roads)
					{
						if (!road)
							continue;
						array<vector> points = {};
						road.GetPoints(points);
						if (points.IsEmpty())
							continue;
						string key = string.Format("%1_%2_%3_%4", Math.Round(points[0][0] * 10), Math.Round(points[0][2] * 10), points.Count(), Math.Round(road.GetWidth() * 10));
						if (seen.Contains(key))
							continue;
						seen.Set(key, true);
						string line = "{\"w\":" + N(road.GetWidth()) + ",\"p\":[";
						foreach (int i, vector p : points)
						{
							if (i > 0)
								line += ",";
							line += "[" + N(p[0]) + "," + N(p[2]) + "]";
						}
						roadsFile.WriteLine(line + "]}");
						roadCount++;
					}
				}
			}
		}
		if (roadsFile)
			roadsFile.Close();

		// Objects, trees and bushes.
		map<IEntity, bool> done = new map<IEntity, bool>();
		map<string, int> trees = new map<string, int>();
		map<string, int> bushes = new map<string, int>();
		int objectCount, treeCount, bushCount;
		FileHandle objectsFile = FileIO.OpenFile("$profile:zcr/map_objects.jsonl", FileMode.WRITE);
		for (float x = wmin[0]; x < wmax[0]; x += CHUNK)
		{
			for (float z = wmin[2]; z < wmax[2]; z += CHUNK)
			{
				s_aFound.Clear();
				world.QueryEntitiesByAABB(Vector(x, -500, z), Vector(x + CHUNK, 2000, z + CHUNK), Add, null, EQueryEntitiesFlags.STATIC);
				foreach (IEntity e : s_aFound)
				{
					if (!e || e.GetRootParent() != e || done.Contains(e) || ChimeraCharacter.Cast(e) || Vehicle.Cast(e))
						continue;
					done.Set(e, true);
					vector o = e.GetOrigin();
					if (o[0] < x || o[0] >= x + CHUNK || o[2] < z || o[2] >= z + CHUNK)
						continue;                  // its own square writes it
					string prefab = "";
					if (e.GetPrefabData())
						prefab = FilePath.StripPath(e.GetPrefabData().GetPrefabName());
					if (BaseTree.Cast(e))
					{
						string cell = string.Format("%1,%2", Math.Floor(o[0] / CELL), Math.Floor(o[2] / CELL));
						if (prefab.StartsWith("t_"))
						{
							trees.Set(cell, trees.Get(cell) + 1);
							treeCount++;
						}
						else
						{
							bushes.Set(cell, bushes.Get(cell) + 1);
							bushCount++;
						}
						continue;
					}
					if (prefab.IsEmpty() || !objectsFile)
						continue;
					vector mins, maxs;
					e.GetBounds(mins, maxs);
					vector ypr = e.GetYawPitchRoll();
					objectsFile.WriteLine(string.Format("{\"n\":\"%1\",\"c\":\"%2\",\"x\":%3,\"z\":%4,\"yaw\":%5,\"sx\":%6,\"sz\":%7,\"h\":%8}",
						prefab, e.ClassName(), N(o[0]), N(o[2]), Math.Round(ypr[0]), N(maxs[0] - mins[0]), N(maxs[2] - mins[2]), N(maxs[1] - mins[1])));
					objectCount++;
				}
			}
		}
		if (objectsFile)
			objectsFile.Close();

		FileHandle treesFile = FileIO.OpenFile("$profile:zcr/map_trees.json", FileMode.WRITE);
		if (treesFile)
		{
			treesFile.Write(string.Format("{\"cell\":%1,\"trees\":{", CELL));
			int k;
			foreach (string cell, int n : trees)
			{
				if (k++ > 0)
					treesFile.Write(",");
				treesFile.Write("\"" + cell + "\":" + n.ToString());
			}
			treesFile.Write("},\"bushes\":{");
			k = 0;
			foreach (string cell, int n : bushes)
			{
				if (k++ > 0)
					treesFile.Write(",");
				treesFile.Write("\"" + cell + "\":" + n.ToString());
			}
			treesFile.Write("}}");
			treesFile.Close();
		}

		int ms = System.GetTickCount() - started;
		FileHandle metaFile = FileIO.OpenFile("$profile:zcr/map_meta.json", FileMode.WRITE);
		if (metaFile)
		{
			metaFile.Write(string.Format("{\"world\":\"%1\",\"min\":[%2,%3],\"max\":[%4,%5],\"roads\":%6,\"objects\":%7,\"trees\":%8,\"bushes\":%9",
				GetGame().GetWorldFile(), N(wmin[0]), N(wmin[2]), N(wmax[0]), N(wmax[2]), roadCount, objectCount, treeCount, bushCount) + string.Format(",\"ms\":%1}", ms));
			metaFile.Close();
		}
		Print(string.Format("[ZCR][MAPDUMP] roads=%1 objects=%2 trees=%3 bushes=%4 ms=%5", roadCount, objectCount, treeCount, bushCount, ms), LogLevel.NORMAL);
	}
}
