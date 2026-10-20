// Watch mode: the game on screen as a camera over an AI-only match, as the Arma 3 lab's camera
// director does (ac-lab lab/director.sqf). The game runs with -zcrWatch, the lab server with
// -zcrWatchServer. The server's director (ZCR_Director) knows every unit and picks each shot; this
// side flies the camera there (RTS view: south of the spot, looking north and steeply down,
// gliding 3 s between shots, or following a soldier in a close-up) and draws what the director
// sends: bases in their owner's colour, each side's main effort as a trail of growing squares,
// losses in side colours, a caption for the shot and a panel with both commanders' intent.
// No side is picked: Conflict's deploy and welcome screens stay closed.

// Server: watchers get every unit on the map and the director starts.
modded class SCR_BaseGameMode
{
	override void OnPlayerConnected(int playerId)
	{
		super.OnPlayerConnected(playerId);
		if (!Replication.IsServer() || !System.IsCLIParam("zcrWatchServer"))
			return;
		PlayerController controller = GetGame().GetPlayerManager().GetPlayerController(playerId);
		if (controller)
			RplComponent.EnableStreamingForConnection(controller.GetRplIdentity(), false);
		ZCR_Director.AddWatcher(playerId);
		Print(string.Format("[ZCR][WATCH] player=%1 watches", playerId), LogLevel.NORMAL);
	}

	void ZCR_SendShot(vector target, float back, float height, RplId follow, string label, int seconds)
	{
		Rpc(RpcDo_ZCRShot, target, back, height, follow, label, seconds);
		// Solo (the game hosts the match): a broadcast doesn't reach the host's own screen.
		if (!System.IsConsoleApp())
			ZCR_Watch.OnShot(target, back, height, follow, label);
	}

	void ZCR_SendOverlay(string top, string left, string right, string bottom, string markers)
	{
		Rpc(RpcDo_ZCROverlay, top, left, right, bottom, markers);
		if (!System.IsConsoleApp())
			ZCR_Watch.OnOverlay(top, left, right, bottom, markers);
	}

	[RplRpc(RplChannel.Reliable, RplRcver.Broadcast)]
	protected void RpcDo_ZCRShot(vector target, float back, float height, RplId follow, string label, int seconds)
	{
		ZCR_Watch.OnShot(target, back, height, follow, label);
	}

	[RplRpc(RplChannel.Reliable, RplRcver.Broadcast)]
	protected void RpcDo_ZCROverlay(string top, string left, string right, string bottom, string markers)
	{
		ZCR_Watch.OnOverlay(top, left, right, bottom, markers);
	}
}

// Client: no deploy or welcome screen while watching (Conflict reopens them every frame for a
// player without a soldier).
modded class SCR_PlayerDeployMenuHandlerComponent
{
	override void Update(float timeSlice)
	{
		if (ZCR_Watch.IsOn())
			return;
		super.Update(timeSlice);
	}
}

// Client: the camera and the overlay, from the game's frame update.
modded class ArmaReforgerScripted
{
	override void OnUpdate(BaseWorld world, float timeslice)
	{
		super.OnUpdate(world, timeslice);
		ZCR_Watch.Update(timeslice);
	}
}

class ZCR_WatchMarker
{
	string m_sKind;
	vector m_vPos;
	ref Color m_Colour;
	float m_fSize;
	string m_sText;
}

class ZCR_Watch
{
	protected static ref ZCR_Watch s_Instance;
	protected static bool s_bChecked;
	protected static const ResourceName FONT = "{3E7733BAC8C831F6}UI/Fonts/RobotoCondensed/RobotoCondensed_Regular.fnt";
	protected static const ResourceName FONT_BOLD = "{EABA4FE9D014CCEF}UI/Fonts/RobotoCondensed/RobotoCondensed_Bold.fnt";

	protected CameraBase m_Camera;
	protected Widget m_Root;
	protected TextWidget m_Caption;
	protected TextWidget m_Panel;
	protected TextWidget m_Left;
	protected TextWidget m_Right;
	protected TextWidget m_Bottom;
	protected ref array<Widget> m_aPool = {};
	protected ref array<ref ZCR_WatchMarker> m_aMarkers = {};
	protected float m_fClock;
	protected float m_fNextMenuCheck;
	protected vector m_vFrom;
	protected vector m_vTo;
	protected float m_fFromBack = 900;
	protected float m_fFromHeight = 900;
	protected float m_fToBack = 900;
	protected float m_fToHeight = 900;
	protected float m_fGlideStart;
	protected RplId m_FollowId;
	protected bool m_bHasShot;
	protected vector m_vSpot;
	protected vector m_vFollowSeen;     // where the followed soldier or drone was last seen
	protected bool m_bFollowSeen;
	protected float m_fNextNear;
	protected ref array<IEntity> m_aNear = {};
	// Free look: the camera is the watcher's - WASD, right mouse held to look, Shift faster, Q/E down/up.
	protected bool m_bFree;
	protected float m_fOrbitYaw;          // the watcher's turn round the shot (right mouse), 0 = from the south
	protected float m_fOrbitLift = 1;     // and up or down (height factor)
	protected int m_iOrbitX = -1;
	protected int m_iOrbitY = -1;

	// AUTO puts the camera back to the director's angle.
	static void ResetOrbit()
	{
		if (!s_Instance)
			return;
		s_Instance.m_fOrbitYaw = 0;
		s_Instance.m_fOrbitLift = 1;
	}
	protected vector m_vFreePos;
	protected float m_fYaw;
	protected float m_fPitch = -30;
	protected int m_iLastTick;
	protected int m_iMouseX = -1;
	protected int m_iMouseY = -1;

	static void SetFree(bool on)
	{
		if (!s_Instance || !s_Instance.m_Camera)
			return;
		s_Instance.m_bFree = on;
		if (on)
		{
			s_Instance.m_vFreePos = s_Instance.m_Camera.GetOrigin();
			vector ypr = s_Instance.m_Camera.GetYawPitchRoll();
			s_Instance.m_fYaw = ypr[0];
			s_Instance.m_fPitch = ypr[1];
			s_Instance.m_iLastTick = System.GetTickCount();
			s_Instance.m_iMouseX = -1;
			if (s_Instance.m_Caption)
				s_Instance.m_Caption.SetText("FREE LOOK - W A S D to move, hold the right mouse button to look, Shift faster, Q / E down / up");
		}
		Print(string.Format("[ZCR][CAMUI] free look %1", on), LogLevel.NORMAL);
	}

	static bool IsFree()
	{
		return s_Instance && s_Instance.m_bFree;
	}

	// With the mouse an action fires only every second frame (the game's own camera does the same).
	protected float m_aLastIn[2];
	protected float Smoothed(float v, int i)
	{
		float prev = m_aLastIn[i];
		m_aLastIn[i] = v;
		if (v == 0 && prev != 0)
			return prev;
		return v;
	}

	protected static bool Down(KeyCode key)
	{
		return (Debug.KeyState(key) & 0x8000) != 0;
	}

	// Real time, not game time (at 3x the game's frame time is three times longer).
	protected void FreeMove(BaseWorld world)
	{
		int tick = System.GetTickCount();
		float dt = Math.Clamp((tick - m_iLastTick) / 1000.0, 0, 0.1);
		m_iLastTick = tick;
		// The game's own free camera input (Game Master's): its context and actions work with menus
		// open - raw key states didn't reach the game (Martin: "those keys don't work on free look").
		InputManager im = GetGame().GetInputManager();
		im.ActivateContext("ManualCameraContext");
		// Turning only while the right mouse button is held (Martin: "the mouse rotates the camera
		// always - right mouse only, like Arma"): the button from the click catcher, the turn from the
		// cursor's movement.
		int mx, my;
		WidgetManager.GetMousePos(mx, my);
		if (ZCR_WatchControls.RightDown() && m_iMouseX >= 0)
		{
			m_fYaw += (mx - m_iMouseX) * 0.2;
			m_fPitch = Math.Clamp(m_fPitch - (my - m_iMouseY) * 0.2, -85, 85);
		}
		if (ZCR_WatchControls.RightDown())
		{
			m_iMouseX = mx;
			m_iMouseY = my;
		}
		else
			m_iMouseX = -1;
		float y = m_fYaw * Math.DEG2RAD;
		float p = m_fPitch * Math.DEG2RAD;
		vector forward = Vector(Math.Sin(y) * Math.Cos(p), Math.Sin(p), Math.Cos(y) * Math.Cos(p));
		vector right = Vector(Math.Cos(y), 0, -Math.Sin(y));
		vector move = forward * im.GetActionValue("ManualCameraMoveLongitudinal") + right * im.GetActionValue("ManualCameraMoveLateral")
			+ Vector(0, im.GetActionValue("ManualCameraMoveVertical"), 0);
		if (Down(KeyCode.KC_W))
			move += forward;
		if (Down(KeyCode.KC_S))
			move -= forward;
		if (Down(KeyCode.KC_D))
			move += right;
		if (Down(KeyCode.KC_A))
			move -= right;
		if (Down(KeyCode.KC_E))
			move += Vector(0, 1, 0);
		if (Down(KeyCode.KC_Q))
			move -= Vector(0, 1, 0);
		float speed = 25;
		if (Down(KeyCode.KC_LSHIFT) || im.GetActionValue("ManualCameraSpeedBoost") > 0)
			speed = 100;
		m_vFreePos = m_vFreePos + move * speed * dt;
		float ground = world.GetSurfaceY(m_vFreePos[0], m_vFreePos[2]);
		if (m_vFreePos[1] < ground + 1.5)
			m_vFreePos[1] = ground + 1.5;
		m_Camera.SetOrigin(m_vFreePos);
		m_Camera.SetYawPitchRoll(Vector(m_fYaw, m_fPitch, 0));
		// Tags for the soldiers in front of the camera.
		m_vSpot = m_vFreePos + Vector(Math.Sin(y), 0, Math.Cos(y)) * 50;
		m_fToHeight = 50;
	}

	static bool IsOn()
	{
		return s_Instance != null;
	}

	static void Update(float timeslice)
	{
		if (!s_bChecked)
		{
			s_bChecked = true;
			// -zcrWatch: the game on screen (joining a lab server, or hosting a solo match itself).
			if (!System.IsCLIParam("zcrWatch"))
				return;
			s_Instance = new ZCR_Watch();
			s_Instance.m_FollowId = RplId.Invalid();
			Print("[ZCR][WATCH] watch mode on", LogLevel.NORMAL);
		}
		if (s_Instance)
			s_Instance.Tick(timeslice);
		SetSpeed();
	}

	// -zcrSpeed=3: the game's time multiplier set from script - the Diag Menu's Cheats > "DTime
	// multiplier" switch (engine ID 375) and value (376), found 19 Oct 23:21 in a game where the key
	// presses had set it (2.88 there). No more ~200 key presses at the start of a match: they fought
	// Martin's typing, landed in other menus and twice crashed the game. Diagnostic build, solo only.
	// Re-applied every 5 s (cheap) in case the game resets it; logs [ZCR][SPEED] once.
	protected static float s_fNextSpeed;
	protected static bool s_bSpeedLogged;

	protected static void SetSpeed()
	{
		string value;
		if (!System.GetCLIParam("zcrSpeed", value) || value.IsEmpty())
			return;
		float now = System.GetTickCount() / 1000.0;
		if (now < s_fNextSpeed)
			return;
		s_fNextSpeed = now + 5;
		float speed = Math.Clamp(value.ToFloat(), 0.1, 10);
		if (DiagMenu.GetEngineValue(375) != 1)
			DiagMenu.SetEngineValue(375, 1);
		if (Math.AbsFloat(DiagMenu.GetEngineRangeValue(376) - speed) > 0.01)
			DiagMenu.SetEngineRangeValue(376, speed);
		if (!s_bSpeedLogged && GetGame().GetWorld())
		{
			s_bSpeedLogged = true;
			Print(string.Format("[ZCR][SPEED] multiplier=%1 switch=%2 value=%3", speed, DiagMenu.GetEngineValue(375), DiagMenu.GetEngineRangeValue(376)), LogLevel.NORMAL);
		}
	}

	static void OnShot(vector target, float back, float height, RplId follow, string label)
	{
		if (!s_Instance)
			return;
		s_Instance.Aim(target, back, height, follow);
		if (s_Instance.m_Caption && !s_Instance.m_bFree)
			s_Instance.m_Caption.SetText(label);
		ZCR_WatchControls.OnLabel(label);
		Print(string.Format("[ZCR][CAM] t=%1 label=%2", ZCR_LossLog.Seconds(), label), LogLevel.NORMAL);
	}

	static void OnOverlay(string top, string left, string right, string bottom, string markers)
	{
		if (!s_Instance)
			return;
		if (s_Instance.m_Panel)
			s_Instance.m_Panel.SetText(top);
		if (s_Instance.m_Left)
			s_Instance.m_Left.SetText(left);
		if (s_Instance.m_Right)
			s_Instance.m_Right.SetText(right);
		if (s_Instance.m_Bottom)
			s_Instance.m_Bottom.SetText(bottom);
		s_Instance.ReadMarkers(markers);
	}

	protected void ReadMarkers(string text)
	{
		m_aMarkers.Clear();
		array<string> lines = {};
		text.Split("\n", lines, true);
		foreach (string line : lines)
		{
			array<string> f = {};
			line.Split(";", f, false);
			if (f.Count() < 7)
				continue;
			ZCR_WatchMarker m = new ZCR_WatchMarker();
			m.m_sKind = f[0];
			m.m_vPos = Vector(f[1].ToFloat(), f[2].ToFloat(), f[3].ToFloat());
			array<string> c = {};
			f[4].Split(" ", c, true);
			if (c.Count() == 3)
				m.m_Colour = new Color(c[0].ToFloat(), c[1].ToFloat(), c[2].ToFloat(), 1);
			else
				m.m_Colour = new Color(1, 1, 1, 1);
			m.m_fSize = f[5].ToFloat();
			m.m_sText = f[6];
			m_aMarkers.Insert(m);
		}
	}

	protected void Tick(float timeslice)
	{
		BaseWorld world = GetGame().GetWorld();
		if (!world || !GetGame().GetCameraManager())
			return;
		m_fClock += timeslice;
		if (m_fClock >= m_fNextMenuCheck)
		{
			m_fNextMenuCheck = m_fClock + 1;
			// Conflict's deploy and welcome screens closed - all menus but the controls' hidden one.
			MenuManager menus = GetGame().GetMenuManager();
			if (menus)
			{
				for (int guard; guard < 8; guard++)
				{
					MenuBase top = menus.GetTopMenu();
					if (!top || ZCR_WatchControls.IsHost(top))
						break;
					menus.CloseMenu(top);
				}
				ZCR_WatchControls.KeepHost(menus);
			}
			if (!m_Camera)
				Create(world);
			if (m_Camera && GetGame().GetCameraManager().CurrentCamera() != m_Camera)
				GetGame().GetCameraManager().SetCamera(m_Camera);
		}
		ZCR_WatchControls.Tick(m_fClock);
		if (m_Camera && m_bFree)
		{
			FreeMove(world);
			Draw(world);
			return;
		}
		if (!m_Camera || !m_bHasShot)
			return;
		Place(world);
		Draw(world);
	}

	protected Widget NewWidget(WidgetType type, int z, Widget parent)
	{
		return GetGame().GetWorkspace().CreateWidget(type, WidgetFlags.VISIBLE | WidgetFlags.IGNORE_CURSOR | WidgetFlags.NOFOCUS, Color.FromInt(Color.WHITE), z, parent);
	}

	protected TextWidget NewText(float x0, float y0, float x1, float y1, int size, float shade, Color tint = null, bool rich = false)
	{
		ImageWidget back = ImageWidget.Cast(NewWidget(WidgetType.ImageWidgetTypeID, 1001, m_Root));
		if (back)
		{
			FrameSlot.SetAnchorMin(back, x0, y0);
			FrameSlot.SetAnchorMax(back, x1, y1);
			FrameSlot.SetOffsets(back, 0, 0, 0, 0);
			if (tint)
				back.SetColor(new Color(tint.R(), tint.G(), tint.B(), shade));
			else
				back.SetColor(new Color(0, 0, 0, shade));
		}
		WidgetType kind = WidgetType.TextWidgetTypeID;
		if (rich)
			kind = WidgetType.RichTextWidgetTypeID;   // colours and bold, like Arma 3's structured text
		TextWidget text = TextWidget.Cast(NewWidget(kind, 1002, m_Root));
		if (text)
		{
			FrameSlot.SetAnchorMin(text, x0 + 0.01, y0 + 0.008);
			FrameSlot.SetAnchorMax(text, x1 - 0.01, y1);
			FrameSlot.SetOffsets(text, 0, 0, 0, 0);
			text.SetExactFontSize(size);
			text.SetTextWrapping(true);
		}
		return text;
	}

	protected void Create(BaseWorld world)
	{
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = Vector(0, 500, 0);
		m_Camera = CameraBase.Cast(GetGame().SpawnEntity(CameraBase, world, params));
		if (!m_Camera)
			return;
		m_Camera.SetVerticalFOV(55);
		m_Camera.SetFarPlane(5000);
		m_Root = NewWidget(WidgetType.FrameWidgetTypeID, 1000, null);
		FrameSlot.SetAnchorMin(m_Root, 0, 0);
		FrameSlot.SetAnchorMax(m_Root, 1, 1);
		FrameSlot.SetOffsets(m_Root, 0, 0, 0, 0);
		// Arma 3's layout: a panel per side - BLUFOR left, OPFOR right - the score along the top, the
		// lab's measures along the bottom, the shot's caption above them.
		m_Caption = NewText(0.26, 0.865, 0.74, 0.945, 22, 0.55);
		// Arma 3's panel look (ZC_fnc_debugPanel): black at 62%, the side's name in its colour, grey
		// section labels, captures green, losses red, attacks and storms yellow.
		m_Panel = NewText(0.26, 0.005, 0.74, 0.045, 20, 0.62, null, true);
		m_Left = NewText(0.004, 0.005, 0.252, 0.47, 15, 0.62, null, true);
		m_Right = NewText(0.748, 0.005, 0.996, 0.47, 15, 0.62, null, true);
		m_Bottom = NewText(0.004, 0.953, 0.996, 0.995, 16, 0.62, null, true);
		if (m_Left)
			m_Left.SetFont(FONT);
		if (m_Right)
			m_Right.SetFont(FONT);
		if (m_Bottom)
			m_Bottom.SetFont(FONT);
		if (m_Caption)
			m_Caption.SetFont(FONT_BOLD);
		if (m_Panel)
			m_Panel.SetFont(FONT);
		ZCR_WatchControls.Create();
	}

	protected void Aim(vector target, float back, float height, RplId follow)
	{
		if (!m_bHasShot)
		{
			m_vTo = target;
			m_fToBack = back;
			m_fToHeight = height;
		}
		m_bHasShot = true;
		// Glide from where the camera looks now (a followed unit may be far from the shot's start).
		m_vFrom = m_vSpot;
		if (m_vSpot == vector.Zero)
			m_vFrom = m_vTo;
		m_bFollowSeen = false;
		m_fFromBack = m_fToBack;
		m_fFromHeight = m_fToHeight;
		m_vTo = target;
		m_fToBack = back;
		m_fToHeight = height;
		m_fGlideStart = m_fClock;
		m_FollowId = follow;
	}

	protected IEntity Followed()
	{
		if (!m_FollowId.IsValid())
			return null;
		RplComponent rpl = RplComponent.Cast(Replication.FindItem(m_FollowId));
		if (!rpl)
			return null;
		return rpl.GetEntity();
	}

	protected void Place(BaseWorld world)
	{
		float k = Math.Clamp((m_fClock - m_fGlideStart) / 3, 0, 1);
		k = k * k * (3 - 2 * k);
		vector target = m_vTo;
		IEntity follow = Followed();
		if (follow)
		{
			target = follow.GetOrigin();
			m_vFollowSeen = target;
			m_bFollowSeen = true;
		}
		else if (m_FollowId.IsValid() && m_bFollowSeen)
		{
			// What we followed is gone - a drone that hit: stay on the spot to see what happened
			// (before, the camera went back to where the shot had started).
			target = m_vFollowSeen;
		}
		vector spot = m_vFrom + (target - m_vFrom) * k;
		m_vSpot = spot;
		float back = m_fFromBack + (m_fToBack - m_fFromBack) * k;
		float height = m_fFromHeight + (m_fToHeight - m_fFromHeight) * k;
		float ground = world.GetSurfaceY(spot[0], spot[2]);
		// Following something in the air (an FPV drone): the camera at its height, looking at it -
		// before, it looked at the ground 30 m below and the drone was a speck off the top (19 Oct).
		if (follow && k >= 1)
		{
			vector fp = follow.GetOrigin();
			if (fp[1] - ground > 5)
				ground = fp[1] - 2;
		}
		// Orbit (Martin: "free look on locked units - rotation"): the right mouse button held and dragged
		// turns the camera round what it shows, up and down too; it stays until AUTO.
		int mx, my;
		WidgetManager.GetMousePos(mx, my);
		if (ZCR_WatchControls.RightDown())
		{
			if (m_iOrbitX >= 0)
			{
				m_fOrbitYaw += (mx - m_iOrbitX) * 0.25;
				m_fOrbitLift = Math.Clamp(m_fOrbitLift + (my - m_iOrbitY) * 0.004, 0.2, 3);
			}
			m_iOrbitX = mx;
			m_iOrbitY = my;
		}
		else
			m_iOrbitX = -1;
		height = height * m_fOrbitLift;
		float oy = m_fOrbitYaw * Math.DEG2RAD;
		vector eye = Vector(spot[0] - Math.Sin(oy) * back, ground + height, spot[2] - Math.Cos(oy) * back);
		float eyeGround = world.GetSurfaceY(eye[0], eye[2]);
		// Above the ground under the camera: 8 m, 4 m for the close-ups (Martin: zoom the firefights more).
		float clearance = 8;
		if (height < 10)
			clearance = 4;
		if (eye[1] < eyeGround + clearance)
			eye[1] = eyeGround + clearance;
		vector look = Vector(spot[0], ground + 2, spot[2]) - eye;
		float pitch = Math.Atan2(look[1], Math.Sqrt(look[0] * look[0] + look[2] * look[2])) * Math.RAD2DEG;
		m_Camera.SetOrigin(eye);
		m_Camera.SetYawPitchRoll(Vector(m_fOrbitYaw, pitch, 0));
	}

	// The overlay: each marker projected onto the screen every frame.
	protected void Draw(BaseWorld world)
	{
		WorkspaceWidget workspace = GetGame().GetWorkspace();
		int used;
		foreach (ZCR_WatchMarker m : m_aMarkers)
		{
			vector screen = workspace.ProjWorldToScreen(m.m_vPos, world);
			if (screen[2] <= 0)
				continue;
			bool label = m.m_sKind == "B" || m.m_sKind == "G";
			Widget w = Pooled(used, label);
			used++;
			if (!w)
				break;
			w.SetVisible(true);
			if (label)
			{
				TextWidget t = TextWidget.Cast(w);
				t.SetText(m.m_sText);
				t.SetColor(m.m_Colour);
				t.SetExactFontSize(18);
				if (m.m_sKind == "G")
					t.SetExactFontSize(22);
				FrameSlot.SetPos(t, screen[0] - 60, screen[1] - 12);
				FrameSlot.SetSize(t, 260, 30);
			}
			else
			{
				float px = 9;
				if (m.m_sKind == "T")
					px = 6 + 10 * m.m_fSize;
				if (m.m_sKind == "L")
					px = 12;
				Color c = new Color(m.m_Colour.R(), m.m_Colour.G(), m.m_Colour.B(), 1);
				if (m.m_sKind == "L")
					c = new Color(m.m_Colour.R(), m.m_Colour.G(), m.m_Colour.B(), Math.Clamp(m.m_fSize, 0.25, 1));
				w.SetColor(c);
				FrameSlot.SetPos(w, screen[0] - px / 2, screen[1] - px / 2);
				FrameSlot.SetSize(w, px, px);
			}
		}
		used = DrawTags(world, workspace, used);
		used = DrawDrones(world, workspace, used);
		for (int i = used; i < m_aPool.Count(); i++)
			m_aPool[i].SetVisible(false);
	}

	// Soldier tags in close views (Arma 3 director, remark 67): when the camera is low, every soldier
	// within 90 m of the spot gets a small tag in his side's colour with his role.
	protected int DrawTags(BaseWorld world, WorkspaceWidget workspace, int used)
	{
		if (m_fToHeight > 140 || m_fClock - m_fGlideStart < 2)
			return used;
		if (m_fClock >= m_fNextNear)
		{
			m_fNextNear = m_fClock + 0.5;
			m_aNear.Clear();
			world.QueryEntitiesBySphere(m_vSpot, 90, OnNear, OnlyCharacters, EQueryEntitiesFlags.DYNAMIC);
		}
		// Soldiers in a vehicle: one tag over the vehicle - side, vehicle, how many aboard.
		map<IEntity, int> aboard = new map<IEntity, int>();
		map<IEntity, string> aboardSide = new map<IEntity, string>();
		foreach (IEntity e : m_aNear)
		{
			if (!e)
				continue;
			IEntity root = e.GetRootParent();
			if (root && root != e)
			{
				aboard.Set(root, aboard.Get(root) + 1);
				aboardSide.Set(root, ZCR_LossLog.SideOf(e));
			}
		}
		foreach (IEntity v, int n : aboard)
		{
			if (!v)
				continue;
			vector vs = workspace.ProjWorldToScreen(v.GetOrigin() + Vector(0, 3.5, 0), world);
			if (vs[2] <= 0)
				continue;
			Widget vw = Pooled(used, true);
			used++;
			if (!vw)
				return used;
			vw.SetVisible(true);
			TextWidget vt = TextWidget.Cast(vw);
			string vside = aboardSide.Get(v);
			vt.SetText(string.Format("%1 %2 (%3)", vside, VehicleName(v), n));
			vt.SetColor(Tint(vside));
			vt.SetExactFontSize(17);
			FrameSlot.SetPos(vt, vs[0] - 60, vs[1] - 12);
			FrameSlot.SetSize(vt, 300, 26);
		}
		foreach (IEntity e : m_aNear)
		{
			if (!e || e.GetRootParent() != e)
				continue;
			vector screen = workspace.ProjWorldToScreen(e.GetOrigin() + Vector(0, 2.3, 0), world);
			if (screen[2] <= 0)
				continue;
			Widget w = Pooled(used, true);
			used++;
			if (!w)
				break;
			w.SetVisible(true);
			TextWidget t = TextWidget.Cast(w);
			string role = ZCR_LossLog.ShortName(e);
			int cut = role.LastIndexOf("_");
			if (cut >= 0)
				role = role.Substring(cut + 1, role.Length() - cut - 1);
			string side = ZCR_LossLog.SideOf(e);
			t.SetText(side + " " + role);
			t.SetColor(Tint(side));
			t.SetExactFontSize(14);
			FrameSlot.SetPos(t, screen[0] - 40, screen[1] - 10);
			FrameSlot.SetSize(t, 200, 22);
		}
		return used;
	}

	// "M998", "UAZ452 transport" - from the vehicle's prefab name.
	protected static string VehicleName(IEntity v)
	{
		if (!v || !v.GetPrefabData())
			return "vehicle";
		string name = v.GetPrefabData().GetPrefabName();
		int slash = name.LastIndexOf("/");
		if (slash >= 0)
			name = name.Substring(slash + 1, name.Length() - slash - 1);
		name.Replace(".et", "");
		name.Replace("_", " ");
		return name;
	}

	// "FPV" over every drone of the commanders' teams in the air, in its side's colour.
	protected int DrawDrones(BaseWorld world, WorkspaceWidget workspace, int used)
	{
		for (int i; i < ZCR_Drones.s_aDrones.Count(); i++)
		{
			IEntity d = ZCR_Drones.s_aDrones[i];
			if (!d)
				continue;
			vector p = d.GetOrigin();
			if (p[1] - world.GetSurfaceY(p[0], p[2]) < 2)
				continue;
			vector screen = workspace.ProjWorldToScreen(p + Vector(0, 1.5, 0), world);
			if (screen[2] <= 0)
				continue;
			Widget w = Pooled(used, true);
			used++;
			if (!w)
				break;
			w.SetVisible(true);
			TextWidget t = TextWidget.Cast(w);
			t.SetText("v FPV " + ZCR_Drones.s_aDroneSide[i]);
			t.SetColor(Tint(ZCR_Drones.s_aDroneSide[i]));
			t.SetExactFontSize(20);
			FrameSlot.SetPos(t, screen[0] - 30, screen[1] - 26);
			FrameSlot.SetSize(t, 200, 28);
		}
		return used;
	}

	protected bool OnNear(IEntity entity)
	{
		ChimeraCharacter character = ChimeraCharacter.Cast(entity);
		if (character && character.GetCharacterController() && !character.GetCharacterController().IsDead())
			m_aNear.Insert(entity);
		return true;
	}

	protected bool OnlyCharacters(IEntity entity)
	{
		return ChimeraCharacter.Cast(entity) != null;
	}

	protected static Color Tint(string side)
	{
		if (side == "US")
			return new Color(0.35, 0.62, 1, 1);
		if (side == "USSR")
			return new Color(1, 0.35, 0.3, 1);
		if (side == "FIA")
			return new Color(0.4, 0.85, 0.4, 1);
		return new Color(0.9, 0.9, 0.9, 1);
	}

	// Widget number i of the pool, of the right type (text for labels, a square otherwise).
	protected Widget Pooled(int i, bool text)
	{
		if (i >= 300)
			return null;
		while (m_aPool.Count() <= i)
			m_aPool.Insert(null);
		Widget w = m_aPool[i];
		bool isText = TextWidget.Cast(w) != null;
		if (w && isText == text)
			return w;
		if (w)
			w.RemoveFromHierarchy();
		if (text)
		{
			w = NewWidget(WidgetType.TextWidgetTypeID, 1003, m_Root);
			TextWidget.Cast(w).SetFont(FONT_BOLD);
		}
		else
			w = NewWidget(WidgetType.ImageWidgetTypeID, 1003, m_Root);
		FrameSlot.SetAnchorMin(w, 0, 0);
		FrameSlot.SetAnchorMax(w, 0, 0);
		m_aPool[i] = w;
		return w;
	}
}
