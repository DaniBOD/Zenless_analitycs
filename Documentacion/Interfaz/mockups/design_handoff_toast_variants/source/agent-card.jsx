// agent-card.jsx — Agent stats card replicating the in-game info panel language
// Big display name with ghost text, faction badge, element/role pills,
// stat rows with yellow-highlighted key stats, recommendation banner.

const { BlockBox: ABlock, Icon: AIcon } = window;

// Element configs — colors + simple SVG mark for each element
const ELEMENTS = {
  electrico: { name: "Eléctrico", color: "#C5A8FF", glow: "rgba(197,168,255,0.6)" },
  igneo:     { name: "Ígneo",     color: "#FF7A45", glow: "rgba(255,122,69,0.6)" },
  hielo:     { name: "Hielo",     color: "#9DE0F0", glow: "rgba(157,224,240,0.6)" },
  fisico:    { name: "Físico",    color: "#FFD66B", glow: "rgba(255,214,107,0.6)" },
  etereo:    { name: "Etéreo",    color: "#FF4D8A", glow: "rgba(255,77,138,0.6)" },
  helada:    { name: "Helada",    color: "#7AC7FF", glow: "rgba(122,199,255,0.6)" },
  auric:     { name: "Auric Ink", color: "#A4FFD9", glow: "rgba(164,255,217,0.6)" },
};
const ROLES = {
  dps:       { name: "DPS",        icon: "sword" },
  anomaly:   { name: "Anomalía",   icon: "anomaly" },
  stun:      { name: "Aturdidor",  icon: "bolt" },
  support:   { name: "Soporte",    icon: "heart" },
  defense:   { name: "Defensor",   icon: "shield" },
  rupture:   { name: "Ruptura",    icon: "flame" },
};

// Mini element glyph (original geometric mark, not from any source)
function ElementGlyph({ element = "etereo", size = 14 }) {
  const e = ELEMENTS[element];
  return (
    <svg width={size} height={size} viewBox="-12 -12 24 24" style={{ flexShrink: 0, filter: `drop-shadow(0 0 4px ${e.glow})` }}>
      <path
        d="M0 -10 L4 -3 L10 0 L4 3 L0 10 L-4 3 L-10 0 L-4 -3 Z"
        fill={e.color}
      />
      <circle cx="0" cy="0" r="2.5" fill="#0a0a0a"/>
    </svg>
  );
}

// Faction badge — circular monogram with chamfered hex frame (original placeholder)
function FactionBadge({ faction = "PHAETHON", color = "#FFCB05", size = 80 }) {
  const initial = faction.charAt(0);
  return (
    <div style={{
      width: size, height: size,
      position: "relative",
      flexShrink: 0,
    }}>
      {/* outer ring */}
      <svg width={size} height={size} viewBox="0 0 100 100" style={{ position: "absolute", inset: 0 }}>
        <defs>
          <radialGradient id={`fg-${faction}`} cx="0.3" cy="0.3">
            <stop offset="0%" stopColor={color} stopOpacity="0.9"/>
            <stop offset="60%" stopColor={color} stopOpacity="0.4"/>
            <stop offset="100%" stopColor="#0a0a0a" stopOpacity="0.95"/>
          </radialGradient>
        </defs>
        <polygon
          points="50,4 88,26 88,74 50,96 12,74 12,26"
          fill={`url(#fg-${faction})`}
          stroke={color}
          strokeWidth="2"
          opacity="0.9"
        />
        <polygon
          points="50,14 78,30 78,70 50,86 22,70 22,30"
          fill="none"
          stroke={color}
          strokeWidth="0.6"
          opacity="0.5"
        />
        {/* decorative wings */}
        <path d="M50 30 L40 22 M50 30 L60 22" stroke={color} strokeWidth="2" strokeLinecap="round" opacity="0.7"/>
        <path d="M50 70 L40 78 M50 70 L60 78" stroke={color} strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
      </svg>
      <div style={{
        position: "absolute", inset: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexDirection: "column",
      }}>
        <div className="display num" style={{
          fontSize: size * 0.32, fontWeight: 800, color,
          lineHeight: 1, letterSpacing: 0,
          textShadow: `0 0 8px ${color}, 0 1px 0 rgba(255,255,255,0.2)`,
        }}>{initial}</div>
        <div className="caps" style={{
          fontSize: size * 0.085, color, fontWeight: 600,
          letterSpacing: "0.18em", marginTop: 2, opacity: 0.8,
        }}>{faction.slice(0, 6)}</div>
      </div>
    </div>
  );
}

// "Film reel" avatar mini (top-right of the card)
function ReelAvatar({ size = 48, color = "#FFCB05", label = "INFO" }) {
  return (
    <div style={{
      width: size, height: size, position: "relative",
      flexShrink: 0,
    }}>
      <svg width={size} height={size} viewBox="0 0 50 50">
        <circle cx="25" cy="25" r="23" fill="#0a0a0a" stroke={color} strokeWidth="1.5"/>
        <circle cx="25" cy="25" r="18" fill="none" stroke={color} strokeWidth="0.7" opacity="0.5" strokeDasharray="2 3"/>
        <circle cx="25" cy="25" r="4" fill={color}/>
        {[0, 60, 120, 180, 240, 300].map(a => {
          const rad = (a * Math.PI) / 180;
          const x = 25 + 13 * Math.cos(rad);
          const y = 25 + 13 * Math.sin(rad);
          return <circle key={a} cx={x} cy={y} r="2" fill="#0a0a0a" stroke={color} strokeWidth="0.7"/>;
        })}
      </svg>
      <div className="caps" style={{
        position: "absolute", inset: 0,
        display: "flex", alignItems: "flex-end", justifyContent: "center",
        fontSize: 7, color, opacity: 0.6,
        letterSpacing: "0.1em",
        paddingBottom: 2,
      }}>{label}</div>
    </div>
  );
}

// Pill with icon (Element / Role)
function AgentPill({ icon, label, color = "var(--text-primary)", glow }) {
  return (
    <div style={{
      flex: 1,
      padding: "10px 14px",
      borderRadius: 14,
      background: "linear-gradient(180deg, #1f1f1f 0%, #0c0c0c 100%)",
      border: "1px solid var(--border-mid)",
      display: "flex", alignItems: "center", gap: 10,
      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06), 0 2px 4px rgba(0,0,0,0.4)",
    }}>
      {icon}
      <span className="display" style={{ fontSize: 16, color, fontWeight: 600, letterSpacing: "0.02em" }}>
        {label}
      </span>
    </div>
  );
}

// Stat row — when highlighted, label and value both go yellow (matches in-game card)
function AgentStat({ label, value, unit, highlight = false }) {
  const color = highlight ? "var(--yellow)" : "var(--text-primary)";
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "10px 14px",
      borderRadius: 12,
      background: highlight ? "rgba(255,203,5,0.04)" : "transparent",
      border: highlight ? "1px solid rgba(255,203,5,0.18)" : "1px solid var(--border-subtle)",
      boxShadow: highlight ? "inset 0 1px 0 rgba(255,255,255,0.04)" : "none",
    }}>
      <span style={{
        fontSize: 13, color,
        fontWeight: highlight ? 700 : 500,
        fontStyle: highlight ? "normal" : "normal",
        letterSpacing: highlight ? "0.01em" : "0.01em",
      }}>{label}</span>
      <span className="display num" style={{
        fontSize: 16, color,
        fontWeight: 700,
        letterSpacing: 0,
      }}>
        {value}{unit && <span style={{ fontSize: 13, marginLeft: 2 }}>{unit}</span>}
      </span>
    </div>
  );
}

// Level pill (Nivel 60 / 60 MAX)
function LevelPill({ level = 60, max = 60 }) {
  const isMax = level >= max;
  return (
    <div style={{
      padding: "8px 4px 8px 16px",
      borderRadius: 14,
      background: "linear-gradient(180deg, #1f1f1f 0%, #0c0c0c 100%)",
      border: "1px solid var(--border-mid)",
      display: "flex", alignItems: "center", gap: 10,
      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06), 0 2px 4px rgba(0,0,0,0.4)",
    }}>
      <span className="display" style={{ fontSize: 16, color: "var(--text-primary)", fontWeight: 700, fontStyle: "italic", letterSpacing: "0.02em" }}>
        Nivel {level}
      </span>
      <div style={{ width: 1, height: 18, background: "var(--border-mid)", transform: "skewX(-12deg)" }}/>
      <span className="display num" style={{ fontSize: 18, color: "var(--text-secondary)", fontWeight: 700, letterSpacing: 0 }}>
        <span style={{ color: "var(--text-primary)" }}>{level}</span><span style={{ opacity: 0.5 }}>/{max}</span>
      </span>
      {isMax && (
        <div style={{
          padding: "4px 10px",
          background: "linear-gradient(180deg, #3a3a3a 0%, #1a1a1a 100%)",
          borderRadius: 10,
          border: "1px solid var(--border-mid)",
        }}>
          <span className="display caps" style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 800, letterSpacing: "0.1em" }}>MAX</span>
        </div>
      )}
    </div>
  );
}

// Main card
function AgentStatsCard({
  agent = {
    name: "Nangong Yu",
    nameSub: "Nangong Yu",
    faction: "Ángeles de la Delusión",
    factionShort: "ANGELS",
    factionColor: "#FF8AB3",
    level: 60, levelMax: 60,
    element: "etereo",
    role: "stun",
    avatarUrl: null,
    stats: {
      pv: 10797, defensa: 925, critico: 19.4, anomTasa: 173, perforacion: 0,
      ataque: 2531, impacto: 138, danoCrit: 93.2, anomMaestria: 305, recupEnergia: 1.2,
    },
    recommendation: "Pistas de disco",
  },
  width = 560,
}) {
  const a = agent;
  const e = ELEMENTS[a.element] || ELEMENTS.etereo;
  const r = ROLES[a.role] || ROLES.dps;

  return (
    <div style={{ width, display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Top "AGENT INFO" header tag */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 4px" }}>
        <div style={{ width: 3, height: 12, background: "var(--yellow)", boxShadow: "0 0 6px var(--yellow)" }}/>
        <div className="caps" style={{ fontSize: 11, color: "var(--text-secondary)", letterSpacing: "0.16em", fontWeight: 600 }}>
          AGENT INFO
        </div>
        <div style={{ flex: 1, height: 1, background: "linear-gradient(90deg, var(--border-mid), transparent)" }}/>
        <ReelAvatar size={36} color="var(--yellow)" label="INFO"/>
      </div>

      {/* Hero block: name + faction badge */}
      <ABlock radius={18} bg="var(--bg-panel-solid)" pattern="carbon" depth="md" borderColor="var(--border-mid)">
        <div style={{ padding: "20px 24px", display: "flex", alignItems: "center", gap: 16, position: "relative", minHeight: 140 }}>
          <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
            {/* Faction tag */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <div style={{
                width: 18, height: 18, borderRadius: "50%",
                background: "linear-gradient(135deg, #FFCB05, #b89008)",
                display: "flex", alignItems: "center", justifyContent: "center",
                boxShadow: "0 0 6px rgba(255,203,5,0.6)",
              }}>
                <span style={{ color: "#0a0a0a", fontSize: 11, fontWeight: 800 }}>$</span>
              </div>
              <span className="display" style={{ fontSize: 18, color: "var(--text-primary)", fontWeight: 700, letterSpacing: "0.01em" }}>
                {a.faction}
              </span>
            </div>
            {/* Big name */}
            <div style={{ position: "relative", marginTop: 4 }}>
              <div className="display" style={{
                fontSize: 44, color: "var(--text-primary)",
                fontWeight: 800, letterSpacing: "0.01em",
                lineHeight: 1, fontStyle: "italic",
                textShadow: "0 2px 8px rgba(0,0,0,0.6)",
              }}>
                {a.name}
              </div>
              {/* Ghost subtext */}
              <div className="display" style={{
                fontSize: 13, color: "var(--text-dim)",
                fontWeight: 500, letterSpacing: "0.4em",
                marginTop: 8, opacity: 0.4,
                textTransform: "none",
              }}>
                {a.nameSub.split("").join(" ")}
              </div>
            </div>
          </div>
          <FactionBadge faction={a.factionShort} color={a.factionColor} size={120}/>
        </div>
      </ABlock>

      {/* Level + element/role row */}
      <div style={{ display: "flex", gap: 10 }}>
        <LevelPill level={a.level} max={a.levelMax}/>
        <AgentPill
          icon={<ElementGlyph element={a.element} size={18}/>}
          label={e.name}
          color="var(--text-primary)"
        />
        <AgentPill
          icon={<AIcon name={r.icon} size={18} color="var(--text-primary)"/>}
          label={r.name}
          color="var(--text-primary)"
        />
      </div>

      {/* Stats grid (2 columns) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <AgentStat label="PV"                value={a.stats.pv.toLocaleString("es-ES")}/>
        <AgentStat label="Ataque"            value={a.stats.ataque.toLocaleString("es-ES")} highlight/>
        <AgentStat label="Defensa"           value={a.stats.defensa}/>
        <AgentStat label="Impacto"           value={a.stats.impacto}/>
        <AgentStat label="Probabilidad de Crítico" value={a.stats.critico} unit=" %"/>
        <AgentStat label="Daño Crítico"      value={a.stats.danoCrit} unit=" %"/>
        <AgentStat label="Tasa de Anomalía"  value={a.stats.anomTasa} highlight/>
        <AgentStat label="Maestría de Anomalía" value={a.stats.anomMaestria} highlight/>
        <AgentStat label="Tasa de Perforación"   value={a.stats.perforacion} unit=" %"/>
        <AgentStat label="Recuperación de Energía" value={a.stats.recupEnergia}/>
      </div>

      {/* Recommendation banner */}
      <div style={{
        padding: "12px 16px",
        borderRadius: 14,
        background: "linear-gradient(90deg, rgba(91,192,235,0.08), rgba(91,192,235,0.02))",
        border: "1px solid rgba(91,192,235,0.4)",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 28, height: 28, borderRadius: "50%",
            background: "rgba(91,192,235,0.15)",
            border: "1px solid var(--info)",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <AIcon name="info" size={14} color="var(--info)"/>
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 600 }}>
              Recomendación de mejora prioritaria:
            </div>
            <div style={{ fontSize: 12, color: "var(--info)", fontWeight: 600, marginTop: 1 }}>
              {a.recommendation}
            </div>
          </div>
        </div>
        <div className="caps" style={{ fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.16em", fontWeight: 600, flexShrink: 0 }}>
          RECOMMENDATION
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { AgentStatsCard, ElementGlyph, FactionBadge, ReelAvatar });
