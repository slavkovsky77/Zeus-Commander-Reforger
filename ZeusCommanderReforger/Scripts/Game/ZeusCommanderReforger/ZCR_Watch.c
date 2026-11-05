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

	// The caption alone (a followed team's distance and step, note 507): the camera stays where it is.
	void ZCR_SendCaption(string label)
	{
		Rpc(RpcDo_ZCRCaption, label);
		if (!System.IsConsoleApp())
			ZCR_Watch.OnCaption(label);
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
	protected void RpcDo_ZCRCaption(string label)
	{
		ZCR_Watch.OnCaption(label);
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
		ZCR_CostScope cost = new ZCR_CostScope("watch_hud");
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
	protected Widget m_TagRoot;
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
	protected ref array<IEntity> m_aNearVehicles = {};   // vehicles near the spot (their crews don't come up in the soldier query)
	// Free look: the camera is the watcher's - WASD, right mouse held to look, Shift faster, Q/E down/up.
	protected bool m_bFree;
	protected float m_fOrbitYaw;          // the watcher's turn round the shot (right mouse), 0 = from the south
	protected float m_fOrbitLift = 1;     // and up or down (height factor)
	protected float m_fOrbitZoom = 1;     // and nearer or farther (distance factor; the camera pad's / gamepad's zoom, 4 Nov)
	protected int m_iOrbitX = -1;
	protected int m_iOrbitY = -1;

	// AUTO puts the camera back to the director's angle.
	static void ResetOrbit()
	{
		if (!s_Instance)
			return;
		s_Instance.m_fOrbitYaw = 0;
		s_Instance.m_fOrbitLift = 1;
		s_Instance.m_fOrbitZoom = 1;
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

	// Where the director camera is (ZCR_AILod: AI detail by distance from it); false without one (a headless server).
	static bool CameraPos(out vector at)
	{
		if (!s_Instance || !s_Instance.m_Camera)
			return false;
		at = s_Instance.m_Camera.GetOrigin();
		return true;
	}

	// Every overlay off and on again (4 Nov - Martin: "there should be button to hide those gui elements in the game so we can
	// watch it nice"): the panels, the caption, the tags and the buttons but a small UI button (ZCR_WatchControls);
	// from the lab app's camera bar too (ZCR_Director.LabCamera).
	protected bool m_bHudHidden;

	// The camera pad's taps (4 Nov - Martin: "do camera controller in game maybe for phone i could hide it or open it make it
	// like rotation of camera and zoom i guess and wasd?", "something standard"): one step a tap in free look, starting from
	// the view on screen - move 20 m, up / down 8 m, turn 20 degrees, tilt 10, zoom 40 m along the view. AUTO gives the
	// camera back to the director.
	// The look stick and the zoom (4 Nov - Martin: "two modes locked and free, in free you can do wasd in locked only
	// rotation", "mimic two joysticks with +- also for zoom, all on right side"): not in free look, they turn the camera
	// round what it shows (20 degrees a tap), lift it and bring it nearer or farther; in free look as below.
	static void Look(string what)
	{
		if (!s_Instance || !s_Instance.m_Camera)
			return;
		if (s_Instance.m_bPano)
		{
			s_Instance.PanoLook(what);
			return;
		}
		if (s_Instance.m_bFree)
		{
			Nudge(what);
			return;
		}
		if (what == "turnl")
			s_Instance.m_fOrbitYaw = s_Instance.m_fOrbitYaw - 20;
		else if (what == "turnr")
			s_Instance.m_fOrbitYaw = s_Instance.m_fOrbitYaw + 20;
		else if (what == "tiltup")
			s_Instance.m_fOrbitLift = Math.Clamp(s_Instance.m_fOrbitLift + 0.2, 0.2, 3);
		else if (what == "tiltdn")
			s_Instance.m_fOrbitLift = Math.Clamp(s_Instance.m_fOrbitLift - 0.2, 0.2, 3);
		else if (what == "zin")
			s_Instance.m_fOrbitZoom = Math.Clamp(s_Instance.m_fOrbitZoom * 0.75, 0.3, 3);
		else if (what == "zout")
			s_Instance.m_fOrbitZoom = Math.Clamp(s_Instance.m_fOrbitZoom / 0.75, 0.3, 3);
	}

	static void Nudge(string what)
	{
		if (!s_Instance || !s_Instance.m_Camera)
			return;
		if (!s_Instance.m_bFree)
			SetFree(true);
		float y = s_Instance.m_fYaw * Math.DEG2RAD;
		float p = s_Instance.m_fPitch * Math.DEG2RAD;
		vector flat = Vector(Math.Sin(y), 0, Math.Cos(y));
		vector right = Vector(Math.Cos(y), 0, -Math.Sin(y));
		vector view = Vector(Math.Sin(y) * Math.Cos(p), Math.Sin(p), Math.Cos(y) * Math.Cos(p));
		if (what == "fwd")
			s_Instance.m_vFreePos = s_Instance.m_vFreePos + flat * 20;
		else if (what == "back")
			s_Instance.m_vFreePos = s_Instance.m_vFreePos - flat * 20;
		else if (what == "left")
			s_Instance.m_vFreePos = s_Instance.m_vFreePos - right * 20;
		else if (what == "right")
			s_Instance.m_vFreePos = s_Instance.m_vFreePos + right * 20;
		else if (what == "up")
			s_Instance.m_vFreePos = s_Instance.m_vFreePos + Vector(0, 8, 0);
		else if (what == "down")
			s_Instance.m_vFreePos = s_Instance.m_vFreePos - Vector(0, 8, 0);
		else if (what == "turnl")
			s_Instance.m_fYaw = s_Instance.m_fYaw - 20;
		else if (what == "turnr")
			s_Instance.m_fYaw = s_Instance.m_fYaw + 20;
		else if (what == "tiltup")
			s_Instance.m_fPitch = Math.Clamp(s_Instance.m_fPitch + 10, -85, 85);
		else if (what == "tiltdn")
			s_Instance.m_fPitch = Math.Clamp(s_Instance.m_fPitch - 10, -85, 85);
		else if (what == "zin")
			s_Instance.m_vFreePos = s_Instance.m_vFreePos + view * 40;
		else if (what == "zout")
			s_Instance.m_vFreePos = s_Instance.m_vFreePos - view * 40;
		if (s_Instance.m_Caption)
			s_Instance.m_Caption.SetText("FREE CAMERA - the left stick moves, the right one looks; CAMERA gives it back");
	}

	// The gamepad's toggle-UI button (the Game Master camera's ManualCameraToggleUI) hides / shows the overlays.
	protected void GamepadUi(InputManager im)
	{
		if (im && !im.IsUsingMouseAndKeyboard() && im.GetActionTriggered("ManualCameraToggleUI"))
			ToggleHud();
	}

	static void ToggleHud()
	{
		if (!s_Instance)
			return;
		s_Instance.m_bHudHidden = !s_Instance.m_bHudHidden;
		if (s_Instance.m_Root)
			s_Instance.m_Root.SetVisible(!s_Instance.m_bHudHidden);
		ZCR_WatchControls.SetHud(!s_Instance.m_bHudHidden);
		Print(string.Format("[ZCR][CAMUI] overlays %1", !s_Instance.m_bHudHidden), LogLevel.NORMAL);
	}

	static bool IsFree()
	{
		return s_Instance && s_Instance.m_bFree;
	}

	// PANORAMA (5 Nov - Martin: "something like panorama view like i would choose town and maybe position then i would start this
	// panorama style view where camera would move slowly around point", "imagine watching it from tv passively around town"): the
	// camera circles the spot it shows - a town picked with TYPE: POINTS, a tapped spot - starting from the view on screen, 2
	// degrees a second of real time (a lap in 3 min at any game speed), 150-700 m out and 40-300 m up. The overlays hide 4 s after
	// it starts and 8 s after the last tap; a tap brings them back, and with them up a tap on the picture circles that spot
	// instead, NEXT / PREV the next pick. The look stick: < > the turn (slower, still, the other way), tilt the height, zoom the
	// distance. PANORAMA or CAMERA again ends it.
	protected bool m_bPano;
	protected vector m_vPanoCenter;
	protected vector m_vPanoTo;          // where the centre glides to (a new spot)
	protected float m_fPanoAngle;        // the camera's yaw; it sits on the far side of the centre, looking at it
	protected float m_fPanoRate = 2;     // degrees a second, + to the right
	protected float m_fPanoR;            // wanted distance and height; the camera's glide to them
	protected float m_fPanoH;
	protected float m_fPanoRNow;
	protected float m_fPanoHNow;
	protected float m_fPanoLift;         // over a hill under the circle
	protected int m_iPanoLastMs;
	protected int m_iPanoShowMs;         // the overlays stay up until this (real time)
	protected int m_iPanoTakeShotMs = -100000;   // a pick asked for: the director's next shot moves the circle

	static bool IsPano()
	{
		return s_Instance && s_Instance.m_bPano;
	}

	static void TogglePano()
	{
		if (!s_Instance || !s_Instance.m_Camera)
			return;
		if (s_Instance.m_bPano)
			s_Instance.StopPano();
		else
			s_Instance.StartPano();
	}

	// A pick (NEXT / PREV, TYPE, the lab app's map) while circling: its shot moves the circle there.
	static void PanoTakeNextShot()
	{
		if (s_Instance && s_Instance.m_bPano)
			s_Instance.m_iPanoTakeShotMs = System.GetTickCount();
	}

	// A tap on the picture while circling, the overlays up: that spot.
	static void PanoAt(vector pos)
	{
		if (!s_Instance || !s_Instance.m_bPano || !Finite(pos))
			return;
		s_Instance.m_vPanoTo = pos;
		s_Instance.m_iPanoShowMs = System.GetTickCount() + 4000;
		Print(string.Format("[ZCR][CAMUI] pano at x=%1 z=%2", Math.Round(pos[0]), Math.Round(pos[2])), LogLevel.NORMAL);
	}

	protected void StartPano()
	{
		BaseWorld world = GetGame().GetWorld();
		if (!world)
			return;
		vector eye = m_Camera.GetOrigin();
		vector center = m_vSpot;
		if (m_bFree || center == vector.Zero)
			center = ViewGround(world, eye);
		if (m_bFree)
			SetFree(false);
		float dx = center[0] - eye[0];
		float dz = center[2] - eye[2];
		float dist = Math.Sqrt(dx * dx + dz * dz);
		float ground = world.GetSurfaceY(center[0], center[2]);
		m_fPanoAngle = Math.Atan2(dx, dz) * Math.RAD2DEG;
		m_fPanoRNow = Math.Max(dist, 1);
		m_fPanoHNow = eye[1] - ground;
		m_fPanoR = Math.Clamp(dist, 150, 700);
		m_fPanoH = Math.Clamp(m_fPanoHNow, 40, 300);
		// From a close-up: out to a view of the town.
		if (dist < 150)
		{
			m_fPanoR = 250;
			m_fPanoH = Math.Max(m_fPanoH, 80);
		}
		m_fPanoRate = 2;
		m_fPanoLift = 0;
		m_vPanoCenter = center;
		m_vPanoTo = center;
		int now = System.GetTickCount();
		m_iPanoLastMs = now;
		m_iPanoShowMs = now + 4000;
		m_bPano = true;
		if (m_Caption)
			m_Caption.SetText("PANORAMA - the camera circles this spot; tap for the controls, then tap the picture to circle another spot");
		Print(string.Format("[ZCR][CAMUI] pano on x=%1 z=%2 r=%3 h=%4", Math.Round(center[0]), Math.Round(center[2]), Math.Round(m_fPanoR), Math.Round(m_fPanoH)), LogLevel.NORMAL);
	}

	protected void StopPano()
	{
		m_bPano = false;
		// Back to the director's shot (or what is locked), gliding from the circle; the view keeps the circle's angle.
		m_vSpot = m_vPanoCenter;
		m_vFrom = m_vPanoCenter;
		m_fOrbitYaw = m_fPanoAngle;
		m_fFromBack = m_fPanoRNow / m_fOrbitZoom;
		m_fFromHeight = m_fPanoHNow / (m_fOrbitLift * m_fOrbitZoom);
		m_fGlideStart = m_fClock;
		if (m_bHudHidden)
			ToggleHud();
		Print("[ZCR][CAMUI] pano off", LogLevel.NORMAL);
	}

	// The ground in the middle of the picture (free look has no shot spot).
	protected vector ViewGround(BaseWorld world, vector eye)
	{
		vector ypr = m_Camera.GetYawPitchRoll();
		float y = ypr[0] * Math.DEG2RAD;
		float p = ypr[1] * Math.DEG2RAD;
		vector dir = Vector(Math.Sin(y) * Math.Cos(p), Math.Sin(p), Math.Cos(y) * Math.Cos(p));
		TraceParam t = new TraceParam();
		t.Start = eye;
		t.End = eye + dir * 4000;
		t.Flags = TraceFlags.WORLD;
		float f = world.TraceMove(t, null);
		vector hit = eye + dir * 4000 * f;
		if (f < 1 && Finite(hit))
			return hit;
		vector ahead = eye + Vector(Math.Sin(y), 0, Math.Cos(y)) * 250;
		ahead[1] = world.GetSurfaceY(ahead[0], ahead[2]);
		return ahead;
	}

	// The look stick while circling.
	protected void PanoLook(string what)
	{
		if (what == "turnl")
			m_fPanoRate = Math.Clamp(m_fPanoRate - 1, -6, 6);
		else if (what == "turnr")
			m_fPanoRate = Math.Clamp(m_fPanoRate + 1, -6, 6);
		else if (what == "tiltup")
			m_fPanoH = Math.Clamp(m_fPanoH * 1.25, 20, 450);
		else if (what == "tiltdn")
			m_fPanoH = Math.Clamp(m_fPanoH / 1.25, 20, 450);
		else if (what == "zin")
			m_fPanoR = Math.Clamp(m_fPanoR * 0.8, 60, 1000);
		else if (what == "zout")
			m_fPanoR = Math.Clamp(m_fPanoR / 0.8, 60, 1000);
		if (m_Caption)
			m_Caption.SetText(string.Format("PANORAMA - %1 degrees a second, %2 m out, %3 m up", m_fPanoRate, Math.Round(m_fPanoR), Math.Round(m_fPanoH)));
		Print(string.Format("[ZCR][CAMUI] pano look=%1 rate=%2 r=%3 h=%4", what, m_fPanoRate, Math.Round(m_fPanoR), Math.Round(m_fPanoH)), LogLevel.NORMAL);
	}

	// Real time, not game time (at 3x a lap would take a minute).
	protected void PanoMove(BaseWorld world)
	{
		int now = System.GetTickCount();
		float dt = Math.Clamp((now - m_iPanoLastMs) / 1000.0, 0, 0.1);
		m_iPanoLastMs = now;
		m_fPanoAngle += m_fPanoRate * dt;
		if (m_fPanoAngle > 360)
			m_fPanoAngle -= 360;
		else if (m_fPanoAngle < -360)
			m_fPanoAngle += 360;
		float glide = Math.Clamp(dt * 1.2, 0, 1);
		m_vPanoCenter = m_vPanoCenter + (m_vPanoTo - m_vPanoCenter) * Math.Clamp(dt * 0.8, 0, 1);
		m_fPanoRNow += (m_fPanoR - m_fPanoRNow) * glide;
		m_fPanoHNow += (m_fPanoH - m_fPanoHNow) * glide;
		vector c = m_vPanoCenter;
		float ground = world.GetSurfaceY(c[0], c[2]);
		float a = m_fPanoAngle * Math.DEG2RAD;
		vector eye = Vector(c[0] - Math.Sin(a) * m_fPanoRNow, ground + m_fPanoHNow, c[2] - Math.Cos(a) * m_fPanoRNow);
		// 15 m over a hill under the circle: up at once, down slowly (no bump as the camera passes it).
		float need = Math.Max(0, world.GetSurfaceY(eye[0], eye[2]) + 15 - eye[1]);
		if (need > m_fPanoLift)
			m_fPanoLift = need;
		else
			m_fPanoLift += (need - m_fPanoLift) * Math.Clamp(dt * 0.5, 0, 1);
		eye[1] = eye[1] + m_fPanoLift;
		vector look = Vector(c[0], ground + 2, c[2]) - eye;
		float pitch = Math.Atan2(look[1], Math.Sqrt(look[0] * look[0] + look[2] * look[2])) * Math.RAD2DEG;
		if (!Finite(eye) || pitch != pitch || m_fPanoAngle != m_fPanoAngle)
			return;
		m_Camera.SetOrigin(eye);
		m_Camera.SetYawPitchRoll(Vector(m_fPanoAngle, pitch, 0));
		m_vSpot = c;
		// Watched like TV: the overlays go 4 s after it starts or the circle moves, 8 s after the last tap.
		int quiet = m_iPanoShowMs;
		int tapQuiet = ZCR_WatchControls.LastTapMs() + 8000;
		if (tapQuiet > quiet)
			quiet = tapQuiet;
		if (!m_bHudHidden && now > quiet)
			ToggleHud();
	}

	// DETAILS (a watch button): the full label texts; off, the short ones (Martin, 21 Oct: "a details button
	// so the GUI is not overfilled with text"). Markers carry "short|full".
	protected static bool s_bDetails;

	static void ToggleDetails()
	{
		s_bDetails = !s_bDetails;
	}

	static bool Details()
	{
		return s_bDetails;
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
		// A gamepad (4 Nov - Martin: "maybe camera gamepad in the game for phone lol?" - Moonlight's on-screen gamepad): the
		// right stick looks round (the left one moves - the camera actions above), its toggle-UI button hides the overlays.
		if (!im.IsUsingMouseAndKeyboard())
		{
			m_fYaw += im.GetActionValue("ManualCameraRotateYaw") * 90 * dt;
			m_fPitch = Math.Clamp(m_fPitch + im.GetActionValue("ManualCameraRotatePitch") * 60 * dt, -85, 85);
			float zoomAxis = im.GetActionValue("ManualCameraZoom");
			if (zoomAxis != 0)
			{
				float zy = m_fYaw * Math.DEG2RAD;
				float zp = m_fPitch * Math.DEG2RAD;
				m_vFreePos = m_vFreePos + Vector(Math.Sin(zy) * Math.Cos(zp), Math.Sin(zp), Math.Cos(zy) * Math.Cos(zp)) * zoomAxis * 40 * dt;
			}
		}
		GamepadUi(im);
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
		if (!ZCR_Watch.Finite(m_vFreePos))
			m_vFreePos = m_Camera.GetOrigin();
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

	// -zcrDiagDump (5 Nov): Reforger's update to engine 193322 moved the Diag Menu's time multiplier off 375 / 376 - SPEED set them
	// and read them back, and the game ran at 1x (Martin: "speeding up game broke down hmm? maybe update?"). Every engine Diag value
	// that is not 0 is logged once, read only, in the old build and the new, to see where the entries went.
	protected static bool s_bDiagDumped;

	protected static void DiagDump()
	{
		if (s_bDiagDumped || !GetGame().GetWorld())
			return;
		s_bDiagDumped = true;
		if (!System.IsCLIParam("zcrDiagDump"))
			return;
		int shown;
		for (int id = 0; id < 1024; id++)
		{
			int v = DiagMenu.GetEngineValue(id);
			float r = DiagMenu.GetEngineRangeValue(id);
			if (v == 0 && r == 0)
				continue;
			shown++;
			Print(string.Format("[ZCR][DIAG] id=%1 v=%2 r=%3", id, v, r), LogLevel.NORMAL);
		}
		Print(string.Format("[ZCR][DIAG] done shown=%1 scale=%2", shown, GetGame().GetWorld().GetTimeScale()), LogLevel.NORMAL);
	}

	// The time multiplier's Diag Menu entries: the switch and the value (375 / 376 to engine 192142). Reforger's update of 5 Nov
	// (engine 193322) moved them - SPEED set 375 / 376 and the game stayed at 1x - so they are found by what they do: SPEED asked
	// for 2x or 3x and the world still at 1x 10 s later (or -zcrSpeedProbe), every engine range value of 1 in 200-799 is set to
	// 3 for 1.2 s, the bool entry before it on with it, nearest to 401 first; the world's time scale is read (the Game Master
	// camera divides by it) and the values set back. The one that runs the world at 3x is kept for this session and logged
	// [ZCR][SPEEDPROBE] found=; then it goes in here. Engine 193322: 400 / 401 (found 5 Nov 17:45, the first candidate - 2.7x at 3).
	protected static int s_iSpeedSwitch = 400;
	protected static int s_iSpeedRange = 401;
	protected static int s_iProbeStage;        // 0 not asked, 1 asked, 2 running, 3 done
	protected static int s_iProbeAskedAt;
	protected static ref array<int> s_aProbe;
	protected static int s_iProbeIdx;
	protected static int s_iProbeAt;           // real time the candidate was set; 0: none set
	protected static float s_fProbeWorld0;
	protected static int s_iProbeOldV;
	protected static float s_fProbeOldR;
	protected static bool s_bProbeSwitched;

	protected static void ProbeAsk(string why)
	{
		if (s_iProbeStage != 0)
			return;
		s_iProbeStage = 1;
		s_iProbeAskedAt = System.GetTickCount();
		Print(string.Format("[ZCR][SPEEDPROBE] asked why=%1", why), LogLevel.NORMAL);
	}

	protected static void ProbeTick()
	{
		BaseWorld world = GetGame().GetWorld();
		if (!world)
			return;
		int now = System.GetTickCount();
		if (s_iProbeStage == 0 && System.IsCLIParam("zcrSpeedProbe"))
			ProbeAsk("cli");
		if (s_iProbeStage == 1)
		{
			// 20 s after it was asked: the world loaded and running.
			if (now - s_iProbeAskedAt < 20000)
				return;
			s_aProbe = {};
			for (int d = 0; d < 300; d++)
			{
				for (int sgn = 0; sgn < 2; sgn++)
				{
					int k = 401 + d;
					if (sgn == 1)
						k = 401 - d - 1;
					if (k < 200 || k >= 800)
						continue;
					if (Math.AbsFloat(DiagMenu.GetEngineRangeValue(k) - 1) < 0.001)
						s_aProbe.Insert(k);
				}
			}
			s_iProbeStage = 2;
			s_iProbeIdx = 0;
			s_iProbeAt = 0;
			Print(string.Format("[ZCR][SPEEDPROBE] start candidates=%1 scale=%2", s_aProbe.Count(), world.GetTimeScale()), LogLevel.NORMAL);
		}
		if (s_iProbeStage != 2)
			return;
		if (s_iProbeAt == 0)
		{
			if (s_iProbeIdx >= s_aProbe.Count())
			{
				// Not found: SPEED writes nothing (the old entries are something else in this build).
				s_iProbeStage = 3;
				s_iSpeedSwitch = -1;
				Print("[ZCR][SPEEDPROBE] not found", LogLevel.NORMAL);
				return;
			}
			int c = s_aProbe[s_iProbeIdx];
			s_fProbeOldR = DiagMenu.GetEngineRangeValue(c);
			s_iProbeOldV = DiagMenu.GetEngineValue(c - 1);
			s_bProbeSwitched = s_iProbeOldV == 0;
			DiagMenu.SetEngineRangeValue(c, 3);
			if (s_bProbeSwitched)
				DiagMenu.SetEngineValue(c - 1, 1);
			s_iProbeAt = now;
			s_fProbeWorld0 = world.GetWorldTime();
			return;
		}
		if (now - s_iProbeAt < 1200)
			return;
		int cand = s_aProbe[s_iProbeIdx];
		float scale = world.GetTimeScale();
		float rate = (world.GetWorldTime() - s_fProbeWorld0) / Math.Max(1, now - s_iProbeAt);
		bool found = scale > 2.2 || rate > 2.2;
		Print(string.Format("[ZCR][SPEEDPROBE] id=%1 switch=%2 scale=%3 rate=%4", cand, s_bProbeSwitched, scale, rate), LogLevel.NORMAL);
		DiagMenu.SetEngineRangeValue(cand, s_fProbeOldR);
		if (s_bProbeSwitched)
			DiagMenu.SetEngineValue(cand - 1, s_iProbeOldV);
		s_iProbeAt = 0;
		s_iProbeIdx++;
		if (!found)
			return;
		s_iSpeedRange = cand;
		s_iSpeedSwitch = cand - 1;
		s_iProbeStage = 3;
		s_fNextSpeed = 0;
		s_bSpeedLogged = false;
		Print(string.Format("[ZCR][SPEEDPROBE] found= switch=%1 value=%2 (the switch was off: %3)", s_iSpeedSwitch, s_iSpeedRange, s_bProbeSwitched), LogLevel.NORMAL);
	}

	static void Update(float timeslice)
	{
		DiagDump();
		ProbeTick();
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
	// multiplier" switch (engine ID 375) and value (376; 400 / 401 since the update of 5 Nov), found 19 Oct 23:21 in a game where the key
	// presses had set it (2.88 there). No more ~200 key presses at the start of a match: they fought
	// Martin's typing, landed in other menus and twice crashed the game. Diagnostic build, solo only.
	// Re-applied every 5 s (cheap) in case the game resets it; logs [ZCR][SPEED] once.
	protected static float s_fNextSpeed;
	protected static bool s_bSpeedLogged;
	protected static bool s_bSpeedTouched;
	protected static int s_iScaleChecks;
	// The SPEED button (Martin, 21 Oct 21:40: "can I set the speed of the game? ... if the speed affects the
	// crazy AI driving"): 3x -> 1x -> 2x -> 3x from the screen, over -zcrSpeed; each change logs [ZCR][SPEED].
	protected static float s_fSpeedOverride;

	static void CycleSpeed()
	{
		float cur = Speed();
		if (cur >= 2.5)
			s_fSpeedOverride = 1;
		else if (cur >= 1.5)
			s_fSpeedOverride = 3;
		else
			s_fSpeedOverride = 2;
		s_fNextSpeed = 0;
		s_bSpeedLogged = false;
		SetSpeed();
	}

	static string SpeedLabel()
	{
		float s = Speed();
		if (s <= 0)
			return "SPEED 1x";
		int r = Math.Round(s);
		return string.Format("SPEED %1x", r);
	}

	// The speed wanted: the button's choice, else -zcrSpeed, else 0 (the game's own).
	protected static float Speed()
	{
		if (s_fSpeedOverride > 0)
			return s_fSpeedOverride;
		string value;
		if (!System.GetCLIParam("zcrSpeed", value) || value.IsEmpty())
			return 0;
		return Math.Clamp(value.ToFloat(), 0.1, 10);
	}

	protected static void SetSpeed()
	{
		float speed = Speed();
		if (speed <= 0)
			return;
		// Not while the entries are being looked for (the probe sets and restores them itself).
		if (s_iProbeStage == 1 || s_iProbeStage == 2 || s_iSpeedSwitch < 0)
			return;
		// 1x and never changed: nothing to write (wrong entries after an update are then left alone).
		if (speed > 1.01 || speed < 0.99)
			s_bSpeedTouched = true;
		if (!s_bSpeedTouched)
			return;
		float now = System.GetTickCount() / 1000.0;
		if (now < s_fNextSpeed)
			return;
		s_fNextSpeed = now + 5;
		if (DiagMenu.GetEngineValue(s_iSpeedSwitch) != 1)
			DiagMenu.SetEngineValue(s_iSpeedSwitch, 1);
		if (Math.AbsFloat(DiagMenu.GetEngineRangeValue(s_iSpeedRange) - speed) > 0.01)
			DiagMenu.SetEngineRangeValue(s_iSpeedRange, speed);
		BaseWorld world = GetGame().GetWorld();
		if (!world)
			return;
		if (!s_bSpeedLogged)
		{
			s_bSpeedLogged = true;
			s_iScaleChecks = 2;
			Print(string.Format("[ZCR][SPEED] multiplier=%1 switch=%2 value=%3 ids=%4/%5 scale=%6", speed, DiagMenu.GetEngineValue(s_iSpeedSwitch), DiagMenu.GetEngineRangeValue(s_iSpeedRange), s_iSpeedSwitch, s_iSpeedRange, world.GetTimeScale()), LogLevel.NORMAL);
		}
		// What the world really runs at, 5 and 10 s later (the update of 5 Nov: the values took, the game stayed at 1x); still
		// 1x at 2x or 3x - the entries moved: look for them (the game window only - a dedicated server has no Diag Menu).
		else if (s_iScaleChecks > 0)
		{
			s_iScaleChecks--;
			float scale = world.GetTimeScale();
			Print(string.Format("[ZCR][SPEED] wanted=%1 scale=%2", speed, scale), LogLevel.NORMAL);
			if (s_iScaleChecks == 0 && speed >= 1.5 && scale < 1.3 && s_Instance)
			{
				ProbeAsk("scale");
				s_iProbeAskedAt = System.GetTickCount() - 20000;
			}
		}
	}

	static void OnShot(vector target, float back, float height, RplId follow, string label)
	{
		if (!s_Instance)
			return;
		s_Instance.Aim(target, back, height, follow);
		// Circling: only a shot asked for (a pick) moves the circle; the director's own shots leave it.
		if (s_Instance.m_bPano && System.GetTickCount() - s_Instance.m_iPanoTakeShotMs < 3000)
		{
			s_Instance.m_iPanoTakeShotMs = -100000;
			PanoAt(target);
		}
		if (s_Instance.m_Caption && !s_Instance.m_bFree && !s_Instance.m_bPano)
			s_Instance.m_Caption.SetText(label);
		ZCR_WatchControls.OnLabel(label);
		Print(string.Format("[ZCR][CAM] t=%1 label=%2", ZCR_LossLog.Seconds(), label), LogLevel.NORMAL);
	}

	static void OnCaption(string label)
	{
		if (!s_Instance)
			return;
		if (s_Instance.m_Caption && !s_Instance.m_bFree && !s_Instance.m_bPano)
			s_Instance.m_Caption.SetText(label);
		ZCR_WatchControls.OnLabel(label);
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
		if (m_Camera && m_bPano)
		{
			PanoMove(world);
			Draw(world);
			return;
		}
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
		// The tags on soldiers, vehicles and drones on their own layer: HIDE UI leaves them (5 Nov - Martin: "when you show ui/hide ui
		// you should still show tag on vehicles, units and drones now it hides everything").
		m_TagRoot = NewWidget(WidgetType.FrameWidgetTypeID, 1000, null);
		FrameSlot.SetAnchorMin(m_TagRoot, 0, 0);
		FrameSlot.SetAnchorMax(m_TagRoot, 1, 1);
		FrameSlot.SetOffsets(m_TagRoot, 0, 0, 0, 0);
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
		// turns the camera round what it shows, up and down too; it stays until AUTO. A gamepad's right stick too (4 Nov).
		InputManager orbitIm = GetGame().GetInputManager();
		orbitIm.ActivateContext("ManualCameraContext");
		if (!orbitIm.IsUsingMouseAndKeyboard())
		{
			float orbitDt = 1.0 / 60;
			m_fOrbitYaw += orbitIm.GetActionValue("ManualCameraRotateYaw") * 90 * orbitDt;
			m_fOrbitLift = Math.Clamp(m_fOrbitLift - orbitIm.GetActionValue("ManualCameraRotatePitch") * 0.6 * orbitDt, 0.2, 3);
			m_fOrbitZoom = Math.Clamp(m_fOrbitZoom - orbitIm.GetActionValue("ManualCameraZoom") * 0.8 * orbitDt, 0.3, 3);
		}
		GamepadUi(orbitIm);
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
		height = height * m_fOrbitLift * m_fOrbitZoom;
		back = back * m_fOrbitZoom;
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
		// A followed drone or vehicle with a NaN position would hand the camera a NaN transform - the engine asserts on
		// it (25 Oct: 6 crashes on a bad matrix, drones flying before each): keep last frame's view instead.
		if (!Finite(eye) || pitch != pitch || m_fOrbitYaw != m_fOrbitYaw)
			return;
		m_Camera.SetOrigin(eye);
		m_Camera.SetYawPitchRoll(Vector(m_fOrbitYaw, pitch, 0));
	}

	static bool Finite(vector v)
	{
		for (int i; i < 3; i++)
		{
			float f = v[i];
			if (f != f || Math.AbsFloat(f) > 100000)
				return false;
		}
		return true;
	}

	// The overlay: each marker projected onto the screen every frame.
	protected void Draw(BaseWorld world)
	{
		WorkspaceWidget workspace = GetGame().GetWorkspace();
		int used;
		// High up (the overview, the map of the points): only the points with their supplies and tasks and the
		// buildings going up, at their spot (Martin: "in the map just supply, if a supply run is expected on a
		// point, or if fortifications are being built"); DETAILS shows everything.
		bool overview;
		if (m_Camera)
		{
			vector eye = m_Camera.GetOrigin();
			overview = eye[1] - world.GetSurfaceY(eye[0], eye[2]) > 450;
		}
		foreach (ZCR_WatchMarker m : m_aMarkers)
		{
			if (overview && !s_bDetails && (m.m_sKind == "S" || m.m_sKind == "A" || m.m_sKind == "F" || m.m_sKind == "L" || m.m_sKind == "T"))
				continue;
			// HIDE UI: of the markers only the armour's tags stay (with the soldiers', vehicles' and drones' below).
			if (m_bHudHidden && m.m_sKind != "A")
				continue;
			vector screen = workspace.ProjWorldToScreen(m.m_vPos, world);
			if (screen[2] <= 0)
				continue;
			// Labels: bases, goals, supply trucks (S), fortifications (F), buildings going up (C), armour (A).
			bool label = m.m_sKind == "B" || m.m_sKind == "G" || m.m_sKind == "S" || m.m_sKind == "F" || m.m_sKind == "C" || m.m_sKind == "A";
			Widget w = Pooled(used, label);
			used++;
			if (!w)
				break;
			w.SetVisible(true);
			if (label)
			{
				TextWidget t = TextWidget.Cast(w);
				string text = m.m_sText;
				int bar = text.IndexOf("|");
				if (bar >= 0)
				{
					if (s_bDetails)
						text = text.Substring(bar + 1, text.Length() - bar - 1);
					else
						text = text.Substring(0, bar);
				}
				t.SetText(text);
				t.SetColor(m.m_Colour);
				t.SetExactFontSize(18);
				if (m.m_sKind == "G")
					t.SetExactFontSize(22);
				float width = 260;
				if (m.m_sKind == "S" || m.m_sKind == "C" || m.m_sKind == "A")
				{
					t.SetExactFontSize(15);
					width = 420;
				}
				if (s_bDetails && m.m_sKind == "B")
					width = 640;
				if (m.m_sKind == "F")
					t.SetExactFontSize(13);
				FrameSlot.SetPos(t, screen[0] - 60, screen[1] - 12);
				FrameSlot.SetSize(t, width, 30);
			}
			else
			{
				float px = 9;
				if (m.m_sKind == "T")
					px = 6 + 10 * m.m_fSize;
				// The point's supply dot, just left of its label (green / amber / red by level).
				if (m.m_sKind == "Y")
				{
					w.SetColor(m.m_Colour);
					FrameSlot.SetPos(w, screen[0] - 80, screen[1] - 4);
					FrameSlot.SetSize(w, 14, 14);
					continue;
				}
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
		used = DrawOperators(world, workspace, used);
		for (int i = used; i < m_aPool.Count(); i++)
			m_aPool[i].SetVisible(false);
	}

	// Soldier tags in close views (Arma 3 director, remark 67): when the camera is low, every soldier
	// within 90 m of the spot gets a small tag in his side's colour with his role.
	protected int DrawTags(BaseWorld world, WorkspaceWidget workspace, int used)
	{
		if (m_bPano)
		{
			if (m_fPanoHNow > 140)
				return used;
		}
		else if (m_fToHeight > 140 || m_fClock - m_fGlideStart < 2)
			return used;
		if (m_fClock >= m_fNextNear)
		{
			m_fNextNear = m_fClock + 0.5;
			m_aNear.Clear();
			world.QueryEntitiesBySphere(m_vSpot, 90, OnNear, OnlyCharacters, EQueryEntitiesFlags.DYNAMIC);
			m_aNearVehicles.Clear();
			world.QueryEntitiesBySphere(m_vSpot, 90, OnNearVehicle, OnlyVehicles, EQueryEntitiesFlags.DYNAMIC);
		}
		// Soldiers in a vehicle: one tag over the vehicle - side, vehicle, how many aboard.
		map<IEntity, int> aboard = new map<IEntity, int>();
		map<IEntity, string> aboardSide = new map<IEntity, string>();
		map<IEntity, int> aboardDead = new map<IEntity, int>();      // the dead in its seats (5 Nov)
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
		// Vehicles found directly, crews counted from their seats (25 Oct - Martin: "I still don't see tags over vehicles":
		// seated crews didn't come up in the soldier query, so no vehicle ever got a tag); a vehicle with a mission (a test
		// van, a supply truck) gets its tag even empty.
		foreach (IEntity veh : m_aNearVehicles)
		{
			if (!veh || aboard.Contains(veh))
				continue;
			array<BaseCompartmentSlot> seats = {};
			AICF_FIAPatrolCrew.Seats(veh, seats);
			// The dead are no crew (5 Nov - Martin: "like it seem vehicles have tags soldiers seem dead or something": a jeep an FPV
			// killed all four in read "US M998 (4)"); they are shown as dead.
			int crew, dead;
			string crewSide, deadSide;
			foreach (BaseCompartmentSlot seat : seats)
			{
				if (!seat || !seat.GetOccupant())
					continue;
				ChimeraCharacter occupant = ChimeraCharacter.Cast(seat.GetOccupant());
				if (occupant && occupant.GetCharacterController() && occupant.GetCharacterController().GetLifeState() == ECharacterLifeState.DEAD)
				{
					dead++;
					if (deadSide.IsEmpty())
						deadSide = ZCR_LossLog.SideOf(occupant);
					continue;
				}
				crew++;
				if (crewSide.IsEmpty())
					crewSide = ZCR_LossLog.SideOf(seat.GetOccupant());
			}
			if (crew == 0 && dead == 0 && ZCR_VehicleTag.Mission(veh).IsEmpty())
				continue;
			if (crewSide.IsEmpty())
				crewSide = deadSide;
			aboard.Set(veh, crew);
			aboardSide.Set(veh, crewSide);
			aboardDead.Set(veh, dead);
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
			// The vehicle's mission on a second line (25 Oct - Martin: "why don't vehicles have tags with their mission and
			// supplies?"): a test van's goal and cargo, an AI Conflict supply truck's run and cargo (ZCR_VehicleTag).
			string mission = ZCR_VehicleTag.Mission(v);
			string vtext = string.Format("%1 %2 (%3)", vside, VehicleName(v), n);
			if (aboardDead.Get(v) > 0)
				vtext = string.Format("%1 %2 (%3 + %4 dead)", vside, VehicleName(v), n, aboardDead.Get(v));
			if (!mission.IsEmpty())
				vtext += "\n" + mission;
			vt.SetText(vtext);
			vt.SetColor(Tint(vside));
			vt.SetExactFontSize(17);
			FrameSlot.SetPos(vt, vs[0] - 60, vs[1] - 30);
			FrameSlot.SetSize(vt, 560, 50);
		}
		foreach (IEntity e : m_aNear)
		{
			if (!e || e.GetRootParent() != e || ZCR_DroneOperator.IsOperator(e))   // operators: their own tag (DrawOperators)
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

	// Drone operators (Martin, 24 Oct 15:32: "the drone operator should be seen in the GUI with some tag that this is a
	// drone operator, so I know how it works"): at any height, in the side's colour - "US DRONE OPERATOR - flying FPV"
	// over the pilot (while a drone of his is up), "US drone operator's guard" over the other (close views only).
	protected int DrawOperators(BaseWorld world, WorkspaceWidget workspace, int used)
	{
		foreach (ZCR_OperatorMan m : ZCR_DroneOperator.s_aMen)
		{
			ChimeraCharacter c = ChimeraCharacter.Cast(m.m_Man);
			if (!c || !c.GetCharacterController() || c.GetCharacterController().GetLifeState() == ECharacterLifeState.DEAD)
				continue;
			if (!m.m_bPilot && m_fToHeight > 140)
				continue;
			vector screen = workspace.ProjWorldToScreen(c.GetOrigin() + Vector(0, 2.4, 0), world);
			if (screen[2] <= 0)
				continue;
			Widget w = Pooled(used, true);
			used++;
			if (!w)
				break;
			w.SetVisible(true);
			TextWidget t = TextWidget.Cast(w);
			string text = m.m_sSide + " drone operator's guard";
			int size = 14;
			if (m.m_bPilot)
			{
				text = m.m_sSide + " DRONE OPERATOR";
				if (m.m_bFlying)
					text += " - flying FPV";
				size = 18;
			}
			t.SetText(text);
			t.SetColor(Tint(m.m_sSide));
			t.SetExactFontSize(size);
			FrameSlot.SetPos(t, screen[0] - 60, screen[1] - 14);
			FrameSlot.SetSize(t, 360, 26);
		}
		return used;
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

	protected bool OnNearVehicle(IEntity entity)
	{
		if (Vehicle.Cast(entity))
			m_aNearVehicles.Insert(entity);
		return true;
	}

	protected bool OnlyVehicles(IEntity entity)
	{
		return Vehicle.Cast(entity) != null;
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
			w = NewWidget(WidgetType.TextWidgetTypeID, 1003, m_TagRoot);
			TextWidget.Cast(w).SetFont(FONT_BOLD);
		}
		else
			w = NewWidget(WidgetType.ImageWidgetTypeID, 1003, m_TagRoot);
		FrameSlot.SetAnchorMin(w, 0, 0);
		FrameSlot.SetAnchorMax(w, 0, 0);
		m_aPool[i] = w;
		return w;
	}
}
