"""El gate de completitud en el controller: ni log ni escritura a `agents` con datos parciales.

Complementa `test_agent_stats_completitud` (que prueba la decisión pura). Acá se prueba el
CABLEADO: que el parcial no llegue al log ni al syncer, que el completo sí, y que el panel de
la UI siga actualizándose siempre — es un binding de datos, no un registro.

Lo que se protege es una escritura: `AgentStatsSyncer.sync` hace update PARCIAL de los campos
que cambiaron, así que un parcial de 2 stats leído en una pantalla ajena escribía esos 2 campos
en `agents`.
"""
from __future__ import annotations

import sys

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication  # noqa: E402

from app.core.detector import ScreenState  # noqa: E402
from app.core.parser_agent_stats import AgentStatsParsed  # noqa: E402

_S18 = ScreenState("S18", 0.97, "s18_atributos_base.png")

_COMUNES = dict(nivel=60, pv=10792, ataque=2347, defensa=1252, impacto=86,
                prob_crit=0.242, dano_crit=0.50, tasa_anomalia=112,
                maestria_anomalia=330)


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


class _SyncerEspia:
    def __init__(self):
        self.llamadas = []

    def sync(self, stats):
        self.llamadas.append(stats)


@pytest.fixture
def ctrl(qapp):
    from app.ui.controller import MonitorController
    c = MonitorController()
    c._logs: list[str] = []
    c._panel: list[dict] = []
    c.log_message.connect(c._logs.append)
    c.agent_stats_detected.connect(c._panel.append)
    c._agent_stats_syncer = _SyncerEspia()
    return c


def _stats(rol="Ataque", **extra):
    base = dict(_COMUNES, agente_nombre="Velina", rol=rol, elemento="Viento",
                tasa_perforacion=0.0, recuperacion_energia=2.16, confianza_global=0.96)
    base.update(extra)
    return AgentStatsParsed(**base)


def _lineas(ctrl, prefijo):
    return [m for m in ctrl._logs if m.startswith(prefijo)]


# --- El caso completo sigue funcionando igual ---------------------------------------------------

def test_completo_loguea_las_tres_lineas_y_persiste(ctrl):
    ctrl._on_agent_stats_from_monitor(_stats(), _S18)
    assert len(_lineas(ctrl, "[reconocido]")) == 1
    assert len(_lineas(ctrl, "[stats]")) == 1
    assert len(_lineas(ctrl, "[completo]")) == 1
    assert len(ctrl._agent_stats_syncer.llamadas) == 1


# --- El parcial no llega a ninguna parte -------------------------------------------------------

def test_diez_de_once_no_loguea_ni_persiste(ctrl):
    """El caso que Daniel puso de ejemplo."""
    ctrl._on_agent_stats_from_monitor(_stats(dano_crit=None), _S18)
    assert _lineas(ctrl, "[stats]") == []
    assert _lineas(ctrl, "[reconocido]") == []
    assert _lineas(ctrl, "[completo]") == []
    assert ctrl._agent_stats_syncer.llamadas == [], "escribió `agents` con datos parciales"


def test_el_fp_de_dos_stats_no_escribe_nada(ctrl):
    """La forma del falso positivo real: una pantalla ajena de la que se leen Nv y PV."""
    parcial = AgentStatsParsed(nivel=60, pv=10792)
    ctrl._on_agent_stats_from_monitor(parcial, _S18)
    assert _lineas(ctrl, "[stats]") == []
    assert ctrl._agent_stats_syncer.llamadas == []


def test_sin_nombre_no_persiste_aunque_esten_los_once(ctrl):
    ctrl._on_agent_stats_from_monitor(_stats(agente_nombre=None), _S18)
    assert ctrl._agent_stats_syncer.llamadas == []
    assert "nombre" in " ".join(_lineas(ctrl, "[parcial]")), _lineas(ctrl, "[parcial]")


# --- Pero no se queda mudo ---------------------------------------------------------------------

def test_el_parcial_dice_que_le_falta(ctrl):
    """Un return mudo es el bug histórico del proyecto. El gate tiene que decir qué falta."""
    ctrl._on_agent_stats_from_monitor(_stats(dano_crit=None, maestria_anomalia=None), _S18)
    parciales = _lineas(ctrl, "[parcial]")
    assert len(parciales) == 1, parciales
    assert "CD" in parciales[0] and "MA" in parciales[0]
    assert "9/11" in parciales[0], f"no dice cuántos leyó: {parciales[0]}"


def test_el_mismo_parcial_repetido_avisa_una_sola_vez(ctrl):
    """S18 es continuo: sin dedup, el log se llena mientras el aggregator madura."""
    for _ in range(5):
        ctrl._on_agent_stats_from_monitor(_stats(dano_crit=None), _S18)
    assert len(_lineas(ctrl, "[parcial]")) == 1


def test_al_avanzar_la_maduracion_vuelve_a_avisar(ctrl):
    """Pasar de 8/11 a 10/11 es información nueva: el usuario ve que progresa."""
    ctrl._on_agent_stats_from_monitor(_stats(dano_crit=None, maestria_anomalia=None,
                                            tasa_anomalia=None), _S18)
    ctrl._on_agent_stats_from_monitor(_stats(dano_crit=None), _S18)
    assert len(_lineas(ctrl, "[parcial]")) == 2


def test_completar_despues_de_un_parcial_si_loguea_y_persiste(ctrl):
    """El caso normal en vivo: entra incompleto y el aggregator lo completa."""
    ctrl._on_agent_stats_from_monitor(_stats(dano_crit=None), _S18)
    ctrl._on_agent_stats_from_monitor(_stats(), _S18)
    assert len(_lineas(ctrl, "[stats]")) == 1
    assert len(ctrl._agent_stats_syncer.llamadas) == 1


# --- El panel es binding, no registro ----------------------------------------------------------

def test_el_panel_se_actualiza_igual_con_parciales(ctrl):
    """La UI muestra el estado en vivo; el gate es sobre el LOG y la ESCRITURA, no sobre la vista.
    Si el panel se congelara, el usuario no vería que el sistema está leyendo."""
    ctrl._on_agent_stats_from_monitor(_stats(dano_crit=None), _S18)
    assert len(ctrl._panel) == 1
    assert ctrl._panel[0]["pv"] == 10792
