"""El roster **declarado por el usuario** — módulo puro, sin Qt ni OpenCV.

El censo por observación funciona para los PJs que se poseen (49/51 en 18 min el 2026-08-17) pero
no puede enumerar los que **no**: de 6 personajes no obtenidos, solo 1 dejó registro, y 4 de 6
matchean a un PJ propio por encima del umbral de identificación (`Norma→Nekomata 0.615`,
`Lichter→Alice 0.667`). Pararse sobre un gris le dice al sistema que estás en otro personaje.

Así que el roster lo declara el usuario y el OCR queda como **verificación**. No contradice RNF-02:
la doctrina es *no inventar*, no *no preguntar* — declarar ~55 casillas que el usuario sabe de
memoria no es lo mismo que transcribir 367 discos con sus substats.

La declaración tiene tres efectos y ninguno borra nada:

1. Se guarda **la tanda completa** en `roster_declarations` (todos, con su 1 o su 0). Es lo único
   que da el **denominador**, que la observación no puede dar por más que recorra el menú.
2. Un declarado **sin fila en `agents`** la recibe, mínima y con NULLs. Sin esa fila la cosecha de
   badges se descarta en silencio (pasó con Aria).
3. Un **sobrante** —en `agents` y no declarado— se marca con la fecha. Es la señal más fuerte que
   el sistema puede dar de una fila espuria, pero sigue siendo una señal (RNF-02).

La escritura copia la ceremonia de `census_store.marcar_huerfanos_en_dominio`, que ya es el patrón
validado del proyecto: gate `is_readonly()`, backup previo, transacción, los dos PRAGMA.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

#: Tiene evidencia de posesión (discos equipados o stats por encima del default). **No se puede
#: destildar**: su build es la prueba. Ojo — el día después de reconstruir la DB nadie califica,
#: y está bien: se está declarando desde cero.
CONFIRMADO = "confirmado"

#: Sin evidencia. El usuario decide.
DECLARABLE = "declarable"

#: Columnas de `agents` cuya presencia prueba que el PJ se posee (el default de una fila recién
#: creada las deja en NULL). Se consultan las que existan: la DB reconstruida las tiene todas en
#: NULL a propósito.
_COLS_EVIDENCIA = ("nivel", "pv", "ataque", "defensa", "impacto", "prob_critico",
                   "dano_critico", "tasa_anomalia", "maestria_anomalia", "rec_energia")


@dataclass(frozen=True)
class PersonajeDeclarable:
    """Una casilla de la pantalla de declaración."""
    nombre: str
    en_agents: bool
    estado: str
    motivo: str = ""
    rango: str | None = None
    elemento: str | None = None
    rol: str | None = None
    faccion: str | None = None
    discos: int = 0

    @property
    def poseido_actual(self) -> bool:
        """Cómo viene tildada la casilla al abrir: lo que la DB cree hoy."""
        return self.en_agents

    @property
    def bloqueado(self) -> bool:
        return self.estado == CONFIRMADO


@dataclass
class ResultadoDeclaracion:
    ts: str
    declarados: int = 0
    total: int = 0
    creados: list[str] = field(default_factory=list)
    marcados: list[str] = field(default_factory=list)
    escribio: bool = False
    motivo_no_escribio: str = ""
    backup: Path | None = None

    def resumen(self) -> str:
        if not self.escribio:
            return f"No se escribió nada — {self.motivo_no_escribio}"
        partes = [f"{self.declarados}/{self.total} declarados"]
        if self.creados:
            partes.append(f"{len(self.creados)} fila(s) nueva(s): {', '.join(self.creados)}")
        if self.marcados:
            partes.append(f"{len(self.marcados)} marcado(s) como no declarado(s)")
        return " · ".join(partes)


# --- el catálogo declarable -------------------------------------------------------------------

def catalogo_declarable(
    *,
    roster_catalogo: tuple[Sequence[tuple[int, str]], Iterable[str]] | None = None,
    db_path: Path | str | None = None,
) -> list[PersonajeDeclarable]:
    """Todos los personajes que el usuario puede tildar, con su estado.

    Es la **unión** del roster (`agents`) con el catálogo de arte, que es la misma que ya usa el
    censo: `census_store.roster_y_catalogo()`. Un PJ que solo tiene arte viene sin identidad — de
    Hugo se sabe el nombre y nada más, y rellenar el resto con algo plausible sería justo lo que
    RNF-02 prohíbe.
    """
    if roster_catalogo is None:
        from app.core.census_store import roster_y_catalogo
        roster, catalogo = roster_y_catalogo()
    else:
        roster, catalogo = roster_catalogo
    nombres = sorted({n for _i, n in roster} | set(catalogo))
    if not nombres:
        return []

    detalle: dict[str, dict] = {}
    discos: dict[str, int] = {}
    try:
        con = _conectar(db_path, readonly=True)
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(agents)")}
            evidencia = [c for c in _COLS_EVIDENCIA if c in cols]
            identidad = [c for c in ("rango", "elemento", "rol", "faccion") if c in cols]
            sel = ", ".join(["nombre", *identidad, *evidencia])
            for r in con.execute(f"SELECT {sel} FROM agents"):
                fila = dict(zip([ "nombre", *identidad, *evidencia], r, strict=True))
                fila["_evidencia"] = any(fila.get(c) is not None for c in evidencia)
                detalle[str(fila["nombre"])] = fila
            if "inventory_discs" in _tablas(con):
                q = ("SELECT a.nombre, COUNT(d.id) FROM agents a "
                     "LEFT JOIN inventory_discs d ON d.agente_asignado = a.id GROUP BY a.id")
                discos = {str(n): int(c) for n, c in con.execute(q)}
        finally:
            con.close()
    except sqlite3.Error:
        log.exception("[roster] no se pudo leer `agents` para armar el catálogo declarable")

    salida: list[PersonajeDeclarable] = []
    for nombre in nombres:
        fila = detalle.get(nombre)
        n_discos = discos.get(nombre, 0)
        if fila and n_discos:
            estado, motivo = CONFIRMADO, f"{n_discos} disco(s) asignado(s) — es prueba de posesión"
        elif fila and fila["_evidencia"]:
            estado, motivo = CONFIRMADO, "tiene stats cargados por encima del default"
        else:
            estado, motivo = DECLARABLE, ""
        salida.append(PersonajeDeclarable(
            nombre=nombre,
            en_agents=fila is not None,
            estado=estado,
            motivo=motivo,
            rango=(fila or {}).get("rango"),
            elemento=(fila or {}).get("elemento"),
            rol=(fila or {}).get("rol"),
            faccion=(fila or {}).get("faccion"),
            discos=n_discos,
        ))
    return salida


# --- la escritura -----------------------------------------------------------------------------

def declarar(
    poseidos: Iterable[str],
    *,
    catalogo: Sequence[PersonajeDeclarable] | Iterable[str],
    fecha: str | None = None,
    db_path: Path | str | None = None,
) -> ResultadoDeclaracion:
    """Guarda la declaración del usuario. Devuelve qué pasó, incluso si no escribió.

    `catalogo` es el universo de personajes conocidos: la tanda se guarda **completa**, con un 0
    para los que no se tildaron. Guardar solo los tildados perdería el registro de los NO poseídos,
    que es justo el dato que la pantalla no expone y el que permite vetar un match difuso.
    """
    fecha = fecha or datetime.now().strftime("%Y-%m-%d")   # noqa: DTZ005
    # Microsegundos, no segundos: `ts` es la CLAVE que agrupa la tanda, y dos declaraciones
    # seguidas dentro del mismo segundo se fusionarían en una sola foto — que es justo lo que la
    # tabla existe para no hacer. Mismo motivo por el que los reportes del censo llevan µs.
    ts = datetime.now().isoformat(timespec="microseconds")  # noqa: DTZ005
    res = ResultadoDeclaracion(ts=ts)

    nombres = [p.nombre if isinstance(p, PersonajeDeclarable) else str(p) for p in catalogo]
    poseidos = {str(n) for n in poseidos}
    res.total = len(nombres)
    res.declarados = len(poseidos & set(nombres))

    if not nombres:
        res.motivo_no_escribio = ("el catálogo vino vacío; una tanda de cero filas declararía que "
                                  "no tenés ningún personaje")
        log.warning("[roster] %s", res.motivo_no_escribio)
        return res

    from app.db.connection import is_readonly
    if is_readonly():
        res.motivo_no_escribio = "la app está en modo solo lectura (DANIBOD_READONLY)"
        log.info("[roster] readonly: no se guarda la declaración de %d personajes", len(nombres))
        return res

    destino = Path(db_path) if db_path else _db_path()
    if not destino.exists():
        res.motivo_no_escribio = f"no existe la DB de dominio ({destino})"
        log.warning("[roster] %s", res.motivo_no_escribio)
        return res

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
    res.backup = destino.with_name(f"{destino.stem}.backup_predeclaracion_{sello}.db")
    shutil.copy2(destino, res.backup)

    marca_falta = f"no_declarado_{fecha}"
    marca_nuevo = f"declarado_por_usuario_{fecha}; pendiente onboarding"

    con = sqlite3.connect(destino, isolation_level=None)
    try:
        con.execute("BEGIN")
        con.executemany(
            "INSERT INTO roster_declarations (ts, nombre, poseido, fuente) VALUES (?,?,?,'usuario')",
            [(ts, n, 1 if n in poseidos else 0) for n in nombres],
        )

        en_agents = {str(r[0]) for r in con.execute("SELECT nombre FROM agents")}

        for nombre in sorted(poseidos - en_agents):
            con.execute("INSERT INTO agents (nombre, notas) VALUES (?, ?)", (nombre, marca_nuevo))
            res.creados.append(nombre)

        for nombre in sorted(en_agents - poseidos):
            cur = con.execute(
                "UPDATE agents SET notas = CASE"
                "   WHEN notas IS NULL OR TRIM(notas) = '' THEN ?"
                "   ELSE notas || ' | ' || ? END"
                " WHERE nombre = ? AND (notas IS NULL OR notas NOT LIKE ?)",
                (marca_falta, marca_falta, nombre, f"%{marca_falta}%"),
            )
            if cur.rowcount:
                res.marcados.append(nombre)

        con.execute("COMMIT")
        res.escribio = True

        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
        if fk or integridad != "ok":
            log.error("[roster] validación post-declaración FALLÓ (fk=%s integrity=%s). Backup: %s",
                      fk, integridad, res.backup)
    except sqlite3.Error:
        con.execute("ROLLBACK")
        log.exception("[roster] falló la declaración — restaurá con %s", res.backup)
        raise
    finally:
        con.close()

    log.info("[roster] declaración guardada — %s", res.resumen())
    return res


# --- helpers ----------------------------------------------------------------------------------

def _db_path() -> Path:
    from app.db.connection import get_db_path
    return get_db_path()


def _conectar(db_path: Path | str | None, *, readonly: bool = False) -> sqlite3.Connection:
    destino = Path(db_path) if db_path else _db_path()
    if readonly:
        return sqlite3.connect(f"file:{destino}?mode=ro", uri=True)
    return sqlite3.connect(destino)


def _tablas(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
