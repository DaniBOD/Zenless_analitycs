"""Tests del contrato REUSABLE de `app/core/badge_surface.py` (5R.L.8 / B1).

`BadgeSurface` = crop_fn + AvatarMatcher + librería propia + canonicalización al
roster + gating de persistencia + presencia estructural, empaquetados para que una
pantalla nueva (S9/S23) declare su superficie sin re-implementar el boilerplate.
`AgentIdentifier` compone tres (row/grid/detail) manteniendo su API histórica.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.avatar_descriptor import AvatarMatcher
from app.core.badge_surface import BadgeOutcome, BadgeSurface

REPO = Path(__file__).resolve().parents[3]
_REFS = REPO / "app" / "resources" / "avatar_refs"


def _cara(name="Ellen.png"):
    img = cv2.imread(str(_REFS / name))
    assert img is not None
    return img


def _surface(tmp_path, **kw):
    kw.setdefault("crop_fn", lambda frame: frame)      # la "pantalla" ya entrega el crop
    kw.setdefault("matcher", AvatarMatcher())
    kw.setdefault("library_path", tmp_path / "surf.npz")
    kw.setdefault("canonicalize", lambda n: {"lucia": "Lucía"}.get(n.lower(), n))
    return BadgeSurface(name="test_surf", **kw)


def test_learn_canonicaliza_y_persiste(tmp_path):
    """learn() canonicaliza el label por el roster ANTES de guardar — la lección del
    bug 2026-06-18 (claves en minúscula → prune_to_roster vació la librería)."""
    s = _surface(tmp_path)
    assert s.learn(_cara(), "Lucia") is True
    assert "Lucía" in s.matcher._refs                  # clave canónica, no el label crudo
    assert (tmp_path / "surf.npz").exists()            # persistida
    # canonicalize devuelve None → label fuera del roster → NO aprende
    s2 = _surface(tmp_path, canonicalize=lambda n: None,
                  library_path=tmp_path / "s2.npz", matcher=AvatarMatcher())
    assert s2.learn(_cara(), "Permiso") is False
    assert not s2.matcher._refs


def test_learn_respeta_el_gate_de_persistencia(tmp_path):
    """persist_gate=False (readonly sin modo cosecha) → learn inerte, no escribe."""
    s = _surface(tmp_path, persist_gate=lambda: False)
    assert s.learn(_cara(), "Ellen") is False
    assert not s.matcher._refs and not (tmp_path / "surf.npz").exists()


def test_sample_devuelve_outcome_completo(tmp_path):
    """sample(frame) = crop + match + presencia en un paso. Con crop y match sobre el
    guard → nombre; sin crop → ausente."""
    s = _surface(tmp_path)
    s.learn(_cara(), "Ellen")
    out = s.sample(_cara())
    assert isinstance(out, BadgeOutcome)
    assert out.present is True and out.name == "Ellen" and out.conf >= 0.80
    # crop_fn devuelve None (no localizó) → ausente, sin naming
    s_no = _surface(tmp_path, crop_fn=lambda f: None,
                    library_path=tmp_path / "s3.npz", matcher=AvatarMatcher())
    out2 = s_no.sample(_cara())
    assert out2.present is False and out2.name is None and out2.crop is None


def test_sample_presencia_estructural_independiente_del_naming(tmp_path):
    """presence_fn (p.ej. cara-vs-texto del detalle) manda sobre la presencia aunque
    el matcher no pueda nombrar: el caso Jane a nivel superficie."""
    s = _surface(tmp_path, presence_fn=lambda crop: True)   # clasificador dice: es cara
    out = s.sample(_cara("Nicole.png"))                     # librería vacía → sin nombre
    assert out.present is True and out.name is None
    s2 = _surface(tmp_path, presence_fn=lambda crop: False,  # clasificador dice: texto
                  library_path=tmp_path / "s4.npz", matcher=AvatarMatcher())
    out2 = s2.sample(_cara())
    assert out2.present is False


def test_guard_de_naming_se_abstiene_bajo_umbral(tmp_path):
    """Un match bajo el guard devuelve name=None (RNF-02) pero conserva conf/margin."""
    s = _surface(tmp_path)
    s.learn(_cara(), "Ellen")
    out = s.sample(_cara("Nicole.png"))                 # otra cara: sim < guard
    assert out.name is None
    assert out.conf < 0.80 or out.rejected


# ---- Dedup por contenido (spec 2026-08-11) ----------------------------------------------
#
# Medido ese día: `row` tenía 365 refs pero 62 imágenes distintas, con 40 de 50 PJs mostrando
# CUATRO copias de la misma foto. La causa es que `learn_s17_detail` se llama una vez por disco y
# el avatar del panel no cambia con el disco seleccionado. Un clon no agrega discriminación —la
# distancia de clase es un `min`— y gasta una ranura; con el cupo lleno, el desalojo FIFO empieza
# a tirar las refs DIVERSAS para meter más copias de lo mismo.


def test_el_mismo_crop_no_entra_dos_veces(tmp_path):
    s = _surface(tmp_path)
    assert s.learn(_cara(), "Ellen") is True
    assert s.learn(_cara(), "Ellen") is False
    assert len(s.matcher._refs["Ellen"]) == 1


def test_una_cara_distinta_del_mismo_pj_si_entra(tmp_path):
    """El dedup no puede castigar variación real: dos refs genuinas del mismo PJ están a
    0.098-0.229, muy por encima del umbral de clon (0.03)."""
    s = _surface(tmp_path)
    s.learn(_cara(), "Ellen")
    assert s.learn(_cara("Nicole.png"), "Ellen") is True
    assert len(s.matcher._refs["Ellen"]) == 2


def test_el_dedup_es_dentro_de_la_clase(tmp_path):
    """Dos PJs pueden tener caras parecidas —Billy y Billy Estelar están a 0.155— y eso no es
    motivo para no aprender: la comparación es SOLO contra las refs del mismo nombre."""
    s = _surface(tmp_path)
    assert s.learn(_cara(), "Ellen") is True
    assert s.learn(_cara(), "Nicole") is True
    assert len(s.matcher._refs["Ellen"]) == 1 and len(s.matcher._refs["Nicole"]) == 1


def test_un_clon_no_reescribe_el_archivo(tmp_path):
    """`learn` persiste en CADA cosecha reescribiendo el .npz entero — el del row pesa 23 MB.
    Un clon no puede pagar ese costo para no agregar nada (RNF-06)."""
    import hashlib
    s = _surface(tmp_path)
    s.learn(_cara(), "Ellen")
    npz = tmp_path / "surf.npz"
    antes = hashlib.sha256(npz.read_bytes()).hexdigest()
    assert s.learn(_cara(), "Ellen") is False
    assert hashlib.sha256(npz.read_bytes()).hexdigest() == antes


@pytest.mark.parametrize("surface", ["row", "grid", "detail"])
def test_las_tres_superficies_dedupean(tmp_path, surface):
    """El dedup vive en el cuello común, así que lo heredan las tres — y las pantallas nuevas
    que registren la suya (S9, S23) sin que nadie tenga que acordarse."""
    from app.core.agent_identifier import AgentIdentifier
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False)
    surf = ident.surfaces[surface]
    cara = _cara()
    assert surf.learn(cara, "Ellen") is True
    assert surf.learn(cara, "Ellen") is False
    assert len(surf.matcher._refs["Ellen"]) == 1


def test_load_merge_reincorpora_lo_persistido(tmp_path):
    s = _surface(tmp_path)
    s.learn(_cara(), "Ellen")
    fresh = _surface(tmp_path, matcher=AvatarMatcher())
    assert fresh.load() == 1
    assert "Ellen" in fresh.matcher._refs


# ---- Auto-restauración desde el baseline versionado --------------------------------------
#
# Las librerías viven en %LOCALAPPDATA%, que no se versiona, y se vaciaron dos veces: el detalle
# el 2026-07-28 (0 dueños en todas las pantallas) y el grid + row el 2026-07-31. La segunda pasó
# desapercibida porque el archivo del grid REAPARECÍA, regenerado con la semilla -ico: una
# librería de arte de comunidad no se abstiene, nombra mal con confianza 0.85.

def _baseline(tmp_path, name="Ellen"):
    """Un .npz versionado con una ref, para hacer de snapshot en audit/."""
    m = AvatarMatcher()
    m.add_reference(name, _cara())
    p = tmp_path / "baseline.npz"
    m.save(p)
    return p


def test_load_restaura_del_baseline_si_falta_la_libreria(tmp_path, caplog):
    import logging
    base = _baseline(tmp_path)
    lib = tmp_path / "runtime" / "surf.npz"              # no existe: subcarpeta incluida
    s = _surface(tmp_path, library_path=lib, baseline_path=base)
    with caplog.at_level(logging.WARNING, logger="app.core.badge_surface"):
        assert s.load() == 1
    assert lib.exists(), "la librería del runtime queda repuesta en disco, no solo en memoria"
    assert "Ellen" in s.matcher._refs
    assert any("NO ESTABA" in r.getMessage() for r in caplog.records), \
        "restaurar en silencio esconde justo el evento que hay que investigar"


def test_load_no_pisa_una_libreria_existente(tmp_path):
    """El baseline es una red de emergencia, no una fuente de verdad: si hay librería del
    runtime —aunque tenga menos refs que el snapshot— manda ella, porque contiene la cosecha
    posterior al snapshot."""
    base = _baseline(tmp_path, name="Ellen")
    s = _surface(tmp_path, matcher=AvatarMatcher())
    s.learn(_cara("Nicole.png"), "Nicole")               # crea la librería del runtime
    fresh = _surface(tmp_path, matcher=AvatarMatcher(), baseline_path=base)
    fresh.load()
    assert "Nicole" in fresh.matcher._refs
    assert "Ellen" not in fresh.matcher._refs


def test_load_sin_baseline_se_comporta_como_antes(tmp_path):
    s = _surface(tmp_path, library_path=tmp_path / "no_esta.npz")
    assert s.load() == 0                                 # sin baseline y sin librería: 0, sin romper


def test_coverage_reporta_la_clase_mas_flaca(tmp_path):
    """La cobertura se loguea al cargar porque el modo de falla de 2026-07-31 fue una librería
    PRESENTE pero degradada, y no había una sola línea que lo dijera."""
    s = _surface(tmp_path)
    assert s.coverage() == (0, 0, 0)
    s.learn(_cara(), "Ellen")
    s.learn(_cara("Nicole.png"), "Nicole")
    s.learn(_cara("Lucy.png"), "Nicole")
    assert s.coverage() == (2, 3, 1)                     # 2 clases, 3 refs, la más flaca tiene 1


def test_agent_identifier_expone_surfaces():
    """AgentIdentifier compone las 3 superficies históricas y las expone por nombre
    (la vía de entrada para consumidores nuevos)."""
    from app.core.agent_identifier import AgentIdentifier
    ident = AgentIdentifier(autoload=False)
    assert set(ident.surfaces) >= {"row", "grid", "detail"}
    assert ident.surfaces["grid"].matcher is ident._badge
    assert ident.surfaces["detail"].matcher is ident._detbadge
    assert ident.surfaces["row"].matcher is ident._row
