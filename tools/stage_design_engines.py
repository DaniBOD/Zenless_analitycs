"""Arma el paquete de referencias para diseñar la pantalla de W-Engines en Claude Design.

    python tools/stage_design_engines.py

Genera `Documentacion/Interfaz/claude_design_upload/w_engines/`:

- `ARMAS_datos_reales.md`   volcado de la DB: las 56 armas del inventario y los huecos del catálogo
                            (se versiona: es texto y es la verdad de tierra con la que se diseña)
- `assets/engines/`         íconos de las armas, renombrados por su nombre EN ESPAÑOL
- `assets/pj_avatares/`     caras de los PJs que tienen un arma equipada
- `assets/iconos_ui/`       íconos de elemento y de especialidad
- `assets/capturas_app/`    cómo se ven HOY las pantallas ya portadas, con datos reales
- `assets/mockups_previos/` los mockups de Claude Design que se usaron para esas pantallas

`assets/` está gitignoreada: son copias de archivos versionados en otro lado y capturas con datos de
la cuenta (regla: las capturas full-res quedan locales).

Sólo LEE la DB (modo `ro`).
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

DB = REPO / "db" / "danibod_zzz_v2.db"
DST = REPO / "Documentacion" / "Interfaz" / "claude_design_upload" / "w_engines"
ASSETS = DST / "assets"
MOCKUPS = REPO / "Documentacion" / "Interfaz" / "mockups" / "design_handoff_toast_variants" / "mockup-exports"
UI_GENERAL = REPO / "Documentacion" / "Interfaz" / "UI_general"


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


# --- 1 · datos -------------------------------------------------------------------------------------

def volcar_datos(con: sqlite3.Connection) -> dict:
    from app.core.asset_resolver import engine_icon_path

    inv = con.execute("""
        SELECT i.id, w.id AS wid, w.nombre, w.nombre_en, w.rareza, w.tipo_especialidad, w.atk_base,
               w.stat_secundario, w.stat_secundario_valor, i.nivel, i.refinamiento, i.equipado,
               a.nombre AS dueno, w.pasiva_descripcion
        FROM inventory_weapons i
        JOIN weapons w ON w.id = i.weapon_id
        LEFT JOIN agents a ON a.id = i.agente_asignado AND i.equipado = 1
        WHERE i.descartado = 0
        ORDER BY w.rareza DESC, w.nombre, i.id
    """).fetchall()
    catalogo = con.execute("SELECT * FROM weapons ORDER BY rareza DESC, nombre").fetchall()

    filas = []
    for r in inv:
        icono = engine_icon_path(r["nombre"], r["nombre_en"])
        filas.append((r, icono))

    n = len(filas)
    eq = sum(1 for r, _ in filas if r["equipado"])
    modelos = len({r["wid"] for r, _ in filas})
    con_icono = len({r["wid"] for r, i in filas if i})
    sin_icono = sorted({r["nombre"] for r, i in filas if not i})

    def dist(campo, prefijo=""):
        d: dict = {}
        for r, _ in filas:
            d[r[campo]] = d.get(r[campo], 0) + 1
        orden = sorted(d.items(), key=lambda kv: (-kv[1], str(kv[0])))
        return " · ".join(f"{prefijo}{k if k is not None else 'sin dato'} **{v}**" for k, v in orden)

    lineas = [
        "# Armas reales de DaniBOD — datos para Claude Design",
        "",
        "> Volcado directo de `db/danibod_zzz_v2.db` por `tools/stage_design_engines.py`. Es el dato",
        "> con el que la pantalla de W-Engines tiene que probarse: distribuciones reales, huecos reales.",
        "",
        "## Resumen",
        "",
        f"- **{n} armas** en el inventario ({modelos} modelos distintos): **{eq} equipadas**, "
        f"**{n - eq} libres**. Hay copias repetidas del mismo modelo (se guardan para refinar).",
        f"- Rareza: {dist('rareza')}",
        f"- Especialidad: {dist('tipo_especialidad')}  ← *sin dato* = el catálogo no la tiene",
        f"- Nivel: {dist('nivel', 'Nv ')}",
        f"- Refinamiento (el juego lo llama **P1–P5**): {dist('refinamiento', 'P')}",
        f"- Ícono: {con_icono} de {modelos} modelos. **Sin ícono**: {', '.join(sin_icono) or '—'}",
        "",
        "## Lo que la pantalla NO puede mostrar todavía",
        "",
        "La app sigue la regla **\"sólo informa\"** (decisión de Daniel en las pantallas anteriores): nada",
        "que salga de un scoring sin calibrar.",
        "",
        f"- `weapon_evaluations`: **{con.execute('SELECT COUNT(*) FROM weapon_evaluations').fetchone()[0]} filas**"
        " → no hay score de arma ni \"mejor arma para X\".",
        f"- `prydwen_weapon_recommendations_snapshots`: **"
        f"{con.execute('SELECT COUNT(*) FROM prydwen_weapon_recommendations_snapshots').fetchone()[0]} filas**"
        " → no hay recomendaciones de la comunidad cargadas.",
        f"- `pj_weapon_synergy`: {con.execute('SELECT COUNT(*) FROM pj_weapon_synergy').fetchone()[0]} filas"
        " (matriz de bonus por rol del RF-14). Es insumo del scoring, no un dato para mostrar crudo.",
        "- **Nivel del PJ y sus stats están vacíos** para los 51 (se re-censan): no diseñar nada que",
        "  dependa de \"ATK del PJ con esta arma\".",
        "",
        "## Las armas del inventario",
        "",
        "| # | arma | rareza | especialidad | ATK base | stat secundario | Nv | P | dueño | ícono |",
        "|--:|---|:-:|---|--:|---|--:|:-:|---|---|",
    ]
    for k, (r, icono) in enumerate(filas, start=1):
        stat = " ".join(x for x in (r["stat_secundario"], r["stat_secundario_valor"]) if x) or "—"
        lineas.append(
            f"| {k} | {r['nombre']} | {r['rareza'] or '—'} | {r['tipo_especialidad'] or '—'} | "
            f"{r['atk_base'] if r['atk_base'] is not None else '—'} | {stat} | {r['nivel']} | "
            f"P{r['refinamiento']} | {r['dueno'] or 'LIBRE'} | "
            f"{'`engines/' + _slug(r['nombre']) + '.webp`' if icono else '**falta**'} |")

    lineas += [
        "",
        "## El catálogo (`weapons`) y sus huecos",
        "",
        f"{len(catalogo)} filas. Campos con datos:",
        "",
        "| campo | cargado |",
        "|---|--:|",
    ]
    for campo in ("nombre_en", "rareza", "tipo_especialidad", "atk_base", "stat_secundario",
                  "stat_secundario_valor", "pasiva_descripcion"):
        k = sum(1 for c in catalogo if c[campo] is not None)
        lineas.append(f"| `{campo}` | {k}/{len(catalogo)} |")
    lineas += [
        "",
        "- Las **pasivas** están escritas a mano, mezclando español e inglés, y **no son el texto del",
        "  juego**: sirven para leer, no para citar en pantalla como si fueran oficiales.",
        "- **Dos filas tienen stat secundario y pasiva que no coinciden con las fuentes** (Última cena y",
        "  Caldero ardiente): corrección pendiente. No usarlas como ejemplo de card.",
        "",
        "### Ejemplo de pasiva (tal como está en la DB)",
        "",
    ]
    ejemplo = next((c for c in catalogo if c["nombre"] == "Llanto mielgo"), None)
    if ejemplo is not None:
        lineas.append(f"> **{ejemplo['nombre']}** — {ejemplo['pasiva_descripcion']}")
    (DST / "ARMAS_datos_reales.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return {"filas": filas, "catalogo": catalogo}


# --- 2 · assets ------------------------------------------------------------------------------------

def copiar_assets(con: sqlite3.Connection, datos: dict) -> None:
    from app.core.asset_resolver import agent_avatar_path, engine_icon_path

    (ASSETS / "engines").mkdir(parents=True, exist_ok=True)
    for c in datos["catalogo"]:
        p = engine_icon_path(c["nombre"], c["nombre_en"])
        if p is not None:
            shutil.copy2(p, ASSETS / "engines" / f"{_slug(c['nombre'])}.webp")

    (ASSETS / "pj_avatares").mkdir(parents=True, exist_ok=True)
    for r, _ in datos["filas"]:
        if r["dueno"]:
            p = agent_avatar_path(r["dueno"], "ico")
            if p is not None:
                shutil.copy2(p, ASSETS / "pj_avatares" / f"{_slug(r['dueno'])}.webp")

    (ASSETS / "iconos_ui").mkdir(parents=True, exist_ok=True)
    for p in UI_GENERAL.glob("Icon_*.webp"):
        if "(" not in p.name:          # fuera los íconos de mecánica de un PJ puntual
            shutil.copy2(p, ASSETS / "iconos_ui" / p.name)

    (ASSETS / "mockups_previos").mkdir(parents=True, exist_ok=True)
    for nombre in ("21-panel-principal-captura-en-vivo.png", "22-tab-discos-inventario-completo.png",
                   "23-modal-disco-detalle.png", "24-modal-pj-yanagi.png"):
        if (MOCKUPS / nombre).exists():
            shutil.copy2(MOCKUPS / nombre, ASSETS / "mockups_previos" / nombre)


# --- 3 · capturas de la app ------------------------------------------------------------------------

def capturar_pantallas(con: sqlite3.Connection, datos: dict) -> list[str]:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    for f in glob.glob(r"C:\Windows\Fonts\*.ttf"):
        QFontDatabase.addApplicationFont(f)
    from app.main import apply_dark_palette
    apply_dark_palette(app)

    from app.core.asset_resolver import agent_avatar_path, engine_icon_path
    from app.ui.disco_modal.modal import DiscoModal
    from app.ui.discos.view import DiscosView
    from app.ui.live.view import LiveView
    from app.ui.pj_modal.datos import ficha_pj
    from app.ui.pj_modal.modal import PjModal
    from app.ui.roster.view import RosterView

    salida = ASSETS / "capturas_app"
    salida.mkdir(parents=True, exist_ok=True)
    hechas = []

    def guardar(widget, nombre, w=None, h=None):
        if w:
            widget.resize(w, h)
        widget.show()
        for _ in range(5):
            app.processEvents()
        widget.grab().save(str(salida / nombre))
        widget.close()
        hechas.append(nombre)

    guardar(RosterView(con), "01_roster_1100x756.png", 1100, 756)
    guardar(DiscosView(con), "02_discos_1100x756.png", 1100, 756)
    guardar(DiscosView(con), "03_discos_maximizada.png", 2316, 1250)

    yanagi = con.execute("SELECT id FROM agents WHERE nombre='Yanagi'").fetchone()
    if yanagi:
        guardar(PjModal(ficha_pj(con, yanagi[0])), "04_modal_pj_yanagi.png")
        disco = con.execute("SELECT id FROM inventory_discs WHERE agente_asignado=? AND equipado=1 "
                            "AND descartado=0 ORDER BY slot LIMIT 1", (yanagi[0],)).fetchone()
        if disco:
            guardar(DiscoModal(con, disco[0]), "05_modal_disco.png")

    # La card de arma de la vista en vivo: lo único de W-Engines que la app ya dibuja.
    r, icono = next(((r, i) for r, i in datos["filas"] if r["dueno"] and i and r["rareza"] == "S"),
                    datos["filas"][0])
    vista = LiveView()
    vista.on_weapon_seen({
        "nombre": r["nombre"], "en_catalogo": True, "rareza": r["rareza"], "nivel": r["nivel"],
        "nivel_max": 60, "refinamiento": r["refinamiento"],
        "stat": " ".join(x for x in (r["stat_secundario"], r["stat_secundario_valor"]) if x),
        "dueno": r["dueno"], "tenencia": "equipada" if r["equipado"] else "libre", "cambio": False,
        "tenencia_previa": None, "icono": str(icono) if icono else None,
        "dueno_avatar": str(agent_avatar_path(r["dueno"], "ico")) if r["dueno"] else None,
    })
    guardar(vista, "06_vista_en_vivo_card_de_arma.png", 1100, 756)
    return hechas


def main() -> None:
    if ASSETS.exists():
        shutil.rmtree(ASSETS)
    DST.mkdir(parents=True, exist_ok=True)
    con = _con()
    datos = volcar_datos(con)
    copiar_assets(con, datos)
    capturas = capturar_pantallas(con, datos)
    con.close()
    for d in sorted(ASSETS.iterdir()):
        archivos = list(d.iterdir())
        mb = sum(f.stat().st_size for f in archivos) / 1e6
        print(f"{d.name:18} {len(archivos):3} archivos  {mb:5.1f} MB")
    print("capturas:", ", ".join(capturas))
    print("datos   :", DST / "ARMAS_datos_reales.md")


if __name__ == "__main__":
    main()
