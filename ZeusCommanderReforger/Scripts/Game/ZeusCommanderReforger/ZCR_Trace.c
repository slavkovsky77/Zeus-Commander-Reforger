// Crash hunting (Martin, 21 Oct: "it's kind of random, couldn't you improve logging?"). The game crashes inside
// its own entity update, or hangs until it closes itself (300 s), and the console log runs right up to that
// moment - but it did not say what our scripts had just done to the world. So:
//   [ZCR][ENT]  before every entity our scripts spawn, delete, move, destroy, or put a soldier into / take one out of;
//   [ZCR][STEP] when each side's commander tick starts, and the step it is in when it takes long:
//   [ZCR][SLOW] a step of the tick that took over 20 ms (a hang inside our tick shows as a STEP with no line after).
// lab/crashes.py reads them back for every crash. Off: -zcrNoTrace.
class ZCR_Trace
{
	protected static string s_sSide;
	protected static string s_sStep;
	protected static int s_iStepAt;

	static bool On()
	{
		return !System.IsCLIParam("zcrNoTrace");
	}

	// What our script is about to do to an entity: op = spawn, delete, destroy, move, crew, kick, board.
	static void Ent(string op, IEntity e, string why)
	{
		if (!On())
			return;
		string what = "none";
		vector at;
		if (e)
		{
			what = ZCR_LossLog.ShortName(e);
			at = e.GetOrigin();
		}
		Print(string.Format("[ZCR][ENT] t=%1 op=%2 what=%3 x=%4 z=%5 why=%6", ZCR_LossLog.Seconds(), op, what, Math.Round(at[0]), Math.Round(at[2]), why), LogLevel.NORMAL);
	}

	// Same, for a spot (an entity about to be spawned there).
	static void At(string op, string what, vector at, string why)
	{
		if (!On())
			return;
		Print(string.Format("[ZCR][ENT] t=%1 op=%2 what=%3 x=%4 z=%5 why=%6", ZCR_LossLog.Seconds(), op, what, Math.Round(at[0]), Math.Round(at[2]), why), LogLevel.NORMAL);
	}

	// The commander tick of one side starts.
	static void Begin(string side)
	{
		if (!On())
			return;
		s_sSide = side;
		s_sStep = "start";
		s_iStepAt = System.GetTickCount();
		Print(string.Format("[ZCR][STEP] t=%1 side=%2 tick", ZCR_LossLog.Seconds(), side), LogLevel.NORMAL);
	}

	// The tick moves on to the next step; the one before is logged if it took over 20 ms.
	static void Step(string step)
	{
		if (!On())
			return;
		int now = System.GetTickCount();
		int took = now - s_iStepAt;
		if (took > 20 && s_sStep != "idle")
			Print(string.Format("[ZCR][SLOW] t=%1 side=%2 step=%3 ms=%4", ZCR_LossLog.Seconds(), s_sSide, s_sStep, took), LogLevel.NORMAL);
		s_sStep = step;
		s_iStepAt = now;
	}
}
