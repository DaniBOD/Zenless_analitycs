"""Tests unitarios — StateMachine (detector multi-capa)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.detector import StateMachine


class TestStateMachine:
    def test_init(self):
        sm = StateMachine()
        assert sm.prev_code is None

    def test_valid_transition_from_none(self):
        sm = StateMachine()
        assert sm.validate("S1") == "S1"
        assert sm.prev_code == "S1"

    def test_valid_transition_s1_to_s2(self):
        sm = StateMachine()
        sm.validate("S1")
        assert sm.validate("S2") == "S2"
        assert sm.prev_code == "S2"

    def test_valid_transition_s2_to_s3(self):
        sm = StateMachine()
        sm.validate("S1")
        sm.validate("S2")
        assert sm.validate("S3") == "S3"

    def test_valid_transition_s8_to_s17(self):
        sm = StateMachine()
        sm.validate("S1")  # None → S1
        sm.validate("S15") # S1 → S15 (menú personajes)
        sm.validate("S8")  # S15 → S8 (vista agente)
        assert sm.validate("S17") == "S17"  # S8 → S17 (detalle disco)

    def test_valid_transition_s17_to_s18(self):
        sm = StateMachine()
        sm.validate("S1")
        sm.validate("S15")
        sm.validate("S8")
        sm.validate("S17")
        assert sm.validate("S18") == "S18"

    def test_invalid_transition_s3_to_s18(self):
        """S3 (modal drop) no puede ir directamente a S18 (perfil agente)."""
        sm = StateMachine()
        sm.validate("S1")
        sm.validate("S2")
        sm.validate("S3")
        # Transición inválida: S3 → S18
        result = sm.validate("S18")
        assert result is not None

    def test_s12_always_valid(self):
        """S12 (no match) debe ser siempre válido desde cualquier estado."""
        sm = StateMachine()
        sm.validate("S3")
        assert sm.validate("S12") == "S12"

    def test_s12_from_any_state(self):
        states = ["S1", "S2", "S3", "S8", "S9", "S17", "S18"]
        for s in states:
            sm = StateMachine()
            sm.validate(s)
            assert sm.validate("S12") == "S12", f"S12 no válido desde {s}"

    def test_chain_completa_pj_route(self):
        """Ruta completa: menú → personajes → agente → detalle disco → atributos."""
        sm = StateMachine()
        assert sm.validate("S15") == "S15"  # menú personajes
        assert sm.validate("S8") == "S8"    # vista agente
        assert sm.validate("S17") == "S17"  # detalle disco
        assert sm.validate("S18") == "S18"  # atributos base
        assert sm.validate("S8") == "S8"    # volver a vista agente
        assert sm.validate("S12") == "S12"  # salir

    def test_reset(self):
        sm = StateMachine()
        sm.validate("S1")
        sm.validate("S2")
        sm.reset()
        assert sm.prev_code is None
        assert sm.validate("S15") == "S15"  # después de reset, desde None

    def test_chain_farmeo(self):
        """Ruta de farmeo: patrulla → desafío → modal drop."""
        sm = StateMachine()
        assert sm.validate("S1") == "S1"
        assert sm.validate("S2") == "S2"
        assert sm.validate("S3") == "S3"
        assert sm.validate("S12") == "S12"
