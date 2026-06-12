"""
Tests del matcher de avatar (Etapa 2) — `AgentIdentifier`.

Valida el bootstrap: aprender el avatar de un PJ desde S18 (donde el nombre viene
por OCR) y reconocerlo luego en S8 (donde no hay nombre). Usa capturas reales de
Nangong Yu (misma en S18 y S8) y otras como negativos.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.agent_identifier import AgentIdentifier  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
NANGONG_S18 = REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/atributos_base_ejemplo_1.png"
NANGONG_S8 = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/03_Pantalla_Agente_Discos_Equipados/Ejemplo_1.png"
OTRO_S18 = REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/atributos_base_ejemplo_2.png"
OTRO_S8 = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/03_Pantalla_Agente_Discos_Equipados/Ejemplo_3.png"


def _read(path: Path):
    if not path.exists():
        return None
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def _ident(tmp_path) -> AgentIdentifier:
    return AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False)


def test_identify_vacio_devuelve_none(tmp_path):
    ident = _ident(tmp_path)
    frame = _read(NANGONG_S8)
    if frame is None:
        pytest.skip("captura no disponible")
    assert ident.identify(frame) is None


def test_bootstrap_s18_identifica_en_s8(tmp_path):
    """Aprende Nangong Yu desde S18 y la reconoce en S8 (sin nombre en pantalla)."""
    s18, s8 = _read(NANGONG_S18), _read(NANGONG_S8)
    if s18 is None or s8 is None:
        pytest.skip("capturas no disponibles")
    ident = _ident(tmp_path)
    assert ident.learn(s18, "Nangong Yu") is True
    res = ident.identify(s8)
    assert res is not None, "no reconoció a Nangong Yu en S8 tras aprenderla en S18"
    name, corr = res
    assert name == "Nangong Yu"
    assert corr > 0.88


def test_no_confunde_con_otro_pj(tmp_path):
    """Con solo Nangong Yu en la librería, otro PJ NO debe matchear (umbral)."""
    s18, otro = _read(NANGONG_S18), _read(OTRO_S8)
    if s18 is None or otro is None:
        pytest.skip("capturas no disponibles")
    ident = _ident(tmp_path)
    ident.learn(s18, "Nangong Yu")
    res = ident.identify(otro)
    # O bien None, o bien NO la nombra Nangong con alta confianza
    assert res is None or res[0] != "Nangong Yu" or res[1] < 0.88


def test_discrimina_entre_dos_pj(tmp_path):
    """Con dos PJs aprendidos, cada uno se reconoce como sí mismo."""
    s18a, s8a = _read(NANGONG_S18), _read(NANGONG_S8)
    otro18 = _read(OTRO_S18)
    if any(f is None for f in (s18a, s8a, otro18)):
        pytest.skip("capturas no disponibles")
    ident = _ident(tmp_path)
    ident.learn(s18a, "Nangong Yu")
    ident.learn(otro18, "PJ_Otro")
    res = ident.identify(s8a)
    assert res is not None and res[0] == "Nangong Yu"


def test_persistencia_round_trip(tmp_path):
    """Aprender + guardar + recargar en otra instancia → sigue reconociendo."""
    s18, s8 = _read(NANGONG_S18), _read(NANGONG_S8)
    if s18 is None or s8 is None:
        pytest.skip("capturas no disponibles")
    path = tmp_path / "lib.npz"
    a = AgentIdentifier(library_path=path, autoload=False)
    a.learn(s18, "Nangong Yu")
    assert a._row_path.exists()      # Fase 5R: la lib de fila se guarda en avatar_row_v2.npz
    b = AgentIdentifier(library_path=path, autoload=True)
    assert "Nangong Yu" in b.names
    res = b.identify(s8)
    assert res is not None and res[0] == "Nangong Yu"
