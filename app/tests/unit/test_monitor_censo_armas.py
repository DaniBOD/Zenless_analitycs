"""Cableado del censo de W-Engines en el monitor.

Espejo de `test_monitor_censo_discos.py`, porque el flujo es el mismo: el inventario de armas
también trae denominador en pantalla (`Amplificadores [57/2000]`), así que la corrida se abre sola
y sabe cuánto le falta.

Lo específico de armas, que es donde se puede meter la pata:

1. **la capacidad es el ancla** — leer este header con la de discos no devuelve nada, y eso es lo
   que impide que una pantalla se haga pasar por la otra;
2. **la identidad es la FILA que la persistencia tocó**, no un recálculo. Acá pesa más que en
   discos: la identidad del parser de un arma colapsa las copias SIEMPRE, no de casualidad;
3. **`inv_id = -1`** es el placeholder del camino read-only y no es una fila.
"""
from __future__ import annotations


class _Ocr:
    def text(self, *a, **k):
        return ("", 0.0)

    def text_with_bboxes(self, *a, **k):
        return []


def _mon(**kw):
    import app.core.monitor as m
    return m.Monitor(ocr=_Ocr(), detector=None, on_disc=lambda *_: None, **kw)


def _arma(nombre="Engranaje infernal", *, dueno=None, nivel=60, refin=2, en_catalogo=True):
    from app.core.parser_weapon_s26 import WeaponParsed
    return WeaponParsed(
        nombre_raw=nombre, nombre_canon=nombre if en_catalogo else None,
        nivel=nivel, nivel_max=60, atk_base=684, rareza="S", refinamiento=refin,
        dueno=dueno, confianza=0.95,
    )


class _Res:
    """Lo que devuelve `WeaponSyncer.persist_s30_weapon`."""

    def __init__(self, inv_id):
        self.inv_id = inv_id


def _contador(monkeypatch, valor):
    import app.core.parser_inventory_header as ph
    monkeypatch.setattr(ph, "parse_inventory_counter", lambda f, o, cap: valor)


# --- apertura y ancla ---------------------------------------------------------------------------

def test_la_corrida_se_abre_sola_al_censar_la_primera_arma():
    mon = _mon()
    assert mon.censo_armas is None or not mon.censo_armas.abierta
    mon._censar_arma(_arma(dueno="Jane"), _Res(7))
    assert mon.censo_armas.abierta
    assert mon.censo_armas.registrados == 1
    assert mon.censo_armas.entidad == "armas"


def test_el_contador_ancla_el_denominador(monkeypatch):
    _contador(monkeypatch, 57)
    mon = _mon()
    mon._anclar_contador_s30(object(), ahora=100.0)
    assert mon.censo_armas.total == 57


def test_el_contador_NO_se_lee_en_cada_frame(monkeypatch):
    """RNF-06: es un OCR dentro de un handler continuo. Sin cadencia propia, una pasada de 57
    tiles pagaría el OCR del header en cada frame."""
    import app.core.monitor as m
    llamadas = []
    import app.core.parser_inventory_header as ph
    monkeypatch.setattr(ph, "parse_inventory_counter",
                        lambda f, o, cap: (llamadas.append(cap), 57)[1])
    mon = _mon()
    mon._anclar_contador_s30(object(), ahora=100.0)
    mon._anclar_contador_s30(object(), ahora=100.0 + m._INV_CONTADOR_PERIODO_S / 2)
    assert len(llamadas) == 1, "se releyó antes de que pasara el período"
    mon._anclar_contador_s30(object(), ahora=100.0 + m._INV_CONTADOR_PERIODO_S + 0.1)
    assert len(llamadas) == 2


def test_el_contador_de_armas_no_lee_el_header_de_discos(monkeypatch):
    """⚠️ La capacidad ES el ancla. Si el camino de armas pasara 3000, anclaría contra el
    inventario equivocado y la cobertura sería un número sin sentido, en silencio."""
    from app.core.parser_inventory_header import CAPACIDAD_ARMAS
    caps = []
    import app.core.parser_inventory_header as ph
    monkeypatch.setattr(ph, "parse_inventory_counter",
                        lambda f, o, cap: (caps.append(cap), 57)[1])
    _mon()._anclar_contador_s30(object(), ahora=100.0)
    assert caps == [CAPACIDAD_ARMAS]


def test_un_contador_ilegible_no_borra_el_ancla(monkeypatch):
    import app.core.monitor as m
    import app.core.parser_inventory_header as ph
    monkeypatch.setattr(ph, "parse_inventory_counter", lambda f, o, cap: 57)
    mon = _mon()
    mon._anclar_contador_s30(object(), ahora=100.0)
    monkeypatch.setattr(ph, "parse_inventory_counter", lambda f, o, cap: None)
    mon._anclar_contador_s30(object(), ahora=100.0 + m._INV_CONTADOR_PERIODO_S + 0.1)
    assert mon.censo_armas.total == 57


# --- identidad: la fila que tocó la persistencia -------------------------------------------------

def test_usa_la_fila_como_identidad():
    """Dos lecturas distintas del OCR sobre la MISMA fila cuentan una sola vez."""
    mon = _mon()
    mon._censar_arma(_arma("Engranaje infernal", dueno="Jane"), _Res(7))
    mon._censar_arma(_arma("Engranaje infernaI", dueno="Jane"), _Res(7))   # I vs l
    assert mon.censo_armas.registrados == 1
    assert mon.censo_armas.provisorios == 0


def test_un_resultado_sin_fila_real_no_es_autoridad():
    """⚠️ `inv_id = -1` es el placeholder de readonly. Tomarlo como identidad metería TODAS las
    armas en un solo cubo y el censo reportaría 1 de 57."""
    mon = _mon()
    mon._censar_arma(_arma("Engranaje infernal"), _Res(-1))
    mon._censar_arma(_arma("Aguijón agudo"), _Res(-1))
    assert mon.censo_armas.registrados == 2
    assert mon.censo_armas.provisorios == 2


def test_sin_persistencia_cae_a_la_identidad_del_parser_y_lo_declara():
    mon = _mon()
    mon._censar_arma(_arma("Engranaje infernal"), None)
    assert mon.censo_armas.registrados == 1
    assert mon.censo_armas.provisorios == 1


def test_lo_que_esta_fuera_del_catalogo_se_cuenta_aparte():
    mon = _mon()
    mon._censar_arma(_arma("Cilindro neumático", en_catalogo=False), None)
    assert mon.censo_armas.registrados == 1
    assert mon.censo_armas.fuera_de_catalogo == 1


def test_el_dueno_viaja_al_censo():
    mon = _mon()
    mon._censar_arma(_arma(dueno="Jane"), _Res(7))
    mon._censar_arma(_arma("Aguijón agudo"), _Res(8))
    assert mon.censo_armas.con_dueno == 1
    assert mon.censo_armas.sin_resolver == 1


def test_el_censo_no_afirma_libre_ninguna_arma():
    """S30 no puede afirmar ausencia de dueño (mide 8/10 y el que falla dice LIBRE de un arma que
    es de Grace). Un arma sin nombrar va a `sin_resolver`, que es lo honesto — no a `libres`."""
    mon = _mon()
    mon._censar_arma(_arma(), _Res(7))
    assert mon.censo_armas.libres == 0
    assert mon.censo_armas.sin_resolver == 1


# --- cierre --------------------------------------------------------------------------------------

def test_el_cierre_reporta_cobertura_contra_el_contador(monkeypatch):
    _contador(monkeypatch, 3)
    mon = _mon()
    mon._anclar_contador_s30(object(), ahora=100.0)
    mon._censar_arma(_arma("Engranaje infernal", dueno="Jane"), _Res(7))
    r = mon.cerrar_censo_armas()
    assert r["entidad"] == "armas"
    assert r["registrados"] == 1 and r["total_pantalla"] == 3 and r["faltan"] == 2
    assert "W-Engine" in r["motivo_incompleto"]


def test_no_se_reabre_despues_de_cerrada():
    """Volver a la pantalla tras cerrar no puede empezar a contar sobre lo ya reportado."""
    mon = _mon()
    mon._censar_arma(_arma(dueno="Jane"), _Res(7))
    mon.cerrar_censo_armas()
    mon._censar_arma(_arma("Aguijón agudo", dueno="Grace"), _Res(8))
    assert mon.censo_armas.registrados == 1


def test_cerrar_sin_pasada_abierta_no_revienta():
    assert _mon().cerrar_censo_armas() is None


def test_f8_cierra_los_dos_inventarios():
    """La hotkey es una sola y hay tres censos. Los de inventario van primero: tienen contador, así
    que cerrarlos produce un número verificable."""
    mon = _mon()
    mon._censar_arma(_arma(dueno="Jane"), _Res(7))
    from app.core.parser_disc import DiscParsed, SubstatParsed

    class _Estado:
        code = "S9"
        slot = None

    disco = DiscParsed(
        set_name_raw="Monarca del Pináculo", set_name_canon="Monarca del Pináculo", slot=1,
        main_stat_raw="DEF", main_stat_canon="DEF", main_valor=184.0, main_unidad="flat",
        nivel=15, rareza="S",
        subs=[SubstatParsed("ATK", "ATK", 38.0, "flat", 1, 0.95)], confianza_global=0.95,
    )
    mon._censar_disco(disco, _Estado())
    assert mon.censo_discos.abierta and mon.censo_armas.abierta
    mon.cerrar_censo()
    assert not mon.censo_discos.abierta
    assert not mon.censo_armas.abierta
