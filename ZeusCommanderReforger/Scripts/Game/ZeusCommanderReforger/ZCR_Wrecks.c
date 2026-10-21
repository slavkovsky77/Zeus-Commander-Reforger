// Wrecks off the roads (Martin, 20 Oct 02:20: "they just crash into dead vehicles", "then they get
// stuck"; vehicle trips had 4-9 stuck/route-recovery events each, at 1x as much as at 3x). A vehicle
// destroyed is removed 60 s later (time to burn out and be seen), unless a living soldier is still in it.
// AI Conflict's own cleanup kept deferring (a player - the watching camera - counted as near).
// Logs [ZCR][WRECK] t= removed= at=. -zcrKeepWrecks turns it off.
class ZCR_Wrecks
{
	protected static ref ZCR_Wrecks s_Instance;
	protected ref array<IEntity> m_aWrecks = {};
	protected ref array<int> m_aAt = {};

	static void Add(IEntity vehicle)
	{
		if (!vehicle || !Replication.IsServer() || System.IsCLIParam("zcrKeepWrecks"))
			return;
		if (!s_Instance)
		{
			s_Instance = new ZCR_Wrecks();
			GetGame().GetCallqueue().CallLater(s_Instance.Tick, 5000, true);
		}
		s_Instance.m_aWrecks.Insert(vehicle);
		s_Instance.m_aAt.Insert(ZCR_LossLog.Seconds());
	}

	protected void Tick()
	{
		int now = ZCR_LossLog.Seconds();
		for (int i = m_aWrecks.Count() - 1; i >= 0; i--)
		{
			IEntity v = m_aWrecks[i];
			if (!v)
			{
				m_aWrecks.Remove(i);
				m_aAt.Remove(i);
				continue;
			}
			if (now - m_aAt[i] < 60 || Occupied(v))
				continue;
			vector at = v.GetOrigin();
			Print(string.Format("[ZCR][WRECK] t=%1 removed=%2 at=%3 %4", now, ZCR_LossLog.ShortName(v), Math.Round(at[0]), Math.Round(at[2])), LogLevel.NORMAL);
			m_aWrecks.Remove(i);
			m_aAt.Remove(i);
			ZCR_Trace.Ent("delete", v, "wreck");
			SCR_EntityHelper.DeleteEntityAndChildren(v);
		}
	}

	// A living soldier still aboard.
	static bool Occupied(IEntity v)
	{
		IEntity child = v.GetChildren();
		while (child)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(child);
			if (c && c.GetCharacterController() && c.GetCharacterController().GetLifeState() != ECharacterLifeState.DEAD)
				return true;
			child = child.GetSibling();
		}
		return false;
	}
}
