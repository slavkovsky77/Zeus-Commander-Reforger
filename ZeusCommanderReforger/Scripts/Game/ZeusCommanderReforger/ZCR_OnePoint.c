// The one-point sub-lab (Martin, 28 Oct evening, after an assault test full of rides that went wrong: "a sublab where
// there will be only main base and one point they will fight for ... just one point!"). -zcrOnePoint <base name,
// underscores for spaces>: the two main bases and that base are the whole war. With -zcrNoFIA the point stays neutral
// (FIA's, without soldiers - the fork spawns no FIA garrison then) while the other bases are dealt to the sides as usual
// (they still give vehicles and supplies); every base but the point and a team's own main base is off every team's list.
class ZCR_OnePoint
{
	static string Name()
	{
		string v;
		if (!System.GetCLIParam("zcrOnePoint", v) || v.IsEmpty())
			return string.Empty;
		v.Replace("_", " ");
		return v;
	}

	static bool Is(SCR_CampaignMilitaryBaseComponent base)
	{
		string n = Name();
		return !n.IsEmpty() && base && ZCR_Strategist.BaseName(base) == n;
	}

	// The point itself (null outside the sub-lab).
	static SCR_CampaignMilitaryBaseComponent Base()
	{
		if (Name().IsEmpty())
			return null;
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return null;
		array<SCR_MilitaryBaseComponent> all = {};
		system.GetBases(all);
		foreach (SCR_MilitaryBaseComponent b : all)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (Is(base) && base.GetOwner())
				return base;
		}
		return null;
	}

	// Off the list: every base but the point and the team's own main base.
	static void Filter(SCR_CampaignFaction faction, array<ref AICF_AdaptiveCandidate> candidates)
	{
		if (Name().IsEmpty() || !faction || !candidates)
			return;
		foreach (AICF_AdaptiveCandidate c : candidates)
		{
			if (c && !Is(c.m_Base) && !(c.m_Base && c.m_Base == faction.GetMainBase()))
				c.m_bAvailable = false;
		}
	}
}

// The game counts a base as a target only inside the side's radio network; with every other base neutral the point
// (Beauregard: linked only to Signal Hill) is outside both (29 Oct 00:48: both plans fell back, both sides stayed home).
// In the one-point sub-lab the point is a target for both sides whatever their radio reaches.
modded class SCR_CampaignMilitaryBaseComponent
{
	override bool IsValidTarget(notnull SCR_CampaignFaction faction)
	{
		if (ZCR_OnePoint.Is(this) && GetFaction() != faction)
			return true;
		return super.IsValidTarget(faction);
	}

	// The point changes hands only by ZCR_PointSeize, the same rule for both sides: the game's own seizing still worked for
	// the side whose radio network reaches the point (2 Nov 19:08: the harbour side took Farm by the game's rule while
	// ours had both sides inside) - blocked there and logged.
	override void SetFaction(SCR_CampaignFaction faction)
	{
		if (ZCR_PointSeize.Guards(this) && faction != GetFaction())
		{
			string to = "none";
			if (faction)
				to = faction.GetFactionKey();
			Print(string.Format("[ZCR][SEIZE] t=%1 base=%2 event=game_capture_blocked to=%3", ZCR_LossLog.Seconds(), ZCR_Strategist.BaseName(this), to),
				LogLevel.NORMAL);
			return;
		}
		super.SetFaction(faction);
	}
}

// The point is taken by being there (2 Nov, note 513 - Martin: "there must be caputring bug", "fix so it can be captured,
// that whole test should be based on that like what happens if they battle over one place"). The game seizes a base only
// inside the side's radio network (the override above makes the point a target for both, not seizable): the side at the
// south HQ has no network at Farm and in ~30 Farm battles never took it, with up to 21 soldiers inside. In the one-point
// sub-lab the point is seized alike for both sides: one side's living soldiers within the base's radius (at most POINT_M)
// and none of the other's - SEIZE_S game seconds there and it is theirs; both sides there: contested, the clock holds;
// nobody there, or only the owner: it runs back. [ZCR][SEIZE] on each change and every 20 s while anyone is there; the
// owner change itself is logged by the director ([ZCR][CAPTURE]). -zcrNoPointSeize: the game's own seizing only.
class ZCR_PointSeize
{
	static const float POINT_M = 60;      // the core of the base (120 m: both sides were always somewhere inside - contested all match)
	static const float SEIZE_S = 60;
	protected static bool s_bStarted;
	protected static bool s_bSetting;   // our own owner change in progress
	protected static ref ZCR_PointSeize s_Instance;
	protected string m_sSide;
	protected float m_fProgress;
	protected int m_iLast = -1;
	protected int m_iLogAt;
	protected string m_sLastState;

	// The game's own capture of the point is blocked while this rule runs (not our own change, not the setup's).
	static bool Guards(SCR_CampaignMilitaryBaseComponent base)
	{
		return s_bStarted && !s_bSetting && ZCR_OnePoint.Is(base);
	}

	static void Start()
	{
		if (s_bStarted || !Replication.IsServer() || ZCR_OnePoint.Name().IsEmpty() || System.IsCLIParam("zcrNoPointSeize"))
			return;
		s_bStarted = true;
		s_Instance = new ZCR_PointSeize();
		GetGame().GetCallqueue().CallLater(s_Instance.Tick, 2000, true);
	}

	protected void Tick()
	{
		SCR_CampaignMilitaryBaseComponent base = ZCR_OnePoint.Base();
		if (!base || !base.GetOwner())
			return;
		int now = ZCR_LossLog.Seconds();
		float dt = 2;
		if (m_iLast >= 0)
			dt = Math.Clamp(now - m_iLast, 0, 10);
		m_iLast = now;
		float radius = POINT_M;
		if (base.GetRadius() > 0)
			radius = Math.Min(POINT_M, base.GetRadius());
		vector at = base.GetOwner().GetOrigin();
		int us;
		int ussr;
		array<IEntity> men = {};
		Men(men);
		foreach (IEntity e : men)
		{
			if (vector.DistanceXZ(e.GetOrigin(), at) > radius)
				continue;
			string side = ZCR_LossLog.SideOf(e);
			if (side == "US")
				us++;
			else if (side == "USSR")
				ussr++;
		}
		string owner;
		if (base.GetFaction())
			owner = base.GetFaction().GetFactionKey();
		string taker;
		if (us > 0 && ussr == 0)
			taker = "US";
		else if (ussr > 0 && us == 0)
			taker = "USSR";
		string state = "seizing";
		if (us > 0 && ussr > 0)
			state = "contested";
		else if (taker.IsEmpty())
			state = "empty";
		else if (taker == owner)
			state = "held";
		if (state == "seizing")
		{
			if (m_sSide != taker)
			{
				m_sSide = taker;
				m_fProgress = 0;
			}
			m_fProgress += dt;
		}
		else if (state != "contested")
			m_fProgress = Math.Max(0, m_fProgress - dt);
		if (state != m_sLastState || (state != "empty" && now >= m_iLogAt))
		{
			m_sLastState = state;
			m_iLogAt = now + 20;
			Print(string.Format("[ZCR][SEIZE] t=%1 base=%2 state=%3 side=%4 progress_s=%5 of=%6 us=%7 ussr=%8 owner=%9", now,
				ZCR_Strategist.BaseName(base), state, m_sSide, Math.Round(m_fProgress), SEIZE_S, us, ussr, owner), LogLevel.NORMAL);
		}
		if (state != "seizing" || m_fProgress < SEIZE_S)
			return;
		SCR_CampaignFaction faction = SCR_CampaignFaction.Cast(GetGame().GetFactionManager().GetFactionByKey(taker));
		m_fProgress = 0;
		m_sSide = "";
		if (!faction)
			return;
		Print(string.Format("[ZCR][SEIZE] t=%1 base=%2 event=taken by=%3 from=%4 us=%5 ussr=%6 radius_m=%7", now,
			ZCR_Strategist.BaseName(base), taker, owner, us, ussr, Math.Round(radius)), LogLevel.NORMAL);
		s_bSetting = true;
		base.SetFaction(faction);
		s_bSetting = false;
	}

	// Every living soldier: the AI's and the players'.
	protected static void Men(notnull array<IEntity> result)
	{
		array<AIAgent> agents = {};
		GetGame().GetAIWorld().GetAIAgents(agents);
		foreach (AIAgent agent : agents)
		{
			if (agent && IsAlive(agent.GetControlledEntity()))
				result.Insert(agent.GetControlledEntity());
		}
		array<int> players = {};
		GetGame().GetPlayerManager().GetPlayers(players);
		foreach (int id : players)
		{
			IEntity e = GetGame().GetPlayerManager().GetPlayerControlledEntity(id);
			if (IsAlive(e) && !result.Contains(e))
				result.Insert(e);
		}
	}

	protected static bool IsAlive(IEntity e)
	{
		ChimeraCharacter c = ChimeraCharacter.Cast(e);
		if (!c)
			return false;
		CharacterControllerComponent controller = c.GetCharacterController();
		return controller && !controller.IsDead();
	}
}
