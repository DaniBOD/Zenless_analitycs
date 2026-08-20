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
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

#: Tiene evidencia de posesión. **No se puede destildar**: su build es la prueba.
CONFIRMADO = "confirmado"

#: Está en `agents` pero sin evidencia. La declaración del usuario ES la evidencia — más débil que
#: 6 discos, pero suficiente para no ofrecer borrarlo por accidente. Destildable.
DECLARADO = "declarado"

#: Ni declarado ni con evidencia: existe en el juego y no es tuyo.
NO_OBTENIDO = "no_obtenido"

#: Predicado de confirmación, textual del diseño (`editor-screen.jsx`):
#:
#:     const evidencia = p => p.tiene && (p.d > 0 || p.n > 1);
#:
#: **discos > 0 O nivel > 1**, y no "algún stat cargado". La diferencia importa: es exactamente lo
#: que salva a Aria (0 discos, Nv 40) y lo que deja a Remielle Dan (0 discos, Nv 1) sin evidencia
#: — el falso positivo que motivó el tercer estado. Ojo: el día después de reconstruir la DB nadie
#: califica, y está bien: se está declarando desde cero.
_NIVEL_DEFAULT = 1


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
    nivel: int | None = None
    discos: int = 0
    #: Nombre del PJ base si esta fila es una variante de atuendo (`Billy Estelar` → `Billy`).
    variante_de: str | None = None
    #: Dos grafías del mismo personaje entre los archivos de arte (`Lichter` / `Lighter`).
    grafia_en_conflicto: bool = False

    @property
    def poseido_actual(self) -> bool:
        """Cómo viene tildada la casilla al abrir: lo que la DB cree hoy."""
        return self.en_agents

    @property
    def bloqueado(self) -> bool:
        return self.estado == CONFIRMADO

    def tooltip_bloqueo(self) -> str:
        """El texto del diseño. Un control deshabilitado sin explicación se lee como un bug — y sin
        la última línea, como un callejón sin salida."""
        detalle = f"{self.discos} discos equipados"
        if self.nivel is not None:
            detalle += f" y nivel {self.nivel}"
        return (f"NO SE PUEDE DESTILDAR\n\n{self.nombre} tiene {detalle}. Eso es prueba de "
                "posesión: destildarlo declararía algo que la evidencia contradice, y borraría "
                "la build.\n\nPara quitarlo hay que borrar su build primero, en la pestaña Discos.")


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
            campos = [c for c in ("rango", "elemento", "rol", "faccion", "nivel") if c in cols]
            sel = ", ".join(["nombre", *campos])
            for r in con.execute(f"SELECT {sel} FROM agents"):
                fila = dict(zip(["nombre", *campos], r, strict=True))
                detalle[str(fila["nombre"])] = fila
            if "inventory_discs" in _tablas(con):
                q = ("SELECT a.nombre, COUNT(d.id) FROM agents a "
                     "LEFT JOIN inventory_discs d ON d.agente_asignado = a.id GROUP BY a.id")
                discos = {str(n): int(c) for n, c in con.execute(q)}
        finally:
            con.close()
    except sqlite3.Error:
        log.exception("[roster] no se pudo leer `agents` para armar el catálogo declarable")

    variantes = _variantes_de_atuendo(set(detalle))
    grafias = _grafias_en_conflicto(nombres)

    salida: list[PersonajeDeclarable] = []
    for nombre in nombres:
        fila = detalle.get(nombre)
        n_discos = discos.get(nombre, 0)
        nivel = (fila or {}).get("nivel")

        if fila is None:
            estado, motivo = NO_OBTENIDO, ""
        elif n_discos > 0:
            estado = CONFIRMADO
            motivo = f"{n_discos} discos" + (f" · Nv {nivel}" if nivel is not None else "")
        elif nivel is not None and nivel > _NIVEL_DEFAULT:
            estado, motivo = CONFIRMADO, f"Nv {nivel} sobre el default"
        else:
            estado, motivo = DECLARADO, "declarado por vos · sin datos aún"

        salida.append(PersonajeDeclarable(
            nombre=nombre,
            en_agents=fila is not None,
            estado=estado,
            motivo=motivo,
            rango=(fila or {}).get("rango"),
            elemento=(fila or {}).get("elemento"),
            rol=(fila or {}).get("rol"),
            faccion=(fila or {}).get("faccion"),
            nivel=nivel,
            discos=n_discos,
            variante_de=variantes.get(nombre),
            grafia_en_conflicto=nombre in grafias,
        ))
    return salida


def _variantes_de_atuendo(bases: set[str]) -> dict[str, str]:
    """Detecta las variantes de atuendo por el nombre: `Billy Estelar` → `Billy`.

    Decisión B7 del diseño: **celda propia, ni anidada ni oculta.** Tienen rango, rol, mindscape y
    build propios (Billy Estelar es S/Disruptivos mientras Billy es A/Ataque) y compiten por discos
    de verdad — esconderlas haría que un disco "desaparezca" del inventario visible. Lo que evita
    leerlas como dos personajes más es la marca, no la ausencia.
    """
    salida: dict[str, str] = {}
    for nombre in bases:
        if ":" in nombre:                                   # `N.º 0: Anby` → `Anby`
            cola = nombre.split(":", 1)[1].strip()
            if cola in bases:
                salida[nombre] = cola
                continue
        partes = nombre.split()                             # `Billy Estelar` → `Billy`
        if len(partes) > 1 and partes[0] in bases:
            salida[nombre] = partes[0]
    return salida


def _grafias_en_conflicto(nombres: Sequence[str]) -> set[str]:
    """Nombres que difieren en una sola letra — el caso `Lichter` / `Lighter`.

    **No se dedupean.** El nombre correcto es el que muestre la pantalla del juego; elegir uno por
    parecido, o por cuántos archivos de arte tiene cada grafía, es exactamente el error que ya nos
    mordió con los nombres de los sets de discos. Las dos ocupan lugar y la pantalla lo dice.
    """
    conflicto: set[str] = set()
    for i, a in enumerate(nombres):
        for b in nombres[i + 1:]:
            if len(a) == len(b) and sum(x != y for x, y in zip(a, b, strict=True)) == 1:
                conflicto.update((a, b))
    return conflicto


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

    # Ver `respaldar_db`: el sello al segundo no discrimina, y `copy2` pisa sin avisar.
    from app.db.connection import respaldar_db
    res.backup = respaldar_db(destino, "predeclaracion")

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


def no_poseidos_declarados(db_path: Path | str | None = None) -> set[str]:
    """Los nombres que el usuario declaró **no** tener, en la última tanda.

    Es la primera lista autoritativa de lo que NO está en la cuenta, y por eso vale para algo que
    la observación no puede hacer: **desmentir** un match difuso. El matcher elige el más parecido
    de `agents`, así que frente a un personaje ajeno no tiene la opción correcta y gana un parecido
    coincidental (`Norma→Nekomata 0.615`). Con estos nombres a mano puede abstenerse.

    Solo la **última** tanda: una declaración vieja que siguiera pesando vetaría para siempre a un
    PJ que el usuario acaba de sacar. Ante cualquier problema devuelve el conjunto vacío — esto
    mejora la identificación, no puede ser un requisito para que funcione.
    """
    try:
        con = _conectar(db_path, readonly=True)
    except sqlite3.Error:
        return set()
    try:
        if "roster_declarations" not in _tablas(con):
            return set()
        fila = con.execute("SELECT MAX(ts) FROM roster_declarations").fetchone()
        ts = fila[0] if fila else None
        if not ts:
            return set()
        return {r[0] for r in con.execute(
            "SELECT nombre FROM roster_declarations WHERE ts = ? AND poseido = 0", (ts,))}
    except sqlite3.Error:
        return set()
    finally:
        con.close()


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
