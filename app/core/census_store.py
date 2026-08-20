"""Persistencia del censo — `census.db`, hermano de la DB de dominio.

## Por qué un archivo aparte

Mismo molde y mismo argumento que `metrics.py` (`metrics.db`), y acá pesa incluso más:

1. **Perfil de escritura.** Una escritura por cambio de selección. RNF-01 —backup + transacción +
   `foreign_key_check` + `integrity_check`— es ceremonia por migración; no se paga por evento
   observacional. Meterlo en el dominio obligaría a inventar una excepción a RNF-01 *dentro de la
   feature cuyo objetivo es restaurar la confianza en esa DB*.
2. **Preserva la prueba del sha256.** La forma de demostrar que un QA en readonly no escribió es
   comparar el hash de `danibod_zzz_v2.db`. El censo es justo el flujo que más conviene ejercitar
   así: mirar el menú y moverse no arriesga nada. Con el estado adentro habría que elegir entre no
   poder correrlo en readonly o perder esa prueba.
3. **Vuelve ESTRUCTURAL lo que si no queda en disciplina.** Sin handle de escritura al dominio, la
   observación no puede contaminarlo por accidente.

Efecto colateral bienvenido: **no hace falta migración**. El esquema se crea solo, porque esto no
es dato de dominio — es *evidencia sobre* el dominio.

La única escritura al dominio del censo es marcar huérfanos al CERRAR, que es un momento discreto
y deliberado, con ceremonia RNF-01 y gate de readonly. No vive acá.

## Conexión por llamada

Como `metrics.flush()`: se abre y se cierra en cada operación, sin conexión compartida. El monitor
corre en su propio hilo y `app/db/connection.py` ya advierte del riesgo de compartir handles.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

from app.core.census import CoverageRow, MenuSighting, RosterCensus

log = logging.getLogger(__name__)

_ENV_DB = "DANIBOD_CENSUS_DB"

# Cuánto puede quedar quieta una pasada antes de considerarla abandonada. Molde de la ventana de
# `FarmSession`. No es un cierre: una pasada vencida NO produce huérfanos (ver `census.py`).
_VENTANA_H = 72.0

_DDL = """
CREATE TABLE IF NOT EXISTS census_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ambito        TEXT    NOT NULL,
    estado        TEXT    NOT NULL,
    ts_apertura   REAL    NOT NULL,
    ts_ultimo     REAL    NOT NULL,
    ts_cierre     REAL,
    cierre_motivo TEXT,
    db_path       TEXT    NOT NULL,
    roster_n      INTEGER,
    readonly      INTEGER NOT NULL DEFAULT 0,
    notas         TEXT
);
CREATE TABLE IF NOT EXISTS census_coverage (
    run_id      INTEGER NOT NULL,
    clave       TEXT    NOT NULL,
    estado      TEXT    NOT NULL,
    en_db       INTEGER NOT NULL,
    en_catalogo INTEGER NOT NULL DEFAULT 1,
    agent_id    INTEGER,
    texto_crudo TEXT,
    n_obs       INTEGER NOT NULL DEFAULT 0,
    conf_max    REAL,
    score_max   REAL,
    ts_primera  REAL,
    ts_ultima   REAL,
    PRIMARY KEY (run_id, clave)
);
CREATE INDEX IF NOT EXISTS idx_cov_run_estado ON census_coverage(run_id, estado);
CREATE TABLE IF NOT EXISTS census_observations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    ts          REAL    NOT NULL,
    clave       TEXT,
    texto_crudo TEXT,
    conf        REAL,
    score       REAL,
    veredicto   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_run ON census_observations(run_id, ts);
"""


def db_path() -> Path:
    """Al lado de la DB de dominio, para que una instalación empaquetada la deje en el directorio
    de usuario y no en el cwd desde donde se lanzó."""
    override = os.environ.get(_ENV_DB, "").strip()
    if override:
        return Path(override)
    from app.db.connection import get_db_path
    return get_db_path().with_name("census.db")


class CensusStore:
    """Acceso a `census.db`. Una conexión por operación, sin estado compartido."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else db_path()

    def _conn(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.executescript(_DDL)
        return con

    # --- corridas -------------------------------------------------------------------------
    def abrir(self, ambito: str, *, ts: float, db_path_dominio: str,
              roster_n: int, readonly: bool) -> int:
        con = self._conn()
        try:
            cur = con.execute(
                "INSERT INTO census_runs (ambito, estado, ts_apertura, ts_ultimo, db_path,"
                " roster_n, readonly) VALUES (?, 'abierta', ?, ?, ?, ?, ?)",
                (ambito, ts, ts, db_path_dominio, roster_n, int(readonly)),
            )
            con.commit()
            return int(cur.lastrowid)
        finally:
            con.close()

    def corrida_abierta(self, ambito: str) -> sqlite3.Row | None:
        con = self._conn()
        try:
            return con.execute(
                "SELECT * FROM census_runs WHERE ambito=? AND estado='abierta'"
                " ORDER BY id DESC LIMIT 1", (ambito,),
            ).fetchone()
        finally:
            con.close()

    def abandonar(self, run_id: int, motivo: str) -> None:
        """Cierra sin producir huérfanos. Vencerse o cambiar de DB **no** es terminar."""
        con = self._conn()
        try:
            con.execute("UPDATE census_runs SET estado='abandonada', cierre_motivo=?"
                        " WHERE id=?", (motivo, run_id))
            con.commit()
        finally:
            con.close()

    def marcar_cierre(self, run_id: int, ts: float, motivo: str) -> None:
        con = self._conn()
        try:
            con.execute("UPDATE census_runs SET estado='cerrada', ts_cierre=?, cierre_motivo=?"
                        " WHERE id=?", (ts, motivo, run_id))
            con.commit()
        finally:
            con.close()

    def historial(self, limit: int = 50) -> list[dict]:
        con = self._conn()
        try:
            filas = con.execute("SELECT * FROM census_runs ORDER BY id DESC LIMIT ?",
                                (limit,)).fetchall()
            return [dict(f) for f in filas]
        finally:
            con.close()

    # --- cobertura y rastro ---------------------------------------------------------------
    def guardar_fila(self, run_id: int, fila: CoverageRow) -> None:
        con = self._conn()
        try:
            con.execute(
                "INSERT INTO census_coverage (run_id, clave, estado, en_db, en_catalogo,"
                " agent_id, texto_crudo, n_obs, conf_max, score_max, ts_primera, ts_ultima)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(run_id, clave) DO UPDATE SET"
                " estado=excluded.estado, texto_crudo=excluded.texto_crudo,"
                " n_obs=excluded.n_obs, conf_max=excluded.conf_max,"
                " score_max=excluded.score_max, ts_ultima=excluded.ts_ultima",
                (run_id, fila.clave, fila.estado, int(fila.en_db), int(fila.en_catalogo),
                 fila.agent_id, fila.texto_crudo, fila.n_obs, fila.conf_max, fila.score_max,
                 fila.ts_primera, fila.ts_ultima),
            )
            con.execute("UPDATE census_runs SET ts_ultimo=? WHERE id=? AND ts_ultimo < ?",
                        (fila.ts_ultima, run_id, fila.ts_ultima or 0.0))
            con.commit()
        finally:
            con.close()

    def cargar_cobertura(self, run_id: int) -> list[CoverageRow]:
        con = self._conn()
        try:
            filas = con.execute("SELECT * FROM census_coverage WHERE run_id=?",
                                (run_id,)).fetchall()
        finally:
            con.close()
        return [CoverageRow(clave=f["clave"], estado=f["estado"], en_db=bool(f["en_db"]),
                            en_catalogo=bool(f["en_catalogo"]), agent_id=f["agent_id"],
                            texto_crudo=f["texto_crudo"], n_obs=f["n_obs"],
                            conf_max=f["conf_max"], score_max=f["score_max"],
                            ts_primera=f["ts_primera"], ts_ultima=f["ts_ultima"])
                for f in filas]

    def anotar_observacion(self, run_id: int, ts: float, s: MenuSighting,
                           clave: str | None, veredicto: str) -> None:
        """Rastro append-only. Es lo único que hace accionable un DUDOSO: sin esto se sabe que
        algo salió mal, pero no qué."""
        con = self._conn()
        try:
            con.execute(
                "INSERT INTO census_observations (run_id, ts, clave, texto_crudo, conf, score,"
                " veredicto) VALUES (?,?,?,?,?,?,?)",
                (run_id, ts, clave, s.texto_crudo, s.conf, s.score, veredicto),
            )
            con.commit()
        finally:
            con.close()


def _sin_variante(stem: str) -> str:
    """`Norma-ico` / `Aria_extend` → el nombre del personaje. Cada PJ tiene dos archivos de arte
    y son el MISMO personaje; el separador varía (`Aria_ico.webp` contra `Alice-ico.webp`)."""
    for suf in ("-ico", "_ico", "-extend", "_extend"):
        if stem.endswith(suf):
            return stem[: -len(suf)]
    return stem


def roster_y_catalogo() -> tuple[list[tuple[int, str]], set[str]]:
    """Las **dos listas distintas** que el censo necesita, y que significan cosas distintas:

    - `roster` — los que POSEÉS, de la tabla `agents`. Es el denominador de la cobertura.
    - `catalogo` — los que EXISTEN en el juego, de los stems del arte `-ico` en
      `app/resources/avatar_refs/`, que se mantiene por delante de la posesión (Aria tenía arte
      antes de que se la cargara).

    La diferencia entre ambas es lo que el menú de personajes lista en GRIS. Sin ella, cada uno
    de esos se reportaría como candidato a PJ nuevo en cada pasada.

    El catálogo es una ayuda, no una garantía: no cubre a todos los no obtenidos (~9 grises en
    una sola pantalla contra 5 de diferencia, medido el 2026-08-16). Lo que quede afuera se
    reporta como "no reconocido" con las dos lecturas posibles.
    """
    roster: list[tuple[int, str]] = []
    try:
        from app.db.connection import get_connection
        con = get_connection()
        try:
            roster = [(int(r[0]), str(r[1]))
                      for r in con.execute("SELECT id, nombre FROM agents ORDER BY id")]
        finally:
            con.close()
    except Exception:
        log.exception("[censo] no se pudo leer el roster de `agents`")

    catalogo: set[str] = set()
    try:
        from app.core.agent_identifier import _ICO_DIR
        from app.core.asset_resolver import SPLASH_ARTS_DIR
        from app.core.avatar_descriptor import build_name_map
        # UNIÓN de las dos carpetas donde vive el arte de un personaje. Cuál se actualice primero
        # no debería importar: `avatar_refs/` es la semilla de badges y `splash_arts/` el paso 7
        # del onboarding. QA 2026-08-17: Norma tenía splash y no semilla, y el censo la reportaba
        # como "no reconocida" en vez de "no poseída".
        stems = [p.stem for p in _ICO_DIR.glob("*.png")]
        stems += [_sin_variante(p.stem) for p in SPLASH_ARTS_DIR.glob("*.webp")]
        catalogo = set(build_name_map(sorted(set(stems)), [n for _i, n in roster]).values())
    except Exception:
        log.exception("[censo] no se pudo leer el catálogo de arte")
    return roster, catalogo


def marcar_huerfanos_en_dominio(
    claves: Iterable[str],
    *,
    fecha: str,
    db_path_dominio: Path | str | None = None,
) -> int:
    """⚠️ **La ÚNICA función del censo que escribe `danibod_zzz_v2.db`.**

    Todo lo demás vive en `census.db` justamente para que esta frontera sea visible. Se invoca
    solo en el CIERRE —un momento discreto y declarado por el usuario— y solo anota: deja
    `no_visto_en_censo_<fecha>` en `agents.notas`.

    **No borra nada** (RNF-02): ausencia de evidencia no es evidencia de ausencia. Un huérfano
    significa que el recorrido no pasó por ahí, no que el PJ no esté en la cuenta.

    Cumple RNF-01 por construcción: backup previo, transacción, y los dos PRAGMA. Respeta
    `is_readonly()`. Idempotente: re-cerrar el mismo día no duplica la marca.

    Devuelve cuántas filas se marcaron.
    """
    claves = [c for c in claves if c]
    if not claves:
        return 0
    from app.db.connection import is_readonly
    if is_readonly():
        log.info("[censo] readonly: no se marcan los %d huérfanos en la DB de dominio",
                 len(claves))
        return 0

    if db_path_dominio is None:
        from app.db.connection import get_db_path
        db_path_dominio = get_db_path()
    destino = Path(db_path_dominio)
    if not destino.exists():
        log.warning("[censo] no existe la DB de dominio %s — no se marca nada", destino)
        return 0

    marca = f"no_visto_en_censo_{fecha}"
    # El nombre del backup NO puede colgar del reloj: dos cierres del mismo segundo caían en el
    # mismo archivo y `copy2` pisaba el estado previo sin avisar. `respaldar_db` es la autoridad.
    from app.db.connection import respaldar_db
    backup = respaldar_db(destino, "precenso")

    con = sqlite3.connect(destino, isolation_level=None)
    marcadas = 0
    try:
        con.execute("BEGIN")
        for clave in claves:
            cur = con.execute(
                "UPDATE agents SET notas = CASE"
                "   WHEN notas IS NULL OR TRIM(notas) = '' THEN ?"
                "   ELSE notas || ' | ' || ? END"
                " WHERE nombre = ? AND (notas IS NULL OR notas NOT LIKE ?)",
                (marca, marca, clave, f"%{marca}%"),
            )
            marcadas += cur.rowcount or 0
        con.execute("COMMIT")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
        if fk or integridad != "ok":
            log.error("[censo] validación post-marca FALLÓ (fk=%s integrity=%s). Backup: %s",
                      fk, integridad, backup)
    except sqlite3.Error:
        con.execute("ROLLBACK")
        log.exception("[censo] falló la marca de huérfanos — restaurá con %s", backup)
        raise
    finally:
        con.close()
    log.info("[censo] %d huérfanos marcados con '%s' (backup: %s)", marcadas, marca, backup.name)
    return marcadas


def abrir_o_reanudar(
    store: CensusStore,
    roster: Sequence[tuple[int, str]],
    catalogo: Iterable[str] | None = None,
    *,
    ts: float,
    ambito: str = "roster",
    ventana_h: float = _VENTANA_H,
    db_path_dominio: Path | str | None = None,
    db_path: Path | str | None = None,
    readonly: bool | None = None,
) -> RosterCensus:
    """Devuelve la pasada en curso, o abre una nueva.

    Reanudar es lo que hace viable un censo de cientos de entidades: se recorre de a ratos. Pero
    hay dos casos en que reanudar MENTIRÍA, y los dos abandonan la corrida vieja en vez de
    cerrarla (abandonar no fabrica huérfanos):

    - **vencida** — la cobertura de hace semanas no describe la cuenta de hoy;
    - **contra otra DB** — QA suele apuntar `DANIBOD_DB_PATH` a una copia, y reanudar a través de
      ese cambio mezclaría dos cuentas en una sola foto.
    """
    if readonly is None:
        from app.db.connection import is_readonly
        readonly = is_readonly()
    destino = db_path_dominio if db_path_dominio is not None else db_path
    if destino is None:
        from app.db.connection import get_db_path
        destino = get_db_path()
    destino = str(destino)

    censo = RosterCensus(roster, catalogo=catalogo, sink=store)

    prev = store.corrida_abierta(ambito)
    if prev is not None:
        if prev["db_path"] != destino:
            store.abandonar(prev["id"], "db_distinta")
            log.info("[censo] la corrida #%d se contabilizó contra otra DB — se abandona",
                     prev["id"])
            prev = None
        elif (ts - float(prev["ts_ultimo"])) > ventana_h * 3600.0:
            store.abandonar(prev["id"], "expirada")
            log.info("[censo] la corrida #%d quedó vencida (>%.0f h sin actividad) — se abandona",
                     prev["id"], ventana_h)
            prev = None

    if prev is not None:
        censo.restaurar(store.cargar_cobertura(prev["id"]), run_id=int(prev["id"]),
                        ts_apertura=float(prev["ts_apertura"]),
                        ts_ultimo=float(prev["ts_ultimo"]))
        return censo

    censo.ensure_open(ts)
    censo.run_id = store.abrir(ambito, ts=ts, db_path_dominio=destino,
                               roster_n=len(list(roster)), readonly=bool(readonly))
    return censo
