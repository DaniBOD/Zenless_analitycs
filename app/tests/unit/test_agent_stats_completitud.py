"""El log de stats de agente solo debe saltar con los datos COMPLETOS.

## Por qué

Pedido de Daniel (2026-07-26): el log de stats le salta como falso positivo cuando pasa por
alguna pantalla o evento que muestra una stat de vida o de ataque. *"Que salte el log cuando ya
tenga todos los datos: nombre y todos los stats. Si salen 10/11 no sería válido."*

Y hay algo peor que el log, que es el motivo real por el que esto importa: ese mismo punto del
controller **persiste a `agents`** con update parcial. Un parcial de 2 stats escribe esos 2
campos en la DB. Exigir completitud antes de loguear Y antes de sincronizar es la conducta
correcta por RNF-02 (abstenerse antes que escribir algo dudoso), no solo una preferencia de UX.

## Lo medido antes de decidir

- **13 de los 14 fixtures reales de S18 logran nombre + 11/11 en UN SOLO frame** (el que falla,
  `ejemplo_14`/Pyrois, pierde CD). Incluye los dos Disruptivos con FB+AD, así que el gate NO
  apaga el log para ningún rol — era la duda que justificaba medir antes de implementar.
- Del corpus de negativos, **solo 2 filtran stats**: `Guia_Rapida_1` (Nv) y `Guia_Rapida_4`
  (Nv, PV — literalmente "una stat de vida"). **Ninguno pasaría el gate.**

**Lo que NO se pudo reproducir:** la pantalla de evento exacta que vio Daniel no está en el
corpus, y las dos que filtran stats no llegan a S18 por ningún camino (`_deep_detect_s18`
devuelve None en ambas). El gate las corta por construcción igual, porque ninguna llega a 11/11.
Si reaparece, esa captura debería sumarse a `Falsos_positivos/`.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_agent_stats import (
    AgentStatsParsed,
    missing_stat_labels,
    required_stat_keys,
    stats_completos,
)

REPO = Path(__file__).resolve().parents[3]
_PERFIL = REPO / "Documentacion" / "Screenshots_Triggers" / "Triggers_Generales" / "Perfil_agente"
_FP = REPO / "Documentacion" / "Screenshots_Triggers" / "Triggers_Generales" / "Falsos_positivos"

_COMUNES = dict(nivel=60, pv=10792, ataque=2347, defensa=1252, impacto=86,
                prob_crit=0.242, dano_crit=0.50, tasa_anomalia=112,
                maestria_anomalia=330)


def _completo(rol="Ataque", **extra):
    """Un AgentStatsParsed con todo lo requerido para su rol."""
    base = dict(_COMUNES, agente_nombre="Velina", rol=rol, elemento="Viento")
    if "disruptiv" in rol.lower():
        base.update(fuerza_bruta=120, acumulacion_adrenalina=45)
    else:
        base.update(tasa_perforacion=0.0, recuperacion_energia=2.16)
    base.update(extra)
    return AgentStatsParsed(**base)


# --- Requeridos por rol ------------------------------------------------------------------------

def test_los_dos_slots_inferiores_son_exclusivos_por_rol():
    """Disruptivos usan FB+AD; el resto TP+ER. Pedir los cuatro haría que ningún rol complete."""
    resto = required_stat_keys(_completo(rol="Ataque"))
    disr = required_stat_keys(_completo(rol="Disruptivos"))
    assert "tasa_perforacion" in resto and "recuperacion_energia" in resto
    assert "fuerza_bruta" not in resto and "acumulacion_adrenalina" not in resto
    assert "fuerza_bruta" in disr and "acumulacion_adrenalina" in disr
    assert "tasa_perforacion" not in disr and "recuperacion_energia" not in disr
    assert len(resto) == len(disr) == 11


def test_sin_rol_identificado_se_asume_no_disruptivo():
    """Caso mayoritario del roster. Asumir disruptivo dejaría a casi todos incompletos."""
    keys = required_stat_keys(AgentStatsParsed(rol=None))
    assert "tasa_perforacion" in keys


# --- El gate -----------------------------------------------------------------------------------

def test_completo_con_nombre_y_once_de_once():
    s = _completo()
    assert missing_stat_labels(s) == []
    assert stats_completos(s) is True


def test_diez_de_once_no_es_completo():
    """El caso que Daniel puso como ejemplo explícito."""
    s = _completo(dano_crit=None)
    assert missing_stat_labels(s) == ["CD"]
    assert stats_completos(s) is False


def test_sin_nombre_no_es_completo_aunque_esten_los_once():
    """Sin identidad los stats no se pueden atribuir a nadie — y el syncer los escribiría en la
    fila equivocada o en ninguna. Misma regla que los discos: sin PJ confiable no se persiste."""
    s = _completo(agente_nombre=None)
    assert missing_stat_labels(s) == []
    assert stats_completos(s) is False


def test_disruptivo_sin_adrenalina_no_es_completo():
    s = _completo(rol="Disruptivos", acumulacion_adrenalina=None)
    assert missing_stat_labels(s) == ["AD"]
    assert stats_completos(s) is False


def test_las_etiquetas_son_las_del_log():
    """Los labels que ve el usuario tienen que ser los mismos que muestra el log."""
    s = _completo(pv=None, prob_crit=None, maestria_anomalia=None)
    assert missing_stat_labels(s) == ["PV", "CR", "MA"]


def test_un_cero_legitimo_no_cuenta_como_faltante():
    """TP=0.0 es un valor REAL y frecuente (la mayoría del roster lo tiene en 0). Si se tratara
    como ausente por ser falsy, esos PJs nunca completarían."""
    s = _completo(tasa_perforacion=0.0, impacto=0)
    assert missing_stat_labels(s) == []
    assert stats_completos(s) is True


# --- Contra los fixtures reales ----------------------------------------------------------------

def _load(p: Path):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture(scope="module")
def paddle():
    pytest.importorskip("paddleocr")
    from app.core.ocr_paddle import PaddleBackend
    return PaddleBackend(lang="es")


@pytest.mark.skipif(not _PERFIL.exists(), reason="fixtures de perfil no presentes")
def test_la_mayoria_de_los_perfiles_reales_completan(paddle):
    """Guarda contra un gate demasiado estricto: si esto baja, el log se apagó de hecho."""
    from app.core.parser_agent_stats import parse_agent_stats
    fixtures = sorted(_PERFIL.glob("atributos_base_ejemplo_*.png"))
    if not fixtures:
        pytest.skip("sin fixtures")
    completos = [p.name for p in fixtures if stats_completos(parse_agent_stats(_load(p), paddle))]
    assert len(completos) >= len(fixtures) - 2, (
        f"solo {len(completos)}/{len(fixtures)} completan: el gate estaría apagando el log"
    )


@pytest.mark.skipif(not _FP.exists(), reason="corpus de negativos no presente")
def test_ningun_negativo_pasa_el_gate(paddle):
    """El corazón del pedido. Los negativos pueden filtrar 1-2 stats sueltas (Nv, PV); lo que no
    pueden es llegar a nombre + 11/11."""
    from app.core.parser_agent_stats import parse_agent_stats
    for p in sorted(_FP.glob("*.png")):
        fr = _load(p)
        if fr is None:
            continue
        assert not stats_completos(parse_agent_stats(fr, paddle)), f"{p.name} pasó el gate"
