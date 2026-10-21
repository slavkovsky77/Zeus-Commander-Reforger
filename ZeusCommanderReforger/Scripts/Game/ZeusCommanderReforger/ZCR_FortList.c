// -zcrListFortifications (lab only): once, 20 s in, each main faction's compositions labelled
// TRAIT_FORTIFICATION in its catalog, with their other labels and whether Conflict's building manager
// knows them (a composition id) - to choose what AI Conflict's builders put up as defenses (Martin,
// 19 Oct: "AI should build bunkers and defenses").
class ZCR_FortList
{
	protected static bool s_bDone;

	static void Tick()
	{
		if (s_bDone || !System.IsCLIParam("zcrListFortifications") || ZCR_LossLog.Seconds() < 20)
			return;
		s_bDone = true;
		SCR_GameModeCampaign campaign = SCR_GameModeCampaign.Cast(GetGame().GetGameMode());
		SCR_CampaignBuildingManagerComponent manager;
		if (campaign)
			manager = SCR_CampaignBuildingManagerComponent.Cast(campaign.FindComponent(SCR_CampaignBuildingManagerComponent));
		if (!manager)
		{
			Print("[ZCR][FORTLIST] no building manager", LogLevel.NORMAL);
			return;
		}
		// Conflict's own list of placeable compositions (what the building mode offers).
		array<ResourceName> prefabs = manager.GetPlaceablePrefabs();
		int forts;
		foreach (ResourceName prefab : prefabs)
		{
			SCR_EditableEntityUIInfo info = SCR_EditableEntityUIInfo.ExtractEditableUIInfoFromPrefab(prefab);
			if (info && info.HasEntityLabel(EEditableEntityLabel.SERVICE_SUPPLY_STORAGE))
				Print(string.Format("[ZCR][FORTLIST] supply_storage faction=%1 prefab=%2", info.GetFactionKey(), prefab), LogLevel.NORMAL);
			if (!info || !info.HasEntityLabel(EEditableEntityLabel.TRAIT_FORTIFICATION))
				continue;
			forts++;
			string labels;
			array<EEditableEntityLabel> list = {};
			info.GetEntityLabels(list);
			foreach (EEditableEntityLabel l : list)
				labels += typename.EnumToString(EEditableEntityLabel, l) + ",";
			Print(string.Format("[ZCR][FORTLIST] faction=%1 id=%2 prefab=%3 labels=%4", info.GetFactionKey(), manager.GetCompositionId(prefab), prefab, labels), LogLevel.NORMAL);
		}
		Print(string.Format("[ZCR][FORTLIST] placeable=%1 fortifications=%2", prefabs.Count(), forts), LogLevel.NORMAL);
		// Each faction's vehicle catalog with its labels (21 Oct, Martin: "use more types of vehicles - APCs,
		// tanks - for combat too").
		array<string> keys = {"US", "USSR", "FIA"};
		foreach (string key : keys)
		{
			SCR_Faction faction = SCR_Faction.Cast(GetGame().GetFactionManager().GetFactionByKey(key));
			if (!faction)
				continue;
			SCR_EntityCatalog catalog = faction.GetFactionEntityCatalogOfType(EEntityCatalogType.VEHICLE);
			if (!catalog)
				continue;
			array<SCR_EntityCatalogEntry> entries = {};
			catalog.GetEntityList(entries);
			foreach (SCR_EntityCatalogEntry entry : entries)
			{
				if (!entry)
					continue;
				string vl;
				array<EEditableEntityLabel> labels = {};
				entry.GetEditableEntityLabels(labels);
				foreach (EEditableEntityLabel l : labels)
				{
					string ls = typename.EnumToString(EEditableEntityLabel, l);
					if (ls.StartsWith("VEHICLE_") || ls.StartsWith("TRAIT_ARMED") || ls.Contains("ARMOR") || ls.Contains("TANK"))
						vl += ls + ",";
				}
				Print(string.Format("[ZCR][VEHLIST] faction=%1 enabled=%2 prefab=%3 labels=%4", key, entry.IsEnabled(), entry.GetPrefab(), vl), LogLevel.NORMAL);
			}
		}
	}
}
