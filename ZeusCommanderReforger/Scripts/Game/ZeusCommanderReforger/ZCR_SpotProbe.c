// -zcrProbeSpots x,z;x,z;... (lab only): what is at a map spot - every entity within 25 m (prefab or class,
// distance, height) and the terrain height around it, 20 s and again 120 s into the match. Written for the
// two places where AI vehicles catch fire on the main bases' exit roads (20 Oct: 191 of 230 crashes).
class ZCR_SpotProbe
{
	protected static int s_iDone;
	protected static ref array<string> s_aLines;

	protected static bool s_bRoads;

	// -zcrSupplyProbe (lab): every 10 s each army's front bases - stock, and what could refill them (the
	// container's own gain, Conflict's regular income settings). Front bases went 1250 -> 3000 in 4 minutes
	// with no truck (21 Oct).
	protected static int s_iNextSupplyProbe;

	// -zcrDepotProbe (lab): every vehicle-depot service on the map at 1 and 6 minutes - its type, side, place and
	// bases - to see whether the HQs have one AI Conflict's supply trucks could start from.
	protected static int s_iDepotProbes;
	static void DepotProbe()
	{
		int at = 60;
		if (s_iDepotProbes > 0)
			at = 360;
		if (!System.IsCLIParam("zcrDepotProbe") || s_iDepotProbes > 1 || ZCR_LossLog.Seconds() < at)
			return;
		s_iDepotProbes++;
		foreach (SCR_CatalogEntitySpawnerComponent production : SCR_CatalogEntitySpawnerComponent.INSTANCES)
		{
			if (!production || !production.GetOwner())
				continue;
			string side = "none";
			if (production.GetFaction())
				side = production.GetFaction().GetFactionKey();
			array<SCR_MilitaryBaseComponent> bases = {};
			production.GetBases(bases);
			string names;
			foreach (SCR_MilitaryBaseComponent b : bases)
			{
				SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
				if (base)
					names += base.GetBaseName() + "/hq" + base.IsHQ().ToString() + ",";
			}
			vector pos = production.GetOwner().GetOrigin();
			string prefab = "-";
			if (production.GetOwner().GetPrefabData())
				prefab = production.GetOwner().GetPrefabData().GetPrefabName();
			Print(string.Format("[ZCR][DEPOT_PROBE] t=%1 type=%2 side=%3 state=%4 x=%5 z=%6 bases=%7 prefab=%8", ZCR_LossLog.Seconds(),
				typename.EnumToString(SCR_EServicePointType, production.GetType()), side,
				typename.EnumToString(SCR_EServicePointStatus, production.GetServiceState()), (int)pos[0], (int)pos[2], names, prefab));
		}
	}

	static void SupplyProbe()
	{
		if (!System.IsCLIParam("zcrSupplyProbe") || ZCR_LossLog.Seconds() < s_iNextSupplyProbe)
			return;
		s_iNextSupplyProbe = ZCR_LossLog.Seconds() + 10;
		SCR_GameModeCampaign campaign = SCR_GameModeCampaign.GetInstance();
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!campaign || !system)
			return;
		array<SCR_MilitaryBaseComponent> all = {};
		system.GetBases(all);
		foreach (SCR_MilitaryBaseComponent b : all)
		{
			SCR_CampaignMilitaryBaseComponent base = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!base || base.IsHQ() || !base.GetFaction() || (base.GetFaction().GetFactionKey() != "US" && base.GetFaction().GetFactionKey() != "USSR"))
				continue;
			string gain = "none";
			SCR_ResourceComponent rc = base.GetResourceComponent();
			if (rc && rc.GetContainer(EResourceType.SUPPLIES))
			{
				SCR_ResourceContainer c = rc.GetContainer(EResourceType.SUPPLIES);
				gain = string.Format("%1/%2/%3s", c.IsResourceGainEnabled(), c.GetResourceGain(), c.GetResourceGainTickrate());
			}
			// Each container the base's stock is summed from: who owns it, its value, its gain.
			string parts;
			SCR_ResourceConsumer consumer;
			if (rc)
				consumer = rc.GetConsumer(EResourceGeneratorID.DEFAULT, EResourceType.SUPPLIES);
			if (consumer && consumer.GetContainerQueue())
			{
				SCR_ResourceContainerQueueBase queue = consumer.GetContainerQueue();
				for (int q; q < queue.GetContainerCount(); q++)
				{
					SCR_ResourceContainer qc = queue.GetContainerAt(q);
					if (!qc || !qc.GetOwner())
						continue;
					parts += string.Format(" [%1 %2 gain=%3/%4]", ZCR_LossLog.ShortName(qc.GetOwner()), Math.Round(qc.GetResourceValue()), qc.IsResourceGainEnabled(), qc.GetResourceGain());
				}
			}
			Print(string.Format("[ZCR][SUPPLY_PROBE3] t=%1 base=%2%3", ZCR_LossLog.Seconds(), ZCR_Strategist.BaseName(base), parts), LogLevel.NORMAL);
			Print(string.Format("[ZCR][SUPPLY_PROBE2] t=%1 base=%2 value=%3 container_gain=%4 auto_regen=%5 threshold=%6 income=%7/%8/%9",
				ZCR_LossLog.Seconds(), ZCR_Strategist.BaseName(base), Math.Round(base.GetSupplies()), gain, campaign.GetSuppliesAutoRegenerationEnabled(),
				campaign.GetSuppliesReplenishThreshold(), campaign.GetRegularSuppliesIncome(), campaign.GetRegularSuppliesIncomeBase(), campaign.GetRegularSuppliesIncomeExtra()), LogLevel.NORMAL);
		}
	}

	// -zcrProbeRoads: once, 20 s in, each base's radius and its nearest road point (any road within 400 m).
	static void Roads()
	{
		if (s_bRoads || !System.IsCLIParam("zcrProbeRoads") || ZCR_LossLog.Seconds() < 20)
			return;
		s_bRoads = true;
		SCR_GameModeCampaign campaign = SCR_GameModeCampaign.Cast(GetGame().GetGameMode());
		SCR_AIWorld aiWorld = SCR_AIWorld.Cast(GetGame().GetAIWorld());
		if (!campaign || !aiWorld)
			return;
		array<SCR_CampaignMilitaryBaseComponent> bases = {};
		campaign.GetBaseManager().GetBases(bases);
		foreach (SCR_CampaignMilitaryBaseComponent base : bases)
		{
			vector c = base.GetOwner().GetOrigin();
			vector road;
			float d = -1;
			if (AICF_LogisticsPlanner.NearestRoadPoint(aiWorld.GetRoadNetworkManager(), c, 400, road))
				d = vector.DistanceXZ(road, c);
			string owner = "none";
			if (base.GetFaction())
				owner = base.GetFaction().GetFactionKey();
			Print(string.Format("[ZCR][ROADS] base=%1 x=%2 z=%3 radius=%4 nearest_road_m=%5 at=%6,%7 type=%8 owner=%9", base.GetOwner().GetID(), Math.Round(c[0]), Math.Round(c[2]),
				Math.Round(base.GetRadius()), Math.Round(d), Math.Round(road[0]), Math.Round(road[2]), typename.EnumToString(SCR_ECampaignBaseType, base.GetType()),
				owner + string.Format(" source_component=%1 supplies=%2/%3", base.GetOwner().FindComponent(SCR_CampaignSourceBaseComponent) != null, Math.Round(base.GetSupplies()), Math.Round(base.GetSuppliesMax()))), LogLevel.NORMAL);
		}
	}

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
