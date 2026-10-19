// Watch mode: the game on screen as a camera over an AI-only match, as the Arma 3 lab's camera
// director does (ac-lab lab/director.sqf). Started with -zcrWatch on the client; the lab server
// runs with -zcrWatchServer so this player gets every unit on the map, not only those near him.
// No side is picked: the game's menus are closed and our camera takes over.
//
// Every shot (about 20 s) it films the busiest spot: where soldiers of both sides are closest to
// each other (a fight), else the biggest group on the move, and every 4th shot a high view over
// the whole fighting area. RTS view: south of the spot, looking north and steeply down, gliding
// 3 s from shot to shot. A caption says what is shown. Every shot is logged as [ZCR][CAM] so the
// lab's recorder can list it in the video's moments.

// Server: no distance streaming for players of a lab server (they only watch).
modded class SCR_BaseGameMode
{
	override void OnPlayerConnected(int playerId)
	{
		super.OnPlayerConnected(playerId);
		if (!Replication.IsServer() || !System.IsCLIParam("zcrWatchServer"))
			return;
		PlayerController controller = GetGame().GetPlayerManager().GetPlayerController(playerId);
		if (!controller)
			return;
		RplComponent.EnableStreamingForConnection(controller.GetRplIdentity(), false);
		Print(string.Format("[ZCR][WATCH] player=%1 streaming=off (sees the whole map)", playerId), LogLevel.NORMAL);
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

// Client: runs the director from the game's frame update.
modded class ArmaReforgerScripted
{
	override void OnUpdate(BaseWorld world, float timeslice)
	{
		super.OnUpdate(world, timeslice);
		ZCR_Watch.Update(timeslice);
	}
}

class ZCR_Watch
{
	protected static ref ZCR_Watch s_Instance;
	protected static bool s_bChecked;

	protected CameraBase m_Camera;
	protected TextWidget m_Caption;
	protected float m_fClock;
	protected float m_fNextMenuCheck;
	protected float m_fShotEnd;
	protected int m_iShot;
	protected vector m_vFrom;
	protected vector m_vTo;
	protected float m_fFromBack = 600;
	protected float m_fFromHeight = 700;
	protected float m_fToBack = 600;
	protected float m_fToHeight = 700;
	protected float m_fGlideStart;
	protected IEntity m_Follow;
	protected ref array<IEntity> m_aFound = {};

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
			Print("[ZCR][WATCH] watch mode on", LogLevel.NORMAL);
		}
		if (s_Instance)
			s_Instance.Tick(timeslice);
	}

	protected void Tick(float timeslice)
	{
		BaseWorld world = GetGame().GetWorld();
		if (!world || !GetGame().GetCameraManager())
			return;
		m_fClock += timeslice;

		// Once a second: no menus over the picture, our camera in use.
		if (m_fClock >= m_fNextMenuCheck)
		{
			m_fNextMenuCheck = m_fClock + 1;
			if (GetGame().GetMenuManager())
				GetGame().GetMenuManager().CloseAllMenus();
			if (!m_Camera)
				CreateCamera(world);
			if (m_Camera && GetGame().GetCameraManager().CurrentCamera() != m_Camera)
				GetGame().GetCameraManager().SetCamera(m_Camera);
		}
		if (!m_Camera)
			return;
		if (m_fClock >= m_fShotEnd || (m_Follow && !Alive(m_Follow)))
			NextShot(world);
		Place(world);
	}

	protected void CreateCamera(BaseWorld world)
	{
		EntitySpawnParams params = new EntitySpawnParams();
		params.TransformMode = ETransformMode.WORLD;
		params.Transform[3] = Vector(0, 500, 0);
		m_Camera = CameraBase.Cast(GetGame().SpawnEntity(CameraBase, world, params));
		if (!m_Camera)
			return;
		m_Camera.SetVerticalFOV(55);
		m_Camera.SetFarPlane(6000);
		Widget root = GetGame().GetWorkspace().CreateWidget(WidgetType.FrameWidgetTypeID, WidgetFlags.VISIBLE | WidgetFlags.IGNORE_CURSOR | WidgetFlags.NOFOCUS, Color.FromInt(Color.WHITE), 1000);
		FrameSlot.SetAnchorMin(root, 0, 0);
		FrameSlot.SetAnchorMax(root, 1, 1);
		FrameSlot.SetOffsets(root, 0, 0, 0, 0);
		m_Caption = TextWidget.Cast(GetGame().GetWorkspace().CreateWidget(WidgetType.TextWidgetTypeID, WidgetFlags.VISIBLE | WidgetFlags.IGNORE_CURSOR | WidgetFlags.NOFOCUS, Color.FromInt(Color.WHITE), 1001, root));
		if (m_Caption)
		{
			FrameSlot.SetAnchorMin(m_Caption, 0.2, 0.86);
			FrameSlot.SetAnchorMax(m_Caption, 0.8, 0.95);
			FrameSlot.SetOffsets(m_Caption, 0, 0, 0, 0);
			m_Caption.SetExactFontSize(26);
			m_Caption.SetTextWrapping(true);
		}
	}

	protected static bool Alive(IEntity entity)
	{
		ChimeraCharacter character = ChimeraCharacter.Cast(entity);
		if (!character)
			return false;
		CharacterControllerComponent controller = character.GetCharacterController();
		return controller && !controller.IsDead();
	}

	protected static string Side(IEntity entity)
	{
		FactionAffiliationComponent affiliation = FactionAffiliationComponent.Cast(entity.FindComponent(FactionAffiliationComponent));
		if (!affiliation || !affiliation.GetAffiliatedFaction())
			return "";
		return affiliation.GetAffiliatedFaction().GetFactionKey();
	}

	protected bool OnFound(IEntity entity)
	{
		if (Alive(entity))
			m_aFound.Insert(entity);
		return true;
	}

	protected bool OnlyCharacters(IEntity entity)
	{
		return ChimeraCharacter.Cast(entity) != null;
	}

	// The nearest base's name, for the caption.
	protected string Near(vector at)
	{
		SCR_MilitaryBaseSystem system = SCR_MilitaryBaseSystem.GetInstance();
		if (!system)
			return "";
		array<SCR_MilitaryBaseComponent> bases = {};
		system.GetBases(bases);
		SCR_CampaignMilitaryBaseComponent best;
		float bestDistance = 1e9;
		foreach (SCR_MilitaryBaseComponent b : bases)
		{
			SCR_CampaignMilitaryBaseComponent campaignBase = SCR_CampaignMilitaryBaseComponent.Cast(b);
			if (!campaignBase)
				continue;
			float d = vector.DistanceXZ(at, campaignBase.GetOwner().GetOrigin());
			if (d < bestDistance)
			{
				bestDistance = d;
				best = campaignBase;
			}
		}
		if (!best)
			return "";
		string name = ZCR_Strategist.BaseName(best);
		if (bestDistance < 400)
			return "at " + name;
		return "near " + name;
	}

	protected void NextShot(BaseWorld world)
	{
		m_iShot++;
		m_Follow = null;
		m_aFound.Clear();
		vector mins, maxs;
		world.GetBoundBox(mins, maxs);
		vector centre = (mins + maxs) * 0.5;
		float radius = vector.DistanceXZ(mins, maxs) * 0.5;
		world.QueryEntitiesBySphere(centre, radius, OnFound, OnlyCharacters, EQueryEntitiesFlags.DYNAMIC);
		if (m_iShot <= 3 || m_iShot % 10 == 0)
		{
			map<string, int> sides = new map<string, int>();
			foreach (IEntity f : m_aFound)
				sides.Set(Side(f), sides.Get(Side(f)) + 1);
			string bySide;
			foreach (string k, int n : sides)
				bySide += string.Format(" %1=%2", k, n);
			Print(string.Format("[ZCR][WATCH_SCAN] shot=%1 found=%2 radius=%3 centre=%4%5", m_iShot, m_aFound.Count(), Math.Round(radius), centre, bySide), LogLevel.NORMAL);
		}

		// 250 m cells: soldiers per side.
		map<string, ref array<IEntity>> cells = new map<string, ref array<IEntity>>();
		vector sum;
		int count;
		vector lo = "1e9 0 1e9";
		vector hi = "-1e9 0 -1e9";
		foreach (IEntity e : m_aFound)
		{
			string side = Side(e);
			if (side != "US" && side != "USSR")
				continue;
			vector p = e.GetOrigin();
			sum += p;
			count++;
			lo[0] = Math.Min(lo[0], p[0]);
			lo[2] = Math.Min(lo[2], p[2]);
			hi[0] = Math.Max(hi[0], p[0]);
			hi[2] = Math.Max(hi[2], p[2]);
			string key = string.Format("%1_%2", Math.Floor(p[0] / 250), Math.Floor(p[2] / 250));
			array<IEntity> cell;
			if (!cells.Find(key, cell))
			{
				cell = {};
				cells.Set(key, cell);
			}
			cell.Insert(e);
		}
		string label;
		string kind;
		if (count == 0)
		{
			kind = "overview";
			label = "Waiting for the armies";
			Aim(centre, 1500, 1800);
		}
		else
		{
			// A fight: the cell (with its neighbours) where the smaller side is largest.
			string bestKey;
			int bestScore;
			vector bestAt;
			int bestUS, bestUSSR;
			foreach (string key, array<IEntity> cell : cells)
			{
				int us, ussr;
				vector at;
				foreach (IEntity e : cell)
				{
					at += e.GetOrigin();
					if (Side(e) == "US")
						us++;
					else
						ussr++;
				}
				// The neighbouring cells count too: sides 300 m apart are in a fight.
				array<string> parts = {};
				key.Split("_", parts, true);
				int cx = parts[0].ToInt();
				int cz = parts[1].ToInt();
				int nUS = us;
				int nUSSR = ussr;
				for (int dx = -1; dx <= 1; dx++)
				{
					for (int dz = -1; dz <= 1; dz++)
					{
						if (dx == 0 && dz == 0)
							continue;
						array<IEntity> other;
						if (!cells.Find(string.Format("%1_%2", cx + dx, cz + dz), other))
							continue;
						foreach (IEntity e : other)
						{
							if (Side(e) == "US")
								nUS++;
							else
								nUSSR++;
						}
					}
				}
				int score = Math.Min(nUS, nUSSR);
				if (score > bestScore)
				{
					bestScore = score;
					bestKey = key;
					bestAt = at / cell.Count();
					bestUS = nUS;
					bestUSSR = nUSSR;
				}
			}
			if (m_iShot % 4 == 0 || bestScore == 0)
			{
				// The whole fighting area from high up (not too high: at most 4 km across).
				float width = Math.Min(4000, Math.Max(800, Math.Max(hi[0] - lo[0], hi[2] - lo[2]) + 400));
				kind = "overview";
				label = string.Format("Overview - %1 soldiers on the map", count);
				Aim((lo + hi) * 0.5, width * 0.55, width * 0.8);
			}
			else if (m_iShot % 4 == 2)
			{
				// Close-up: one soldier of the fight, followed.
				array<IEntity> cell;
				cells.Find(bestKey, cell);
				m_Follow = cell.GetRandomElement();
				kind = "close-up";
				label = string.Format("Close-up: %1 soldier in the fight %2", Side(m_Follow), Near(m_Follow.GetOrigin()));
				Aim(m_Follow.GetOrigin(), 45, 35);
			}
			else
			{
				kind = "fight";
				label = string.Format("Fight %1 - US %2 v USSR %3 within 400 m", Near(bestAt), bestUS, bestUSSR);
				Aim(bestAt, 220, 260);
			}
		}
		m_fShotEnd = m_fClock + 20;
		if (m_Caption)
			m_Caption.SetText(label);
		Print(string.Format("[ZCR][CAM] t=%1 shot=%2 kind=%3 label=%4", ZCR_LossLog.Seconds(), m_iShot, kind, label), LogLevel.NORMAL);
	}

	// Next shot: glide from where the camera is to this spot, from back metres south, height up.
	protected void Aim(vector target, float back, float height)
	{
		m_vFrom = m_vTo;
		m_fFromBack = m_fToBack;
		m_fFromHeight = m_fToHeight;
		m_vTo = target;
		m_fToBack = back;
		m_fToHeight = height;
		m_fGlideStart = m_fClock;
		if (m_vFrom == vector.Zero)
		{
			m_vFrom = target;
			m_fFromBack = back;
			m_fFromHeight = height;
		}
	}

	protected void Place(BaseWorld world)
	{
		float k = Math.Clamp((m_fClock - m_fGlideStart) / 3, 0, 1);
		k = k * k * (3 - 2 * k);
		vector target = m_vTo;
		if (m_Follow && Alive(m_Follow))
			target = m_Follow.GetOrigin();
		vector spot = m_vFrom + (target - m_vFrom) * k;
		float back = m_fFromBack + (m_fToBack - m_fFromBack) * k;
		float height = m_fFromHeight + (m_fToHeight - m_fFromHeight) * k;
		float ground = world.GetSurfaceY(spot[0], spot[2]);
		vector eye = Vector(spot[0], ground + height, spot[2] - back);
		float eyeGround = world.GetSurfaceY(eye[0], eye[2]);
		if (eye[1] < eyeGround + 10)
			eye[1] = eyeGround + 10;
		vector look = Vector(spot[0], ground + 2, spot[2]) - eye;
		float pitch = Math.Atan2(look[1], Math.Sqrt(look[0] * look[0] + look[2] * look[2])) * Math.RAD2DEG;
		m_Camera.SetOrigin(eye);
		m_Camera.SetYawPitchRoll(Vector(0, pitch, 0));
	}
}
