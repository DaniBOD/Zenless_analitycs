"""Lo que la pantalla Armas sabe del inventario de W-Engines — puro, sin Qt.

El diseño de Claude Design (`engines-data.jsx`) se dibujó con 33 engines de los cuales **5** tenían
datos leídos; el resto iba en ámbar. Cuando se portó, el censo de armas ya había cerrado: las 56
tienen nivel, refinamiento y dueño. Así que de ese archivo **no se toma un solo dato** — se toma el
criterio, que sigue valiendo:

- **"sin leer" no es "por subir".** Un nivel que el OCR no leyó no es un nivel bajo: son dos
  contadores, y mezclarlos haría leer "27 armas por subir" donde no se sabe de ninguna.
- **Refinamiento mínimo 1.** En el juego no existe P0; dibujar cinco estrellas vacías sería inventar
  un estado. Sin lectura, va texto explícito.
- **Una celda por arma FÍSICA** (decisión de Daniel, 2026-09-15): las copias del mismo modelo tienen
  nivel, refinamiento y dueño propios — 5 Última cena, 5 Llanto mielgo, 3 Cañón bombástico. El `×n`
  del diseño se conserva como marca de "hay n copias de este modelo".
- **Dueño a la vista = equipada**, igual que en Discos.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.core.asset_resolver import agent_avatar_path, engine_icon_path
from app.core.roster_declaration import _variantes_de_atuendo

#: Orden de rarezas: S primero (12 de 56), después A.
_ORDEN_RAREZA = {"S": 0, "A": 1, "B": 2}

#: Los ejes de la banda ámbar de auditoría y progreso, con su texto.
AUDITORIA = {
    "libres": "Sin usar",
    "nivel_bajo": "Nivel < 60",
    "refin_bajo": "P < 5",
    "nivel_sin_leer": "Nivel sin leer",
    "refin_sin_leer": "P sin leer",
    "sin_icono": "Sin ícono",
}


@dataclass(frozen=True)
class FilaArma:
    #: id de `inventory_weapons`: identifica la copia física, no el modelo.
    id: int
    weapon_id: int
    nombre: str
    nombre_en: str | None
    rareza: str | None
    especialidad: str | None
    atk_base: int | None
    stat: str | None
    stat_valor: str | None
    nivel: int | None
    refinamiento: int | None
    equipado: bool
    dueno: str | None
    dueno_id: int | None
    dueno_avatar: str | None
    icono: str | None
    #: Cuántas copias activas hay de este mismo modelo (esta incluida).
    copias: int

    @property
    def libre(self) -> bool:
        return not self.equipado


def leer_armas(con: sqlite3.Connection) -> list[FilaArma]:
    """Una fila por arma activa. Dos consultas: el inventario y el conteo de copias."""
    filas = con.execute("""
        SELECT i.id, w.id AS wid, w.nombre, w.nombre_en, w.rareza, w.tipo_especialidad, w.atk_base,
               w.stat_secundario, w.stat_secundario_valor, i.nivel, i.refinamiento, i.equipado,
               a.nombre AS dueno, a.id AS dueno_id
        FROM inventory_weapons i
        JOIN weapons w ON w.id = i.weapon_id
        LEFT JOIN agents a ON a.id = i.agente_asignado AND i.equipado = 1
        WHERE i.descartado = 0
        ORDER BY i.id
    """).fetchall()
    copias = Counter(tuple(f)[1] for f in filas)

    salida = []
    for f in filas:
        (inv_id, wid, nombre, nombre_en, rareza, esp, atk, stat, stat_v, nivel, refin, equipado,
         dueno, dueno_id) = tuple(f)
        equipado = bool(equipado)
        icono = engine_icon_path(nombre, nombre_en)
        avatar = agent_avatar_path(dueno, "ico") if equipado and dueno else None
        salida.append(FilaArma(
            id=inv_id, weapon_id=wid, nombre=nombre, nombre_en=nombre_en, rareza=rareza,
            especialidad=esp, atk_base=atk, stat=stat, stat_valor=stat_v, nivel=nivel,
            refinamiento=refin, equipado=equipado,
            dueno=dueno if equipado else None, dueno_id=dueno_id if equipado else None,
            dueno_avatar=str(avatar) if avatar else None,
            icono=str(icono) if icono else None, copias=copias[wid],
        ))
    return salida


def ordenar(filas: Iterable[FilaArma]) -> list[FilaArma]:
    """S primero, después alfabético, y entre copias del mismo modelo por id."""
    return sorted(filas, key=lambda f: (_ORDEN_RAREZA.get(f.rareza or "", 9),
                                        f.nombre.casefold(), f.id))


def conteos(filas: list[FilaArma]) -> dict[str, int]:
    return {
        "armas": len(filas),
        "modelos": len({f.weapon_id for f in filas}),
        "equipadas": sum(1 for f in filas if f.equipado),
        "libres": sum(1 for f in filas if f.libre),
        "s": sum(1 for f in filas if f.rareza == "S"),
        "a": sum(1 for f in filas if f.rareza == "A"),
        "sin_icono": sum(1 for f in filas if not f.icono),
        "sin_especialidad": sum(1 for f in filas if not f.especialidad),
    }


def _valor_eje(f: FilaArma, eje: str):
    if eje == "estado":
        return "equipada" if f.equipado else "libre"
    return getattr(f, eje)


def filtrar(filas: Iterable[FilaArma], filtros: Mapping[str, set]) -> list[FilaArma]:
    """Dentro de un eje SUMAN, entre ejes RESTAN — igual que en Roster y Discos.
    Ejes: `rareza`, `estado` (`equipada` | `libre`), `especialidad`, `dueno`, y `auditoria`."""
    activos = {e: v for e, v in filtros.items() if v}
    audit = activos.pop("auditoria", None)
    salida = [f for f in filas if all(_valor_eje(f, e) in v for e, v in activos.items())]
    if audit:
        grupos = auditoria(salida)
        permitidos = {x.id for clave in audit for x in grupos.get(clave, [])}
        salida = [f for f in salida if f.id in permitidos]
    return salida


def auditoria(filas: Iterable[FilaArma]) -> dict[str, list[FilaArma]]:
    """Los grupos de la banda ámbar. `nivel_bajo` y `refin_bajo` sólo miran lo LEÍDO: un dato
    ausente no es un dato bajo (el criterio central del diseño)."""
    filas = list(filas)
    return {
        "libres": [f for f in filas if f.libre],
        "nivel_bajo": [f for f in filas if f.nivel is not None and f.nivel < 60],
        "refin_bajo": [f for f in filas if f.refinamiento is not None and f.refinamiento < 5],
        "nivel_sin_leer": [f for f in filas if f.nivel is None],
        "refin_sin_leer": [f for f in filas if f.refinamiento is None],
        "sin_icono": [f for f in filas if not f.icono],
    }


def pjs_sin_arma(con: sqlite3.Connection) -> list[dict]:
    """Los PJs del roster sin W-Engine equipado — se CALCULA (el diseño traía una lista vieja).

    Trae lo que la celda de auditoría muestra, y nada más: el nivel va `None` si no se leyó, y la
    variante de atuendo se marca con la misma regla que el Roster.
    """
    filas = con.execute("""
        SELECT a.id, a.nombre, a.rango, a.elemento, a.rol, a.nivel,
               EXISTS (SELECT 1 FROM agent_thresholds t WHERE t.agente_id = a.id) AS umbrales
        FROM agents a
        WHERE NOT EXISTS (
            SELECT 1 FROM inventory_weapons w
            WHERE w.agente_asignado = a.id AND w.equipado = 1 AND w.descartado = 0)
        ORDER BY a.nombre
    """).fetchall()
    nombres = {r[0] for r in con.execute("SELECT nombre FROM agents")}
    variantes = _variantes_de_atuendo(nombres)
    salida = []
    for pj_id, nombre, rango, elemento, rol, nivel, umbrales in (tuple(f) for f in filas):
        avatar = agent_avatar_path(nombre, "ico")
        salida.append({
            "id": pj_id, "nombre": nombre, "rango": rango, "elemento": elemento, "rol": rol,
            "nivel": nivel, "sin_thresholds": not umbrales,
            "variante_de": variantes.get(nombre),
            "avatar": str(avatar) if avatar else None,
        })
    return salida
