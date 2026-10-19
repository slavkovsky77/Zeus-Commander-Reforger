// Phone controls for watch mode, as on Arma 3 (ac-lab lab/director.sqf; review notes 70, 79-83):
// Martin watches the match over a phone stream and can only tap. Two columns of big buttons on the
// left: PREV / NEXT SHOT, PREV / NEXT GROUP (the squads around, nearest first, following the
// leader), LOCK (stay on this scene; AUTO goes off), ACTION (the best fight now), CLOSER / WIDER
// (zoom every shot from now on), OVERVIEW (the hot zone), AUTO (the director picks again). A tap on
// a soldier or vehicle follows it; anywhere else the camera flies there for 30 s.
// Over the stream a tap clicks before the cursor has moved (Arma 3, note 80), so one catcher takes
// every click and reads where the cursor is a moment later. A hidden menu stays open so the game
// shows the cursor. Commands go to the server's director (ZCR_Director.Command) through the
// watcher's own player controller.

modded class SCR_PlayerController
{
	void ZCR_CamCommand(string cmd, vector pos)
	{
		// Solo: the host's own buttons go straight to its director.
		if (Replication.IsServer())
		{
			ZCR_Director.Command(GetPlayerId(), cmd, pos);
			return;
		}
		Rpc(RpcAsk_ZCRCam, cmd, pos);
	}

	[RplRpc(RplChannel.Reliable, RplRcver.Server)]
	protected void RpcAsk_ZCRCam(string cmd, vector pos)
	{
		ZCR_Director.Command(GetPlayerId(), cmd, pos);
	}
}

class ZCR_WatchTapHandler : ScriptedWidgetEventHandler
{
	override bool OnMouseButtonUp(Widget w, int x, int y, int button)
	{
		if (button == 0)
			ZCR_WatchControls.OnClick();
		return true;
	}
}

class ZCR_WatchButton
{
	ImageWidget m_wBack;
	TextWidget m_wText;
	string m_sCmd;
	float m_fFlashUntil;
}

class ZCR_WatchControls
{
	protected static ref ZCR_WatchControls s_Instance;
	protected static const ResourceName FONT_BOLD = "{EABA4FE9D014CCEF}UI/Fonts/RobotoCondensed/RobotoCondensed_Bold.fnt";
	protected static const float X0 = 0.005;
	protected static const float W = 0.08;
	protected static const float GAP = 0.004;
	protected static const float Y0 = 0.23;
	protected static const float H = 0.05;

	protected ImageWidget m_Catcher;
	protected ref ZCR_WatchTapHandler m_Handler;
	protected ref array<ref ZCR_WatchButton> m_aButtons = {};
	protected MenuBase m_Host;
	protected bool m_bLocked;
	protected bool m_bAutoOff;
	protected float m_fClock;
	protected float m_fLastClick = -10;
	protected bool m_bListening;

	static void Create()
	{
		if (s_Instance)
			return;
		s_Instance = new ZCR_WatchControls();
		s_Instance.Build();
	}

	static void Tick(float clock)
	{
		if (s_Instance)
			s_Instance.Update(clock);
	}

	static bool IsHost(MenuBase menu)
	{
		return s_Instance && menu && menu == s_Instance.m_Host;
	}

	// Keep the hidden host menu open: with a menu open the game shows the cursor.
	static void KeepHost(MenuManager menus)
	{
		if (!s_Instance || !menus)
			return;
		if (s_Instance.m_Host && s_Instance.m_Host.IsOpen())
			return;
		s_Instance.m_Host = menus.OpenMenu(ChimeraMenuPreset.PlayerListMenu);
		if (s_Instance.m_Host && s_Instance.m_Host.GetRootWidget())
			s_Instance.m_Host.GetRootWidget().SetVisible(false);
		Print(string.Format("[ZCR][CAMUI] cursor menu open=%1", s_Instance.m_Host != null), LogLevel.NORMAL);
	}

	// The shot's caption tells the state: LOCKED, or AUTO off while following a pick or a tapped spot.
	static void OnLabel(string label)
	{
		if (!s_Instance)
			return;
		s_Instance.m_bLocked = label.StartsWith("LOCKED");
		s_Instance.m_bAutoOff = s_Instance.m_bLocked || label.StartsWith("HERE") || label.StartsWith("BACK") || label.StartsWith("FOLLOWING");
		s_Instance.Labels();
	}

	static void OnClick()
	{
		if (!s_Instance || s_Instance.m_fClock - s_Instance.m_fLastClick < 0.3)
			return;
		s_Instance.m_fLastClick = s_Instance.m_fClock;
		GetGame().GetCallqueue().CallLater(s_Instance.Resolve, 120, false);
	}

	protected void OnMouseLeft(float value = 0, EActionTrigger reason = 0)
	{
		OnClick();
	}

	protected void Build()
	{
		WorkspaceWidget ws = GetGame().GetWorkspace();
		// The catcher: the whole screen, invisible, under the overlay - every click lands here.
		m_Catcher = ImageWidget.Cast(ws.CreateWidget(WidgetType.ImageWidgetTypeID, WidgetFlags.VISIBLE, new Color(0, 0, 0, 0.01), 990, null));
		if (m_Catcher)
		{
			FrameSlot.SetAnchorMin(m_Catcher, 0, 0);
			FrameSlot.SetAnchorMax(m_Catcher, 1, 1);
			FrameSlot.SetOffsets(m_Catcher, 0, 0, 0, 0);
			m_Handler = new ZCR_WatchTapHandler();
			m_Catcher.AddHandler(m_Handler);
		}
		Add("PREV SHOT", "prev", 0, 0);
		Add("NEXT SHOT", "next", 0, 1);
		Add("PREV GROUP", "group-", 1, 0);
		Add("NEXT GROUP", "group+", 1, 1);
		Add("LOCK", "lock", 2, 0);
		Add("ACTION", "action", 2, 1);
		Add("CLOSER", "closer", 3, 0);
		Add("WIDER", "wider", 3, 1);
		Add("OVERVIEW", "overview", 4, 0);
		Add("AUTO ON", "auto", 4, 1);
		Labels();
	}

	protected void Add(string text, string cmd, int row, int col)
	{
		WorkspaceWidget ws = GetGame().GetWorkspace();
		float x0 = X0 + col * (W + GAP);
		float y0 = Y0 + row * (H + GAP * 1.6);
		ZCR_WatchButton b = new ZCR_WatchButton();
		b.m_sCmd = cmd;
		b.m_wBack = ImageWidget.Cast(ws.CreateWidget(WidgetType.ImageWidgetTypeID, WidgetFlags.VISIBLE | WidgetFlags.IGNORE_CURSOR | WidgetFlags.NOFOCUS, new Color(0, 0, 0, 0.6), 1010, null));
		b.m_wText = TextWidget.Cast(ws.CreateWidget(WidgetType.TextWidgetTypeID, WidgetFlags.VISIBLE | WidgetFlags.IGNORE_CURSOR | WidgetFlags.NOFOCUS, Color.FromInt(Color.WHITE), 1011, null));
		if (!b.m_wBack || !b.m_wText)
			return;
		FrameSlot.SetAnchorMin(b.m_wBack, x0, y0);
		FrameSlot.SetAnchorMax(b.m_wBack, x0 + W, y0 + H);
		FrameSlot.SetOffsets(b.m_wBack, 0, 0, 0, 0);
		FrameSlot.SetAnchorMin(b.m_wText, x0 + 0.008, y0 + H * 0.25);
		FrameSlot.SetAnchorMax(b.m_wText, x0 + W, y0 + H);
		FrameSlot.SetOffsets(b.m_wText, 0, 0, 0, 0);
		b.m_wText.SetFont(FONT_BOLD);
		b.m_wText.SetExactFontSize(18);
		b.m_wText.SetText(text);
		m_aButtons.Insert(b);
	}

	protected void Labels()
	{
		foreach (ZCR_WatchButton b : m_aButtons)
		{
			if (b.m_sCmd == "lock")
			{
				if (m_bLocked)
					b.m_wText.SetText("UNLOCK");
				else
					b.m_wText.SetText("LOCK");
			}
			else if (b.m_sCmd == "auto")
			{
				if (m_bAutoOff)
					b.m_wText.SetText("AUTO OFF");
				else
					b.m_wText.SetText("AUTO ON");
			}
		}
		Colours();
	}

	protected void Colours()
	{
		foreach (ZCR_WatchButton b : m_aButtons)
		{
			Color c = new Color(0, 0, 0, 0.6);
			if (m_fClock < b.m_fFlashUntil)
				c = new Color(1, 1, 1, 0.7);              // the tap was taken
			else if (b.m_sCmd == "lock" && m_bLocked)
				c = new Color(0.75, 0.15, 0.12, 0.8);
			else if (b.m_sCmd == "auto")
			{
				if (m_bAutoOff)
					c = new Color(0.75, 0.15, 0.12, 0.8);
				else
					c = new Color(0.15, 0.55, 0.22, 0.8);
			}
			b.m_wBack.SetColor(c);
		}
	}

	protected void Update(float clock)
	{
		m_fClock = clock;
		if (!m_bListening && GetGame().GetInputManager())
		{
			// A second way in, in case the catcher doesn't get the click (debounced in OnClick).
			GetGame().GetInputManager().AddActionListener("MouseLeft", EActionTrigger.UP, OnMouseLeft);
			m_bListening = true;
		}
		Colours();
	}

	// Where the tap really was: a button, else the picture.
	protected void Resolve()
	{
		int x, y;
		WidgetManager.GetMousePos(x, y);
		foreach (ZCR_WatchButton b : m_aButtons)
		{
			float bx, by, bw, bh;
			b.m_wBack.GetScreenPos(bx, by);
			b.m_wBack.GetScreenSize(bw, bh);
			if (x >= bx && x <= bx + bw && y >= by && y <= by + bh)
			{
				b.m_fFlashUntil = m_fClock + 0.25;
				if (b.m_sCmd == "lock")
					m_bLocked = !m_bLocked;
				if (b.m_sCmd == "auto")
				{
					m_bLocked = false;
					m_bAutoOff = false;
				}
				Labels();
				Send(b.m_sCmd, vector.Zero);
				return;
			}
		}
		// The picture: the ground under the tap.
		BaseWorld world = GetGame().GetWorld();
		vector dir;
		vector from = GetGame().GetWorkspace().ProjScreenToWorldNative(x, y, dir, world, -1);
		TraceParam p = new TraceParam();
		p.Start = from;
		p.End = from + dir * 6000;
		p.Flags = TraceFlags.WORLD;
		float f = world.TraceMove(p, null);
		if (f >= 1)
			return;
		Send("tap", from + dir * 6000 * f);
	}

	protected void Send(string cmd, vector pos)
	{
		Print(string.Format("[ZCR][CAMUI] tap cmd=%1 x=%2 z=%3", cmd, Math.Round(pos[0]), Math.Round(pos[2])), LogLevel.NORMAL);
		SCR_PlayerController pc = SCR_PlayerController.Cast(GetGame().GetPlayerController());
		if (pc)
			pc.ZCR_CamCommand(cmd, pos);
	}
}
