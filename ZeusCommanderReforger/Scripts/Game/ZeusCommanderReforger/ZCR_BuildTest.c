// The base-building sub-lab (25 Oct - Martin: "before the real match let's test building of the base by the infantry guys";
// "let's make a sub-lab for that, I want to test it and look at it"). Lab only, -zcrBuildTest "US=x,z|x,z;USSR=x,z|x,z":
// AI Conflict runs as in a match but without squads (the runner caps each side at 1 soldier, so only builders and supply
// trucks come out), the listed bases go to their sides a few seconds in, and every base a side holds is topped up to its
// full supply store every 30 s - building is tested, not the economy: where AI Conflict's planner puts each building and
// how the base's builder (one soldier) walks there and builds it. The camera follows the builders (one at work first);
// [ZCR][BUILDTEST] lines say which bases were given and topped up; the construction itself is AI Conflict's own log.
class ZCR_BuildTest
{
	protected static ref ZCR_BuildTest s_Instance;
	protected int m_iCamTurn;
	protected int m_iGiven;

	static bool Active()
	{
		return s_Instance != null;
	}

	static void Start()
	{
		string spec;
		if (s_Instance || !Replication.IsServer() || !System.GetCLIParam("zcrBuildTest", spec) || spec.IsEmpty())
			return;
		s_Instance = new ZCR_BuildTest();
		GetGame().GetCallqueue().CallLater(s_Instance.Give, 8000, false, spec);
		GetGame().GetCallqueue().CallLater(s_Instance.Stock, 30000, true);
		GetGame().GetCallqueue().CallLater(s_Instance.Clear, 10000, true);
	}

	// No squads: AI Conflict spawns each side's whole starting roster past the side cap (the cap of 1 from the runner only
	// stops replacements) - their soldiers are taken off the map as they appear, for the first 3 minutes. Builders and
	// supply truck crews are not in the squad slots and stay.
	protected int m_iCleared;

	protected void Clear()
	{
		int now = ZCR_LossLog.Seconds();
		if (now > 180)
		{
			GetGame().GetCallqueue().Remove(Clear);
			return;
		}
		int men, groups;
		foreach (FactionKey faction, AICF_FactionState state : ZCR_Strategist.s_mStates)
		{
			for (int s; state && s < state.GetSlotCount(); s++)
			{
				AICF_GroupSlot slot = state.GetSlot(s);
				if (!slot || !slot.GetGroup())
					continue;
				array<AIAgent> agents = {};
				slot.GetGroup().GetAgents(agents);
				if (agents.IsEmpty())
					continue;
				groups++;
				foreach (AIAgent a : agents)
				{
					IEntity e = a.GetControlledEntity();
					if (!e)
						continue;
					RplComponent.DeleteRplEntity(e, false);
					men++;
				}
			}
		}
		m_iCleared += men;
		if (men > 0)
			Print(string.Format("[ZCR][BUILDTEST] t=%1 event=CLEAR men=%2 groups=%3 total=%4", now, men, groups, m_iCleared), LogLevel.NORMAL);
	}

	// The listed bases to their sides ("US=2293,1224|2727,1681;USSR=2209,2909"): the base nearest each point, within 250 m.
	protected void Give(string spec)
	{
		int now = ZCR_LossLog.Seconds();
		array<string> sides = {};
		spec.Split(";", sides, true);
		foreach (string s : sides)
		{
			array<string> kv = {};
			s.Split("=", kv, true);
			if (kv.Count() < 2)
				continue;
			SCR_CampaignFaction faction = SCR_CampaignFaction.Cast(GetGame().GetFactionManager().GetFactionByKey(kv[0]));
			if (!faction)
			{
				Print(string.Format("[ZCR][BUILDTEST] t=%1 event=NO_SIDE side=%2", now, kv[0]), LogLevel.WARNING);
				continue;
			}
			array<SCR_CampaignMilitaryBaseComponent> given = {};
			// "US=2": the side's 2 bases with a supply store nearest its HQ (Arland puts the HQs either way round).
			if (!kv[1].Contains(","))
				NearestToHq(faction, kv[1].ToInt(), given);
			array<string> spots = {};
			kv[1].Split("|", spots, true);
			foreach (string spot : spots)
			{
				array<string> xz = {};
				spot.Split(",", xz, true);
				if (xz.Count() < 2)
					continue;
				SCR_CampaignMilitaryBaseComponent near = BaseNear(Vector(xz[0].ToFloat(), 0, xz[1].ToFloat()), 250);
				if (near)
					given.Insert(near);
				else
					Print(string.Format("[ZCR][BUILDTEST] t=%1 event=NO_BASE side=%2 at=%3", now, kv[0], spot), LogLevel.WARNING);
			}
			foreach (SCR_CampaignMilitaryBaseComponent base : given)
			{
				base.SetFaction(faction);
				m_iGiven++;
				vector at = base.GetOwner().GetOrigin();
				Print(string.Format("[ZCR][BUILDTEST] t=%1 event=GIVE side=%2 x=%3 z=%4 storage=%5 base=%6", now, kv[0], Math.Round(at[0]), Math.Round(at[2]),
					Math.Round(base.GetSuppliesMax()), ZCR_LiveMap.Name(ZCR_Strategist.BaseName(base))), LogLevel.NORMAL);
			}
		}
		Stock();
	}

	// Every base a side holds, to its full store.
	protected void Stock()
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return;
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		int topped;
		float added;
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || !base.GetFaction() || base.GetSuppliesMax() <= 0)
				continue;
			string key = base.GetFaction().GetFactionKey();
			if (key != "US" && key != "USSR")
				continue;
			float room = base.GetSuppliesMax() - base.GetSupplies();
			if (room < 1)
				continue;
			base.AddSupplies(Math.Round(room));
			topped++;
			added += room;
		}
		Print(string.Format("[ZCR][BUILDTEST] t=%1 event=STOCK bases=%2 added=%3", ZCR_LossLog.Seconds(), topped, Math.Round(added)), LogLevel.NORMAL);
	}

	// The side's n bases with a supply store nearest its HQ, not its HQ, not held by the other side.
	protected static void NearestToHq(SCR_CampaignFaction faction, int n, notnull array<SCR_CampaignMilitaryBaseComponent> into)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		SCR_CampaignMilitaryBaseComponent hq = faction.GetMainBase();
		if (!system || !hq || !hq.GetOwner())
			return;
		vector home = hq.GetOwner().GetOrigin();
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		array<SCR_CampaignMilitaryBaseComponent> free = {};
		array<float> dist = {};
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || !base.GetOwner() || base.IsHQ() || base.GetSuppliesMax() <= 0)
				continue;
			if (base.GetFaction() && base.GetFaction() != faction && (base.GetFaction().GetFactionKey() == "US" || base.GetFaction().GetFactionKey() == "USSR"))
				continue;
			float d = vector.DistanceXZ(base.GetOwner().GetOrigin(), home);
			int at = 0;
			while (at < dist.Count() && dist[at] < d)
				at++;
			dist.InsertAt(d, at);
			free.InsertAt(base, at);
		}
		for (int i; i < n && i < free.Count(); i++)
			into.Insert(free[i]);
	}

	protected static SCR_CampaignMilitaryBaseComponent BaseNear(vector p, float within)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return null;
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		SCR_CampaignMilitaryBaseComponent best;
		float bestM = within;
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || !base.GetOwner())
				continue;
			float d = vector.DistanceXZ(base.GetOwner().GetOrigin(), p);
			if (d < bestM)
			{
				bestM = d;
				best = base;
			}
		}
		return best;
	}

	// What a builder is doing: BUILDING (at his work spot), WALKING (to it), RETURNING (home), WAITING (no work).
	static string Doing(AICF_BaseBuilder b)
	{
		if (!b || !b.m_Character)
			return "GONE";
		if (!b.m_Target)
		{
			if (b.m_bReturning)
				return "RETURNING";
			return "WAITING";
		}
		if (b.m_bToolActive || b.m_iWorkAtMs > 0 || vector.DistanceXZ(b.m_Character.GetOrigin(), b.m_vWorkPosition) < 4)
			return "BUILDING";
		return "WALKING";
	}

	// The building he works on: "light depot" ... from the construction order AI Conflict left on the layout.
	static string What(AICF_BaseBuilder b)
	{
		if (!b || !b.m_Target || !b.m_Target.m_AICFConstructionReceipt)
			return "";
		string what = typename.EnumToString(AICF_EConstructionType, b.m_Target.m_AICFConstructionReceipt.m_eType);
		what.ToLower();
		what.Replace("_", " ");
		return what;
	}

	// Build progress of his target, "30/50" (empty without one).
	static string Progress(AICF_BaseBuilder b)
	{
		if (!b || !b.m_Target)
			return "";
		SCR_CampaignBuildingLayoutComponent layout = b.m_Target.GetCompositionLayout();
		if (!layout)
			return "";
		return string.Format("%1/%2", Math.Round(layout.GetCurrentBuildValue()), layout.GetToBuildValue());
	}

	// "BUILDER: US at Moss Hill - light depot 30/50 - walking, 120 m to go".
	static string Tag(AICF_BaseBuilder b)
	{
		string side = "?";
		if (b.m_Faction)
			side = b.m_Faction.GetFactionKey();
		string text = string.Format("BUILDER: %1 ", side);
		if (b.m_Base)
			text += "at " + ZCR_Strategist.BaseName(b.m_Base) + " ";
		string doing = Doing(b);
		string what = What(b);
		if (!what.IsEmpty())
			text += "- " + what + " " + Progress(b) + " ";
		doing.ToLower();
		text += "- " + doing;
		if (doing == "walking" && b.m_Character)
			text += string.Format(", %1 m to go", Math.Round(vector.DistanceXZ(b.m_Character.GetOrigin(), b.m_vWorkPosition)));
		return text;
	}

	protected static void Live(notnull array<AICF_BaseBuilder> into)
	{
		array<AICF_BaseBuilder> all = {};
		AICF_BaseBuilderService.ZCR_Builders(all);
		foreach (AICF_BaseBuilder b : all)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(b.m_Character);
			if (c && c.GetCharacterController() && !c.GetCharacterController().IsDead())
				into.Insert(b);
		}
	}

	// For the camera: a builder at work first, then one walking to his site, then any - in turn.
	static IEntity CameraUnit(out string label)
	{
		if (!s_Instance)
			return null;
		array<AICF_BaseBuilder> live = {};
		Live(live);
		int n = live.Count();
		AICF_BaseBuilder pick;
		for (int pass; !pick && pass < 3 && n > 0; pass++)
		{
			for (int i = 1; !pick && i <= n; i++)
			{
				AICF_BaseBuilder b = live[(s_Instance.m_iCamTurn + i) % n];
				string doing = Doing(b);
				if ((pass == 0 && doing != "BUILDING") || (pass == 1 && doing != "WALKING"))
					continue;
				pick = b;
				s_Instance.m_iCamTurn = (s_Instance.m_iCamTurn + i) % n;
			}
		}
		if (!pick)
			return null;
		label = Tag(pick);
		return pick.m_Character;
	}

	// PREV / NEXT: every builder.
	static void Units(notnull array<IEntity> units, notnull array<string> labels)
	{
		if (!s_Instance)
			return;
		array<AICF_BaseBuilder> live = {};
		Live(live);
		foreach (AICF_BaseBuilder b : live)
		{
			units.Insert(b.m_Character);
			labels.Insert(Tag(b));
		}
	}
}
