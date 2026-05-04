// components.jsx — Reusable ZZZ-style primitives
// Exposed on window for cross-script access.

const { useState, useEffect, useRef, useMemo } = React;

// --- Icon set (minimal, original line icons) ----------------------------------
function Icon({ name, size = 14, color = "currentColor", strokeWidth = 1.6 }) {
  const s = size;
  const props = { width: s, height: s, viewBox: "0 0 24 24", fill: "none", stroke: color, strokeWidth, strokeLinecap: "round", strokeLinejoin: "round" };
  switch (name) {
    case "disc":
      return (<svg {...props}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="1" fill={color}/></svg>);
    case "spark":
      return (<svg {...props}><path d="M12 2 L13.5 9 L20 10 L13.5 12 L12 20 L10.5 12 L4 10 L10.5 9 Z"/></svg>);
    case "lock":
      return (<svg {...props}><rect x="5" y="11" width="14" height="10"/><path d="M8 11 V7 a4 4 0 0 1 8 0 v4"/></svg>);
    case "filter":
      return (<svg {...props}><path d="M3 5 H21 L14 13 V20 L10 18 V13 Z"/></svg>);
    case "back":
      return (<svg {...props}><path d="M15 6 L9 12 L15 18"/></svg>);
    case "trash":
      return (<svg {...props}><path d="M4 7 H20"/><path d="M9 7 V5 a1 1 0 0 1 1-1 h4 a1 1 0 0 1 1 1 v2"/><path d="M6 7 L7 20 a1 1 0 0 0 1 1 h8 a1 1 0 0 0 1-1 L18 7"/></svg>);
    case "tag":
      return (<svg {...props}><path d="M3 13 L11 5 H21 V15 L13 23 Z"/><circle cx="17" cy="9" r="1.4" fill={color}/></svg>);
    case "info":
      return (<svg {...props}><circle cx="12" cy="12" r="9"/><path d="M12 8 V8.01"/><path d="M12 11 V17"/></svg>);
    case "up":
      return (<svg {...props}><path d="M5 13 L12 6 L19 13"/><path d="M5 19 L12 12 L19 19"/></svg>);
    case "down":
      return (<svg {...props}><path d="M5 11 L12 18 L19 11"/></svg>);
    case "x":
      return (<svg {...props}><path d="M6 6 L18 18 M18 6 L6 18"/></svg>);
    case "minimize":
      return (<svg {...props}><path d="M5 19 H19"/></svg>);
    case "maximize":
      return (<svg {...props}><rect x="5" y="5" width="14" height="14"/></svg>);
    case "pause":
      return (<svg {...props}><rect x="6" y="5" width="4" height="14" fill={color}/><rect x="14" y="5" width="4" height="14" fill={color}/></svg>);
    case "settings":
      return (<svg {...props}><circle cx="12" cy="12" r="3"/><path d="M19 12 a7 7 0 0 0-.1-1.2 l2-1.5 -2-3.4 -2.4.9 a7 7 0 0 0-2-1.2 L14 3 h-4 l-.5 2.6 a7 7 0 0 0-2 1.2 L5 6 l-2 3.4 2 1.5 a7 7 0 0 0 0 2.4 l-2 1.5 2 3.4 2.4-.9 a7 7 0 0 0 2 1.2 L10 21 h4 l.5-2.6 a7 7 0 0 0 2-1.2 l2.4.9 2-3.4 -2-1.5 a7 7 0 0 0 .1-1.2 z"/></svg>);
    case "bolt":
      return (<svg {...props}><path d="M13 2 L4 14 H11 L9 22 L20 10 H13 Z"/></svg>);
    case "shield":
      return (<svg {...props}><path d="M12 3 L20 6 V12 a10 10 0 0 1 -8 9 a10 10 0 0 1 -8 -9 V6 Z"/></svg>);
    case "heart":
      return (<svg {...props}><path d="M12 21 L4 13 a5 5 0 0 1 8-6 a5 5 0 0 1 8 6 Z"/></svg>);
    case "crit":
      return (<svg {...props}><path d="M12 3 L13.5 9 L20 10 L13.5 12 L12 20 L10.5 12 L4 10 L10.5 9 Z" fill={color} stroke="none"/></svg>);
    case "anomaly":
      return (<svg {...props}><circle cx="12" cy="12" r="9"/><path d="M7 12 Q9.5 7, 12 12 T17 12"/></svg>);
    case "flame":
      return (<svg {...props}><path d="M12 3 C8 8, 6 10, 6 14 a6 6 0 0 0 12 0 c0-3 -2-5 -3-8 -1 3 -2 4 -3 4 -1-2 0-4 0-7 z"/></svg>);
    case "bell":
      return (<svg {...props}><path d="M6 16 V11 a6 6 0 1 1 12 0 v5 l2 2 H4 z"/><path d="M10 21 a2 2 0 0 0 4 0"/></svg>);
    case "feed":
      return (<svg {...props}><path d="M4 11 a9 9 0 0 1 9 9"/><path d="M4 4 a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1.5" fill={color}/></svg>);
    case "expand":
      return (<svg {...props}><path d="M4 14 V20 H10"/><path d="M20 10 V4 H14"/><path d="M4 20 L10 14"/><path d="M20 4 L14 10"/></svg>);
    case "play":
      return (<svg {...props}><path d="M7 4 L19 12 L7 20 Z" fill={color} stroke="none"/></svg>);
    case "stack":
      return (<svg {...props}><path d="M12 3 L21 8 L12 13 L3 8 Z"/><path d="M3 12 L12 17 L21 12"/><path d="M3 16 L12 21 L21 16"/></svg>);
    case "users":
      return (<svg {...props}><circle cx="9" cy="8" r="3"/><path d="M3 20 a6 6 0 0 1 12 0"/><circle cx="17" cy="8" r="2.5"/><path d="M15 20 a5 5 0 0 1 6-3"/></svg>);
    case "trend":
      return (<svg {...props}><path d="M3 17 L9 11 L13 15 L21 6"/><path d="M15 6 H21 V12"/></svg>);
    case "sword":
      return (<svg {...props}><path d="M14 4 L20 4 L20 10 L9 21 L3 21 L3 15 Z"/><path d="M9 15 L14 10"/></svg>);
    case "book":
      return (<svg {...props}><path d="M5 4 H11 a3 3 0 0 1 3 3 V21 a2 2 0 0 0 -2 -2 H5 Z"/><path d="M19 4 H13 a3 3 0 0 0 -3 3 V21 a2 2 0 0 1 2 -2 H19 Z"/></svg>);
    case "check":
      return (<svg {...props}><path d="M5 12 L10 17 L20 7"/></svg>);
    case "dot":
      return (<svg {...props}><circle cx="12" cy="12" r="4" fill={color} stroke="none"/></svg>);
    default:
      return null;
  }
}

// --- BlockBox: rounded-corner panel with "physical block" depth --------------
// Mimics the in-game panel language: generous radius, top inner highlight,
// bottom inner shadow, drop-shadow underneath. Optional outer border + glow.
function BlockBox({
  radius = 14,
  borderColor = "var(--border-mid)",
  borderWidth = 1,
  bg = "var(--bg-panel-solid)",
  pattern = "none", // 'none' | 'carbon'
  glow,             // 'yellow' | 'positive' | 'info' | 'warning' | undefined
  depth = "md",     // 'none' | 'sm' | 'md' | 'lg'
  glassTop = true,
  style = {},
  className = "",
  children,
  onClick, onMouseEnter, onMouseLeave,
  innerStyle,
}) {
  const depthBox = {
    none: "none",
    sm: "0 2px 6px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05), inset 0 -1px 0 rgba(0,0,0,0.5)",
    md: "0 6px 18px rgba(0,0,0,0.6), 0 2px 4px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.07), inset 0 -1px 0 rgba(0,0,0,0.55)",
    lg: "0 14px 36px rgba(0,0,0,0.75), 0 4px 8px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.09), inset 0 -1px 0 rgba(0,0,0,0.6)",
  }[depth];
  const glowBox = glow === "yellow" ? "0 0 22px rgba(255,203,5,0.45)"
    : glow === "positive" ? "0 0 22px rgba(123,201,31,0.45)"
    : glow === "info" ? "0 0 22px rgba(91,192,235,0.45)"
    : glow === "warning" ? "0 0 22px rgba(255,107,71,0.45)"
    : null;
  const boxShadow = [depthBox, glowBox].filter(Boolean).filter(s => s !== "none").join(", ");
  return (
    <div
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={className}
      style={{
        position: "relative",
        borderRadius: radius,
        background: bg,
        border: `${borderWidth}px solid ${borderColor}`,
        boxShadow,
        overflow: "hidden",
        ...style,
      }}
    >
      {pattern === "carbon" && (
        <div className="zzz-carbon" style={{
          position: "absolute", inset: 0,
          borderRadius: radius - borderWidth,
          pointerEvents: "none",
        }}/>
      )}
      {glassTop && <div className="zzz-glass-top" style={{ borderRadius: `${radius}px ${radius}px 0 0` }}/>}
      <div style={{ position: "relative", zIndex: 1, ...innerStyle }}>
        {children}
      </div>
    </div>
  );
}

// Backward-compat alias — keeps existing call sites working with new visual language.
function ChamferBox({ cut, cutCorners, glow, ...rest }) {
  // Map old chamfer params → new block params:
  //  - cut → radius (clamped 8..18)
  //  - "all" cuts → larger radius for hero panels
  //  - glow drop-shadow string → glow keyword (sniffed)
  let radius = Math.max(8, Math.min(18, cut || 14));
  if (cutCorners === "all") radius = 18;
  let glowKeyword;
  if (typeof glow === "string") {
    if (glow.includes("203,5"))   glowKeyword = "yellow";
    else if (glow.includes("201,31")) glowKeyword = "positive";
    else if (glow.includes("192,235")) glowKeyword = "info";
    else if (glow.includes("107,71"))  glowKeyword = "warning";
  }
  return <BlockBox radius={radius} glow={glowKeyword} {...rest}/>;
}

function makePoly(cut, kind, inset) {
  const c = Math.max(0, cut - inset);
  const i = inset;
  switch (kind) {
    case "tl-br":
      return `polygon(${c+i}px ${i}px, calc(100% - ${i}px) ${i}px, calc(100% - ${i}px) calc(100% - ${c+i}px), calc(100% - ${c+i}px) calc(100% - ${i}px), ${i}px calc(100% - ${i}px), ${i}px ${c+i}px)`;
    case "tr-bl":
      return `polygon(${i}px ${i}px, calc(100% - ${c+i}px) ${i}px, calc(100% - ${i}px) ${c+i}px, calc(100% - ${i}px) calc(100% - ${i}px), ${c+i}px calc(100% - ${i}px), ${i}px calc(100% - ${c+i}px))`;
    case "all":
      return `polygon(${c+i}px ${i}px, calc(100% - ${c+i}px) ${i}px, calc(100% - ${i}px) ${c+i}px, calc(100% - ${i}px) calc(100% - ${c+i}px), calc(100% - ${c+i}px) calc(100% - ${i}px), ${c+i}px calc(100% - ${i}px), ${i}px calc(100% - ${c+i}px), ${i}px ${c+i}px)`;
    case "strip-r":
      return `polygon(${i}px ${i}px, calc(100% - ${c+i}px) ${i}px, calc(100% - ${i}px) calc(100% - ${i}px), ${i}px calc(100% - ${i}px))`;
    case "strip-l":
      return `polygon(${c+i}px ${i}px, calc(100% - ${i}px) ${i}px, calc(100% - ${i}px) calc(100% - ${i}px), ${i}px calc(100% - ${i}px))`;
    case "tl-only":
      return `polygon(${c+i}px ${i}px, calc(100% - ${i}px) ${i}px, calc(100% - ${i}px) calc(100% - ${i}px), ${i}px calc(100% - ${i}px), ${i}px ${c+i}px)`;
    case "tl-tr":
      return `polygon(${c+i}px ${i}px, calc(100% - ${c+i}px) ${i}px, calc(100% - ${i}px) ${c+i}px, calc(100% - ${i}px) calc(100% - ${i}px), ${i}px calc(100% - ${i}px), ${i}px ${c+i}px)`;
    default:
      return `inset(${i}px)`;
  }
}

// --- Hexagon of 6 disc slots (composition icon) -------------------------------
// Slots arranged: top-left, top-right, mid-right, bottom-right, bottom-left, mid-left
function Hexagon6({ size = 220, slots, highlightIndex = -1, centerImg, centerLabel = "AGENT" }) {
  // 6 positions on a regular hexagon
  const r = size * 0.34;
  const cx = size / 2, cy = size / 2;
  const positions = Array.from({ length: 6 }, (_, i) => {
    const a = (-Math.PI / 2) + (i * Math.PI / 3); // start at top
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  });
  // Reorder so visual order matches slots 1..6 nicely (top, TR, BR, bottom, BL, TL)
  const slotOrder = [0, 1, 2, 3, 4, 5];
  const slotSize = size * 0.22;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      {/* Decorative connector lines */}
      <svg width={size} height={size} style={{ position: "absolute", inset: 0 }}>
        <polygon
          points={positions.map(p => `${p.x},${p.y}`).join(" ")}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth="1"
        />
      </svg>
      {/* Center "agent" disc */}
      <div style={{
        position: "absolute",
        left: cx - size * 0.16, top: cy - size * 0.16,
        width: size * 0.32, height: size * 0.32,
        borderRadius: "50%",
        border: "1.5px solid var(--border-mid)",
        background: "radial-gradient(circle at 30% 30%, #2a2a28, #0a0a0a 70%)",
        display: "flex", alignItems: "center", justifyContent: "center",
        overflow: "hidden",
        boxShadow: "inset 0 0 12px rgba(255,203,5,0.08)",
      }}>
        {centerImg ? centerImg : (
          <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.12em" }}>
            {centerLabel}
          </div>
        )}
      </div>
      {/* Slots */}
      {slotOrder.map((idx, i) => {
        const p = positions[idx];
        const slot = slots?.[i];
        const isHi = highlightIndex === i;
        return (
          <div key={i} style={{
            position: "absolute",
            left: p.x - slotSize / 2,
            top: p.y - slotSize / 2,
            width: slotSize, height: slotSize,
          }}>
            <DiscSlot slot={slot} highlight={isHi} index={i + 1} size={slotSize}/>
          </div>
        );
      })}
    </div>
  );
}

function DiscSlot({ slot, highlight, index, size = 50 }) {
  const empty = !slot;
  const tone = slot?.tone || "yellow"; // yellow | purple | empty
  const fill = tone === "purple"
    ? "#9D4EDD"
    : tone === "yellow"
    ? "#FFCB05"
    : "#444";
  const ringColor = highlight ? "var(--yellow)" : "var(--border-mid)";
  return (
    <div style={{
      width: size, height: size,
      borderRadius: "50%",
      background: "#0a0a0a",
      border: `${highlight ? 2 : 1}px solid ${ringColor}`,
      boxShadow: highlight ? "0 0 14px rgba(255,203,5,0.7)" : "inset 0 0 6px rgba(0,0,0,0.6)",
      position: "relative",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      {empty ? (
        <div className="caps" style={{ fontSize: 8, color: "var(--text-dim)" }}>0{index}</div>
      ) : (
        <DiscMark tone={tone} fill={fill} size={size * 0.78}/>
      )}
      {/* level pip */}
      {!empty && slot?.level != null && (
        <div className="num caps" style={{
          position: "absolute",
          bottom: -7, left: "50%",
          transform: "translateX(-50%)",
          background: "#0a0a0a",
          border: "1px solid var(--border-mid)",
          color: tone === "purple" ? "#c79bff" : "var(--yellow)",
          fontSize: 8, padding: "1px 4px",
          letterSpacing: "0.06em",
          whiteSpace: "nowrap",
        }}>
          <span style={{ color: "var(--text-muted)" }}>L</span>{slot.level}
        </div>
      )}
    </div>
  );
}

// Visual fan-blade pattern inside each disc — original mark, not from any specific source
function DiscMark({ tone, fill, size = 36 }) {
  const blades = 5;
  return (
    <svg width={size} height={size} viewBox="-50 -50 100 100" style={{ display: "block" }}>
      {Array.from({ length: blades }).map((_, i) => {
        const a = (i * 360) / blades;
        return (
          <path
            key={i}
            d="M 0 -30 Q 12 -20 14 -4 Q 8 4 0 4 Q -8 4 -14 -4 Q -12 -20 0 -30 Z"
            fill={fill}
            opacity={tone === "yellow" ? 0.95 : 0.85}
            transform={`rotate(${a})`}
          />
        );
      })}
      <circle cx="0" cy="0" r="6" fill="#0a0a0a"/>
      <circle cx="0" cy="0" r="2" fill={fill}/>
    </svg>
  );
}

// --- Chamfered button ----------------------------------------------------------
function ZButton({
  children,
  variant = "default", // default | primary | positive | warning | ghost | yellow
  size = "md", // sm | md | lg
  icon,
  trailingIcon,
  active,
  onClick,
  style = {},
  shortcut,
}) {
  const sizes = {
    sm: { h: 30, px: 14, fs: 11, gap: 6, r: 10 },
    md: { h: 38, px: 18, fs: 12, gap: 8, r: 12 },
    lg: { h: 46, px: 24, fs: 13, gap: 10, r: 14 },
  }[size];
  const palette = {
    default: { bg: "linear-gradient(180deg, #1f1f1f 0%, #121212 100%)", color: "var(--text-primary)", border: "var(--border-mid)", glow: undefined },
    yellow:  { bg: "linear-gradient(180deg, #FFE25C 0%, #E8B500 100%)", color: "#0a0a0a", border: "#FFCB05", glow: "yellow" },
    primary: { bg: "linear-gradient(180deg, #1f1f1f 0%, #0c0c0c 100%)", color: "var(--yellow)", border: "var(--yellow)", glow: "yellow" },
    positive:{ bg: "linear-gradient(180deg, #97E03A 0%, #5fa510 100%)", color: "#0a0a0a", border: "#7BC91F", glow: "positive" },
    warning: { bg: "linear-gradient(180deg, #FF8A6E 0%, #D14A26 100%)", color: "#0a0a0a", border: "#FF6B47", glow: "warning" },
    info:    { bg: "linear-gradient(180deg, #7AD2F5 0%, #3FA6D4 100%)", color: "#0a0a0a", border: "#5BC0EB", glow: "info" },
    ghost:   { bg: "rgba(255,255,255,0.02)", color: "var(--text-secondary)", border: "var(--border-subtle)", glow: undefined },
  }[variant];
  return (
    <BlockBox
      radius={sizes.r}
      bg={palette.bg}
      borderColor={palette.border}
      depth="sm"
      glow={palette.glow}
      onClick={onClick}
      style={{ height: sizes.h, cursor: "pointer", ...style }}
    >
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: sizes.h, padding: `0 ${sizes.px}px`, gap: sizes.gap,
        color: palette.color, fontSize: sizes.fs,
        textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600,
        whiteSpace: "nowrap",
        textShadow: variant === "default" || variant === "primary" || variant === "ghost" ? "none" : "0 1px 0 rgba(255,255,255,0.18)",
      }}>
        {icon && <Icon name={icon} size={sizes.fs + 3} color={palette.color}/>}
        <span>{children}</span>
        {shortcut && (
          <span style={{
            fontSize: sizes.fs - 1, padding: "1px 5px",
            border: `1px solid ${palette.color}`,
            opacity: 0.7,
            fontFamily: "var(--font-mono)",
            letterSpacing: 0,
            borderRadius: 4,
          }}>{shortcut}</span>
        )}
        {trailingIcon && <Icon name={trailingIcon} size={sizes.fs + 3} color={palette.color}/>}
      </div>
    </BlockBox>
  );
}

// --- Stat row (label + value with optional +N badge) --------------------------
function StatRow({ label, value, unit, delta, accent = "default", emphasis = false }) {
  const accentColor = {
    default: "var(--text-primary)",
    yellow: "var(--yellow)",
    positive: "var(--positive)",
    warning: "var(--warning)",
  }[accent];
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "7px 12px",
      borderBottom: "1px solid var(--border-subtle)",
      background: emphasis ? "var(--yellow-tint)" : "transparent",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 500 }}>{label}</span>
        {delta != null && (
          <span className="num" style={{
            fontSize: 10, padding: "1px 5px",
            background: "var(--yellow)", color: "#0a0a0a",
            fontWeight: 700, letterSpacing: "0.04em",
          }}>+{delta}</span>
        )}
      </div>
      <div className="num" style={{
        fontSize: 13, fontWeight: 600, color: accentColor,
        letterSpacing: "0.02em",
      }}>
        {value}{unit && <span style={{ marginLeft: 3, color: "var(--text-secondary)", fontWeight: 500 }}>{unit}</span>}
      </div>
    </div>
  );
}

// --- Score gauge (horizontal bar w/ threshold marker) -------------------------
function ScoreGauge({ score, threshold = 75, max = 100, color = "var(--positive)", height = 10 }) {
  const pct = Math.min(100, (score / max) * 100);
  const tpct = (threshold / max) * 100;
  return (
    <div style={{ position: "relative", height, background: "#0a0a0a", border: "1px solid var(--border-subtle)", overflow: "hidden" }}>
      <div style={{
        position: "absolute", inset: 0, width: `${pct}%`,
        background: `linear-gradient(90deg, ${color}, ${color})`,
        boxShadow: `0 0 8px ${color}`,
        transition: "width 400ms ease-out",
      }}/>
      {/* tick marks */}
      <div style={{ position: "absolute", inset: 0, backgroundImage: "repeating-linear-gradient(90deg, transparent 0, transparent 9px, rgba(0,0,0,0.4) 9px, rgba(0,0,0,0.4) 10px)" }}/>
      {/* threshold marker */}
      <div style={{
        position: "absolute", top: -2, bottom: -2, left: `${tpct}%`,
        width: 2, background: "var(--yellow)",
        boxShadow: "0 0 6px rgba(255,203,5,0.8)",
      }}/>
    </div>
  );
}

// --- Tag / pill ---------------------------------------------------------------
function Tag({ children, color = "default", size = "sm" }) {
  const palette = {
    default: { bg: "rgba(255,255,255,0.04)", border: "var(--border-mid)", color: "var(--text-secondary)" },
    yellow:  { bg: "rgba(255,203,5,0.14)", border: "var(--yellow)", color: "var(--yellow)" },
    positive:{ bg: "rgba(123,201,31,0.14)", border: "var(--positive)", color: "var(--positive)" },
    warning: { bg: "rgba(255,107,71,0.14)", border: "var(--warning)", color: "var(--warning)" },
    info:    { bg: "rgba(91,192,235,0.14)", border: "var(--info)", color: "var(--info)" },
    purple:  { bg: "rgba(157,78,221,0.14)", border: "var(--purple)", color: "var(--purple)" },
    pink:    { bg: "rgba(255,77,138,0.14)", border: "var(--pink)", color: "var(--pink)" },
    solid:   { bg: "linear-gradient(180deg, #FFE25C, #E8B500)", border: "var(--yellow)", color: "#0a0a0a" },
  }[color];
  const fs = size === "sm" ? 10 : 11;
  const py = size === "sm" ? 2 : 3;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontSize: fs, padding: `${py}px 8px`,
      background: palette.bg,
      border: `1px solid ${palette.border}`,
      color: palette.color,
      textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600,
      lineHeight: 1.2,
      borderRadius: 999,
      fontFamily: "var(--font-ui)",
      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06)",
    }}>
      {children}
    </span>
  );
}

// --- Rarity badge with depth ---------------------------------------------------
function Rarity({ tier = "S" }) {
  const color = { S: "#FFCB05", A: "#9D4EDD", B: "#5BC0EB" }[tier] || "#aaa";
  return (
    <div style={{
      width: 24, height: 24, borderRadius: 6,
      background: `linear-gradient(180deg, ${color} 0%, ${color}cc 100%)`,
      display: "flex", alignItems: "center", justifyContent: "center",
      boxShadow: `0 2px 4px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.4), 0 0 8px ${color}66`,
      border: `1px solid ${color}`,
    }}>
      <span className="display num" style={{ color: "#0a0a0a", fontSize: 14, fontWeight: 800, lineHeight: 1, textShadow: "0 1px 0 rgba(255,255,255,0.3)" }}>{tier}</span>
    </div>
  );
}

// --- KPI card ------------------------------------------------------------------
function KPI({ label, value, sub, color = "var(--text-primary)", small = false }) {
  return (
    <BlockBox radius={10} depth="sm" bg="rgba(255,255,255,0.025)" borderColor="var(--border-subtle)" glassTop={false}
      style={{ minWidth: small ? 70 : 100 }}>
      <div style={{ padding: small ? "8px 10px" : "10px 14px" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
        <div className="display num" style={{ fontSize: small ? 18 : 24, color, fontWeight: 700, lineHeight: 1 }}>{value}</div>
        {sub && <div className="num" style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 3 }}>{sub}</div>}
      </div>
    </BlockBox>
  );
}

// --- Section heading inside a panel -------------------------------------------
function SectionHead({ children, right, accent = "var(--yellow)" }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "10px 14px",
      borderBottom: "1px solid var(--border-subtle)",
      background: "rgba(0,0,0,0.4)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 3, height: 12, background: accent, boxShadow: `0 0 6px ${accent}` }}/>
        <div className="caps" style={{ fontSize: 11, color: "var(--text-primary)", fontWeight: 600 }}>{children}</div>
      </div>
      {right}
    </div>
  );
}

// Export to window for cross-script usage
Object.assign(window, {
  Icon, ChamferBox, BlockBox, Hexagon6, DiscSlot, DiscMark, ZButton, StatRow, ScoreGauge, Tag, Rarity, KPI, SectionHead, makePoly,
});
