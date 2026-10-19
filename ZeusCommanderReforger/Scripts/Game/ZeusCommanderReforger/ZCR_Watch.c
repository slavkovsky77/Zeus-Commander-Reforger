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
	}

	void ZCR_SendOverlay(string panel, string markers)
	{
		Rpc(RpcDo_ZCROverlay, panel, markers);
	}

	[RplRpc(RplChannel.Reliable, RplRcver.Broadcast)]
	protected void RpcDo_ZCRShot(vector target, float back, float height, RplId follow, string label, int seconds)
	{
		ZCR_Watch.OnShot(target, back, height, follow, label);
	}

	[RplRpc(RplChannel.Reliable, RplRcver.Broadcast)]
	protected void RpcDo_ZCROverlay(string panel, string markers)
	{
		ZCR_Watch.OnOverlay(panel, markers);
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

	static bool IsOn()
	{
		return s_Instance != null;
	}

	static void Update(float timeslice)
	{
		if (!s_bChecked)
		{
			s_bChecked = true;
			if (Replication.IsServer() || !System.IsCLIParam("zcrWatch"))
				return;
			s_Instance = new ZCR_Watch();
			s_Instance.m_FollowId = RplId.Invalid();
			Print("[ZCR][WATCH] watch mode on", LogLevel.NORMAL);
		}
		if (s_Instance)
			s_Instance.Tick(timeslice);
	}

	static void OnShot(vector target, float back, float height, RplId follow, string label)
	{
		if (!s_Instance)
			return;
		s_Instance.Aim(target, back, height, follow);
		if (s_Instance.m_Caption)
			s_Instance.m_Caption.SetText(label);
		Print(string.Format("[ZCR][CAM] t=%1 label=%2", ZCR_LossLog.Seconds(), label), LogLevel.NORMAL);
	}

	static void OnOverlay(string panel, string markers)
	{
		if (!s_Instance)
			return;
		if (s_Instance.m_Panel)
			s_Instance.m_Panel.SetText(panel);
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
			if (GetGame().GetMenuManager())
				GetGame().GetMenuManager().CloseAllMenus();
			if (!m_Camera)
				Create(world);
			if (m_Camera && GetGame().GetCameraManager().CurrentCamera() != m_Camera)
				GetGame().GetCameraManager().SetCamera(m_Camera);
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

	protected TextWidget NewText(float x0, float y0, float x1, float y1, int size, float shade)
	{
		ImageWidget back = ImageWidget.Cast(NewWidget(WidgetType.ImageWidgetTypeID, 1001, m_Root));
		if (back)
		{
			FrameSlot.SetAnchorMin(back, x0, y0);
			FrameSlot.SetAnchorMax(back, x1, y1);
			FrameSlot.SetOffsets(back, 0, 0, 0, 0);
			back.SetColor(new Color(0, 0, 0, shade));
		}
		TextWidget text = TextWidget.Cast(NewWidget(WidgetType.TextWidgetTypeID, 1002, m_Root));
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
		m_Caption = NewText(0.15, 0.84, 0.85, 0.95, 24, 0.55);
		m_Panel = NewText(0.005, 0.005, 0.55, 0.14, 17, 0.5);
		if (m_Caption)
			m_Caption.SetFont(FONT_BOLD);
		if (m_Panel)
			m_Panel.SetFont(FONT);
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
		m_vFrom = m_vTo;
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
			target = follow.GetOrigin();
		vector spot = m_vFrom + (target - m_vFrom) * k;
		float back = m_fFromBack + (m_fToBack - m_fFromBack) * k;
		float height = m_fFromHeight + (m_fToHeight - m_fFromHeight) * k;
		float ground = world.GetSurfaceY(spot[0], spot[2]);
		vector eye = Vector(spot[0], ground + height, spot[2] - back);
		float eyeGround = world.GetSurfaceY(eye[0], eye[2]);
		if (eye[1] < eyeGround + 8)
			eye[1] = eyeGround + 8;
		vector look = Vector(spot[0], ground + 2, spot[2]) - eye;
		float pitch = Math.Atan2(look[1], Math.Sqrt(look[0] * look[0] + look[2] * look[2])) * Math.RAD2DEG;
		m_Camera.SetOrigin(eye);
		m_Camera.SetYawPitchRoll(Vector(0, pitch, 0));
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
		for (int i = used; i < m_aPool.Count(); i++)
			m_aPool[i].SetVisible(false);
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
