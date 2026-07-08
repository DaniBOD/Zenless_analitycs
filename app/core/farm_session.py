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

# Estados que arman la sesión de farmeo (antelación a captura, ver detector.py).
_FARM_ARMING_STATES: frozenset[str] = frozenset({"S13", "S14"})

# Ventana por defecto (s). Un farmeo puede llevar minutos entre el set-select y los resultados.
_FARM_WINDOW_S = 600.0


class FarmSession:
    """Arma una ventana de confianza al ver S13/S14; la consulta al llegar a S2."""

    def __init__(self, window_s: float = _FARM_WINDOW_S):
        self._window_s = window_s
        self._armed_until: float = -1.0
        # Predicción de sets leída en S13 (título del nodo → 2 sets). Se consulta en S2
        # para restringir el matcher de badges. Expira con la misma ventana temporal.
        self._pred_node: str | None = None
        self._pred_sets: list[tuple[int | None, str]] = []
        self._pred_until: float = -1.0

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

    def predicted(
        self, ts: float
    ) -> tuple[str, list[tuple[int | None, str]]] | None:
        """Predicción vigente (nodo, sets) si estamos dentro de la ventana; si no, None."""
        if self._pred_node is None or ts >= self._pred_until:
            return None
        return self._pred_node, list(self._pred_sets)
