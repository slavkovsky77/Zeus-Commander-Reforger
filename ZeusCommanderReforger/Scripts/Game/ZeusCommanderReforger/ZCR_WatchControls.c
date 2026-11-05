// Phone controls for watch mode, as on Arma 3 (ac-lab lab/director.sqf; review notes 70, 79-83):
// Martin watches the match over a phone stream and can only tap. Eight buttons on the left (4 Nov - Martin: "optimize number
// of buttons to basically next/prev type free and details", then "sides were important, details too"): PREV / NEXT through
// what TYPE says (AUTO: the director's shots; teams, vehicles, drones, points, fights), CAMERA (AUTO -> LOCKED on what it
// shows -> FREE, flown by the sticks), SIDE, DETAILS (the full label texts), HIDE UI and SPEED. Two sticks for the thumbs: the move
// stick bottom left (FREE only), the look stick with ZOOM bottom right. A tap on a soldier or vehicle follows it; anywhere
// else the camera flies there for 30 s. REPORT is on the lab app's camera bar (ZCR_Director.LabCamera).
// Over the stream a tap clicks before the cursor has moved (Arma 3, note 80), so one catcher takes every click and reads
// where the cursor is once it has come to rest. A hidden menu stays open so the game shows the cursor. Commands go to the
// server's director (ZCR_Director.Command) through the watcher's own player controller.

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
	override bool OnMouseButtonDown(Widget w, int x, int y, int button)
	{
		if (button == 0)
			ZCR_WatchControls.OnPress();
		if (button == 1)
			ZCR_WatchControls.s_bRight = true;
		return true;
	}

	override bool OnMouseButtonUp(Widget w, int x, int y, int button)
	{
		if (button == 0)
			ZCR_WatchControls.OnClick();
		if (button == 1)
			ZCR_WatchControls.s_bRight = false;
		return true;
	}
}

class ZCR_WatchButton
{
	ImageWidget m_wBack;
	TextWidget m_wText;
	string m_sCmd;
	float m_fFlashUntil;
	bool m_bPad;            // a camera pad button (shown while the pad is open)
	bool m_bMove;           // ... of the move stick (shown in FREE only)
}

class ZCR_WatchControls
{
	protected static ref ZCR_WatchControls s_Instance;
	static bool s_bRight;       // the right mouse button held over the picture (camera turning)

	static bool RightDown()
	{
		return s_bRight;
	}
	protected static const ResourceName FONT_BOLD = "{EABA4FE9D014CCEF}UI/Fonts/RobotoCondensed/RobotoCondensed_Bold.fnt";
	protected static const float X0 = 0.005;
	protected static const float W = 0.08;
	protected static const float GAP = 0.004;
	protected static const float Y0 = 0.49;       // under the BLUFOR panel
	protected static const float H = 0.05;

	protected ImageWidget m_Catcher;
	protected ref ZCR_WatchTapHandler m_Handler;
	protected ref array<ref ZCR_WatchButton> m_aButtons = {};
	protected MenuBase m_Host;
	protected bool m_bLocked;
	protected string m_sFocus;          // the side the camera keeps to: "" both, "US", "USSR"
	protected string m_sKind = "teams"; // what PREV / NEXT steps through: teams, vehicles, drones
	protected string m_sType = "auto";  // TYPE: auto (the director's shots), teams, vehicles, drones, points, fights
	protected bool m_bAutoOff;
	protected float m_fClock;
	protected int m_iLastClickMs = -10000;   // real time: the watch clock runs at the game's speed
	protected bool m_bListening;
	protected bool m_bWasFree;
	protected bool m_bSettling;         // a tap waiting for the cursor to come to rest
	protected int m_iClickX;
	protected int m_iClickY;
	protected int m_iSampleX;
	protected int m_iSampleY;
	// A touch that came without a click (see Update): the cursor jumped there, no click followed.
	protected static const int JUMP_PX = 40;
	protected static const int TOUCH_WAIT_MS = 350;
	protected int m_iMouseX = -1;
	protected int m_iMouseY = -1;
	protected bool m_bJumpPending;
	protected int m_iJumpAt;
	protected int m_iJumpX;
	protected int m_iJumpY;
	protected int m_iJumpSeenAt = -100000;   // the last cursor jump a touch made (confirmed: still before and after)
	protected bool m_bJumpCandidate;         // a jump this frame, to confirm on the next
	protected float m_fLastStep;             // how far the cursor moved the frame before
	// A mouse glides, a touch only jumps (5 Nov 00:10-00:55 - Martin, with the mouse: "clicking on ui on computer resets mouse
	// to middle", "clicking on next/prev drone mouse resets to middle that bug"): the cursor moving GLIDE_FRAMES frames in a
	// row is a hand on a mouse, and for MOUSE_MS after it every press acts at once where the cursor is, nothing parks the
	// cursor and a cursor resting on a button is no tap. A one-frame jump alone was not enough: the cursor coming back into
	// the window (the 00:34 battle: 'touch no-button' five times near 1200,1160, the mouse back from the chat) and a fast
	// flick at 25 FPS jump like a touch, and the click after one was read as a touch and parked the cursor.
	protected static const int GLIDE_FRAMES = 3;
	protected static const int MOUSE_MS = 5000;
	protected int m_iGlideFrames;
	protected int m_iGlideAt = -100000;
	// A press in the gap between two buttons (8 px between the rows) is the nearer button (5 Nov 00:39:17 - 'press
	// at=123,733', between PREV and TYPE, flew the camera to a USSR soldier there).
	protected static const int HIT_PX = 6;

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

	// The overlays shown or hidden (ZCR_Watch.ToggleHud): every button but HIDE UI / SHOW UI.
	static void SetHud(bool on)
	{
		if (!s_Instance)
			return;
		s_Instance.m_bHudOn = on;
		foreach (ZCR_WatchButton b : s_Instance.m_aButtons)
		{
			if (b.m_sCmd == "ui")
			{
				if (on)
					b.m_wText.SetText("HIDE UI");
				else
					b.m_wText.SetText("SHOW UI");
			}
		}
		s_Instance.Visibility();
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
		{
			// Kept hidden: a key had shown it over the picture (Martin's screen 02:01:24) and a click in
			// it most likely restarted the mission (a new playthrough at 02:01:46).
			if (s_Instance.m_Host.GetRootWidget() && s_Instance.m_Host.GetRootWidget().IsVisible())
				s_Instance.m_Host.GetRootWidget().SetVisible(false);
			return;
		}
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

	// A mouse press acts at once (5 Nov - Martin: "why does button react on mouse release not on mouse click?"): the release and
	// the 0.3 s wait for the cursor to rest are for a phone's touch over Moonlight / Artemis, whose click can come before the
	// finger's position. A press with no touch jump just before it is a mouse: resolved where the cursor is, and its release
	// (both ways in - the catcher and the listener) is ignored.
	protected bool m_bDownHandled;
	protected int m_iDownAt;

	static void OnPress()
	{
		if (!s_Instance)
			return;
		int nowMs = System.GetTickCount();
		s_Instance.m_bDownHandled = false;
		s_Instance.m_iDownAt = nowMs;
		// A mouse in use (see GLIDE_FRAMES): every press at once. The 0.5 s guard is for a touch's click after its touch tap; with
		// it a quick second mouse click went the release-and-wait way (5 Nov 00:52:55 'click from=377,678 at=290,717': read 0.3 s
		// later, 87 px on) or was lost - Martin's "why does button react on mouse release".
		bool mouse = s_Instance.MouseMode();
		if (mouse && nowMs - s_Instance.m_iLastClickMs < 60)
			return;
		if (!mouse && (nowMs - s_Instance.m_iJumpSeenAt < 1500 || s_Instance.m_bJumpCandidate || nowMs - s_Instance.m_iLastClickMs < 500))
			return;
		int x, y;
		WidgetManager.GetMousePos(x, y);
		s_Instance.m_bDownHandled = true;
		s_Instance.m_iLastClickMs = nowMs;
		s_Instance.m_bJumpPending = false;
		if (s_Instance.m_bSettling)
		{
			s_Instance.m_bSettling = false;
			GetGame().GetCallqueue().Remove(s_Instance.Settle);
		}
		Print(string.Format("[ZCR][CAMUI] press at=%1,%2 mouse=%3", x, y, mouse), LogLevel.NORMAL);
		s_Instance.Resolve(x, y);
	}

	protected bool MouseMode()
	{
		return System.GetTickCount() - m_iGlideAt < MOUSE_MS;
	}

	static void OnClick()
	{
		// The release of a press already acted on.
		if (s_Instance && s_Instance.m_bDownHandled && System.GetTickCount() - s_Instance.m_iDownAt < 5000)
			return;
		// One tap arrives twice (the catcher and the mouse-up listener): the second within 0.5 s of real time is the same
		// tap. It was 0.3 s on the watch clock, which runs at the game's speed - at 2x the window was 0.15 s (28 Oct:
		// SPEED went 1x -> 2x -> 3x within 0.32 s, Martin watching).
		int nowMs = System.GetTickCount();
		if (!s_Instance)
			return;
		// A click came: the touch that moved the cursor was a real tap (no touch tap from it, see Update).
		s_Instance.m_bJumpPending = false;
		if (nowMs - s_Instance.m_iLastClickMs < 500)
		{
			Print(string.Format("[ZCR][CAMUI] click dropped gap_ms=%1", nowMs - s_Instance.m_iLastClickMs), LogLevel.NORMAL);
			return;
		}
		// A tap still waiting: taken where the cursor rested last (this new click came before the cursor moved on).
		if (s_Instance.m_bSettling)
		{
			s_Instance.m_bSettling = false;
			GetGame().GetCallqueue().Remove(s_Instance.Settle);
			s_Instance.Resolve(s_Instance.m_iSampleX, s_Instance.m_iSampleY);
		}
		s_Instance.m_iLastClickMs = nowMs;
		// Over Moonlight / Artemis the click reaches the game before the finger's position does (4 Nov - Martin: "buttons on
		// Artemis are not responsive on first touch", "why do i have to tap two times in moonlight artemis to touch button"):
		// the cursor was still where the last tap had been, so the tap was read there and lost; the second one was right.
		// Now it is read once the cursor has come to rest: sampled every 0.1 s from 0.15 s, taken at the first still sample
		// after 0.3 s (0.9 s at most). [ZCR][CAMUI] click from=... at=... ms=... says how far and how late it came.
		int cx, cy;
		WidgetManager.GetMousePos(cx, cy);
		s_Instance.m_iClickX = cx;
		s_Instance.m_iClickY = cy;
		s_Instance.m_iSampleX = cx;
		s_Instance.m_iSampleY = cy;
		s_Instance.m_bSettling = true;
		GetGame().GetCallqueue().CallLater(s_Instance.Settle, 150, false);
	}

	protected void Settle()
	{
		if (!m_bSettling)
			return;
		int x, y;
		WidgetManager.GetMousePos(x, y);
		int waited = System.GetTickCount() - m_iLastClickMs;
		bool still = Math.AbsFloat(x - m_iSampleX) <= 2 && Math.AbsFloat(y - m_iSampleY) <= 2;
		m_iSampleX = x;
		m_iSampleY = y;
		if ((!still || waited < 300) && waited < 900)
		{
			GetGame().GetCallqueue().CallLater(Settle, 100, false);
			return;
		}
		m_bSettling = false;
		Print(string.Format("[ZCR][CAMUI] click from=%1,%2 at=%3,%4 ms=%5 mouse=%6", m_iClickX, m_iClickY, x, y, waited, MouseMode()), LogLevel.NORMAL);
		Resolve(x, y);
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
		// Eight buttons (4 Nov - Martin: "next/prev type free and details", "sides were important, details too", "speed game").
		Add("PREV", "step-", 0, 0);
		Add("NEXT", "step+", 0, 1);
		Add("TYPE: AUTO", "type", 1, 0);
		Add("CAMERA: AUTO", "mode", 1, 1);
		Add("BOTH SIDES", "side", 2, 0);
		Add("DETAILS: OFF", "details", 2, 1);
		Add("HIDE UI", "ui", 3, 0);
		Add("SPEED 3x", "speed", 3, 1);
		// The two sticks, one for each thumb (Martin: "two modes locked and free, in free you can do wasd in locked only
		// rotation", "mimic two joysticks with +- also for zoom", "good to have those pad on left and right so i can use my
		// thumbs"): bottom left the move stick (FREE only: forward, back, sideways, UP / DN), bottom right the look stick
		// (turn, tilt, ZOOM + / -; round what the camera shows, in FREE the view itself). Corners toward the middle.
		float sw = 0.05;
		float sh = 0.068;
		float sg = 0.006;
		float l0 = 0.73;
		float m0 = 0.012;
		float m1 = m0 + sw + sg;
		float m2 = m1 + sw + sg;
		AddPad("^", "cam-fwd", m1, l0, true);
		AddPad("<", "cam-left", m0, l0 + sh + sg, true);
		AddPad(">", "cam-right", m2, l0 + sh + sg, true);
		AddPad("v", "cam-back", m1, l0 + 2 * (sh + sg), true);
		AddPad("UP", "cam-up", m2, l0, true);
		AddPad("DN", "cam-down", m2, l0 + 2 * (sh + sg), true);
		float c2 = 0.985 - sw;
		float c1 = c2 - sw - sg;
		float c0 = c1 - sw - sg;
		AddPad("^", "look-tiltup", c1, l0, false);
		AddPad("<", "look-turnl", c0, l0 + sh + sg, false);
		AddPad(">", "look-turnr", c2, l0 + sh + sg, false);
		AddPad("v", "look-tiltdn", c1, l0 + 2 * (sh + sg), false);
		AddPad("+", "look-zin", c0, l0, false);
		AddPad("-", "look-zout", c0, l0 + 2 * (sh + sg), false);
		Visibility();
		Labels();
	}

	protected bool m_bHudOn = true;

	// The camera's mode: free (the watcher flies it), locked (on what it shows - a pick, a tap, LOCK), else auto.
	protected string CameraMode()
	{
		if (ZCR_Watch.IsFree())
			return "free";
		if (m_bLocked || m_bAutoOff)
			return "locked";
		return "auto";
	}

	// A camera pad button at a screen spot (fractions of the screen).
	protected void AddPad(string text, string cmd, float x0, float y0, bool move)
	{
		WorkspaceWidget ws = GetGame().GetWorkspace();
		ZCR_WatchButton b = new ZCR_WatchButton();
		b.m_sCmd = cmd;
		b.m_bPad = true;
		b.m_bMove = move;
		b.m_wBack = ImageWidget.Cast(ws.CreateWidget(WidgetType.ImageWidgetTypeID, WidgetFlags.VISIBLE | WidgetFlags.IGNORE_CURSOR | WidgetFlags.NOFOCUS, new Color(0.05, 0.08, 0.12, 0.72), 1010, null));
		b.m_wText = TextWidget.Cast(ws.CreateWidget(WidgetType.TextWidgetTypeID, WidgetFlags.VISIBLE | WidgetFlags.IGNORE_CURSOR | WidgetFlags.NOFOCUS, Color.FromInt(Color.WHITE), 1011, null));
		if (!b.m_wBack || !b.m_wText)
			return;
		FrameSlot.SetAnchorMin(b.m_wBack, x0, y0);
		FrameSlot.SetAnchorMax(b.m_wBack, x0 + 0.05, y0 + 0.068);
		FrameSlot.SetOffsets(b.m_wBack, 0, 0, 0, 0);
		FrameSlot.SetAnchorMin(b.m_wText, x0 + 0.017, y0 + 0.016);
		FrameSlot.SetAnchorMax(b.m_wText, x0 + 0.05, y0 + 0.068);
		FrameSlot.SetOffsets(b.m_wText, 0, 0, 0, 0);
		b.m_wText.SetFont(FONT_BOLD);
		b.m_wText.SetExactFontSize(24);
		b.m_wText.SetText(text);
		m_aButtons.Insert(b);
	}

	// What shows: every button while the overlays are on (hidden: HIDE UI alone, as SHOW UI), the move stick in FREE only.
	protected void Visibility()
	{
		foreach (ZCR_WatchButton b : m_aButtons)
		{
			bool show = m_bHudOn;
			if (b.m_bMove && !ZCR_Watch.IsFree())
				show = false;
			if (b.m_sCmd == "ui")
				show = true;
			b.m_wBack.SetVisible(show);
			b.m_wText.SetVisible(show);
		}
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
			if (b.m_sCmd == "details")
			{
				if (ZCR_Watch.Details())
					b.m_wText.SetText("DETAILS: ON");
				else
					b.m_wText.SetText("DETAILS: OFF");
			}
			else if (b.m_sCmd == "speed")
				b.m_wText.SetText(ZCR_Watch.SpeedLabel());
			else if (b.m_sCmd == "side")
			{
				if (m_sFocus == "US")
					b.m_wText.SetText("US ONLY");
				else if (m_sFocus == "USSR")
					b.m_wText.SetText("USSR ONLY");
				else
					b.m_wText.SetText("BOTH SIDES");
			}
			else if (b.m_sCmd == "mode")
			{
				string modeText = CameraMode();
				modeText.ToUpper();
				b.m_wText.SetText("CAMERA: " + modeText);
			}
			else if (b.m_sCmd == "type")
			{
				string typeText = m_sType;
				typeText.ToUpper();
				b.m_wText.SetText("TYPE: " + typeText);
			}
			else if (b.m_sCmd == "step-" || b.m_sCmd == "step+")
			{
				string stepWhat = "SHOT";
				if (m_sType == "teams")
					stepWhat = "TEAM";
				else if (m_sType == "vehicles")
					stepWhat = "VEHICLE";
				else if (m_sType == "drones")
					stepWhat = "DRONE";
				else if (m_sType == "points")
					stepWhat = "POINT";
				else if (m_sType == "fights")
					stepWhat = "FIGHT";
				if (b.m_sCmd == "step-")
					b.m_wText.SetText("PREV " + stepWhat);
				else
					b.m_wText.SetText("NEXT " + stepWhat);
			}
		}
		Colours();
	}

	protected void Colours()
	{
		foreach (ZCR_WatchButton b : m_aButtons)
		{
			Color c = new Color(0, 0, 0, 0.6);
			if (b.m_bPad)
				c = new Color(0.05, 0.08, 0.12, 0.72);
			if (m_fClock < b.m_fFlashUntil)
				c = new Color(1, 1, 1, 0.7);              // the tap was taken
			else if (b.m_sCmd == "mode" && CameraMode() == "auto")
				c = new Color(0.15, 0.55, 0.22, 0.8);
			else if (b.m_sCmd == "mode" && CameraMode() == "locked")
				c = new Color(0.75, 0.15, 0.12, 0.8);
			else if (b.m_sCmd == "mode" && CameraMode() == "free")
				c = new Color(0.18, 0.35, 0.75, 0.85);
			else if (b.m_sCmd == "details" && ZCR_Watch.Details())
				c = new Color(0.15, 0.55, 0.22, 0.8);
			else if (b.m_sCmd == "side" && m_sFocus == "US")
				c = new Color(0.18, 0.35, 0.75, 0.85);
			else if (b.m_sCmd == "side" && m_sFocus == "USSR")
				c = new Color(0.7, 0.18, 0.15, 0.85);
			else if (b.m_sCmd == "type" && m_sType == "vehicles")
				c = new Color(0.55, 0.42, 0.12, 0.85);
			else if (b.m_sCmd == "type" && m_sType == "drones")
				c = new Color(0.45, 0.2, 0.6, 0.85);
			else if (b.m_sCmd == "type" && m_sType == "points")
				c = new Color(0.12, 0.45, 0.45, 0.85);
			else if (b.m_sCmd == "type" && m_sType == "fights")
				c = new Color(0.7, 0.3, 0.1, 0.85);
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
		TouchTap();
		// Free look switched on or off elsewhere too (a tap on the picture, AUTO from the lab app): the move stick follows.
		bool free = ZCR_Watch.IsFree();
		if (free != m_bWasFree)
		{
			m_bWasFree = free;
			Visibility();
			Labels();
		}
		Colours();
	}

	// A single tap over Moonlight / Artemis on Android reaches the game as the cursor jumping to the finger with no click; only
	// a double tap brings a click (4 Nov - Martin: "button react only when i doubletap"; the 03:25 battle logged 50 clicks,
	// every one read at the finger - the single taps never came as clicks). So: the cursor jumping JUMP_PX+ in one frame onto
	// a button and resting there, with no click within TOUCH_WAIT_MS, is a tap on that button. Buttons only - a mouse moved
	// over the picture never flies the camera. [ZCR][CAMUI] touch-tap / touch no-button logs each.
	protected void TouchTap()
	{
		int x, y;
		WidgetManager.GetMousePos(x, y);
		int now = System.GetTickCount();
		if (m_iMouseX < 0)
		{
			m_iMouseX = x;
			m_iMouseY = y;
			return;
		}
		// A touch teleports the cursor in one frame from rest, and it stays; a mouse moves over several frames (5 Nov 00:10 -
		// Martin, with the mouse: "clicking on ui on computer resets mouse to middle" - a fast mouse move counted as a touch and
		// the click parked the cursor). The jump is confirmed on the next frame if the cursor is still; else it was a mouse.
		float step = Math.AbsFloat(x - m_iMouseX) + Math.AbsFloat(y - m_iMouseY);
		// Gliding (see GLIDE_FRAMES): a mouse - the jump before it, if any, was no touch.
		if (step >= 3)
			m_iGlideFrames++;
		else
			m_iGlideFrames = 0;
		if (m_iGlideFrames >= GLIDE_FRAMES)
		{
			m_iGlideAt = now;
			m_iJumpSeenAt = -100000;
			m_bJumpPending = false;
			m_bJumpCandidate = false;
		}
		if (m_bJumpCandidate)
		{
			m_bJumpCandidate = false;
			if (step <= 2)
				m_iJumpSeenAt = m_iJumpAt;
			else
				m_bJumpPending = false;
		}
		if (step >= JUMP_PX && m_fLastStep <= 2)
		{
			m_bJumpCandidate = true;
			m_bJumpPending = true;
			m_iJumpAt = now;
			m_iJumpX = x;
			m_iJumpY = y;
		}
		m_fLastStep = step;
		m_iMouseX = x;
		m_iMouseY = y;
		if (!m_bJumpPending || now - m_iJumpAt < TOUCH_WAIT_MS)
			return;
		m_bJumpPending = false;
		if (m_bSettling || now - m_iLastClickMs < 500 || MouseMode())
			return;
		if (Math.AbsFloat(x - m_iJumpX) > 4 || Math.AbsFloat(y - m_iJumpY) > 4)
			return;      // the cursor moved on: a mouse, not a touch
		if (!OnButton(x, y))
		{
			Print(string.Format("[ZCR][CAMUI] touch no-button at=%1,%2", x, y), LogLevel.NORMAL);
			return;
		}
		m_iLastClickMs = now;
		Print(string.Format("[ZCR][CAMUI] touch-tap at=%1,%2", x, y), LogLevel.NORMAL);
		Resolve(x, y);
	}

	// After a touch on a button the cursor goes to the picture's upper middle (4 Nov 03:45 - Martin: "still double tap issue"):
	// a single tap brings only the cursor to the finger, so a second tap on the same button, the cursor already on it, brought
	// nothing at all (the 03:37 battle: 3 clicks and 1 touch tap in 3 minutes of tapping). Parked, every tap is a jump.
	protected void Park()
	{
		if (!m_Catcher)
			return;
		float w, h;
		m_Catcher.GetScreenSize(w, h);
		int px = w * 0.5;
		int py = h * 0.3;
		Print(string.Format("[ZCR][CAMUI] park from=%1,%2", m_iMouseX, m_iMouseY), LogLevel.NORMAL);
		GetGame().GetInputManager().GetMouseDeviceHandler().SetCursorPosition(px, py);
		m_iMouseX = px;
		m_iMouseY = py;
		m_bJumpPending = false;
		m_bJumpCandidate = false;
		m_fLastStep = 0;
		m_iGlideFrames = 0;
	}

	protected bool OnButton(int x, int y)
	{
		return Hit(x, y) != null;
	}

	// The button at a screen spot: the one it is on, else the nearest within HIT_PX (a press in the gap between two).
	protected ZCR_WatchButton Hit(int x, int y)
	{
		ZCR_WatchButton best;
		float bestGap = HIT_PX + 1;
		foreach (ZCR_WatchButton b : m_aButtons)
		{
			if (!b.m_wBack.IsVisible())
				continue;
			float bx, by, bw, bh;
			b.m_wBack.GetScreenPos(bx, by);
			b.m_wBack.GetScreenSize(bw, bh);
			float gx = Math.Max(0, Math.Max(bx - x, x - bx - bw));
			float gy = Math.Max(0, Math.Max(by - y, y - by - bh));
			float gap = Math.Max(gx, gy);
			if (gap < bestGap)
			{
				bestGap = gap;
				best = b;
			}
		}
		if (bestGap > HIT_PX)
			return null;
		return best;
	}

	// Where the tap really was (x, y: the cursor at rest): a button, else the picture.
	protected void Resolve(int x, int y)
	{
		ZCR_WatchButton b = Hit(x, y);
		if (b)
		{
			b.m_fFlashUntil = m_fClock + 0.25;
			// The cursor parks only after a touch: never while a mouse is in use, and only with the cursor still where the
			// touch's jump put it (5 Nov - Martin: "the park must only follow a real touch").
			if (!MouseMode() && System.GetTickCount() - m_iJumpSeenAt < 1500 && Math.AbsFloat(x - m_iJumpX) <= 8 && Math.AbsFloat(y - m_iJumpY) <= 8)
				Park();
			string cmd = b.m_sCmd;
			if (cmd.StartsWith("cam-"))
			{
				ZCR_Watch.Nudge(cmd.Substring(4, cmd.Length() - 4));
				return;
			}
			if (cmd.StartsWith("look-"))
			{
				ZCR_Watch.Look(cmd.Substring(5, cmd.Length() - 5));
				return;
			}
			if (cmd == "ui")
			{
				ZCR_Watch.ToggleHud();
				return;
			}
			if (cmd == "details")
			{
				ZCR_Watch.ToggleDetails();
				Labels();
				return;
			}
			// The game speed (Martin: "can I set the speed?"): 3x -> 1x -> 2x -> 3x; the game's own time multiplier, solo only.
			if (cmd == "speed")
			{
				ZCR_Watch.CycleSpeed();
				Labels();
				return;
			}
			// One side or both (Martin: "a button to switch between the factions"): BOTH -> US -> USSR.
			if (cmd == "side")
			{
				if (m_sFocus.IsEmpty())
					m_sFocus = "US";
				else if (m_sFocus == "US")
					m_sFocus = "USSR";
				else
					m_sFocus = "";
				Labels();
				Send("side-" + m_sFocus, vector.Zero);
				return;
			}
			// CAMERA: AUTO -> LOCKED (on what it shows) -> FREE -> back to what it showed before free look.
			if (cmd == "mode")
			{
				string mode = CameraMode();
				if (mode == "free")
					ZCR_Watch.SetFree(false);
				else if (mode == "locked")
					ZCR_Watch.SetFree(true);
				else
				{
					Send("lock", vector.Zero);
					m_bLocked = true;
					m_bAutoOff = true;
				}
				Visibility();
				Labels();
				return;
			}
			// What is picked is shown, so a pick ends free look.
			if (ZCR_Watch.IsFree())
				ZCR_Watch.SetFree(false);
			// TYPE: auto -> teams -> vehicles -> drones -> points -> fights; each tap shows one of the new kind at once
			// (AUTO gives the camera back to the director).
			if (cmd == "type")
			{
				if (m_sType == "auto")
					m_sType = "teams";
				else if (m_sType == "teams")
					m_sType = "vehicles";
				else if (m_sType == "vehicles")
					m_sType = "drones";
				else if (m_sType == "drones")
					m_sType = "points";
				else if (m_sType == "points")
					m_sType = "fights";
				else
					m_sType = "auto";
				if (m_sType == "auto")
				{
					m_bLocked = false;
					m_bAutoOff = false;
					ZCR_Watch.ResetOrbit();
					Send("auto", vector.Zero);
				}
				else if (m_sType == "points")
					Send("point+", vector.Zero);
				else if (m_sType == "fights")
					Send("action", vector.Zero);
				else
				{
					m_sKind = m_sType;
					Send("kind-" + m_sType, vector.Zero);
				}
				Labels();
				return;
			}
			// PREV / NEXT: through what TYPE says.
			if (cmd == "step-" || cmd == "step+")
			{
				bool back = cmd == "step-";
				if (m_sType == "auto")
					cmd = "next";
				else if (m_sType == "points")
					cmd = "point+";
				else if (m_sType == "fights")
					cmd = "action";
				else
					cmd = "group+";
				if (back && cmd == "next")
					cmd = "prev";
				else if (back && cmd != "action")
					cmd.Replace("+", "-");
			}
			Labels();
			Send(cmd, vector.Zero);
			return;
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
