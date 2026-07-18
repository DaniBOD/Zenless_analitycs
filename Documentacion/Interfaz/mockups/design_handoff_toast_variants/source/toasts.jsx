// toasts.jsx — 5 variants + 3 states of the floating toast (360x110)
// Variants: equipar (positive), mejorar (info), reserva (yellow), descartar (warning), lategame (yellow/info)
// States: idle | hover (paused) | expanding | fade-out

const { Icon: TIcon, ChamferBox: TChamferBox, ZButton: TBtn, Tag: TTag, Rarity: TRarity } = window;

// Disc thumbnail used inside toasts (small) — real set logo, fallback to abstract mark
function DiscThumb({ tone = "yellow", tier = "S", size = 64, setLogo, accent }) {
  const fill = accent || (tone === "purple" ? "#9D4EDD" : tone === "info" ? "#5BC0EB" : "#FFCB05");
  return (
    <div style={{
      width: size, height: size,
      position: "relative",
      background: `radial-gradient(circle at 30% 30%, ${fill}1a, #050505 75%)`,
      border: `1px solid ${fill}66`,
      borderRadius: 12,
      display: "flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0,
      boxShadow: `inset 0 1px 0 rgba(255,255,255,0.06), 0 2px 4px rgba(0,0,0,0.5), 0 0 10px ${fill}33`,
      overflow: "hidden",
    }}>
      {setLogo ? (
        <img src={setLogo} style={{ width: size * 0.78, height: size * 0.78, objectFit: "contain", filter: `drop-shadow(0 0 4px ${fill}88)` }}/>
      ) : (
        <window.DiscMark tone={tone} fill={fill} size={size * 0.7}/>
      )}
      <div style={{ position: "absolute", right: 4, bottom: 4 }}>
        <window.Rarity tier={tier} size={Math.round(size * 0.36)}/>
      </div>
    </div>
  );
}

// Urgency bar with countdown
function UrgencyBar({ urgency = 0.7, paused = false, color = "var(--yellow)" }) {
  return (
    <div style={{
      height: 4, background: "rgba(255,255,255,0.06)",
      position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", inset: 0,
        width: `${urgency * 100}%`,
        background: color,
        boxShadow: `0 0 8px ${color}`,
        animation: paused ? "none" : "zzz-pulse-y 1.6s infinite",
      }}/>
    </div>
  );
}

// Countdown ring (top-right)
function Countdown({ secs = 4, paused = false }) {
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontFamily: "var(--font-mono)",
      fontSize: 10, color: paused ? "var(--yellow)" : "var(--text-secondary)",
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%",
        background: paused ? "var(--yellow)" : "var(--positive)",
        boxShadow: paused ? "0 0 6px var(--yellow)" : "0 0 6px var(--positive)",
        animation: paused ? "none" : "zzz-blink 1.2s infinite",
      }}/>
      <span className="num">{paused ? "PAUSE" : `${secs}.0s`}</span>
    </div>
  );
}

// Variant config — color, icon, title
const VARIANTS = {
  equipar:   { label: "EQUIPAR",  color: "var(--positive)", glow: "positive", icon: "check", barColor: "var(--positive)", tone: "yellow" },
  equipado:  { label: "EQUIPADO", color: "var(--positive)", glow: "positive", icon: "check", barColor: "var(--positive)", tone: "yellow" },
  mejorar:   { label: "MEJORAR",  color: "var(--info)",     glow: "info",     icon: "up",    barColor: "var(--info)",     tone: "info"   },
  reserva:   { label: "RESERVA",  color: "var(--yellow)",   glow: "yellow",   icon: "stack", barColor: "var(--yellow)",   tone: "yellow" },
  descartar: { label: "DESCARTAR",color: "var(--warning)",  glow: "warning",  icon: "trash", barColor: "var(--warning)",  tone: "purple" },
  lategame:  { label: "RUN REGISTRADA", color: "var(--yellow)", glow: "yellow", icon: "feed", barColor: "var(--yellow)", tone: "yellow" },
  reemplazado: { label: "REEMPLAZADO", color: "var(--purple)", glow: "purple", icon: "swap", barColor: "var(--purple)", tone: "purple" },
};

// Generic toast frame
function Toast({
  variant = "equipar",
  state = "idle", // idle | hover | expanding | fade
  width = 380, height = 116,
  data,
  showOuterChrome = true,
  label,
}) {
  const v = VARIANTS[variant];
  const isHover = state === "hover";
  const isFade = state === "fade";
  const isExpanding = state === "expanding";

  const opacity = isFade ? 0.35 : isHover ? 1 : 0.96;
  const scale = isHover ? 1.02 : isExpanding ? 1.08 : 1;

  return (
    <div style={{ position: "relative", width, height: height + (showOuterChrome ? 28 : 0) }}>
      {showOuterChrome && (
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0,
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "0 4px 6px",
        }}>
          <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.14em" }}>
            {label}
          </div>
          <div className="caps num" style={{ fontSize: 9, color: "var(--text-dim)", letterSpacing: "0.1em" }}>
            ALWAYS-ON-TOP · BR
          </div>
        </div>
      )}
      <div style={{
        position: "absolute",
        top: showOuterChrome ? 28 : 0,
        left: 0, width, height,
        opacity, transform: `scale(${scale})`,
        transformOrigin: "bottom right",
        transition: "opacity 200ms ease-out, transform 200ms ease-out",
      }}>
        <window.BlockBox
          radius={16}
          borderColor={v.color}
          borderWidth={1.5}
          bg="rgba(10,10,10,0.94)"
          pattern="carbon"
          glow={v.glow}
          depth="lg"
          glassTop={true}
          style={{ width, height }}
          innerStyle={{ width, height, padding: "10px 14px 0", display: "flex", flexDirection: "column", overflow: "hidden" }}
        >
          {variant === "lategame" ? (
            <LategameContent data={data} state={state} v={v}/>
          ) : variant === "reemplazado" ? (
            <SwapToastContent data={data} state={state} v={v}/>
          ) : variant === "equipado" ? (
            <EquipadoContent data={data} state={state} v={v}/>
          ) : (
            <DiscToastContent variant={variant} data={data} state={state} v={v}/>
          )}
        </window.BlockBox>
        {/* Hover prompt */}
        {isHover && (
          <div style={{
            position: "absolute", left: 12, bottom: -22,
            display: "flex", gap: 8, alignItems: "center",
            fontSize: 9, color: "var(--text-secondary)",
            fontFamily: "var(--font-mono)", letterSpacing: "0.04em",
          }}>
            <kbd style={kbdStyle}>CLICK</kbd> ABRIR PANEL
            <kbd style={kbdStyle}>HOVER</kbd> CONGELADO
          </div>
        )}
        {isExpanding && (
          <div style={{
            position: "absolute", inset: -8,
            border: "1.5px dashed var(--yellow)",
            borderRadius: 22,
            opacity: 0.6,
            pointerEvents: "none",
          }}/>
        )}
      </div>
    </div>
  );
}

const kbdStyle = {
  border: "1px solid var(--border-mid)",
  padding: "1px 5px",
  background: "rgba(255,255,255,0.04)",
  color: "var(--text-secondary)",
  fontSize: 9,
  fontFamily: "var(--font-mono)",
};

function DiscToastContent({ variant, data, state, v }) {
  const d = data || {};
  return (
    <>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 18, height: 18,
            background: v.color, color: "#0a0a0a",
            display: "flex", alignItems: "center", justifyContent: "center",
            clipPath: "polygon(4px 0, 100% 0, calc(100% - 4px) 100%, 0 100%)",
            boxShadow: `0 0 8px ${v.color}`,
          }}>
            <TIcon name={v.icon} size={11} color="#0a0a0a" strokeWidth={2.4}/>
          </div>
          <div className="caps" style={{ fontSize: 11, color: v.color, fontWeight: 700, letterSpacing: "0.12em" }}>
            {v.label}
          </div>
          <div style={{ width: 1, height: 12, background: "var(--border-mid)" }}/>
          <div className="caps num" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.1em" }}>
            #{d.id || "00482"}
          </div>
        </div>
        <Countdown secs={d.secs ?? 4} paused={state === "hover"}/>
      </div>

      {/* Body: thumb + meta */}
      <div style={{ display: "flex", gap: 10, flex: 1 }}>
        <DiscThumb tone={v.tone} tier={d.tier || "S"} size={56} setLogo={d.setLogo} accent={d.accent || v.color}/>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 600, lineHeight: 1.15, marginBottom: 1, letterSpacing: "0.01em" }}>
              {d.set || "Tecno Pícido"}
              <span style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
                · Slot {d.slot ?? 4}
              </span>
            </div>
            <div className="num" style={{ fontSize: 11, color: "var(--text-secondary)", letterSpacing: "0.02em" }}>
              {d.main || "ATK%"} <span style={{ color: "var(--yellow)" }}>{d.mainVal || "30%"}</span>
              {d.subs && <span style={{ color: "var(--text-muted)" }}> · {d.subs}</span>}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <div style={{ fontSize: 9, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.1em" }}>→</div>
              {d.targetIco && (
                <img src={d.targetIco} style={{
                  width: 18, height: 18, borderRadius: "50%",
                  objectFit: "cover",
                  border: `1px solid ${v.color}`,
                  boxShadow: `0 0 4px ${v.color}66`,
                  flexShrink: 0,
                }}/>
              )}
              <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 600 }}>
                {d.target || "Yanagi"}
                <span className="num" style={{ color: "var(--text-secondary)", fontWeight: 400, marginLeft: 4, fontSize: 10 }}>
                  M{d.mind ?? 2}
                </span>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span className="caps" style={{ fontSize: 9, color: "var(--text-muted)" }}>SCORE</span>
              <span className="display num" style={{ fontSize: 18, fontWeight: 700, color: v.color, letterSpacing: 0 }}>
                {d.score ?? "87.3"}
              </span>
              {d.delta != null && (
                <span className="num" style={{ fontSize: 10, color: "var(--positive)", fontWeight: 600 }}>
                  ▲{d.delta}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Footer urgency bar */}
      <div style={{ marginTop: 8, marginLeft: -14, marginRight: -14, marginBottom: 0 }}>
        <UrgencyBar urgency={d.urgency ?? 0.78} paused={state === "hover"} color={v.barColor}/>
        <div style={{
          display: "flex", justifyContent: "space-between",
          padding: "5px 14px 7px",
          fontSize: 9, color: "var(--text-muted)",
          letterSpacing: "0.06em", textTransform: "uppercase",
        }}>
          <span>{d.urgencyLabel || "URGENCIA ALTA"}</span>
          <span className="num">{d.threshold || "thr 0.75"}</span>
        </div>
      </div>
    </>
  );
}

function LategameContent({ data, state, v }) {
  const d = data || {};
  const team = d.team || ["Yanagi", "Burnice", "Lighter"];
  const stars = d.stars ?? 3;
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 18, height: 18, background: v.color, color: "#0a0a0a",
            display: "flex", alignItems: "center", justifyContent: "center",
            clipPath: "polygon(4px 0, 100% 0, calc(100% - 4px) 100%, 0 100%)",
            boxShadow: `0 0 8px ${v.color}`,
          }}>
            <TIcon name="feed" size={11} color="#0a0a0a" strokeWidth={2.4}/>
          </div>
          <div className="caps" style={{ fontSize: 11, color: v.color, fontWeight: 700, letterSpacing: "0.12em" }}>
            RUN LATEGAME REGISTRADA
          </div>
        </div>
        <Countdown secs={d.secs ?? 4} paused={state === "hover"}/>
      </div>

      <div style={{ display: "flex", gap: 10, flex: 1 }}>
        {/* Team triplet */}
        <div style={{ display: "flex", gap: 4 }}>
          {team.map((member, i) => {
            const isObj = typeof member === "object";
            const name = isObj ? member.name : member;
            const ico = isObj ? member.ico : null;
            const accent = isObj ? member.accent : (i === 0 ? "var(--yellow)" : "var(--border-mid)");
            const isLead = i === 0;
            return (
            <div key={i} style={{
              width: 38, height: 50,
              background: isLead ? "linear-gradient(180deg, #2a2418, #0a0a0a)" : "linear-gradient(180deg, #1a1820, #0a0a0a)",
              border: isLead ? `1.5px solid ${accent}` : "1px solid var(--border-mid)",
              boxShadow: isLead ? `0 0 8px ${accent}66` : "none",
              display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end",
              padding: "2px",
            }}>
              <div style={{
                width: 24, height: 24, borderRadius: "50%",
                background: "#0a0a0a",
                border: `1px solid ${isLead ? accent : "var(--border-mid)"}`,
                marginBottom: 2,
                overflow: "hidden",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                {ico ? <img src={ico} style={{ width: "100%", height: "100%", objectFit: "cover" }}/>
                     : <div style={{ width: "100%", height: "100%", background: ["#3a2a18", "#2a3a18", "#18283a"][i] }}/>}
              </div>
              <div style={{ fontSize: 7, color: isLead ? accent : "var(--text-secondary)", letterSpacing: "0.04em", textAlign: "center", fontWeight: isLead ? 600 : 400 }}>
                {name.slice(0, 6)}
              </div>
            </div>
          );})}
        </div>

        {/* Stats */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div className="caps" style={{ fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.1em" }}>
              {d.contenido || "DEADLY ASSAULT · NODO 3"}
            </div>
            <div style={{ display: "flex", gap: 1 }}>
              {Array.from({ length: 3 }).map((_, i) => (
                <span key={i} style={{
                  fontSize: 13, color: i < stars ? "var(--yellow)" : "var(--text-dim)",
                  textShadow: i < stars ? "0 0 4px rgba(255,203,5,0.7)" : "none",
                  lineHeight: 1,
                }}>★</span>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginTop: 4 }}>
            <div>
              <span className="caps" style={{ fontSize: 9, color: "var(--text-muted)", marginRight: 6 }}>TIEMPO</span>
              <span className="display num" style={{ fontSize: 18, color: "var(--positive)", fontWeight: 700 }}>
                {d.time || "1:48"}
              </span>
              <span className="num" style={{ fontSize: 9, color: "var(--positive)", marginLeft: 4 }}>−14s</span>
            </div>
            <div>
              <span className="caps" style={{ fontSize: 9, color: "var(--text-muted)", marginRight: 6 }}>DPS·SHARE</span>
              <span className="display num" style={{ fontSize: 16, color: "var(--yellow)", fontWeight: 700 }}>
                {d.dps || "67%"}
              </span>
              <span className="num" style={{ fontSize: 9, color: "var(--text-secondary)", marginLeft: 4 }}>{d.dpsTarget || "Yanagi"}</span>
            </div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 8, marginLeft: -14, marginRight: -14, marginBottom: 0 }}>
        <UrgencyBar urgency={1} paused={state === "hover"} color="var(--yellow)"/>
        <div style={{
          display: "flex", justifyContent: "space-between",
          padding: "5px 14px 7px",
          fontSize: 9, color: "var(--text-muted)",
          letterSpacing: "0.06em", textTransform: "uppercase",
        }}>
          <span>F11 · MARCADO PARA RF-13 RETRO-FEEDBACK</span>
          <span className="num">+EXP 600</span>
        </div>
      </div>
    </>
  );
}

// ---- REEMPLAZADO · swap confirmation (no score, no urgency, passive sync) ----
function SwapPj({ ico, name, mind, label, highlight }) {
  const accent = "var(--purple)";
  const ring = highlight ? accent : "var(--border-mid)";
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, width: 56, flexShrink: 0 }}>
      <div className="caps" style={{
        fontSize: 8, letterSpacing: "0.14em", fontWeight: 700,
        color: highlight ? accent : "var(--text-muted)",
      }}>{label}</div>
      <div style={{
        width: 38, height: 38, borderRadius: "50%",
        border: `${highlight ? 1.5 : 1}px solid ${ring}`,
        background: "#0a0a0a",
        overflow: "hidden", flexShrink: 0,
        opacity: highlight ? 1 : 0.55,
        filter: highlight ? "none" : "grayscale(0.5)",
        boxShadow: highlight ? "0 0 9px rgba(157,78,221,0.55), inset 0 0 6px rgba(157,78,221,0.25)" : "none",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {ico
          ? <img src={ico} style={{ width: "100%", height: "100%", objectFit: "cover" }}/>
          : <div style={{ width: "100%", height: "100%", background: "#222" }}/>}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 3, maxWidth: 56 }}>
        <span style={{
          fontSize: 10, fontWeight: 600, lineHeight: 1,
          color: highlight ? "var(--text-primary)" : "var(--text-secondary)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 44,
        }}>{name}</span>
        {mind != null && (
          <span className="num" style={{ fontSize: 8, color: "var(--text-muted)" }}>M{mind}</span>
        )}
      </div>
    </div>
  );
}

function SwapArrow() {
  return (
    <svg width="22" height="14" viewBox="0 0 22 14" style={{ flexShrink: 0 }}>
      <path d="M1 7 H17" stroke="var(--purple)" strokeWidth="1.6" strokeLinecap="round"
        style={{ filter: "drop-shadow(0 0 3px rgba(157,78,221,0.6))" }}/>
      <path d="M14 3 L18 7 L14 11" stroke="var(--purple)" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round"
        style={{ filter: "drop-shadow(0 0 3px rgba(157,78,221,0.6))" }}/>
    </svg>
  );
}

function SwapToastContent({ data, state, v }) {
  const d = data || {};
  const disc = d.disc || {};
  const from = d.from || {};
  const to = d.to || {};
  return (
    <>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 18, height: 18,
            background: v.color, color: "#0a0a0a",
            display: "flex", alignItems: "center", justifyContent: "center",
            clipPath: "polygon(4px 0, 100% 0, calc(100% - 4px) 100%, 0 100%)",
            boxShadow: `0 0 8px ${v.color}`,
          }}>
            <TIcon name={v.icon} size={11} color="#0a0a0a" strokeWidth={2.4}/>
          </div>
          <div className="caps" style={{ fontSize: 11, color: v.color, fontWeight: 700, letterSpacing: "0.12em" }}>
            {v.label}
          </div>
          <div style={{ width: 1, height: 12, background: "var(--border-mid)" }}/>
          <div className="caps num" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.1em" }}>
            #{d.id || "00731"}
          </div>
        </div>
        {/* Synced badge instead of countdown */}
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          padding: "2px 7px",
          border: "1px solid rgba(123,201,31,0.4)",
          background: "rgba(123,201,31,0.08)",
          borderRadius: 3,
        }}>
          <TIcon name="check" size={9} color="var(--positive)" strokeWidth={3}/>
          <span className="caps num" style={{ fontSize: 8.5, color: "var(--positive)", letterSpacing: "0.1em", fontWeight: 600 }}>
            SINCRONIZADO
          </span>
        </div>
      </div>

      {/* Body: PJ origen → disco → PJ destino */}
      <div style={{ display: "flex", alignItems: "center", gap: 4, flex: 1 }}>
        <SwapPj ico={from.ico} name={from.name || "Yixuan"} mind={from.mind} label="DEJA" highlight={false}/>
        <SwapArrow/>
        {/* Disc center */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, flex: 1, minWidth: 0 }}>
          <DiscThumb tone="purple" tier={disc.tier || "S"} size={42} setLogo={disc.setLogo} accent={disc.accent || v.color}/>
          <div style={{ textAlign: "center", lineHeight: 1.1, maxWidth: "100%" }}>
            <span style={{
              fontSize: 10.5, fontWeight: 600, color: "var(--text-primary)",
              display: "inline-block", maxWidth: 124,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", verticalAlign: "bottom",
            }}>{disc.set || "Monarca del Pináculo"}</span>
            <span className="num" style={{ fontSize: 9, color: "var(--text-muted)", marginLeft: 5 }}>
              Slot {disc.slot ?? 2}
            </span>
          </div>
        </div>
        <SwapArrow/>
        <SwapPj ico={to.ico} name={to.name || "Nangong Yu"} mind={to.mind} label="EQUIPA" highlight={true}/>
      </div>

      {/* Footer: static purple bar + sync status line */}
      <div style={{ marginTop: 6, marginLeft: -14, marginRight: -14, marginBottom: 0 }}>
        <div style={{ height: 3, background: "rgba(255,255,255,0.05)", position: "relative", overflow: "hidden" }}>
          <div style={{ position: "absolute", inset: 0, background: "var(--purple)", boxShadow: "0 0 8px var(--purple)" }}/>
        </div>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "5px 14px 7px",
          fontSize: 9, color: "var(--text-muted)",
          letterSpacing: "0.06em", textTransform: "uppercase",
        }}>
          <span>EQUIPAMIENTO SINCRONIZADO</span>
          <span className="num" style={{ textTransform: "none" }}>inventory_discs ✓</span>
        </div>
      </div>
    </>
  );
}

// ---- EQUIPADO · post-suggestion confirmation (sugerencia "Equipar" ya fue aplicada) ----
function EquipadoContent({ data, state, v }) {
  const d = data || {};
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 18, height: 18,
            background: v.color, color: "#0a0a0a",
            display: "flex", alignItems: "center", justifyContent: "center",
            clipPath: "polygon(4px 0, 100% 0, calc(100% - 4px) 100%, 0 100%)",
            boxShadow: `0 0 8px ${v.color}`,
          }}>
            <TIcon name={v.icon} size={11} color="#0a0a0a" strokeWidth={2.4}/>
          </div>
          <div className="caps" style={{ fontSize: 11, color: v.color, fontWeight: 700, letterSpacing: "0.12em" }}>
            {v.label}
          </div>
          <div style={{ width: 1, height: 12, background: "var(--border-mid)" }}/>
          <div className="caps num" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.1em" }}>
            #{d.id || "00482"}
          </div>
        </div>
        {/* Confirmed badge instead of countdown — passive, sugerencia ya resuelta */}
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          padding: "2px 7px",
          border: "1px solid rgba(123,201,31,0.4)",
          background: "rgba(123,201,31,0.08)",
          borderRadius: 3,
        }}>
          <TIcon name="check" size={9} color="var(--positive)" strokeWidth={3}/>
          <span className="caps num" style={{ fontSize: 8.5, color: "var(--positive)", letterSpacing: "0.1em", fontWeight: 600 }}>
            CONFIRMADO
          </span>
        </div>
      </div>

      {/* Body: thumb + meta (mismo layout que EQUIPAR, sin score/urgencia) */}
      <div style={{ display: "flex", gap: 10, flex: 1 }}>
        <DiscThumb tone={v.tone} tier={d.tier || "S"} size={56} setLogo={d.setLogo} accent={d.accent || v.color}/>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 600, lineHeight: 1.15, marginBottom: 1, letterSpacing: "0.01em" }}>
              {d.set || "Tecno Pícido"}
              <span style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
                · Slot {d.slot ?? 4}
              </span>
            </div>
            <div className="num" style={{ fontSize: 11, color: "var(--text-secondary)", letterSpacing: "0.02em" }}>
              {d.main || "ATK%"} <span style={{ color: "var(--yellow)" }}>{d.mainVal || "30%"}</span>
              {d.subs && <span style={{ color: "var(--text-muted)" }}> · {d.subs}</span>}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <TIcon name="check" size={10} color="var(--positive)" strokeWidth={3}/>
              {d.targetIco && (
                <img src={d.targetIco} style={{
                  width: 18, height: 18, borderRadius: "50%",
                  objectFit: "cover",
                  border: `1px solid ${v.color}`,
                  boxShadow: `0 0 4px ${v.color}66`,
                  flexShrink: 0,
                }}/>
              )}
              <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 600 }}>
                {d.target || "Yanagi"}
                <span className="num" style={{ color: "var(--text-secondary)", fontWeight: 400, marginLeft: 4, fontSize: 10 }}>
                  M{d.mind ?? 2}
                </span>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span className="caps" style={{ fontSize: 9, color: "var(--text-muted)" }}>SCORE</span>
              <span className="display num" style={{ fontSize: 18, fontWeight: 700, color: v.color, letterSpacing: 0 }}>
                {d.score ?? "87.3"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer: static confirmation bar, no urgency/countdown */}
      <div style={{ marginTop: 8, marginLeft: -14, marginRight: -14, marginBottom: 0 }}>
        <div style={{ height: 4, background: "rgba(255,255,255,0.06)", position: "relative", overflow: "hidden" }}>
          <div style={{ position: "absolute", inset: 0, background: v.color, boxShadow: `0 0 8px ${v.color}` }}/>
        </div>
        <div style={{
          display: "flex", justifyContent: "space-between",
          padding: "5px 14px 7px",
          fontSize: 9, color: "var(--text-muted)",
          letterSpacing: "0.06em", textTransform: "uppercase",
        }}>
          <span>SUGERENCIA APLICADA · DETECTADO EN JUEGO</span>
          <span className="num" style={{ textTransform: "none" }}>inventory_discs ✓</span>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { Toast, DiscThumb });
