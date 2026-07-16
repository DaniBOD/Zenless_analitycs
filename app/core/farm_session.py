"""Gate de confianza por flujo de farmeo (RF-04, fase de captura de drops).

El flujo orgánico del juego para farmear discos es:

    S13 (selección de set a farmear) → S14 (pre-combate) → [combate] → S2 (resultados) → S3 (drop)

La pantalla "Resultados del desafío" (S2) aparece para MUCHO contenido distinto (no solo
farmeo de discos), así que el template solo no alcanza para clasificar un farmeo real. Esta
clase ARMA una ventana temporal al ver S13/S14 y se consulta al llegar a S2 para subir la
confianza de que el resultado ES un farmeo de discos (anti-falso-positivo).

Es **time-windowed**, no de adyacencia estricta: entre S14 y S2 hay combate (clasificado como
S1/S12), de modo que NO dependemos del mapa de transiciones del detector. La ventana es
generosa (un farmeo puede durar varios minutos). Espejo conceptual liviano de `UpgradeSyncer`.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# Estados que arman la sesión de farmeo (antelación a captura, ver detector.py). S21 (modal de
# usos de batería) arma porque el farmeo por baterías NO pasa por S14: es S13 → S21 → [auto-
# combate] → "Obtenido". Sin re-armar en S21 la ventana podría vencer durante un auto-combate ×4.
_FARM_ARMING_STATES: frozenset[str] = frozenset({"S13", "S14", "S21"})

# Ventana por defecto (s). Un farmeo puede llevar minutos entre el set-select y los resultados.
_FARM_WINDOW_S = 600.0


class FarmSession:
    """Arma una ventana de confianza al ver S13/S14; la consulta al llegar a S2."""

    def __init__(self, window_s: float = _FARM_WINDOW_S, state_path: str | Path | None = None):
        self._window_s = window_s
        self._armed_until: float = -1.0
        # Predicción de sets leída en S13 (título del nodo → 2 sets). Se consulta en S2
        # para restringir el matcher de badges. Expira con la misma ventana temporal.
        self._pred_node: str | None = None
        self._pred_sets: list[tuple[int | None, str]] = []
        self._pred_until: float = -1.0
        # Nº de corridas leído en S21 ("Cantidad consumida × N"). Lo consulta el "Obtenido" para
        # el denominador de "uso 2/4". NO se persiste en el breadcrumb: es del momento.
        self._usos: int | None = None
        self._usos_until: float = -1.0
        # Breadcrumb opcional en disco (solo QA): al predecir en S13 deja la última predicción
        # para que un REINICIO de la app (tras aplicar un fix) pueda recargar el contexto sin
        # revisitar S13. `time.monotonic()` no sobrevive el reinicio, así que el restore rearma
        # con ventana fresca. Sin state_path (producción) no persiste ni restaura.
        self._state_path: Path | None = Path(state_path) if state_path else None

    def on_state(self, code: str, ts: float) -> None:
        """Alimentar en cada ciclo con el estado activo. Re-arma si es un estado de farmeo."""
        if code in _FARM_ARMING_STATES:
            self._armed_until = ts + self._window_s

    def is_armed(self, ts: float) -> bool:
        """True si hubo un S13/S14 dentro de la ventana → contexto de farmeo de discos."""
        return ts < self._armed_until

    def set_prediction(
        self, node_titulo: str, sets: list[tuple[int | None, str]], ts: float
    ) -> None:
        """Guardar la predicción del nodo S13 (título + [(set_id, nombre_en), ...])."""
        self._pred_node = node_titulo
        self._pred_sets = list(sets)
        self._pred_until = ts + self._window_s
        if self._state_path is not None:
            self._persist()

    def predicted(
        self, ts: float
    ) -> tuple[str, list[tuple[int | None, str]]] | None:
        """Predicción vigente (nodo, sets) si estamos dentro de la ventana; si no, None."""
        if self._pred_node is None or ts >= self._pred_until:
            return None
        return self._pred_node, list(self._pred_sets)

    def set_usos(self, n: int, ts: float) -> None:
        """Guardar el nº de corridas leído en S21 (modal de usos de batería)."""
        self._usos = n
        self._usos_until = ts + self._window_s

    def usos(self, ts: float) -> int | None:
        """Nº de corridas vigente si estamos dentro de la ventana; si no, None."""
        if self._usos is None or ts >= self._usos_until:
            return None
        return self._usos

    # --- persistencia / restore (contexto de QA entre reinicios) ------------

    def _persist(self) -> None:
        """Vuelca la última predicción a `state_path` (JSON). Best-effort: un fallo de disco
        nunca debe interrumpir el flujo de captura (solo se loguea en debug)."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            payload = {"node": self._pred_node,
                       "sets": [[sid, en] for sid, en in self._pred_sets]}
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._state_path)   # rename atómico
        except OSError:
            log.debug("No se pudo persistir el breadcrumb de farmeo", exc_info=True)

    def restore(self, ts: float) -> tuple[str, list[tuple[int | None, str]]] | None:
        """QA: recarga la última predicción persistida (si hay) con ventana FRESCA desde `ts` y
        ARMA el gate (contexto=flujo en S2). Devuelve (nodo, sets) o None si no hay nada válido
        que cargar. No re-escribe el breadcrumb (lectura pura)."""
        if self._state_path is None:
            return None
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        node = data.get("node")
        raw = data.get("sets") or []
        sets = [(item[0], item[1]) for item in raw
                if isinstance(item, (list, tuple)) and len(item) == 2]
        if not node or not sets:
            return None
        self._pred_node = node
        self._pred_sets = sets
        self._pred_until = ts + self._window_s
        self._armed_until = ts + self._window_s   # armar gate → contexto=flujo
        return node, list(sets)
