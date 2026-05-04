// panel.jsx — Main app window with sidebar + "Captura en vivo" tab
// Window: 1320x820. Custom dark chrome (no Windows controls — game-style).

const { ChamferBox: PChamferBox, Hexagon6: PHex, ZButton: PBtn, Icon: PIcon, Tag: PTag,
        StatRow: PStatRow, ScoreGauge: PScoreGauge, Rarity: PRarity, KPI: PKPI, SectionHead: PSectionHead,
        Toast: PToast, DiscThumb: PDiscThumb, DiscMark: PDiscMark } = window;

// Build hex — 6 disc slots around a central PJ portrait, using real set logos
function BuildHex({ size = 220, slots, highlightIndex = -1, centerImg }) {
  const r = size * 0.34;
  const cx = size / 2, cy = size / 2;
  const positions = Array.from({ length: 6 }, (_, i) => {
    const a = (-Math.PI / 2) + (i * Math.PI / 3);
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  });
  const slotSize = size * 0.22;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ position: "absolute", inset: 0 }}>
        <polygon points={positions.map(p => `${p.x},${p.y}`).join(" ")} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1"/>
      </svg>
      <div style={{
        position: "absolute",
        left: cx - size * 0.16, top: cy - size * 0.16,
        width: size * 0.32, height: size * 0.32,
        borderRadius: "50%",
        border: "2px solid var(--yellow)",
        background: "#0a0a0a",
        overflow: "hidden",
        boxShadow: "0 0 14px rgba(255,203,5,0.3)",
      }}>
        <img src={centerImg} style={{ width: "100%", height: "100%", objectFit: "cover" }}/>
      </div>
      {positions.map((p, i) => {
        const slot = slots?.[i];
        const isHi = highlightIndex === i;
        return (
          <div key={i} style={{
            position: "absolute",
            left: p.x - slotSize / 2,
            top: p.y - slotSize / 2,
            width: slotSize, height: slotSize,
          }}>
            <BuildHexSlot slot={slot} highlight={isHi} index={i + 1} size={slotSize}/>
          </div>
        );
      })}
    </div>
  );
}

function BuildHexSlot({ slot, highlight, index, size }) {
  if (!slot) {
    return (
      <div style={{
        width: size, height: size, borderRadius: "50%",
        background: "#0a0a0a", border: "1px dashed var(--border-mid)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <span className="caps" style={{ fontSize: 8, color: "var(--text-dim)" }}>0{index}</span>
      </div>
    );
  }
  const ringColor = highlight ? "var(--yellow)" : (slot.accent || "var(--border-mid)");
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%",
      background: "#0a0a0a",
      border: `${highlight ? 2.5 : 1.5}px solid ${ringColor}`,
      boxShadow: highlight ? "0 0 16px rgba(255,203,5,0.7), inset 0 0 8px rgba(255,203,5,0.2)" : `inset 0 0 6px ${slot.accent}33`,
      position: "relative",
      display: "flex", alignItems: "center", justifyContent: "center",
      animation: highlight ? "zzz-pulse-y 1.6s infinite" : "none",
    }}>
      <img src={slot.logo} style={{ width: size * 0.7, height: size * 0.7, objectFit: "contain" }}/>
      {slot.level != null && (
        <div className="num caps" style={{
          position: "absolute",
          bottom: -7, left: "50%",
          transform: "translateX(-50%)",
          background: "#0a0a0a",
          border: `1px solid ${ringColor}`,
          color: highlight ? "var(--yellow)" : (slot.accent || "var(--text-secondary)"),
          fontSize: 8, padding: "1px 4px",
          letterSpacing: "0.06em",
          whiteSpace: "nowrap",
        }}>
          <span style={{ color: "var(--text-muted)" }}>L</span>{slot.level}
        </div>
      )}
      {slot.incoming && (
        <div style={{
          position: "absolute", top: -8, right: -4,
          background: "var(--yellow)", color: "#0a0a0a",
          fontSize: 8, fontWeight: 800, letterSpacing: "0.04em",
          padding: "1px 4px", borderRadius: 2,
          boxShadow: "0 0 6px var(--yellow)",
        }}>NEW</div>
      )}
    </div>
  );
}

function AppWindow({ width = 1320, height = 820 }) {
  const [tab, setTab] = React.useState("live");
  return (
    <div style={{
      width, height,
      position: "relative",
      background: "var(--bg-deep)",
      filter: "drop-shadow(0 24px 60px rgba(0,0,0,0.85))",
    }}>
      {/* Outer chamfered chrome */}
      <PChamferBox
        cut={18} cutCorners="all"
        borderColor="var(--border-mid)"
        bg="var(--bg-base)"
        style={{ width, height }}
        innerStyle={{ width, height, display: "flex", flexDirection: "column" }}
      >
        <TitleBar/>
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <Sidebar tab={tab} setTab={setTab}/>
          <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
            <LiveCaptureTab/>
          </div>
        </div>
        <StatusBar/>
      </PChamferBox>
    </div>
  );
}

function TitleBar() {
  return (
    <div style={{
      height: 40, display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0 14px",
      background: "linear-gradient(180deg, #161614 0%, #0a0a0a 100%)",
      borderBottom: "1px solid var(--border-subtle)",
      flexShrink: 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {/* Custom logo mark */}
        <div style={{ position: "relative", width: 26, height: 26 }}>
          <div style={{
            position: "absolute", inset: 0,
            background: "var(--yellow)",
            clipPath: "polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)",
            boxShadow: "0 0 8px rgba(255,203,5,0.5)",
          }}/>
          <div style={{
            position: "absolute", inset: 4,
            background: "#0a0a0a",
            clipPath: "polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span className="display" style={{ color: "var(--yellow)", fontSize: 11, fontWeight: 700 }}>D</span>
          </div>
        </div>
        <div>
          <div className="display caps" style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 600, lineHeight: 1, letterSpacing: "0.14em" }}>
            DaniBOD <span style={{ color: "var(--yellow)" }}>// </span> ZZZ Analytics
          </div>
          <div className="caps num" style={{ fontSize: 8, color: "var(--text-muted)", letterSpacing: "0.16em", marginTop: 2 }}>
            v0.9.4 · OCR ACTIVO · 332 DISCOS · 45 PJs
          </div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%",
            background: "var(--positive)",
            boxShadow: "0 0 8px var(--positive)",
            animation: "zzz-blink 1.6s infinite",
          }}/>
          <span className="caps num" style={{ fontSize: 10, color: "var(--text-secondary)", letterSpacing: "0.1em" }}>
            CAPTURA · 18 fps
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span className="caps num" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.1em" }}>LATENCIA</span>
          <span className="display num" style={{ fontSize: 12, color: "var(--positive)", fontWeight: 700 }}>312ms</span>
        </div>
        <div style={{ width: 1, height: 18, background: "var(--border-mid)" }}/>
        <div style={{ display: "flex", gap: 2 }}>
          <ChromeBtn icon="minimize"/>
          <ChromeBtn icon="maximize"/>
          <ChromeBtn icon="x" warning/>
        </div>
      </div>
    </div>
  );
}

function ChromeBtn({ icon, warning }) {
  return (
    <div style={{
      width: 28, height: 28,
      display: "flex", alignItems: "center", justifyContent: "center",
      cursor: "pointer",
      color: warning ? "var(--text-secondary)" : "var(--text-muted)",
    }}>
      <PIcon name={icon} size={11}/>
    </div>
  );
}

function Sidebar({ tab, setTab }) {
  const groups = [
    {
      label: "MONITOREO",
      items: [
        { key: "live",    icon: "spark",  label: "Captura en vivo", badge: "LIVE", live: true },
        { key: "history", icon: "feed",   label: "Histórico",       badge: "1.2k" },
        { key: "lateg",   icon: "trend",  label: "Lategame",        badge: "12" },
      ],
    },
    {
      label: "BUILD",
      items: [
        { key: "discs",   icon: "disc",   label: "Discos",          badge: "332" },
        { key: "roster",  icon: "users",  label: "Roster",          badge: "45" },
        { key: "weapons", icon: "sword",  label: "Armas" },
        { key: "teams",   icon: "stack",  label: "Equipos",         badge: "AI", purple: true },
      ],
    },
    {
      label: "SISTEMA",
      items: [
        { key: "catal",   icon: "book",     label: "Catálogos" },
        { key: "config",  icon: "settings", label: "Configuración" },
      ],
    },
  ];
  return (
    <div style={{
      width: 220, flexShrink: 0,
      background: "linear-gradient(180deg, #0c0c0c, #050505)",
      borderRight: "1px solid var(--border-subtle)",
      display: "flex", flexDirection: "column",
      padding: "12px 0 10px",
    }}>
      {/* User / UID block */}
      <div style={{ padding: "6px 14px 12px", borderBottom: "1px solid var(--border-subtle)", marginBottom: 10, display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 34, height: 34, borderRadius: 10, background: "linear-gradient(135deg, #FFCB05, #b89008)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 0 10px rgba(255,203,5,0.3)" }}>
          <span className="display" style={{ color: "#0a0a0a", fontSize: 14, fontWeight: 800, fontStyle: "italic" }}>D</span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, color: "var(--text-primary)", fontWeight: 600 }}>Proxy 1660</div>
          <div className="caps num" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.1em" }}>NIVEL 60 · UID ·8060143</div>
        </div>
        <div style={{ width: 18, height: 18, border: "1px solid var(--border-mid)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", flexShrink: 0 }}>
          <PIcon name="down" size={9}/>
        </div>
      </div>

      {groups.map((g, gi) => (
        <div key={gi} style={{ marginBottom: 8 }}>
          <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.18em", padding: "4px 14px 6px", fontWeight: 600 }}>
            {g.label}
          </div>
          {g.items.map((item) => (
            <SidebarItem key={item.key} item={item} active={tab === item.key} onClick={() => setTab(item.key)}/>
          ))}
        </div>
      ))}

      <div style={{ flex: 1 }}/>
      <div style={{ margin: "0 10px", padding: "8px 10px", border: "1px solid var(--border-subtle)", borderRadius: 6, background: "rgba(0,0,0,0.4)" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.14em", marginBottom: 6, fontWeight: 600 }}>
          HOTKEYS
        </div>
        {[
          { k: "F8",  v: "Captura" },
          { k: "F9",  v: "Panel" },
          { k: "F10", v: "Pausa" },
          { k: "F11", v: "Run", hl: true },
        ].map((h) => (
          <div key={h.k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "2px 0" }}>
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: 9,
              color: h.hl ? "var(--yellow)" : "var(--text-secondary)",
              padding: "0 4px",
              border: `1px solid ${h.hl ? "var(--yellow)" : "var(--border-mid)"}`,
              borderRadius: 3,
            }}>{h.k}</span>
            <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>{h.v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SidebarItem({ item, active, onClick }) {
  return (
    <div onClick={onClick} style={{ position: "relative", margin: "0 8px", cursor: "pointer" }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "7px 10px",
        borderRadius: 6,
        background: active ? "linear-gradient(90deg, rgba(255,203,5,0.14), rgba(255,203,5,0.04))" : "transparent",
        color: active ? "var(--yellow)" : "var(--text-secondary)",
        border: active ? "1px solid rgba(255,203,5,0.35)" : "1px solid transparent",
        boxShadow: active ? "inset 0 1px 0 rgba(255,255,255,0.05)" : "none",
      }}>
        <PIcon name={item.icon} size={14} color={active ? "var(--yellow)" : "currentColor"}/>
        <span style={{ flex: 1, fontSize: 12, fontWeight: active ? 600 : 500, letterSpacing: "0.02em" }}>
          {item.label}
        </span>
        {item.badge && (
          item.live ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 9, color: "var(--positive)", letterSpacing: "0.1em", fontWeight: 700 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--positive)", boxShadow: "0 0 6px var(--positive)", animation: "zzz-blink 1.4s infinite" }}/>
              {item.badge}
            </span>
          ) : (
            <span className="num" style={{
              fontSize: 9, padding: "1px 5px",
              background: item.purple ? "rgba(157,78,221,0.18)" : "rgba(255,255,255,0.04)",
              color: item.purple ? "var(--purple)" : (active ? "var(--yellow)" : "var(--text-muted)"),
              border: `1px solid ${item.purple ? "var(--purple)" : (active ? "var(--yellow)" : "var(--border-subtle)")}`,
              letterSpacing: "0.04em",
              borderRadius: 3,
            }}>{item.badge}</span>
          )
        )}
      </div>
    </div>
  );
}

function StatusBar() {
  return (
    <div style={{
      height: 24, flexShrink: 0,
      borderTop: "1px solid var(--border-subtle)",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0 14px",
      background: "#070707",
      fontSize: 9, color: "var(--text-muted)",
      letterSpacing: "0.08em", textTransform: "uppercase",
      fontFamily: "var(--font-mono)",
    }}>
      <div style={{ display: "flex", gap: 16 }}>
        <span>SQLITE · 18.4 MB</span>
        <span>OCR · TESSERACT 5.4 · ES</span>
        <span>CICLO ACTUAL · 12 / 28d</span>
      </div>
      <div style={{ display: "flex", gap: 16 }}>
        <span style={{ color: "var(--positive)" }}>● MONITOREANDO</span>
        <span>UID 1000860143</span>
        <span>23:41:08</span>
      </div>
    </div>
  );
}

// ----- Live Capture tab content ------------------------------------------------
function LiveCaptureTab() {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "400px 1fr 260px",
      gap: 12,
      padding: 14,
      height: "100%",
      background: "var(--bg-base)",
      overflow: "hidden",
      backgroundImage: "radial-gradient(circle at 80% 0%, rgba(255,203,5,0.04), transparent 50%)",
    }}>
      <DiscPanel/>
      <ScoringPanel/>
      <AlternativesPanel/>
    </div>
  );
}

function DiscPanel() {
  // sample disc — Yanagi build, 4pc Jazz Caótico + 2pc Blues Libre
  const slots = [
    { logo: "assets/set-jazz-caotico.webp", level: 15, accent: "#FFCB05" },
    { logo: "assets/set-jazz-caotico.webp", level: 15, accent: "#FFCB05" },
    { logo: "assets/set-jazz-caotico.webp", level: 15, accent: "#FFCB05" },
    { logo: "assets/set-jazz-caotico.webp", level: 15, accent: "#FFCB05", incoming: true },
    { logo: "assets/set-blues-libre.webp",  level: 15, accent: "#9D4EDD" },
    { logo: "assets/set-blues-libre.webp",  level: 15, accent: "#9D4EDD" },
  ];
  return (
    <PChamferBox
      cut={14} cutCorners="tl-br"
      borderColor="var(--border-mid)"
      bg="var(--bg-panel-solid)"
      pattern="carbon"
      style={{ display: "flex", flexDirection: "column", minHeight: 0 }}
      innerStyle={{ display: "flex", flexDirection: "column", height: "100%" }}
    >
      <PSectionHead right={<><PTag color="yellow">CAPTURADO 23:41:02</PTag></>}>
        Disco capturado · #00482
      </PSectionHead>

      <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
        {/* Set title + rarity */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div className="display caps" style={{ fontSize: 22, color: "var(--yellow)", fontWeight: 700, letterSpacing: "0.04em", lineHeight: 1.1 }}>
              Tecno Pícido <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>(4)</span>
            </div>
            <div className="num" style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2, letterSpacing: "0.02em" }}>
              Slot 4 · Nivel <span className="num" style={{ color: "var(--yellow)" }}>00</span><span style={{ color: "var(--text-muted)" }}>/15</span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            <PRarity tier="S"/>
          </div>
        </div>

        {/* Hexagon visualization */}
        <div style={{ display: "flex", justifyContent: "center", padding: "8px 0", position: "relative" }}>
          <BuildHex size={220} slots={slots} highlightIndex={3} centerImg="assets/yanagi-ico.webp"/>
          <div style={{
            position: "absolute", left: 6, top: 6,
            display: "flex", flexDirection: "column", gap: 2,
          }}>
            <PTag size="sm" color="yellow">SLOT 4 · NUEVO</PTag>
            <PTag size="sm" color="default">SET 4P · ELÉCTRICO</PTag>
          </div>
        </div>

        {/* Stats */}
        <div style={{ border: "1px solid var(--border-subtle)" }}>
          <div className="caps" style={{ fontSize: 10, color: "var(--text-muted)", padding: "6px 12px", borderBottom: "1px solid var(--border-subtle)", letterSpacing: "0.12em", background: "rgba(0,0,0,0.4)" }}>
            ATRIBUTO PRINCIPAL
          </div>
          <PStatRow label="ATAQUE %" value="30.0" unit="%" accent="yellow" emphasis/>
          <div className="caps" style={{ fontSize: 10, color: "var(--text-muted)", padding: "6px 12px", borderBottom: "1px solid var(--border-subtle)", borderTop: "1px solid var(--border-subtle)", letterSpacing: "0.12em", background: "rgba(0,0,0,0.4)" }}>
            ATRIBUTOS SECUNDARIOS
          </div>
          <PStatRow label="Prob. Crítica" value="2.4" unit="%" />
          <PStatRow label="Daño Crítico" value="9.6" unit="%" delta={1}/>
          <PStatRow label="Ataque" value="38" delta={1}/>
          <PStatRow label="Anomalía" value="27" delta={2}/>
        </div>

        {/* Set effect */}
        <div style={{ background: "rgba(255,203,5,0.04)", border: "1px solid var(--border-subtle)", padding: "10px 12px" }}>
          <div className="caps" style={{ fontSize: 10, color: "var(--yellow)", marginBottom: 4, letterSpacing: "0.12em", fontWeight: 600 }}>
            EFECTO DE CONJUNTO
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>
            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>2 pistas:</span> ATK +10 %.{" "}
            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>4 pistas:</span> el <span style={{ color: "var(--info)" }}>daño eléctrico</span> aumenta un 28 % cuando el portador inflige <span style={{ color: "var(--yellow)" }}>aturdimiento</span>.
          </div>
        </div>
      </div>

      {/* Bottom action bar */}
      <div style={{ marginTop: "auto", padding: "10px 14px", borderTop: "1px solid var(--border-subtle)", display: "flex", gap: 8, justifyContent: "space-between" }}>
        <PBtn variant="ghost" size="sm" icon="lock">Bloquear</PBtn>
        <PBtn variant="ghost" size="sm" icon="trash">Descartar</PBtn>
        <PBtn variant="positive" size="sm" icon="check">Equipar a Yanagi</PBtn>
      </div>
    </PChamferBox>
  );
}

function ScoringPanel() {
  return (
    <PChamferBox
      cut={14} cutCorners="tl-br"
      borderColor="var(--border-mid)"
      bg="var(--bg-panel-solid)"
      pattern="carbon"
      style={{ display: "flex", flexDirection: "column", minHeight: 0 }}
      innerStyle={{ display: "flex", flexDirection: "column", height: "100%" }}
    >
      <PSectionHead right={<><PTag color="positive">RECOMENDADO · EQUIPAR</PTag></>}>
        Desglose de scoring · → Yanagi (M2)
      </PSectionHead>

      <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 12, overflow: "auto", minWidth: 0 }}>
        {/* Hero score */}
        <div style={{ display: "flex", gap: 10, alignItems: "stretch" }}>
          <div style={{ flex: 1, minWidth: 0, padding: "10px 14px", border: "1px solid var(--positive)", borderRadius: 10, background: "rgba(123,201,31,0.06)", position: "relative", overflow: "hidden" }}>
            <div style={{ position: "absolute", inset: 0, background: "linear-gradient(135deg, rgba(123,201,31,0.12), transparent 50%)", pointerEvents: "none" }}/>
            <div className="caps" style={{ fontSize: 10, color: "var(--text-secondary)", letterSpacing: "0.12em" }}>
              SCORE FINAL · YANAGI
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
              <span className="display num" style={{ fontSize: 42, color: "var(--positive)", fontWeight: 700, lineHeight: 1, letterSpacing: 0, textShadow: "0 0 16px rgba(123,201,31,0.6)" }}>
                87.3
              </span>
              <span className="num" style={{ fontSize: 13, color: "var(--positive)", fontWeight: 600 }}>▲ 12.4</span>
            </div>
            <div style={{ marginTop: 8 }}>
              <PScoreGauge score={87.3} threshold={75} max={100} color="var(--positive)"/>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 9, color: "var(--text-muted)" }}>
                <span className="caps">0</span>
                <span className="caps" style={{ color: "var(--yellow)" }}>THR · 75</span>
                <span className="caps">100</span>
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateRows: "1fr 1fr", gap: 6, width: 130 }}>
            <PKPI small label="ROLLS +" value="+45.6" color="var(--positive)" sub="3 substats útiles"/>
            <PKPI small label="ROLLS −" value="−7.5" color="var(--warning)" sub="1 perjudicial"/>
          </div>
        </div>

        {/* Substat breakdown */}
        <div>
          <div className="caps" style={{ fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.14em", marginBottom: 8, paddingLeft: 2 }}>
            DESGLOSE POR SUBSTAT
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <SubstatBar label="Daño Crítico" value="+9.6 %" rolls={3} contribution={37.8} weight="MUY ALTO" sign="+"/>
            <SubstatBar label="Ataque (plano)" value="+38" rolls={2} contribution={14.2} weight="ALTO" sign="+"/>
            <SubstatBar label="Maestría Anomalía" value="+27" rolls={1} contribution={6.4} weight="MEDIO" sign="+"/>
            <SubstatBar label="Prob. Crítica" value="+2.4 %" rolls={1} contribution={4.8} weight="MEDIO" sign="+"/>
            <SubstatBar label="DEF % (no rollada)" value="—" rolls={1} contribution={-7.5} weight="PERJUDICIAL" sign="−"/>
          </div>
        </div>

        {/* Bonus */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
          <BonusCard label="MAIN BONUS" value="+18.4" sub="ATK% slot 4"/>
          <BonusCard label="LEVEL BONUS" value="+0.0" sub="lvl 0/15" muted/>
          <BonusCard label="SET MATCH" value="+8.2" sub="Pícido 3/4"/>
        </div>
      </div>

      {/* Bottom action footer */}
      <div style={{ marginTop: "auto", padding: "10px 14px", borderTop: "1px solid var(--border-subtle)", display: "flex", gap: 8, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center", minWidth: 0 }}>
          <PIcon name="info" size={11} color="var(--text-muted)"/>
          <span style={{ fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.02em" }}>
            Arquetipo <span style={{ color: "var(--purple)" }}>ANOMALY</span>
          </span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <PBtn variant="ghost" size="sm" icon="info">Fórmula</PBtn>
          <PBtn variant="positive" size="sm" icon="up">Mejorar +15</PBtn>
        </div>
      </div>
    </PChamferBox>
  );
}

function SubstatBar({ label, value, rolls, contribution, weight, sign = "+" }) {
  const positive = sign === "+";
  const color = positive ? "var(--positive)" : "var(--warning)";
  const pct = Math.min(100, (Math.abs(contribution) / 40) * 100);
  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border-subtle)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500 }}>{label}</span>
          <span className="num" style={{ fontSize: 11, color: positive ? "var(--text-secondary)" : "var(--text-muted)" }}>{value}</span>
          <span className="num" style={{
            fontSize: 9, padding: "1px 5px",
            border: "1px solid var(--border-mid)",
            color: "var(--text-secondary)",
            letterSpacing: "0.04em",
          }}>{rolls} ROLL{rolls > 1 ? "S" : ""}</span>
          <span className="caps" style={{ fontSize: 9, color: positive ? "var(--text-muted)" : "var(--warning)", letterSpacing: "0.1em" }}>{weight}</span>
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
          <span className="num display" style={{ fontSize: 16, color, fontWeight: 700 }}>
            {sign === "+" ? "+" : "−"}{Math.abs(contribution).toFixed(1)}
          </span>
          <span style={{ fontSize: 9, color: "var(--text-muted)" }}>pts</span>
        </div>
      </div>
      <div style={{ height: 4, background: "rgba(255,255,255,0.04)", position: "relative" }}>
        <div style={{
          position: "absolute", inset: 0, width: `${pct}%`,
          background: color,
          opacity: positive ? 1 : 0.6,
          boxShadow: `0 0 6px ${color}`,
        }}/>
      </div>
    </div>
  );
}

function BonusCard({ label, value, sub, muted }) {
  return (
    <div style={{
      padding: "8px 10px",
      border: "1px solid var(--border-subtle)",
      borderRadius: 8,
      background: "rgba(255,255,255,0.018)",
      minWidth: 0,
      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
    }}>
      <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.1em", marginBottom: 3 }}>
        {label}
      </div>
      <div className="display num" style={{ fontSize: 16, color: muted ? "var(--text-muted)" : "var(--yellow)", fontWeight: 700, lineHeight: 1 }}>
        {value}
      </div>
      <div style={{ fontSize: 9, color: "var(--text-secondary)", marginTop: 3 }}>{sub}</div>
    </div>
  );
}

function AlternativesPanel() {
  const alternatives = [
    { id: "yanagi",  name: "Yanagi",  mind: 0, score: 87.3, delta: 0,     role: "DPS·Anomalía",   match: "ANOMALY",    best: true },
    { id: "burnice", name: "Burnice", mind: 0, score: 81.4, delta: -5.9,  role: "DPS·Anomalía",   match: "ANOMALY" },
    { id: "ellen",   name: "Ellen",   mind: 0, score: 64.8, delta: -22.5, role: "DPS·Hielo",      match: "ATK_DPS" },
    { id: "yixuan",  name: "Yixuan",  mind: 0, score: 58.1, delta: -29.2, role: "Disruptivo",     match: "HP_SHEER" },
    { id: "caesar",  name: "Caesar",  mind: 2, score: 41.7, delta: -45.6, role: "Defensor",       match: "DEFENSE" },
  ];
  return (
    <PChamferBox
      cut={14} cutCorners="tl-br"
      borderColor="var(--border-mid)"
      bg="var(--bg-panel-solid)"
      pattern="carbon"
      style={{ display: "flex", flexDirection: "column", minHeight: 0 }}
      innerStyle={{ display: "flex", flexDirection: "column", height: "100%" }}
    >
      <PSectionHead right={<PTag color="purple">AI · RF-12</PTag>}>
        Alternativas compatibles
      </PSectionHead>

      <div style={{ padding: "12px", overflow: "auto", flex: 1 }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", marginBottom: 8, letterSpacing: "0.12em" }}>
          5 PJs por delta
        </div>
        {alternatives.map((alt, i) => {
          const pj = window.PJS[alt.id];
          const accent = pj?.palette?.p || "#7BC91F";
          return (
          <div key={i} style={{
            padding: "8px 10px",
            margin: "0 0 6px",
            border: alt.best ? "1px solid var(--yellow)" : "1px solid var(--border-subtle)",
            background: alt.best ? "rgba(255,203,5,0.06)" : "transparent",
            borderLeft: `3px solid ${accent}`,
            display: "flex", gap: 8, alignItems: "center",
          }}>
            <img src={pj.ico} style={{
              width: 38, height: 38, borderRadius: 8, objectFit: "cover",
              border: `1px solid ${alt.best ? "var(--yellow)" : "var(--border-mid)"}`,
              flexShrink: 0,
              boxShadow: alt.best ? "0 0 10px rgba(255,203,5,0.4)" : "none",
            }}/>
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <div>
                  <span style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 600 }}>{alt.name}</span>
                  <span className="num" style={{ fontSize: 10, color: "var(--text-secondary)", marginLeft: 4 }}>M{alt.mind}</span>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                  <span className="display num" style={{ fontSize: 14, color: alt.best ? "var(--yellow)" : "var(--text-primary)", fontWeight: 700 }}>
                    {alt.score.toFixed(1)}
                  </span>
                  {alt.delta !== 0 && (
                    <span className="num" style={{ fontSize: 10, color: "var(--warning)" }}>
                      {alt.delta.toFixed(1)}
                    </span>
                  )}
                  {alt.best && <span className="caps" style={{ fontSize: 8, color: "var(--yellow)", fontWeight: 700, marginLeft: 2 }}>★</span>}
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{alt.role}</span>
                <span className="caps" style={{ fontSize: 8, color: "var(--purple)", letterSpacing: "0.1em", padding: "1px 4px", border: "1px solid var(--purple)" }}>
                  {alt.match}
                </span>
              </div>
            </div>
          </div>
          );
        })}

        {/* Synergy hint */}
        <div style={{ marginTop: 12, padding: "10px", border: "1px dashed var(--purple)", background: "rgba(157,78,221,0.04)" }}>
          <div className="caps" style={{ fontSize: 9, color: "var(--purple)", marginBottom: 4, letterSpacing: "0.12em" }}>
            ★ SINERGIA SUGERIDA
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.4 }}>
            Yanagi + Burnice + Lighter — combo ANOMALY·DISORDER eléctrico/ígneo. Confianza <span className="num" style={{ color: "var(--purple)", fontWeight: 600 }}>0.84</span>.
          </div>
        </div>

        {/* Retro feedback */}
        <div style={{ marginTop: 10, padding: "10px", border: "1px solid var(--border-subtle)", background: "rgba(255,77,138,0.04)" }}>
          <div className="caps" style={{ fontSize: 9, color: "var(--pink)", marginBottom: 6, letterSpacing: "0.12em" }}>
            ◇ RETRO RF-13
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>Última run con Yanagi</span>
            <span className="num" style={{ fontSize: 11, color: "var(--positive)", fontWeight: 600 }}>S · 1:48</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
            <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>Confianza modelo</span>
            <span className="num" style={{ fontSize: 11, color: "var(--pink)", fontWeight: 600 }}>↑ 0.91</span>
          </div>
        </div>
      </div>
    </PChamferBox>
  );
}

Object.assign(window, { AppWindow, LiveCaptureTab });
