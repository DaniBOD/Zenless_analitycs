"""Tests — thresholds dinámicos por estado en detector.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.detector import THRESHOLD_BY_STATE, CAPTURE_DISC_STATES


class TestThresholdsPerState:
    def test_all_18_states_have_thresholds(self):
        """Cada estado S1-S18 debe tener un threshold definido."""
        for i in range(1, 19):
            code = f"S{i}"
            assert code in THRESHOLD_BY_STATE, f"Falta threshold para {code}"

    def test_new_disc_capture_states_higher_threshold(self):
        """Estados de captura de discos NUEVOS deben tener threshold ≥ 0.80.
        S17 (disco equipado, informativo) puede tener threshold más bajo."""
        new_capture = CAPTURE_DISC_STATES - {"S17"}
        for code in new_capture:
            assert THRESHOLD_BY_STATE[code] >= 0.80, f"{code} threshold {THRESHOLD_BY_STATE[code]} < 0.80"

    def test_transition_states_lower_threshold(self):
        """Estados de transición deben tener threshold ≤ 0.75."""
        for code in ("S13", "S14", "S15"):
            assert THRESHOLD_BY_STATE[code] <= 0.75, f"{code} threshold {THRESHOLD_BY_STATE[code]} > 0.75"

    def test_s12_zero_threshold(self):
        assert THRESHOLD_BY_STATE["S12"] == 0.0

    def test_s17_threshold_permisive(self):
        """S17 (informativo) debe tener threshold ≤ 0.80."""
        assert THRESHOLD_BY_STATE["S17"] <= 0.80

    def test_s18_threshold_permisive(self):
        """S18 (informativo) debe tener threshold ≤ 0.80."""
        assert THRESHOLD_BY_STATE["S18"] <= 0.80

    def test_s3_threshold_strict(self):
        """S3 (captura crítica) debe tener threshold ≥ 0.85."""
        assert THRESHOLD_BY_STATE["S3"] >= 0.85


class TestCaptureDiscStates:
    def test_s17_in_capture_states(self):
        assert "S17" in CAPTURE_DISC_STATES

    def test_new_disc_states(self):
        for code in ("S3", "S6", "S7"):
            assert code in CAPTURE_DISC_STATES

    def test_non_capture_not_included(self):
        for code in ("S1", "S2", "S11", "S12", "S18"):
            assert code not in CAPTURE_DISC_STATES
