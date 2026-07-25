"""Lógica de una tanda de desmontaje: reconciliar el censo de tildes contra el contador.

Módulo **puro** a propósito: no importa OpenCV, ni OCR, ni Qt. Toda la parte del feature que no
se puede verificar mirando una captura —qué pasa si el usuario clickea más rápido que el OCR, si
scrollea, si cancela, si el contador sale ilegible— vive acá y se prueba con tuplas.

## Las dos fuentes y su autoridad

- **El contador `N/300` del header manda el conteo.** Es global: sobrevive al scroll.
- **El censo de tildes solo sirve para APAREAR** (qué celda cambió), nunca para contar: solo ve
  el viewport. En `Ejemplo_3` hay 7 discos marcados y 1 visible.

## La regla de atribución

El censo y el parseo del panel salen del **mismo frame**. Entonces un delta de exactamente una
celda, *confirmado por el contador*, prueba que ese fue el único click de la ventana ⇒ el panel
DETAIL está mostrando ese disco. Cualquier delta mayor o mezclado significa que se perdieron
clicks: se declara el hueco y no se atribuye nada.

Que el OCR sea lento solo puede costar **discos sin datos** (aceptable: el conteo igual sale
del contador), nunca **apareos cruzados** (inaceptable, RNF-02).

## Por qué el contador tiene que confirmar cada evento

| Situación | Tildes | Contador | Decisión |
|---|---|---|---|
| click real | +1 celda | +1 | atribuir |
| scroll trae un tilde al viewport | +1 celda | **igual** | no atribuir |
| scroll saca un tilde del viewport | −1 celda | **igual** | **no borrar** lo ya capturado |
| destilde real | −1 celda | −1 | quitar |
| clicks más rápidos que la cadencia | ≥2 | ≥2 | hueco, sin atribuir |
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# Movimiento del thumb del scrollbar que cuenta como scroll real (el centroide tiembla un poco
# entre frames por el degradé del track).
_SCROLL_EPS = 0.02

# Salto de contador en un solo ciclo que delata selección MASIVA (los botones "Selección rápida"
# / "Descarte inteligente"). Por debajo de esto es simplemente clickear rápido.
_MASIVA_MIN = 5

_SCHEMA = "desmontaje/1"


@dataclass
class TeardownDecision:
    """Qué debe hacer el monitor tras una observación."""
    cell_a_capturar: tuple[int, int] | None = None
    logs: list[str] = field(default_factory=list)


def _norm(s: str | None) -> str:
    from app.core.stats_vocab import _norm_key
    return _norm_key(s or "")


def _es_disco_original(nombre: str) -> bool:
    return _norm(nombre).startswith("discooriginal")


class TeardownBatch:
    """Una tanda: se abre al entrar a la pantalla y se cierra al confirmar el desmontaje."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._abierta = False
        self._committed = False
        # Hora de pared: el `ts` que pasa el monitor es `time.monotonic()` (sin época), útil para
        # medir intervalos pero no para fechar el registro.
        self._wall_apertura: datetime | None = None
        self._declarado: int | None = None
        self._prev_counter: int | None = None
        self._prev_tildes: frozenset[tuple[int, int]] = frozenset()
        self._prev_scroll: float | None = None
        self._capturados: dict[tuple[int, int], dict] = {}
        self._avisos: list[str] = []
        self._hubo_scroll = False
        self._modo = "manual"
        self._seq = 0

    # --- estado ---------------------------------------------------------------------------
    @property
    def abierta(self) -> bool:
        return self._abierta

    @property
    def committed(self) -> bool:
        return self._committed

    @property
    def declarado(self) -> int | None:
        return self._declarado

    @property
    def capturados(self) -> dict[tuple[int, int], dict]:
        return dict(self._capturados)

    @property
    def faltantes(self) -> int:
        if self._declarado is None:
            return 0
        return max(0, self._declarado - len(self._capturados))

    @property
    def modo(self) -> str:
        return self._modo

    @property
    def avisos(self) -> list[str]:
        return list(self._avisos)

    @property
    def huecos(self) -> list[dict]:
        n = self.faltantes
        if n <= 0:
            return []
        return [{"motivo": self._motivo_hueco(), "n": n}]

    def _motivo_hueco(self) -> str:
        if self._modo != "manual":
            return "seleccion_masiva"
        if self._hubo_scroll:
            return "fuera_de_viewport"
        return "click_superpuesto"

    def _avisar(self, msg: str) -> bool:
        """Agrega un aviso una sola vez. Devuelve True si es nuevo (para loguear por flanco)."""
        if msg in self._avisos:
            return False
        self._avisos.append(msg)
        return True

    # --- ciclo de vida --------------------------------------------------------------------
    def ensure_open(self, ts: float) -> bool:
        """Abre la tanda si no lo estaba. True si la abrió recién."""
        if self._abierta:
            return False
        self._reset()                       # sin arrastrar nada de la tanda anterior
        self._abierta = True
        self._wall_apertura = datetime.now()
        return True

    def drop(self, motivo: str) -> None:
        """Cierra sin producir registro (tanda abandonada o cancelada)."""
        self._abierta = False
        self._committed = False

    # --- observación ----------------------------------------------------------------------
    def observe(
        self,
        tildes: frozenset[tuple[int, int]],
        counter: int | None,
        scroll: float | None,
        ts: float,
    ) -> TeardownDecision:
        """Procesa un frame: actualiza el conteo y decide si hay que leer el panel DETAIL."""
        d = TeardownDecision()
        if not self._abierta or self._committed:
            return d

        # --- scroll: invalida el apareo de este ciclo, pero nunca borra lo ya capturado ----
        scrolled = (
            scroll is not None
            and self._prev_scroll is not None
            and abs(scroll - self._prev_scroll) > _SCROLL_EPS
        )
        if scrolled:
            self._hubo_scroll = True
            if self._avisar("scroll durante la tanda"):
                d.logs.append("scroll detectado — las celdas dejan de identificar al disco")

        # --- contador ilegible: se declara desconocido, NO se sustituye por el censo ------
        if counter is None:
            if self._avisar("contador del header ilegible"):
                d.logs.append("no se pudo leer el contador N/300 — conteo declarado desconocido")
            self._prev_tildes = tildes
            self._prev_scroll = scroll if scroll is not None else self._prev_scroll
            return d

        altas = tildes - self._prev_tildes
        bajas = self._prev_tildes - tildes
        prev_c = self._prev_counter
        dc = None if prev_c is None else counter - prev_c

        # --- nada seleccionado: cubre "Cancelar selección" y entrar de nuevo a la pantalla -
        if counter == 0:
            if self._capturados:
                d.logs.append(f"selección vacía — se descartan {len(self._capturados)} disco(s) anotados")
                self._capturados.clear()
            self._declarado = 0
            self._prev_counter = 0
            self._prev_tildes = tildes
            self._prev_scroll = scroll if scroll is not None else self._prev_scroll
            return d

        self._declarado = counter

        if dc is not None and dc >= _MASIVA_MIN:
            self._modo = "masiva" if not self._capturados else "mixto"
            if self._avisar(f"selección masiva: {prev_c} → {counter} en un ciclo"):
                d.logs.append(
                    f"⚠ selección masiva: {prev_c} → {counter}/300 en un ciclo · "
                    f"{counter - len(self._capturados)} sin datos"
                )
        elif altas and bajas:
            # Marcar uno y desmarcar otro en el mismo ciclo: el contador no lo desambigua y no
            # se puede saber cuál mostró el panel.
            if self._avisar("cambio ambiguo (alta y baja en el mismo ciclo)"):
                d.logs.append("alta y baja en el mismo ciclo — no se atribuye ni se borra")
        elif altas and dc == len(altas) == 1:
            (cell,) = tuple(altas)
            if not scrolled:
                d.cell_a_capturar = cell
        elif bajas and dc is not None and dc < 0:
            # Destilde REAL (el contador lo confirma): se quitan tantas celdas como evidencia.
            for cell in list(bajas)[: abs(dc)]:
                quitado = self._capturados.pop(cell, None)
                if quitado is not None:
                    d.logs.append(f"−1 → {counter}/300 · destildado: {quitado.get('set_canon') or quitado.get('set_raw')}")

        self._prev_counter = counter
        self._prev_tildes = tildes
        self._prev_scroll = scroll if scroll is not None else self._prev_scroll
        return d

    # --- atribución -----------------------------------------------------------------------
    def attach(self, cell: tuple[int, int], disc, set_id: int | None = None) -> None:
        """Asocia el disco leído del panel DETAIL a la celda que acaba de tildarse."""
        if not self._abierta or self._committed or disc is None:
            return
        self._seq += 1
        self._capturados[cell] = self._record(cell, disc, set_id, self._seq)

    @staticmethod
    def _record(cell: tuple[int, int], disc, set_id: int | None, seq: int) -> dict:
        subs = []
        for s in (getattr(disc, "subs", None) or []):
            subs.append({
                "canon": getattr(s, "nombre_canon", None),
                "raw": getattr(s, "nombre_raw", None),
                "valor": getattr(s, "valor", None),
                "unidad": getattr(s, "unidad", None),
                "rolls": getattr(s, "rolls", 0) or 0,
            })
        main_canon = getattr(disc, "main_stat_canon", None) or getattr(disc, "main_stat_raw", None)
        return {
            "seq": seq,
            "celda": {"fila": cell[0], "col": cell[1]},
            "set_raw": getattr(disc, "set_name_raw", None),
            "set_canon": getattr(disc, "set_name_canon", None),
            "set_id": set_id,
            "slot": getattr(disc, "slot", None),
            "nivel": getattr(disc, "nivel", None),
            "rareza": getattr(disc, "rareza", None),
            "main": {
                "canon": main_canon,
                "raw": getattr(disc, "main_stat_raw", None),
                "valor": getattr(disc, "main_valor", None),
                "unidad": getattr(disc, "main_unidad", None),
            },
            "subs": subs,
            "confianza": getattr(disc, "confianza_global", None),
            # Identidad con la MISMA definición que `InventoryDiscRepo.row_matches_parsed_identity`
            # (set_id, slot, nivel, main normalizado, {substat normalizado + rolls}), para que el
            # futuro script de baja compare directo en vez de re-derivarla y desincronizarse.
            #
            # OJO: en Nivel 0 todos los rolls son 0, así que esta firma colapsa a
            # (set, slot, main, nombres de substat) — y la mayoría de lo que se desmonta es Nivel
            # 0. Por eso el registro guarda ADEMÁS los valores de cada substat y del main: el
            # matcher futuro debe usar identidad ∧ valores y, ante ≥2 candidatos, reportar
            # ambigüedad en vez de dar de baja la fila equivocada.
            "identidad": {
                "set_id": set_id,
                "slot": getattr(disc, "slot", None),
                "nivel": getattr(disc, "nivel", None),
                "main": _norm(main_canon),
                "subs": sorted(
                    (_norm(s["canon"] or s["raw"]), s["rolls"]) for s in subs
                ),
            },
        }

    # --- cierre ---------------------------------------------------------------------------
    def commit(self, materiales, ts: float) -> dict | None:
        """Cierra la tanda y devuelve el registro para la bitácora. `None` si no hay nada que
        registrar (no se declaró selección) o si ya se commiteó — el modal "Obtenido" es un
        estado continuo, así que el gate corre en cada ciclo."""
        if not self._abierta or self._committed:
            return None
        if not self._declarado:
            return None

        material_primero = None
        for nombre, cantidad in (materiales or []):
            if _es_disco_original(nombre):
                material_primero = cantidad
                break

        registro = {
            "schema": _SCHEMA,
            "ts_apertura": (self._wall_apertura.isoformat(timespec="seconds")
                            if self._wall_apertura else None),
            "ts_commit": datetime.now().isoformat(timespec="seconds"),
            "conteo": {
                "declarado": self._declarado,
                "capturados": len(self._capturados),
                "faltantes": self.faltantes,
                "fuente_declarado": "contador_header",
                # Oráculo INDEPENDIENTE, nunca la fuente: la evidencia de los fixtures es
                # contradictoria (la previsualización de Ejemplo_3 dice 7 y el "Obtenido" de
                # Ejemplo_7 dice 1). Se registra y se compara; el contador manda.
                "material_primero": material_primero,
                "corroborado": (None if material_primero is None
                                else material_primero == self._declarado),
            },
            "modo": self._modo,
            "avisos": list(self._avisos),
            "discos": [self._capturados[k] for k in sorted(self._capturados,
                                                           key=lambda c: self._capturados[c]["seq"])],
            "huecos": self.huecos,
        }
        self._committed = True
        self._abierta = False
        return registro


def write_teardown_record(registro: dict | None) -> Path | None:
    """Escribe el registro de una tanda en `audit/desmontajes/`. Devuelve el path o `None`.

    Un archivo POR TANDA, no un JSONL append-only: un registro de 300 discos ronda los 100 KB y
    el append atómico no está garantizado en Windows; un archivo por tanda es atómico por
    construcción (`tmp` + `os.replace`, mismo patrón que `FarmSession._persist`) y tiene
    precedente en el repo (`audit/s23_parse_fallo/`).

    **No toca la DB.** La bitácora es observacional: registra lo que se vio en pantalla, y la
    baja real de las filas de `inventory_discs` es un paso futuro y separado, que además necesita
    el censo de la cuenta hecho primero."""
    if not registro:
        return None
    try:
        from app.core.audit_paths import resolve_audit_dir
        carpeta = resolve_audit_dir() / "desmontajes"
        carpeta.mkdir(parents=True, exist_ok=True)
        # Marca con microsegundos: dos tandas seguidas no pueden pisarse.
        nombre = f"{datetime.now():%Y%m%d_%H%M%S_%f}_desmontaje.json"
        destino = carpeta / nombre
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, destino)
        return destino
    except Exception as e:                                  # pragma: no cover - defensivo
        log.warning("no se pudo escribir la bitácora de desmontaje: %s", e)
        return None
