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
	}
}
