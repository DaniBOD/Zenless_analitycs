"""Tests del contrato REUSABLE de `app/core/owner_vote.py` (5R.L.8).

`OwnerVoteAccumulator` es la maquinaria de voto/presencia extraída de monitor.py
para que futuras pantallas (S9 inventario global, S23 reemplazo) la instancien.
La política de `decide_owner` (grid-primario / det-solo / anti-imán) se cubre en
`test_s17_owner_vote.py` (vía el alias histórico); acá se cubre el ciclo de vida
del acumulador y la regla LIBRE de presencia estructural.
"""
from app.core.owner_vote import DETAIL, GRID, OwnerVoteAccumulator


def test_ciclo_vote_y_decide_grid_primario():
    acc = OwnerVoteAccumulator()
    acc.vote(GRID, "Vivian", 0.9)
    acc.vote(DETAIL, "Vivian", 1.0)
    assert acc.decide() == ("Vivian", "grid+det")
    # el detail NO puede pisar al grid aunque acumule más score (RNF-02)
    acc.vote(DETAIL, "Nangong Yu", 5.0)
    owner, src = acc.decide()
    assert owner == "Vivian" and src == "grid"


def test_detail_solo_bajo_guard_y_anti_iman():
    acc = OwnerVoteAccumulator()
    acc.vote(DETAIL, "Yanagi", 1.0)          # 1 frame confiable ≥ solo_min_score
    assert acc.decide() == ("Yanagi", "det")
    assert acc.decide(latch="Yanagi") == (None, None)   # anti-imán: det-solo == latch


def test_is_libre_presencia_gana():
    acc = OwnerVoteAccumulator()
    # sin evidencia → LIBRE (latencia 1 frame)
    assert acc.is_libre() is True
    # ausencias puras (libre real) → LIBRE
    acc.mark_absent(DETAIL)
    acc.mark_absent(DETAIL)
    assert acc.is_libre() is True
    # UN frame con cara (presencia estructural) → bloquea LIBRE aunque dominen ausencias
    acc.mark_present(DETAIL)
    assert acc.is_libre() is False
    # la presencia del GRID (gate leaky en libres, L.7.2) NO bloquea
    acc2 = OwnerVoteAccumulator()
    acc2.mark_present(GRID)
    assert acc2.is_libre() is True
    # cualquier voto → no libre
    acc3 = OwnerVoteAccumulator()
    acc3.vote(GRID, "Ellen", 0.9)
    assert acc3.is_libre() is False


def test_reset_limpia_todo():
    acc = OwnerVoteAccumulator()
    acc.vote(GRID, "Ellen", 0.9)
    acc.mark_present(DETAIL)
    acc.passes = 7
    acc.reset()
    assert acc.decide() == (None, None)
    assert acc.is_libre() is True
    assert acc.passes == 0 and acc.present(DETAIL) == 0


def test_superficies_custom_para_otras_pantallas():
    """S9/S23: superficies propias sin tocar la política (primaria configurable)."""
    acc = OwnerVoteAccumulator(primary="s9_tile", presence_surface="s9_tile")
    acc.vote("s9_tile", "Burnice", 0.9)
    assert acc.decide() == ("Burnice", "grid")   # source refleja el rol primario
    acc2 = OwnerVoteAccumulator(primary="s9_tile", presence_surface="s9_tile")
    acc2.mark_present("s9_tile")
    assert acc2.is_libre() is False
