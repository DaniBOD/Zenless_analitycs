// disc-modal.jsx — Modal de disco · 1100×700 · 3 columnas
const { ChamferBox: DMC, Icon: DMI, Tag: DMT, Rarity: DMR, SectionHead: DMS, ZButton: DMB, Hexagon6: DMH } = window;

function DiscModal({ width = 1100, height = 700 }) {
  const d = window.DISCS[0]; // #00482
  const set = window.SETS[d.set];
  return (
    <div style={{ width, height, position: "relative", background: "rgba(0,0,0,0.85)", backdropFilter: "blur(6px)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      {/* Decorative ambient */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 20% 30%, rgba(255,203,5,0.08), transparent 50%)" }}/>
      <DMC cut={18} cutCorners="all" borderColor="var(--yellow)" bg="var(--bg-panel-solid)" pattern="carbon"
        style={{ width: width - 60, height: height - 60, boxShadow: "0 0 0 2px var(--yellow), 0 0 40px rgba(255,203,5,0.4)" }}
        innerStyle={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {/* Header */}
        <div style={{ padding: "14px 22px", borderBottom: "1px solid var(--border-mid)", display: "flex", alignItems: "center", justifyContent: "space-between", background: "linear-gradient(180deg, rgba(255,203,5,0.06), transparent)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 6, height: 22, background: "var(--yellow)", boxShadow: "0 0 8px var(--yellow)" }}/>
            <div>
              <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.16em" }}>DETALLE DE DISCO</div>
              <div className="display caps num" style={{ fontSize: 18, color: "var(--text-primary)", fontWeight: 700, letterSpacing: "0.06em" }}>
                #{d.id} <span style={{ color: "var(--yellow)" }}>·</span> {set.name} <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>· Slot {d.slot} · Nv {d.lvl}</span>
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <DMT color="positive">EQUIPADO · YANAGI</DMT>
            <DMT color="yellow">SCORE 87.3 · S</DMT>
            <div style={{ width: 28, height: 28, marginLeft: 8, border: "1px solid var(--border-mid)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "var(--text-secondary)" }}>
              <DMI name="x" size={12}/>
            </div>
          </div>
        </div>

        {/* 3 columns */}
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", overflow: "hidden" }}>
          <ColDisc d={d} set={set}/>
          <ColCompat/>
          <ColFuture/>
        </div>

        {/* Footer */}
        <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border-mid)", display: "flex", gap: 8, justifyContent: "space-between", background: "rgba(0,0,0,0.4)" }}>
          <div style={{ display: "flex", gap: 8 }}>
            <DMB variant="ghost" size="sm" icon="lock">Bloquear</DMB>
            <DMB variant="ghost" size="sm" icon="trash">Descartar</DMB>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <DMB variant="ghost" size="sm" icon="users">Reasignar PJ ▾</DMB>
            <DMB variant="info" size="sm" icon="up">Mejorar +0</DMB>
            <DMB variant="positive" size="sm" icon="check">Confirmar build</DMB>
          </div>
        </div>
      </DMC>
    </div>
  );
}

function ColDisc({ d, set }) {
  return (
    <div style={{ padding: "16px 18px", borderRight: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", gap: 12, overflow: "auto" }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <div style={{ width: 72, height: 72, borderRadius: 14, background: "radial-gradient(circle at 30% 30%, #1a1a18, #050505)", border: "1px solid var(--border-mid)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 12px rgba(0,0,0,0.6)" }}>
          <img src={set.logo} style={{ width: 56, height: 56, objectFit: "contain" }}/>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="display caps" style={{ fontSize: 18, color: "var(--yellow)", fontWeight: 700, lineHeight: 1.1, letterSpacing: "0.04em" }}>{set.name}</div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}>Slot {d.slot} · Nv <span className="num" style={{ color: "var(--yellow)" }}>{d.lvl}</span><span style={{ color: "var(--text-muted)" }}>/15</span> · MAX</div>
          <div style={{ marginTop: 4 }}><DMR tier={d.tier}/></div>
        </div>
      </div>

      <div style={{ border: "1px solid var(--border-subtle)" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", padding: "5px 10px", borderBottom: "1px solid var(--border-subtle)", letterSpacing: "0.12em", background: "rgba(0,0,0,0.4)" }}>MAIN</div>
        <div style={{ padding: "8px 10px", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--yellow-tint)" }}>
          <span style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 600 }}>ATAQUE %</span>
          <span className="num display" style={{ fontSize: 16, color: "var(--yellow)", fontWeight: 700 }}>30.0<span style={{ fontSize: 11, marginLeft: 1 }}>%</span></span>
        </div>
      </div>

      <div style={{ border: "1px solid var(--border-subtle)" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", padding: "5px 10px", borderBottom: "1px solid var(--border-subtle)", letterSpacing: "0.12em", background: "rgba(0,0,0,0.4)" }}>SUBSTATS · 4 ROLLS</div>
        <SubLine label="Prob. Crítica" v="2.4 %" rolls={3} hot/>
        <SubLine label="Daño Crítico" v="9.6 %" rolls={2} hot/>
        <SubLine label="Ataque" v="38" rolls={1}/>
        <SubLine label="Maestría Anomalía" v="27" rolls={2}/>
      </div>

      <div style={{ background: "var(--yellow-tint)", border: "1px solid var(--yellow)", padding: "10px 12px" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--yellow)", letterSpacing: "0.12em", marginBottom: 4, fontWeight: 700 }}>EFECTOS DEL CONJUNTO</div>
        <div style={{ fontSize: 10, color: "var(--text-secondary)", lineHeight: 1.5 }}>
          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>2pc:</span> ATK +10%. <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>4pc:</span> Maestría Anomalía +30. Genera +1 al asalto especial al activar Disorder.
        </div>
      </div>
    </div>
  );
}

function SubLine({ label, v, rolls, hot }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 10px", borderBottom: "1px solid var(--border-subtle)" }}>
      <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{label}</span>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span className="num" style={{ fontSize: 11, color: "var(--text-primary)", fontWeight: 600 }}>{v}</span>
        <div style={{ display: "flex", gap: 1 }}>
          {Array.from({ length: rolls }).map((_, i) => (
            <span key={i} style={{ width: 5, height: 5, background: hot ? "var(--yellow)" : "var(--text-secondary)", boxShadow: hot ? "0 0 4px var(--yellow)" : "none" }}/>
          ))}
        </div>
      </div>
    </div>
  );
}

function ColCompat() {
  const list = [
    { pj: "yanagi",  s: 87.3, dl: 0,    badge: "ANOMALY", best: true },
    { pj: "burnice", s: 81.4, dl: -5.9, badge: "ANOMALY" },
    { pj: "ellen",   s: 64.8, dl: -22.5, badge: "ATK_DPS" },
    { pj: "caesar",  s: 41.7, dl: -45.6, badge: "DEFENSE" },
  ];
  return (
    <div style={{ padding: "16px 18px", borderRight: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", gap: 8, overflow: "auto" }}>
      <div className="caps" style={{ fontSize: 10, color: "var(--text-secondary)", letterSpacing: "0.14em", fontWeight: 600, marginBottom: 4 }}>PJs COMPATIBLES · RANKED</div>
      {list.map((row, i) => {
        const pj = window.PJS[row.pj];
        return (
          <div key={i} style={{
            padding: "10px 12px",
            border: row.best ? "1px solid var(--yellow)" : "1px solid var(--border-subtle)",
            background: row.best ? "var(--yellow-tint)" : "rgba(255,255,255,0.02)",
            display: "flex", alignItems: "center", gap: 10,
            boxShadow: row.best ? "0 0 14px rgba(255,203,5,0.25)" : "none",
          }}>
            <img src={pj.ico} style={{ width: 36, height: 36, borderRadius: 8, objectFit: "cover", border: `1px solid ${row.best ? "var(--yellow)" : "var(--border-mid)"}` }}/>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <span style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 600 }}>{pj.name} <span className="num" style={{ color: "var(--text-secondary)", fontWeight: 400, fontSize: 10 }}>M{pj.mind}</span></span>
                <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                  <span className="num display" style={{ fontSize: 16, color: row.best ? "var(--yellow)" : "var(--text-primary)", fontWeight: 700 }}>{row.s.toFixed(1)}</span>
                  <span className="num" style={{ fontSize: 9, color: row.dl >= 0 ? "var(--positive)" : "var(--warning)" }}>{row.dl >= 0 ? "▲" : "▼"}{Math.abs(row.dl).toFixed(1)}</span>
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3 }}>
                <span className="caps" style={{ fontSize: 8, color: "var(--purple)", letterSpacing: "0.1em", padding: "1px 5px", border: "1px solid var(--purple)" }}>{row.badge}</span>
                {row.best && <span className="caps" style={{ fontSize: 8, color: "var(--yellow)", fontWeight: 700, letterSpacing: "0.1em" }}>⭐ MEJOR · ▲ EQUIPAR</span>}
              </div>
            </div>
          </div>
        );
      })}

      <div style={{ marginTop: 8, padding: "10px", border: "1px dashed var(--border-mid)" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.12em", marginBottom: 6 }}>ALTERNATIVAS EN INVENTARIO · SLOT 4 · JAZZ</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}><span className="num" style={{ color: "var(--text-secondary)" }}>#00521</span><span className="num" style={{ color: "var(--warning)" }}>79.0 · inferior</span></div>
          <div style={{ display: "flex", justifyContent: "space-between" }}><span className="num" style={{ color: "var(--text-secondary)" }}>#00638</span><span className="num" style={{ color: "var(--info)" }}>84.1 · cercano</span></div>
        </div>
      </div>
    </div>
  );
}

function ColFuture() {
  return (
    <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 12, overflow: "auto" }}>
      <div>
        <div className="caps" style={{ fontSize: 10, color: "var(--text-secondary)", letterSpacing: "0.14em", fontWeight: 600 }}>ARQUETIPO</div>
        <div className="display" style={{ fontSize: 16, color: "var(--purple)", fontWeight: 700, marginTop: 4 }}>ANOMALY <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 11 }}>· match S+</span></div>
      </div>

      <div style={{ border: "1px solid var(--border-subtle)", padding: "10px 12px" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.12em", marginBottom: 6 }}>SCORE PROYECTADO</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span className="num display" style={{ fontSize: 26, color: "var(--yellow)", fontWeight: 700 }}>87.3</span>
          <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>actual · MAX</span>
        </div>
        <div style={{ height: 4, background: "rgba(255,255,255,0.05)", marginTop: 6 }}>
          <div style={{ height: "100%", width: "87%", background: "var(--yellow)", boxShadow: "0 0 8px var(--yellow)" }}/>
        </div>
        <div className="num" style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 4 }}>Sin upgrade posible · disco ya está en lvl 15</div>
      </div>

      <div style={{ border: "1px solid var(--border-subtle)", padding: "10px 12px" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.12em", marginBottom: 6 }}>MATCH SET 4PC</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <img src={window.SETS.jazz.logo} style={{ width: 28, height: 28, objectFit: "contain" }}/>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 600 }}>Jazz Caótico → ANOMALY</div>
            <div className="caps" style={{ fontSize: 9, color: "var(--positive)", fontWeight: 600, letterSpacing: "0.1em" }}>S+ COMPATIBLE</div>
          </div>
        </div>
        <div style={{ fontSize: 10, color: "var(--text-secondary)", lineHeight: 1.5 }}>Yanagi tiene 3/4 piezas Jazz Caótico equipadas. Este disco completa el bonus 4pc.</div>
      </div>

      <div style={{ background: "rgba(123,201,31,0.06)", border: "1px solid var(--positive)", padding: "12px 14px" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--positive)", letterSpacing: "0.14em", fontWeight: 700, marginBottom: 6 }}>⭐ RECOMENDACIÓN FINAL</div>
        <div className="display" style={{ fontSize: 14, color: "var(--text-primary)", fontWeight: 700, lineHeight: 1.3 }}>MANTENER · YA ÓPTIMO</div>
        <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 4, lineHeight: 1.5 }}>Para Yanagi y Burnice. No equipar a otros PJs — pierde 22+ pts.</div>
      </div>

      <div style={{ marginTop: "auto", padding: "8px 10px", border: "1px dashed var(--pink)", background: "rgba(255,77,138,0.04)" }}>
        <div className="caps" style={{ fontSize: 9, color: "var(--pink)", letterSpacing: "0.12em", marginBottom: 4, fontWeight: 700 }}>◇ HISTORIAL · RF-13</div>
        <div style={{ fontSize: 10, color: "var(--text-secondary)" }}>Equipado en 3 runs S+ · DPS-share 67% promedio.</div>
      </div>
    </div>
  );
}

Object.assign(window, { DiscModal });
