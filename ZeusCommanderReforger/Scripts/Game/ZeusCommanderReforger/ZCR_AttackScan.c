// Lab: -zcrAttackScan "x,z,radius,step" - the ground round one objective, for the attack planner (29 Oct night, Martin:
// "attacks should be planned in some smarter way, we have to read the maps ... where they have cover", "where it could
// hide if something happens - drone maybe?"; review note 449). For every land cell of a step-m grid within radius m of
// the objective: its height, how many of 9 defender eye points on the objective (8 on its edge 50 m out, 1.8 m up, and its
// centre 3 m up - a window, a roof) see a crouching soldier there (1.0 m up; solid things and foliage block), and whether something is overhead (a roof or
// a canopy within 15 m up). Written to $profile:zcr/attackscan.jsonl (lab/attackplan.py reads it), 2000 cells a frame:
//   {"x":..,"z":..,"y":..,"seen":0-9,"roof":0|1}
//   [ZCR][ATTACKSCAN] done cells= seen_any= roofed= ms=
// -zcrAttackScan all[,radius,step] (29 Oct evening, plans for the normal matches - Martin's go, review note 451): every base of
// the map in turn, each to $profile:zcr/attackscan/<x>_<z>.jsonl (the header also names the base).
class ZCR_AttackScan
{
	static const int PER_FRAME = 2000;
	protected static ref ZCR_AttackScan s_Scan;

	protected vector m_vObjective;
	protected float m_fRadius;
	protected float m_fStep;
	protected float m_fX;
	protected float m_fZ;
	protected ref array<vector> m_aEyes = {};
	protected ref TraceParam m_Trace;
	protected ref FileHandle m_File;
	protected int m_iCells;
	protected int m_iSeen;
	protected int m_iRoofed;
	protected int m_iStartedAt;
	protected string m_sName;
	protected string m_sPath = "$profile:zcr/attackscan.jsonl";
	protected ref array<vector> m_aQueue = {};
	protected ref array<string> m_aQueueNames = {};

	static void Start()
	{
		string spec;
		if (s_Scan || !Replication.IsServer() || !System.GetCLIParam("zcrAttackScan", spec) || spec.IsEmpty())
			return;
		array<string> p = {};
		spec.Split(",", p, true);
		if (p.IsEmpty() || (p[0] != "all" && p.Count() < 2))
			return;
		s_Scan = new ZCR_AttackScan();
		s_Scan.m_fRadius = 1000;
		s_Scan.m_fStep = 10;
		if (p[0] == "all")
		{
			if (p.Count() > 1)
				s_Scan.m_fRadius = Math.Max(200, p[1].ToFloat());
			if (p.Count() > 2)
				s_Scan.m_fStep = Math.Max(5, p[2].ToFloat());
			// The bases are registered a moment after the world is up.
			GetGame().GetCallqueue().CallLater(s_Scan.QueueBases, 8000, false);
			return;
		}
		s_Scan.m_vObjective = Vector(p[0].ToFloat(), 0, p[1].ToFloat());
		if (p.Count() > 2)
			s_Scan.m_fRadius = Math.Max(200, p[2].ToFloat());
		if (p.Count() > 3)
			s_Scan.m_fStep = Math.Max(5, p[3].ToFloat());
		GetGame().GetCallqueue().CallLater(s_Scan.Begin, 5000, false);
	}

	protected void QueueBases()
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return;
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || !base.GetOwner())
				continue;
			m_aQueue.Insert(base.GetOwner().GetOrigin());
			m_aQueueNames.Insert(ZCR_Strategist.BaseName(base));
		}
		Print(string.Format("[ZCR][ATTACKSCAN] all bases=%1 radius=%2 step=%3", m_aQueue.Count(), m_fRadius, m_fStep), LogLevel.NORMAL);
		FileIO.MakeDirectory("$profile:zcr");
		FileIO.MakeDirectory("$profile:zcr/attackscan");
		Next();
	}

	// The next base of an all-bases scan, else nothing.
	protected void Next()
	{
		if (m_aQueue.IsEmpty())
		{
			Print("[ZCR][ATTACKSCAN] all done", LogLevel.NORMAL);
			return;
		}
		m_vObjective = m_aQueue[0];
		m_sName = m_aQueueNames[0];
		m_aQueue.RemoveOrdered(0);
		m_aQueueNames.RemoveOrdered(0);
		m_sPath = string.Format("$profile:zcr/attackscan/%1_%2.jsonl", Math.Round(m_vObjective[0]), Math.Round(m_vObjective[2]));
		m_aEyes.Clear();
		m_iCells = 0;
		m_iSeen = 0;
		m_iRoofed = 0;
		Begin();
	}

	protected void Begin()
	{
		BaseWorld world = GetGame().GetWorld();
		m_vObjective[1] = world.GetSurfaceY(m_vObjective[0], m_vObjective[2]);
		vector centre = m_vObjective;
		centre[1] = world.GetSurfaceY(centre[0], centre[2]) + 3;
		m_aEyes.Insert(centre);
		for (int k; k < 8; k++)
		{
			float a = k * 45 * Math.DEG2RAD;
			vector eye = m_vObjective + Vector(Math.Sin(a) * 50, 0, Math.Cos(a) * 50);
			eye[1] = world.GetSurfaceY(eye[0], eye[2]) + 1.8;
			m_aEyes.Insert(eye);
		}
		m_Trace = new TraceParam();
		m_Trace.Flags = TraceFlags.ENTS | TraceFlags.WORLD;
		m_Trace.TargetLayers = EPhysicsLayerDefs.ViewGeometry | EPhysicsLayerDefs.Foliage;
		FileIO.MakeDirectory("$profile:zcr");
		m_File = FileIO.OpenFile(m_sPath, FileMode.WRITE);
		if (!m_File)
		{
			Print("[ZCR][ATTACKSCAN] cannot write " + m_sPath, LogLevel.WARNING);
			return;
		}
		m_File.WriteLine(string.Format("{\"objective\":[%1,%2,%3],\"radius\":%4,\"step\":%5,\"name\":\"%6\"}", m_vObjective[0], m_vObjective[1], m_vObjective[2], m_fRadius, m_fStep, m_sName));
		m_fX = m_vObjective[0] - m_fRadius;
		m_fZ = m_vObjective[2] - m_fRadius;
		m_iStartedAt = System.GetTickCount();
		GetGame().GetCallqueue().CallLater(Chunk, 10, false);
	}

	protected void Chunk()
	{
		BaseWorld world = GetGame().GetWorld();
		float sea = world.GetOceanBaseHeight();
		int done;
		while (done < PER_FRAME && m_fX <= m_vObjective[0] + m_fRadius)
		{
			float x = m_fX;
			float z = m_fZ;
			m_fZ += m_fStep;
			if (m_fZ > m_vObjective[2] + m_fRadius)
			{
				m_fZ = m_vObjective[2] - m_fRadius;
				m_fX += m_fStep;
			}
			if (vector.DistanceXZ(Vector(x, 0, z), m_vObjective) > m_fRadius)
				continue;
			float y = world.GetSurfaceY(x, z);
			if (y < sea + 0.5)
				continue;
			done++;
			vector body = Vector(x, y + 1.0, z);
			int seen;
			foreach (vector eye : m_aEyes)
			{
				m_Trace.Start = eye;
				m_Trace.End = body;
				if (world.TraceMove(m_Trace, null) >= 0.99)
					seen++;
			}
			m_Trace.Start = body;
			m_Trace.End = Vector(x, y + 16, z);
			int roof;
			if (world.TraceMove(m_Trace, null) < 1.0)
				roof = 1;
			m_iCells++;
			if (seen > 0)
				m_iSeen++;
			m_iRoofed += roof;
			m_File.WriteLine(string.Format("{\"x\":%1,\"z\":%2,\"y\":%3,\"seen\":%4,\"roof\":%5}", Math.Round(x), Math.Round(z), Math.Round(y * 10) / 10, seen, roof));
		}
		if (m_fX <= m_vObjective[0] + m_fRadius)
		{
			GetGame().GetCallqueue().CallLater(Chunk, 10, false);
			return;
		}
		m_File.Close();
		Print(string.Format("[ZCR][ATTACKSCAN] done cells=%1 seen_any=%2 roofed=%3 ms=%4 base=%5 file=%6", m_iCells, m_iSeen, m_iRoofed, System.GetTickCount() - m_iStartedAt, m_sName, m_sPath), LogLevel.NORMAL);
		if (m_sPath != "$profile:zcr/attackscan.jsonl")
			GetGame().GetCallqueue().CallLater(Next, 10, false);
	}
}
