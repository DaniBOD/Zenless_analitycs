// pj-modal.jsx — Modal de PJ · 1000×640 · paleta dinámica por PJ
const { ChamferBox: PMC, Icon: PMI, Tag: PMT, SectionHead: PMS, ZButton: PMB, Hexagon6: PMH } = window;

function PjModal({ pjId = "yanagi", width = 1000, height = 640 }) {
  const pj = window.PJS[pjId];
  const pal = pj.palette;
  const set4 = Object.values(window.SETS).find(s => s.name === pj.set4);
  const set2 = Object.values(window.SETS).find(s => s.name === pj.set2);
  // hex slots: 4 from set4, 2 from set2
  const slots = [
    { logo: set4.logo, level: 15 },
    { logo: set4.logo, level: 15 },
    { logo: set4.logo, level: 15 },
    { logo: set4.logo, level: 15 },
    { logo: set2.logo, level: 12 },
    { logo: set2.logo, level: 9 },
  ];
  return (
    <div style={{ width, height, position: "relative", background: "rgba(0,0,0,0.85)", backdropFilter: "blur(6px)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <PMC cut={18} cutCorners="all" borderColor={pal.p} bg="var(--bg-panel-solid)" pattern="carbon"
        style={{ width: width - 60, height: height - 60, boxShadow: `0 0 0 2px ${pal.p}, 0 0 60px ${pal.p}66`, position: "relative", overflow: "hidden" }}
        innerStyle={{ display: "flex", flexDirection: "column", height: "100%" }}>

        {/* Hero header — gradient + extend image */}
        <div style={{ position: "relative", height: 200, overflow: "hidden", flexShrink: 0 }}>
          <div style={{ position: "absolute", inset: 0, background: `linear-gradient(135deg, ${pal.p} 0%, ${pal.s} 50%, #0a0a0a 100%)`, opacity: 0.85 }}/>
          <img src={pj.ext} style={{ position: "absolute", right: 30, top: -40, height: 320, opacity: 0.95, filter: "drop-shadow(0 12px 30px rgba(0,0,0,0.6))" }}/>
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(0,0,0,0.1) 0%, transparent 40%, rgba(10,10,10,0.6) 100%)" }}/>

          {/* Close */}
          <div style={{ position: "absolute", right: 14, top: 14, width: 28, height: 28, border: `1px solid ${pal.p}`, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "var(--text-primary)" }}>
            <PMI name="x" size={12}/>
          </div>

          {/* Identity */}
          <div style={{ position: "absolute", left: 24, bottom: 18, display: "flex", alignItems: "flex-end", gap: 16 }}>
            <div style={{ width: 96, height: 96, borderRadius: 16, overflow: "hidden", border: `2px solid ${pal.p}`, boxShadow: `0 0 24px ${pal.p}99`, flexShrink: 0, background: "#0a0a0a" }}>
              <img src={pj.ico} style={{ width: "100%", height: "100%", objectFit: "cover" }}/>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <img src={pj.factionLogo} style={{ height: 22, objectFit: "contain", filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.6))" }}/>
                <span className="caps" style={{ fontSize: 10, color: "rgba(255,255,255,0.8)", letterSpacing: "0.16em", fontWeight: 600 }}>{pj.faction}</span>
              </div>
              <div className="display" style={{ fontSize: 42, color: "#fff", fontWeight: 800, letterSpacing: "0.02em", lineHeight: 1, fontStyle: "italic", textShadow: "0 4px 12px rgba(0,0,0,0.7)" }}>
                {pj.name}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                <span style={{ padding: "3px 10px", background: "rgba(0,0,0,0.5)", border: `1px solid ${pj.elemColor}`, color: pj.elemColor, fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>{pj.elem}</span>
                <span style={{ padding: "3px 10px", background: "rgba(0,0,0,0.5)", border: `1px solid ${pal.p}`, color: pal.p, fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>{pj.role}</span>
                <span style={{ padding: "3px 10px", background: pal.p, color: "#0a0a0a", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em" }}>M{pj.mind}</span>
              </div>
            </div>
          </div>

          {/* Build pct */}
          <div style={{ position: "absolute", right: 24, bottom: 18, textAlign: "right" }}>
            <div className="caps" style={{ fontSize: 9, color: "rgba(255,255,255,0.7)", letterSpacing: "0.14em", marginBottom: 2 }}>BUILD COMPLETION</div>
            <div className="display num" style={{ fontSize: 32, color: pal.p, fontWeight: 800, lineHeight: 1, textShadow: `0 0 16px ${pal.p}` }}>{pj.buildPct}<span style={{ fontSize: 16 }}>%</span></div>
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 280px 1fr", gap: 0, overflow: "hidden" }}>
          {/* Stats col */}
          <div style={{ padding: "14px 18px", borderRight: "1px solid var(--border-subtle)", overflow: "auto" }}>
            <div className="caps" style={{ fontSize: 10, color: pal.p, letterSpacing: "0.14em", fontWeight: 700, marginBottom: 8 }}>STATS COMBATE</div>
            <StatGauge label="PV" v={pj.stats.pv.toLocaleString("es-ES")} pct={Math.min(100, pj.stats.pv / 200)} c={pal.p}/>
            <StatGauge label="Ataque" v={pj.stats.atk.toLocaleString("es-ES")} pct={Math.min(100, pj.stats.atk / 30)} c={pal.p} hi/>
            <StatGauge label="Defensa" v={pj.stats.def} pct={Math.min(100, pj.stats.def / 14)} c={pal.p}/>
            <StatGauge label="Impacto" v={pj.stats.impact} pct={Math.min(100, pj.stats.impact / 2)} c={pal.p}/>
            <StatGauge label="Prob. Crítico" v={`${pj.stats.cr.toFixed(1)}%`} pct={pj.stats.cr} c={pal.p} hi={pj.stats.cr > 50}/>
            <StatGauge label="Daño Crítico" v={`${pj.stats.cd.toFixed(1)}%`} pct={Math.min(100, pj.stats.cd / 2)} c={pal.p} hi={pj.stats.cd > 100}/>
            <StatGauge label="Maestría Anom" v={pj.stats.anom} pct={Math.min(100, pj.stats.anom / 5)} c={pal.p} hi={pj.stats.anom > 250}/>
            <StatGauge label="Recup. Energía" v={pj.stats.er.toFixed(2)} pct={Math.min(100, pj.stats.er * 50)} c={pal.p}/>
          </div>

          {/* Hexagon col */}
          <div style={{ padding: "14px 12px", borderRight: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-start" }}>
            <div className="caps" style={{ fontSize: 10, color: pal.p, letterSpacing: "0.14em", fontWeight: 700, alignSelf: "flex-start" }}>BUILD · 6 SLOTS</div>
            <div style={{ position: "relative", marginTop: 12 }}>
              <HexBuild slots={slots} accentColor={pal.p} centerImg={pj.ico}/>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%", marginTop: 18 }}>
              <SetRow logo={set4.logo} name={pj.set4} pcs="4 PIEZAS" archetype={set4.archetype} accent={pal.p}/>
              <SetRow logo={set2.logo} name={pj.set2} pcs="2 PIEZAS" archetype={set2.archetype} accent={pal.p}/>
            </div>
          </div>

          {/* Engine + bonus col */}
          <div style={{ padding: "14px 18px", overflow: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div className="caps" style={{ fontSize: 10, color: pal.p, letterSpacing: "0.14em", fontWeight: 700, marginBottom: 8 }}>W-ENGINE</div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", border: `1px solid ${pal.p}`, background: `${pal.p}11` }}>
                <img src={pj.engineLogo} style={{ width: 56, height: 56, objectFit: "contain", filter: `drop-shadow(0 0 8px ${pal.p}66)` }}/>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="display" style={{ fontSize: 14, color: "var(--text-primary)", fontWeight: 700 }}>{pj.engine}</div>
                  <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                    {Array.from({ length: 5 }).map((_, i) => (
                      <span key={i} style={{ width: 16, height: 4, background: i < pj.engineR ? pal.p : "rgba(255,255,255,0.1)", boxShadow: i < pj.engineR ? `0 0 4px ${pal.p}` : "none" }}/>
                    ))}
                    <span className="num" style={{ marginLeft: 4, fontSize: 9, color: pal.p, fontWeight: 700 }}>R{pj.engineR}</span>
                  </div>
                </div>
              </div>
            </div>

            <div style={{ padding: "10px 12px", border: "1px solid var(--border-subtle)", background: "rgba(255,255,255,0.02)" }}>
              <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.12em", marginBottom: 4 }}>BONUS ELEMENTAL</div>
              <div style={{ fontSize: 12, color: pj.elemColor, fontWeight: 600 }}>{pj.stats.bonus}</div>
            </div>

            <div>
              <div className="caps" style={{ fontSize: 10, color: pal.p, letterSpacing: "0.14em", fontWeight: 700, marginBottom: 6 }}>AWAKENING</div>
              <div style={{ display: "flex", gap: 4 }}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} style={{ flex: 1, height: 22, border: `1px solid ${i < 4 ? pal.p : "var(--border-mid)"}`, background: i < 4 ? `${pal.p}33` : "transparent", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, color: i < 4 ? pal.p : "var(--text-muted)", fontWeight: 700 }}>nv{i+1}</div>
                ))}
              </div>
              <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 6, lineHeight: 1.4 }}>Nivel <span style={{ color: pal.p, fontWeight: 700 }}>4/6</span> · próximo node desbloquea bonus crítico ×1.3</div>
            </div>

            <div style={{ marginTop: "auto", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              <ActionMini label="OPTIMIZAR BUILD" color={pal.p}/>
              <ActionMini label="OPTIMIZAR ARMA" color={pal.p}/>
              <ActionMini label="SUGERIR EQUIPO" color={pal.p}/>
              <ActionMini label="VER RUNS" color={pal.p}/>
            </div>
          </div>
        </div>
      </PMC>
    </div>
  );
}

function StatGauge({ label, v, pct, c, hi }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ fontSize: 11, color: hi ? c : "var(--text-secondary)", fontWeight: hi ? 700 : 500 }}>{label}</span>
        <span className="num" style={{ fontSize: 12, color: hi ? c : "var(--text-primary)", fontWeight: 700, textShadow: hi ? `0 0 6px ${c}66` : "none" }}>{v}</span>
      </div>
      <div style={{ height: 4, background: "rgba(255,255,255,0.05)", position: "relative" }}>
        <div style={{ position: "absolute", left: "75%", top: -2, bottom: -2, width: 1, background: "var(--yellow)", boxShadow: "0 0 4px var(--yellow)" }}/>
        <div style={{ height: "100%", width: `${pct}%`, background: c, opacity: hi ? 1 : 0.65, boxShadow: hi ? `0 0 6px ${c}` : "none" }}/>
      </div>
    </div>
  );
}

function HexBuild({ slots, accentColor, centerImg }) {
  const size = 200, r = 70, cx = size/2, cy = size/2;
  const positions = Array.from({ length: 6 }, (_, i) => {
    const a = (-Math.PI/2) + (i * Math.PI/3);
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  });
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ position: "absolute", inset: 0 }}>
        <polygon points={positions.map(p => `${p.x},${p.y}`).join(" ")} fill="none" stroke={`${accentColor}33`} strokeWidth="1"/>
      </svg>
      <div style={{
        position: "absolute", left: cx - 24, top: cy - 24, width: 48, height: 48,
        borderRadius: "50%", border: `2px solid ${accentColor}`, overflow: "hidden",
        background: "#0a0a0a", boxShadow: `0 0 16px ${accentColor}66`,
      }}>
        <img src={centerImg} style={{ width: "100%", height: "100%", objectFit: "cover" }}/>
      </div>
      {positions.map((p, i) => (
        <div key={i} style={{
          position: "absolute", left: p.x - 22, top: p.y - 22,
          width: 44, height: 44, borderRadius: "50%",
          background: "#0a0a0a", border: `1.5px solid ${accentColor}99`,
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: `inset 0 0 6px ${accentColor}33`,
        }}>
          <img src={slots[i].logo} style={{ width: 32, height: 32, objectFit: "contain" }}/>
          <div className="num" style={{ position: "absolute", bottom: -8, right: -4, background: "#0a0a0a", border: `1px solid ${accentColor}`, color: accentColor, fontSize: 8, padding: "0 3px", fontWeight: 700 }}>L{slots[i].level}</div>
        </div>
      ))}
    </div>
  );
}

function SetRow({ logo, name, pcs, archetype, accent }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", border: "1px solid var(--border-subtle)", background: "rgba(255,255,255,0.02)" }}>
      <img src={logo} style={{ width: 22, height: 22, objectFit: "contain" }}/>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: "var(--text-primary)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</div>
        <div className="caps" style={{ fontSize: 8, color: "var(--text-muted)", letterSpacing: "0.1em" }}>{pcs} · {archetype}</div>
      </div>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: accent, boxShadow: `0 0 4px ${accent}` }}/>
    </div>
  );
}

function ActionMini({ label, color }) {
  return (
    <div style={{ padding: "8px 10px", border: `1px solid ${color}`, background: `${color}11`, textAlign: "center", cursor: "pointer", color, fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase" }}>
      {label}
    </div>
  );
}

Object.assign(window, { PjModal });
