// discs-tab.jsx — Tab DISCOS · vista tabla 332 discos
const { ChamferBox: DChamfer, Icon: DIcon, Tag: DTag, Rarity: DRarity, SectionHead: DSec, ZButton: DBtn } = window;

function DiscsTab() {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: "var(--bg-base)", overflow: "hidden" }}>
      <FiltersBar/>
      <div style={{ flex: 1, padding: "0 14px 14px", overflow: "hidden", display: "flex", gap: 12 }}>
        <DiscsTable/>
        <DiscsSidebar/>
      </div>
    </div>
  );
}

function FiltersBar() {
  const filters = [
    { label: "Set", val: "Todos", n: "26" },
    { label: "Slot", val: "1—6" },
    { label: "Main", val: "Todos" },
    { label: "Asignado", val: "Todos" },
    { label: "Estado", val: "Activos" },
  ];
  return (
    <div style={{ padding: "12px 14px", display: "flex", gap: 8, alignItems: "center", borderBottom: "1px solid var(--border-subtle)", background: "rgba(0,0,0,0.3)", flexWrap: "wrap" }}>
      {filters.map((f, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", border: "1px solid var(--border-mid)", borderRadius: 8, background: "rgba(255,255,255,0.02)" }}>
          <span className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.1em" }}>{f.label}</span>
          <span style={{ fontSize: 11, color: "var(--text-primary)", fontWeight: 600 }}>{f.val}</span>
          {f.n && <span className="num" style={{ fontSize: 9, color: "var(--yellow)", padding: "0 4px", background: "var(--yellow-tint)", borderRadius: 4 }}>{f.n}</span>}
          <DIcon name="down" size={10} color="var(--text-muted)"/>
        </div>
      ))}
      {/* Score slider */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", border: "1px solid var(--border-mid)", borderRadius: 8 }}>
        <span className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.1em" }}>SCORE</span>
        <div style={{ width: 80, height: 4, background: "rgba(255,255,255,0.06)", position: "relative" }}>
          <div style={{ position: "absolute", left: "20%", right: "10%", top: 0, bottom: 0, background: "var(--yellow)" }}/>
          <div style={{ position: "absolute", left: "20%", top: -3, width: 10, height: 10, background: "var(--yellow)", borderRadius: "50%" }}/>
          <div style={{ position: "absolute", left: "90%", top: -3, width: 10, height: 10, background: "var(--yellow)", borderRadius: "50%" }}/>
        </div>
        <span className="num" style={{ fontSize: 10, color: "var(--yellow)" }}>20—90</span>
      </div>
      {/* Search */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", border: "1px solid var(--border-mid)", borderRadius: 8, marginLeft: "auto" }}>
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>🔍</span>
        <span className="num" style={{ fontSize: 11, color: "var(--text-muted)" }}>#ID</span>
      </div>
      {/* View toggle */}
      <div style={{ display: "flex", border: "1px solid var(--border-mid)", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "5px 10px", background: "var(--yellow)", color: "#0a0a0a", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em" }}>☰ TABLA</div>
        <div style={{ padding: "5px 10px", color: "var(--text-muted)", fontSize: 10, fontWeight: 600, letterSpacing: "0.08em" }}>▦ GRID</div>
      </div>
    </div>
  );
}

function DiscsTable() {
  const cols = [
    { l: "#ID", w: 60 },
    { l: "Set", w: 130 },
    { l: "Sl", w: 30 },
    { l: "Main stat", w: 140 },
    { l: "Top subs", w: 170 },
    { l: "Nv", w: 30 },
    { l: "Score", w: 70 },
    { l: "Asignado a", w: 110 },
    { l: "Estado", w: 80 },
  ];
  return (
    <DChamfer cut={14} cutCorners="tl-br" borderColor="var(--border-mid)" bg="var(--bg-panel-solid)" pattern="carbon"
      style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}
      innerStyle={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <DSec right={<><DTag color="default">332 discos · 24 visibles</DTag></>}>Inventario · vista tabla</DSec>
      {/* Header */}
      <div style={{ display: "flex", padding: "8px 12px", background: "rgba(0,0,0,0.5)", borderBottom: "1px solid var(--border-mid)", fontSize: 9, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600 }}>
        {cols.map((c, i) => <div key={i} style={{ width: c.w, flexShrink: 0 }}>{c.l}</div>)}
      </div>
      {/* Rows */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {window.DISCS.map((d, i) => <DiscRow key={d.id} d={d} hi={d.hi}/>)}
      </div>
      {/* Footer */}
      <div style={{ borderTop: "1px solid var(--border-subtle)", padding: "8px 14px", display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)", background: "rgba(0,0,0,0.4)" }}>
        <span>1—24 de 332 · ordenado por Score ↓</span>
        <span className="num">◀ 1 2 3 … 14 ▶</span>
      </div>
    </DChamfer>
  );
}

function DiscRow({ d, hi }) {
  const set = window.SETS[d.set];
  const pj = d.pj ? window.PJS[d.pj] : null;
  const tierColor = d.tier === "S" ? "var(--yellow)" : d.tier === "A" ? "var(--purple)" : "var(--info)";
  const stateBadge = {
    equipped:  { label: "EQUIPADO", color: "var(--positive)" },
    loose:     { label: "SUELTO",   color: "var(--text-secondary)" },
    discarded: { label: "DESCARTE", color: "var(--warning)" },
  }[d.state];
  return (
    <div style={{
      display: "flex", padding: "7px 12px", alignItems: "center",
      borderBottom: "1px solid var(--border-subtle)",
      background: hi ? "rgba(255,203,5,0.07)" : "transparent",
      borderLeft: hi ? "2px solid var(--yellow)" : "2px solid transparent",
      fontSize: 11,
    }}>
      <div style={{ width: 60, flexShrink: 0, fontFamily: "var(--font-mono)", fontSize: 10, color: hi ? "var(--yellow)" : "var(--text-muted)", fontWeight: hi ? 700 : 400 }}>#{d.id}</div>
      <div style={{ width: 130, flexShrink: 0, display: "flex", alignItems: "center", gap: 6 }}>
        <img src={set.logo} style={{ width: 18, height: 18, objectFit: "contain", flexShrink: 0 }}/>
        <span style={{ color: "var(--text-primary)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{set.name}</span>
      </div>
      <div style={{ width: 30, flexShrink: 0, fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>{d.slot}</div>
      <div style={{ width: 140, flexShrink: 0, color: "var(--text-primary)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.main}</div>
      <div style={{ width: 170, flexShrink: 0, fontSize: 10, color: "var(--text-secondary)", fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.subs}</div>
      <div style={{ width: 30, flexShrink: 0, fontFamily: "var(--font-mono)", color: d.lvl === 15 ? "var(--yellow)" : "var(--text-secondary)", fontWeight: 600 }}>{d.lvl}</div>
      <div style={{ width: 70, flexShrink: 0, display: "flex", alignItems: "baseline", gap: 4 }}>
        <span className="num display" style={{ fontSize: 13, fontWeight: 700, color: tierColor }}>{d.score.toFixed(1)}</span>
        <span className="caps" style={{ fontSize: 8, padding: "0 3px", background: tierColor, color: "#0a0a0a", borderRadius: 2, fontWeight: 700 }}>{d.tier}</span>
      </div>
      <div style={{ width: 110, flexShrink: 0, display: "flex", alignItems: "center", gap: 6 }}>
        {pj ? <>
          <img src={pj.ico} style={{ width: 22, height: 22, borderRadius: "50%", objectFit: "cover", border: "1px solid var(--border-mid)" }}/>
          <span style={{ color: "var(--text-primary)", fontSize: 11, fontWeight: 500 }}>{pj.name}</span>
        </> : <span style={{ color: "var(--text-dim)", fontStyle: "italic", fontSize: 10 }}>—</span>}
      </div>
      <div style={{ width: 80, flexShrink: 0 }}>
        <span style={{ fontSize: 8, padding: "2px 6px", border: `1px solid ${stateBadge.color}`, color: stateBadge.color, letterSpacing: "0.08em", fontWeight: 600 }}>{stateBadge.label}</span>
      </div>
    </div>
  );
}

function DiscsSidebar() {
  return (
    <div style={{ width: 240, flexShrink: 0, display: "flex", flexDirection: "column", gap: 10 }}>
      <DChamfer cut={14} cutCorners="tl-br" borderColor="var(--border-mid)" bg="var(--bg-panel-solid)" pattern="carbon">
        <DSec>Distribución por set</DSec>
        <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
          {[
            { name: "Jazz Caótico", n: 64, color: "var(--yellow)" },
            { name: "Polar Metal", n: 48, color: "var(--info)" },
            { name: "Puffer Electro", n: 42, color: "var(--positive)" },
            { name: "Balada rama", n: 38, color: "var(--purple)" },
            { name: "Fábula Yunkui", n: 34, color: "var(--pink)" },
            { name: "Otros (21 sets)", n: 106, color: "var(--text-muted)" },
          ].map((s, i) => (
            <div key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 3 }}>
                <span style={{ color: "var(--text-secondary)" }}>{s.name}</span>
                <span className="num" style={{ color: s.color, fontWeight: 600 }}>{s.n}</span>
              </div>
              <div style={{ height: 3, background: "rgba(255,255,255,0.05)" }}>
                <div style={{ height: "100%", width: `${(s.n / 106) * 100}%`, background: s.color, opacity: 0.7 }}/>
              </div>
            </div>
          ))}
        </div>
      </DChamfer>

      <DChamfer cut={14} cutCorners="tl-br" borderColor="var(--border-mid)" bg="var(--bg-panel-solid)" pattern="carbon">
        <DSec>Acciones rápidas</DSec>
        <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: 6 }}>
          <DBtn variant="ghost" size="sm" icon="filter">Filtrar por PJ</DBtn>
          <DBtn variant="ghost" size="sm" icon="trash">Limpiar descartes</DBtn>
          <DBtn variant="primary" size="sm" icon="up">Re-puntuar todos</DBtn>
        </div>
      </DChamfer>

      <DChamfer cut={14} cutCorners="tl-br" borderColor="var(--purple)" bg="rgba(157,78,221,0.05)">
        <div style={{ padding: "12px" }}>
          <div className="caps" style={{ fontSize: 9, color: "var(--purple)", letterSpacing: "0.12em", marginBottom: 6, fontWeight: 700 }}>★ AI · RF-12 INSIGHT</div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", lineHeight: 1.5 }}>
            Tienes <span style={{ color: "var(--yellow)", fontWeight: 600 }}>14 discos</span> Slot 4 sin asignar. <span style={{ color: "var(--purple)" }}>4 podrían</span> mejorar a Yanagi o Burnice.
          </div>
        </div>
      </DChamfer>
    </div>
  );
}

Object.assign(window, { DiscsTab });
