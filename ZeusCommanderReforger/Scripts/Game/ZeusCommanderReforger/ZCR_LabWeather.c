// Lab conditions (-zcrLabWeather on the server): every lab match in the same clear midday - no fog,
// no rain, the clock standing still - so matches compare fairly and the videos show the ground.
// Applied once the strategist starts, and again every few minutes (a weather change can undo it).
class ZCR_LabWeather
{
	protected static int s_iNextAt = -1;

	static void Apply()
	{
		if (!Replication.IsServer() || !System.IsCLIParam("zcrLabWeather"))
			return;
		int now = ZCR_LossLog.Seconds();
		if (s_iNextAt >= 0 && now < s_iNextAt)
			return;
		s_iNextAt = now + 180;
		ChimeraWorld world = ChimeraWorld.CastFrom(GetGame().GetWorld());
		if (!world)
			return;
		TimeAndWeatherManagerEntity weather = world.GetTimeAndWeatherManager();
		if (!weather)
			return;
		weather.SetIsDayAutoAdvanced(false);
		weather.SetTimeOfTheDay(11.5, true);
		weather.ForceWeatherTo(true, "Clear", 0, 99999);
		weather.SetFogAmountOverride(true, 0);
		weather.SetFogHeightDensityOverride(true, 0);
		weather.SetRainIntensityOverride(true, 0);
		Print(string.Format("[ZCR][LAB_WEATHER] t=%1 clear, 11:30, no fog or rain", now), LogLevel.NORMAL);
	}
}
