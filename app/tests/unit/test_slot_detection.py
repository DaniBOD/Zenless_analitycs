"""Tests — Slot detection multi-método para S17."""
import sys
from pathlib import Path
import numpy as np
import cv2
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.detector import (
    _SLOT_RE, _SLOT_POSITIONS, _SLOT_GLOW_HSV_LOWER, _SLOT_GLOW_HSV_UPPER,
    _detect_slot_by_glow,
)


class TestSlotRegex:
    def test_slot_1(self):
        m = _SLOT_RE.search("Fábula Yunkui (1)")
        assert m and m.group(1) == "1"

    def test_slot_6(self):
        m = _SLOT_RE.search("Monarca de la niebla (6)")
        assert m and m.group(1) == "6"

    def test_no_slot(self):
        assert _SLOT_RE.search("Personalización de pistas") is None

    def test_multiple_parentheses(self):
        m = _SLOT_RE.search("Tecno Pícido (3) (mejorado)")
        assert m and m.group(1) == "3"


class TestSlotPositions:
    def test_all_6_slots_defined(self):
        assert len(_SLOT_POSITIONS) == 6
        for i in range(1, 7):
            assert i in _SLOT_POSITIONS

    def test_positions_are_normalized(self):
        """Cada posición debe tener 4 floats en rango [0, 1]."""
        for slot, pos in _SLOT_POSITIONS.items():
            assert len(pos) == 4
            for v in pos:
                assert 0.0 <= v <= 1.0, f"Slot {slot} coord {v} fuera de rango"

    def test_layout_hexagonal_zzz(self):
        """Verificar layout hexagonal ZZZ (diamante).
        Top: slot1. Upper: slot6(izq), slot2(der).
        Lower: slot5(izq), slot3(der). Bottom: slot4."""
        # Slot 1 en el top (y más chico que todos)
        for s in (2, 3, 4, 5, 6):
            assert _SLOT_POSITIONS[1][1] < _SLOT_POSITIONS[s][1], \
                f"Slot 1 debe estar arriba de Slot {s}"
        # Slot 4 en el bottom (y más grande que todos)
        for s in (1, 2, 3, 5, 6):
            assert _SLOT_POSITIONS[4][1] > _SLOT_POSITIONS[s][1], \
                f"Slot 4 debe estar abajo de Slot {s}"
        # Slot 6 y 5 son izq (x menor), Slot 2 y 3 son der (x mayor)
        assert _SLOT_POSITIONS[6][0] < _SLOT_POSITIONS[2][0], "Slot 6 izq de Slot 2"
        assert _SLOT_POSITIONS[5][0] < _SLOT_POSITIONS[3][0], "Slot 5 izq de Slot 3"
        # Slot 6 arriba de slot 5 (misma columna izq)
        assert _SLOT_POSITIONS[6][1] < _SLOT_POSITIONS[5][1]
        # Slot 2 arriba de slot 3 (misma columna der)
        assert _SLOT_POSITIONS[2][1] < _SLOT_POSITIONS[3][1]


class TestGlowHSV:
    def test_glow_hsv_range_valid(self):
        """Rango HSV debe tener 3 canales cada uno."""
        assert len(_SLOT_GLOW_HSV_LOWER) == 3
        assert len(_SLOT_GLOW_HSV_UPPER) == 3
        # H: 40-80 (verde/amarillo)
        assert 40 <= _SLOT_GLOW_HSV_LOWER[0] <= 80
        assert _SLOT_GLOW_HSV_UPPER[0] >= 40
        # S: 100-255
        assert _SLOT_GLOW_HSV_LOWER[1] >= 50
        # V: 170-255 (brillante)
        assert _SLOT_GLOW_HSV_LOWER[2] >= 100

    def test_detect_slot_no_glow(self):
        """Sin frame (None) debe retornar None."""
        assert _detect_slot_by_glow(None) is None

    def test_detect_slot_empty_frame(self):
        """Frame vacío debe retornar None."""
        assert _detect_slot_by_glow(np.zeros((10, 10, 3), dtype=np.uint8)) is None

    def test_detect_slot_black_frame(self):
        """Frame negro no debe detectar glow."""
        black = np.zeros((480, 640, 3), dtype=np.uint8)
        assert _detect_slot_by_glow(black) is None

    def test_detect_slot_with_green_glow(self):
        """Frame con píxeles verdes brillantes en slot position."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        nx, ny, nw, nh = _SLOT_POSITIONS[1]
        x, y = int(nx * 1920), int(ny * 1080)
        rw, rh = int(nw * 1920), int(nh * 1080)
        # BGR: verde brillante (G=200, B=60)
        frame[y:y+rh, x:x+rw] = (60, 200, 60)
        slot = _detect_slot_by_glow(frame)
        assert slot == 1, f"Esperaba slot=1, obtuve {slot}"
