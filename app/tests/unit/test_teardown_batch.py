"""Lógica de la tanda de desmontaje — reconciliación entre el censo de tildes y el contador.

`TeardownBatch` es deliberadamente PURO: no toca OpenCV, ni OCR, ni Qt. Todo lo que decide se
prueba con tuplas. Es donde vive la parte del feature que no se puede verificar mirando una
captura: qué pasa cuando el usuario clickea más rápido de lo que el OCR lee, cuando scrollea,
cuando cancela, o cuando el contador sale ilegible.

**La regla de atribución.** El censo y el parseo del panel salen del MISMO frame, así que un
delta de exactamente una celda (con el contador confirmándolo) prueba que ese click es el único
que ocurrió en la ventana ⇒ el panel DETAIL está mostrando ese disco. Cualquier delta mayor, o
mezclado, significa que se perdieron clicks: se declara el hueco y no se atribuye nada. Perder
stats es aceptable; atribuirle a un disco los stats de otro, no (RNF-02).

**La autoridad del conteo es el contador `N/300`, nunca el censo.** El censo solo ve el viewport.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.core.teardown_batch import TeardownBatch


@dataclass
class FakeDisc:
    """Sustituto de `DiscParsed` — la tanda lo consume por duck-typing."""
    set_name_raw: str = "Firmamento llameante"
    set_name_canon: str | None = None
    slot: int = 2
    nivel: int = 0
    rareza: str = "S"
    main_stat_canon: str | None = "ATK"
    main_stat_raw: str | None = "Ataque"
    main_valor: float | None = 79.0
    main_unidad: str | None = "flat"
    subs: list = field(default_factory=list)
    confianza_global: float = 0.95
    notas: list = field(default_factory=list)


def _batch() -> TeardownBatch:
    b = TeardownBatch()
    b.ensure_open(ts=0.0)
    return b


# --- Alta: el caso normal ------------------------------------------------------------------

def test_una_alta_confirmada_por_el_contador_pide_el_detalle():
    b = _batch()
    b.observe(tildes=frozenset(), counter=0, scroll=0.1, ts=1.0)
    d = b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=2.0)
    assert d.cell_a_capturar == (0, 0)
    b.attach((0, 0), FakeDisc())
    assert b.declarado == 1 and len(b.capturados) == 1 and b.faltantes == 0


def test_un_tilde_nuevo_sin_subida_del_contador_no_se_atribuye():
    """Guarda anti-scroll: un tilde que ENTRA al viewport al scrollear no es un click. Si se
    atribuyera, se le pegarían los stats del disco que esté en el panel en ese momento."""
    b = _batch()
    b.observe(tildes=frozenset(), counter=5, scroll=0.1, ts=1.0)
    d = b.observe(tildes=frozenset({(0, 0)}), counter=5, scroll=0.1, ts=2.0)
    assert d.cell_a_capturar is None
    assert b.capturados == {}


def test_dos_altas_en_un_ciclo_declaran_hueco_y_no_atribuyen():
    """El usuario clickeó más rápido que la cadencia. Se sabe CUÁNTOS (el contador) pero no
    cuáles ⇒ hueco declarado, cero atribución."""
    b = _batch()
    b.observe(tildes=frozenset(), counter=0, scroll=0.1, ts=1.0)
    d = b.observe(tildes=frozenset({(0, 0), (0, 1)}), counter=2, scroll=0.1, ts=2.0)
    assert d.cell_a_capturar is None
    assert b.declarado == 2 and len(b.capturados) == 0 and b.faltantes == 2


def test_alta_y_baja_simultaneas_son_ambiguas():
    """Marcar uno y desmarcar otro en el mismo ciclo deja el contador igual: no se puede saber
    cuál mostró el panel ⇒ no se atribuye ni se borra a ciegas."""
    b = _batch()
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), FakeDisc())
    d = b.observe(tildes=frozenset({(0, 1)}), counter=1, scroll=0.1, ts=2.0)
    assert d.cell_a_capturar is None
    assert any("ambig" in a.lower() for a in b.avisos), b.avisos


# --- Baja: solo con evidencia del contador -------------------------------------------------

def test_baja_confirmada_por_el_contador_quita_el_disco():
    b = _batch()
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), FakeDisc())
    b.observe(tildes=frozenset(), counter=0, scroll=0.1, ts=2.0)
    assert b.capturados == {} and b.declarado == 0


def test_baja_sin_bajar_el_contador_no_borra_nada():
    """Un tilde que DESAPARECE del viewport por scroll no es un destilde. Sin evidencia del
    contador no se borra un registro ya logrado."""
    b = _batch()
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), FakeDisc())
    b.observe(tildes=frozenset(), counter=1, scroll=0.5, ts=2.0)
    assert len(b.capturados) == 1, "se borró un disco sin evidencia"


# --- Scroll ---------------------------------------------------------------------------------

def test_el_scroll_no_genera_eventos_y_marca_el_aviso():
    b = _batch()
    b.observe(tildes=frozenset({(0, 0)}), counter=3, scroll=0.10, ts=1.0)
    d = b.observe(tildes=frozenset({(2, 4)}), counter=3, scroll=0.60, ts=2.0)
    assert d.cell_a_capturar is None
    assert any("scroll" in a.lower() for a in b.avisos), b.avisos


def test_los_huecos_se_atribuyen_al_viewport_si_hubo_scroll():
    b = _batch()
    b.observe(tildes=frozenset(), counter=0, scroll=0.10, ts=1.0)
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.10, ts=2.0)
    b.attach((0, 0), FakeDisc())
    b.observe(tildes=frozenset({(0, 0)}), counter=4, scroll=0.55, ts=3.0)   # scroll + 3 más
    res = b.commit(materiales=[("Disco original", 4)], ts=4.0)
    motivos = {h["motivo"] for h in res["huecos"]}
    assert "fuera_de_viewport" in motivos, res["huecos"]


# --- Selección masiva -----------------------------------------------------------------------

def test_un_salto_grande_marca_modo_masiva_y_avisa():
    """No se usa hoy, pero al distribuir la app otro usuario puede apretar "Descarte
    inteligente" y llevarse 30 discos sin que se lea ni un detalle."""
    b = _batch()
    b.observe(tildes=frozenset(), counter=0, scroll=0.1, ts=1.0)
    b.observe(tildes=frozenset({(r, c) for r in range(4) for c in range(8)}), counter=31,
              scroll=0.1, ts=2.0)
    assert b.modo in ("masiva", "mixto")
    assert any("masiva" in a.lower() for a in b.avisos), b.avisos
    assert b.faltantes == 31


# --- Contador ilegible ----------------------------------------------------------------------

def test_contador_ilegible_no_se_sustituye_por_el_censo():
    """RNF-02. El censo subcuenta cuando hay scroll: usarlo como conteo sería afirmar un número
    que no se midió."""
    b = _batch()
    b.observe(tildes=frozenset({(0, 0), (0, 1)}), counter=None, scroll=0.1, ts=1.0)
    assert b.declarado is None
    assert any("contador" in a.lower() for a in b.avisos), b.avisos


def test_sin_contador_no_se_atribuye():
    b = _batch()
    b.observe(tildes=frozenset(), counter=None, scroll=0.1, ts=1.0)
    d = b.observe(tildes=frozenset({(0, 0)}), counter=None, scroll=0.1, ts=2.0)
    assert d.cell_a_capturar is None


# --- Cancelar / reiniciar -------------------------------------------------------------------

def test_contador_en_cero_limpia_las_atribuciones():
    """Cubre los dos casos con una sola regla: "Cancelar selección" y entrar de nuevo a la
    pantalla. En ambos no hay nada marcado, así que lo capturado ya no corresponde."""
    b = _batch()
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), FakeDisc())
    b.observe(tildes=frozenset(), counter=0, scroll=0.1, ts=2.0)
    assert b.capturados == {} and b.declarado == 0 and not b.committed


# --- Commit ---------------------------------------------------------------------------------

def test_commit_devuelve_el_registro_y_es_idempotente():
    b = _batch()
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), FakeDisc())
    r1 = b.commit(materiales=[("Disco original de grado S", 1)], ts=2.0)
    assert r1 is not None and r1["conteo"]["declarado"] == 1 and len(r1["discos"]) == 1
    assert b.committed
    assert b.commit(materiales=[("Disco original", 1)], ts=3.0) is None, "commiteó dos veces"


def test_commit_corrobora_con_el_material_pero_no_lo_usa_como_fuente():
    """La cantidad del primer material es un oráculo INDEPENDIENTE. La evidencia de los fixtures
    es contradictoria (la previsualización de Ejemplo_3 dice 7 y el "Obtenido" de Ejemplo_7 dice
    1), así que se registra y se compara — nunca reemplaza al contador."""
    b = _batch()
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), FakeDisc())
    r = b.commit(materiales=[("Disco original", 9)], ts=2.0)
    assert r["conteo"]["declarado"] == 1, "el material pisó al contador"
    assert r["conteo"]["material_primero"] == 9
    assert r["conteo"]["corroborado"] is False


def test_commit_sin_nada_declarado_no_produce_registro():
    b = _batch()
    b.observe(tildes=frozenset(), counter=0, scroll=0.1, ts=1.0)
    assert b.commit(materiales=[], ts=2.0) is None


def test_drop_cierra_sin_registro():
    b = _batch()
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), FakeDisc())
    b.drop("abandonada")
    assert not b.abierta and not b.committed


# --- El registro ----------------------------------------------------------------------------

def test_el_registro_guarda_valores_ademas_de_la_identidad():
    """En Nivel 0 todos los rolls son 0, así que la identidad canónica colapsa a
    (set, slot, main, nombres de substat) — y la mayoría de lo que se desmonta es Nivel 0. Sin
    los VALORES, el futuro script de baja no podría distinguir dos discos gemelos."""
    from types import SimpleNamespace
    sub = SimpleNamespace(nombre_canon="DEF%", nombre_raw="Defensa", valor=4.8,
                          unidad="%", rolls=0, confianza=1.0)
    b = _batch()
    b.observe(tildes=frozenset({(1, 1)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((1, 1), FakeDisc(subs=[sub]))
    r = b.commit(materiales=[], ts=2.0)
    disco = r["discos"][0]
    assert disco["main"]["valor"] == 79.0
    assert disco["subs"][0]["valor"] == 4.8 and disco["subs"][0]["unidad"] == "%"
    assert "identidad" in disco and disco["identidad"]["slot"] == 2
    assert disco["celda"] == {"fila": 1, "col": 1}


def test_el_registro_declara_el_esquema_y_los_faltantes():
    b = _batch()
    b.observe(tildes=frozenset(), counter=0, scroll=0.1, ts=1.0)
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=2.0)
    b.attach((0, 0), FakeDisc())
    b.observe(tildes=frozenset({(0, 0), (0, 1), (0, 2)}), counter=3, scroll=0.1, ts=3.0)
    r = b.commit(materiales=[("Disco original", 3)], ts=4.0)
    assert r["schema"] == "desmontaje/1"
    assert r["conteo"] == {"declarado": 3, "capturados": 1, "faltantes": 2,
                           "fuente_declarado": "contador_header",
                           "material_primero": 3, "corroborado": True}
