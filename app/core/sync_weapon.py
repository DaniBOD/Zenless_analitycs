"""Sync RF-15 — el W-Engine observado en pantalla entra a `inventory_weapons`.

Primera escritura que esa tabla recibe en la vida del proyecto: existía desde la Fase 1 con 0
filas y sin un solo repo ni syncer que la tocara (`app/db/repositories.py` no tenía una sola
referencia a armas hasta el 2026-09-06).

**Sólo persiste.** Ni scoring ni catálogo: `weapon_evaluations` y `weapon_passives_structured`
están vacías y son RF-14, un tramo aparte. La forma es la de `persist_s17_disc`, que hace bien en
hacer una sola cosa.

## De qué se fía cada fila, y por qué no todo vale igual

Hay tres pantallas que ven un arma y no dan la misma certeza sobre el dueño:

  · **S26** con el botón en 'Desequipar' — el juego AFIRMA que el PJ en pantalla la lleva. No pasa
    por la librería de badges. Es el camino certero.
  · **S30** (inventario) — el dueño sale del matcher de avatares. Medido en
    `test_s30_dueno_verdad_de_tierra.py`: **8/10**, y el desglose importa: los 6 que NOMBRA salen
    los 6 bien; el que falla AFIRMA que un arma está libre y es de Grace.
  · **S29** — el diálogo de sustitución, que el juego escribe en texto.

De ahí la regla de v1: **se escribe lo que se NOMBRA, nunca lo que se declara libre.** Nombrar es
fiable, negar dueño no — la misma asimetría que ya dejó escrita la práctica *"reportar y aprender
piden evidencia distinta"*. Un `agente_asignado = NULL` escrito desde una lectura equivocada es el
"falso LIBRE" que en discos habilitó reemplazos erróneos.

Y la guarda que en discos protege ese caso —un libre que choca con una fila EQUIPADA se abstiene—
**no sirve al principio de una pasada de censo**, porque todavía no hay filas contra las cuales
chocar. Por eso acá la abstención es previa, no reactiva.

## Las armas son FUNGIBLES, y eso cambia qué cuenta como conflicto

Un disco es único: sus substats salen de una tirada, así que dos filas iguales casi siempre son un
duplicado a corregir. Un W-Engine no — dos copias del mismo son **idénticas en todo campo
observable**, y de las A de gacha estándar es normal tener varias.

Por eso el único invariante que se defiende es *un PJ lleva un arma sola* (bucket B + el índice
único parcial de la migración `_26`). Que un arma aparezca en dos PJs **no** es un conflicto: son
dos copias, y van dos filas. La v1 se abstenía ahí y la pasada del 2026-09-08 mostró el costo —
'Última cena' salió en Gatillo, Koleda y Lycaon, y se escribió una sola.

`origen_evidencia` deja registrado en la fila cuál de los tres caminos la respalda: ninguna otra
cosa permite reconstruirlo después.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.parser_weapon_s26 import WeaponParsed
from app.db.connection import is_readonly
from app.db.repositories import AgentRepo, InventoryWeaponRepo, WeaponRepo

log = logging.getLogger(__name__)

# Mismo default que `sync_equip` y `optimizer`: la ruta REAL la resuelve el controller con
# `get_db_path()` y la pasa por constructor (empaquetada, la DB vive en %LOCALAPPDATA%).
DB_PATH = Path("db/danibod_zzz_v2.db")


@dataclass
class WeaponSyncResult:
    """Qué hizo el syncer con un arma observada.

    `inv_id = -1` es el placeholder del camino read-only y **no es una fila**: quien lo use como
    identidad (el censo) tiene que rechazarlo, o colapsa todas las armas en un solo elemento. Es la
    misma trampa que el censo de discos dejó documentada.
    """
    inv_id: int
    trigger: str
    weapon_id: int | None
    nombre: str
    agente_nombre: str | None = None
    latency_ms: float = 0.0


class WeaponSyncer:
    """Persiste W-Engines observados. Una instancia por sesión de app."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self._db_path = db_path
        # `check_same_thread=False`: el syncer se construye en el hilo de la UI y se usa desde el
        # del monitor. El uso es single-thread real (no hay accesos concurrentes a esta conexión);
        # sin esto SQLite lanza "objects created in a thread can only be used in that thread". Es
        # el mismo bug que `DiscSyncer` documenta y que tiene test de regresión.
        self._con_r = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con_r.row_factory = sqlite3.Row
        self._agent_repo = AgentRepo(self._con_r)
        self._weapon_repo = WeaponRepo(self._con_r)

    def close(self) -> None:
        self._con_r.close()

    # -- API ----------------------------------------------------------------
    def persist_s30_weapon(self, p: WeaponParsed) -> WeaponSyncResult | None:
        """Persiste un arma vista en el inventario (S30). `None` si se abstuvo.

        Cada abstención loguea su motivo. No es verborragia: un camino que se abstiene en silencio
        no se distingue de uno que nunca corrió (A2), y este syncer es todo abstenciones.
        """
        t0 = time.perf_counter()
        nombre = p.nombre_canon or p.nombre_raw or "?"

        # 1. Fuera de catálogo. NO se da de alta en `weapons`: esa tabla es curada, tiene 42 armas
        #    de menos y completarla es una pasada aparte con el nombre español leído de pantalla
        #    (`audit/weapons_catalog_20260728.md`). Insertar acá con lo que devuelva el OCR
        #    repetiría el pecado original del catálogo, que fue emparejar por parecido.
        if not p.nombre_canon:
            log.info("Arma fuera del catálogo: %r — no se persiste ni se da de alta.", p.nombre_raw)
            return None

        weapon_id = self._weapon_repo.get_id_by_nombre(p.nombre_canon)
        if weapon_id is None:
            log.warning("Arma '%s' canonizada pero sin fila en weapons — no se persiste.", nombre)
            return None

        # 2. Sin dueño NOMBRADO no se escribe. Incluye el caso en que S30 dice LIBRE: esa
        #    afirmación es justamente la que se mide mal (ver docstring del módulo).
        agente_id = self._agent_repo.get_id_by_nombre(p.dueno)
        if agente_id is None:
            log.info("Arma '%s' sin dueño identificado (dueno=%r) — se registra, no se escribe.",
                     nombre, p.dueno)
            return None

        if is_readonly():
            log.info("[readonly] arma NO persiste — %s · %s · Nv%s · P%s",
                     nombre, p.dueno, p.nivel, p.refinamiento)
            return WeaponSyncResult(inv_id=-1, trigger="readonly", weapon_id=weapon_id,
                                    nombre=nombre, agente_nombre=p.dueno)

        con_w = sqlite3.connect(str(self._db_path))
        con_w.row_factory = sqlite3.Row
        repo = InventoryWeaponRepo(con_w)
        try:
            with con_w:
                res = self._resolver(repo, p, weapon_id, agente_id, p.dueno, nombre)
            if res is not None:
                res.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
                log.info("Arma persistida id=%d %s %s · %s · Nv%s · P%s %.0fms",
                         res.inv_id, res.trigger, nombre, p.dueno,
                         p.nivel, p.refinamiento, res.latency_ms)
            return res
        except Exception:
            log.exception("Error persistiendo el arma '%s'", nombre)
            return None
        finally:
            con_w.close()

    # -- reparto de candidatos ----------------------------------------------
    def _resolver(self, repo: InventoryWeaponRepo, p: WeaponParsed, weapon_id: int,
                  agente_id: int, agente_nombre: str | None,
                  nombre: str) -> WeaponSyncResult | None:
        """Los cuatro buckets. Corre DENTRO de la transacción.

        La clave natural es el PJ: un PJ equipa exactamente un W-Engine, que es para las armas lo
        que `(PJ, slot)` para los discos. Desde la migración `_26` además es un índice único
        parcial, así que un choque no se puede colar en silencio.
        """
        def _ok(inv_id: int, trigger: str) -> WeaponSyncResult:
            return WeaponSyncResult(inv_id=inv_id, trigger=trigger, weapon_id=weapon_id,
                                    nombre=nombre, agente_nombre=agente_nombre)

        actual = repo.find_equipped_by_agent(agente_id)

        # A · el PJ ya tiene ESTA arma: refrescar nivel/refinamiento y listo.
        if actual is not None and actual.weapon_id == weapon_id:
            repo.update_estado(actual.id, nivel=p.nivel, refinamiento=p.refinamiento)
            return _ok(actual.id, "s30_update")

        # B · el PJ figura con OTRA arma. Durante una pasada de censo eso significa que una de las
        #     dos lecturas del badge está mal, y no hay forma de saber cuál. Se abstiene: un insert
        #     de más se corrige en el próximo censo, una escritura equivocada destruye.
        if actual is not None:
            log.warning(
                "Conflicto: %s ya figura con weapon_id=%d (fila %d) y esta lectura dice '%s' "
                "(weapon_id=%d) — no se toca ninguna de las dos. Un PJ lleva un arma sola, así que "
                "una de las dos lecturas del badge está mal y no se sabe cuál.",
                agente_nombre, actual.weapon_id, actual.id, nombre, weapon_id,
            )
            return None

        # C · el arma ya figura equipada por OTRO PJ: es una COPIA, y se inserta como fila nueva.
        #
        #     La v1 se abstenía acá, leyendo el choque como "una de las dos lecturas del badge
        #     está mal". La pasada del 2026-09-08 mostró que la premisa era falsa: 'Última cena'
        #     salió equipada por Gatillo, Koleda y Lycaon, y sólo se escribió la primera. Los
        #     W-Engines son FUNGIBLES —dos copias son idénticas en todo campo observable— así que
        #     tener varias de una A estándar es lo normal, no un síntoma.
        #
        #     El invariante que sí hay que defender es *un PJ lleva un arma sola*, y de ese ya se
        #     ocupan el bucket B y el índice único parcial de la migración `_26`. Pedir además que
        #     un arma tenga un solo dueño era más estricto que el invariante — y encima incoherente:
        #     ante el MISMO badge mal leído, si el arma no estaba en otro PJ el bucket D insertaba
        #     igual. La guarda sólo tapaba un subconjunto de los errores que decía cubrir, al precio
        #     de perder todas las copias legítimas.
        #
        #     Lo que NO cambia: la fila ajena no se toca. Mover sobre una lectura equivocada le saca
        #     el arma a un PJ que sí la tiene (destructivo e invisible); insertar de más se corrige
        #     en el próximo censo. Es la misma asimetría que gobierna `dar_de_baja_desmontados`.
        ajenas = [w for w in repo.find_by_weapon(weapon_id)
                  if w.equipado == 1 and w.agente_asignado is not None
                  and w.agente_asignado != agente_id]

        # D · nada matchea: es un arma que la DB no tenía.
        inv_id = repo.insert(weapon_id, nivel=p.nivel, refinamiento=p.refinamiento,
                             agente_asignado=agente_id, equipado=1,
                             origen_evidencia="s30_badge")
        if ajenas:
            # Se avisa igual, en INFO y no en WARNING: una copia es un hecho del inventario, no un
            # problema. Se nombran las filas hermanas porque son la única pista de que el badge
            # PODRÍA haberse equivocado — quien revise el censo decide mirando la pantalla.
            log.info(
                "Copia: '%s' ya figuraba en otro PJ (filas %s) y esta lectura la pone en %s — se "
                "inserta como fila nueva, la otra no se toca. Los W-Engines son fungibles: tener "
                "dos copias es normal. Si en realidad es una sola, sobra una fila y la saca el "
                "próximo censo.",
                nombre, ", ".join(str(w.id) for w in ajenas), agente_nombre,
            )
            return _ok(inv_id, "s30_insert_copia")
        return _ok(inv_id, "s30_insert")
