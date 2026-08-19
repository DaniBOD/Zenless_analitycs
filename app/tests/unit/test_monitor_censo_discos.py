"""Cableado del censo de discos en el monitor.

Tres cosas que tienen que pasar en una pasada por el inventario:

1. la corrida se **abre sola** al entrar a S9 — hay un disparador claro (estás en el inventario) y
   no hace falta pedirle al usuario que lo declare, a diferencia del roster;
2. el contador del header ancla el denominador **con cadencia propia**, no en cada frame (RNF-06:
   es un OCR y el handler corre continuo);
3. cada disco emitido entra al censo **una vez**, con la misma identidad que usa el dedup de
   emisión — dos definiciones de "mismo disco" en el mismo flujo sería una de más.

Y el cierre reporta cobertura contra el contador, que es lo que el censo del roster no puede hacer.
"""
from __future__ import annotations


class _Ocr:
    def text(self, *a, **k):
        return ("", 0.0)

    def text_with_bboxes(self, *a, **k):
        return []


def _mon(**kw):
    import app.core.monitor as m
    return m.Monitor(ocr=_Ocr(), detector=None, on_disc=kw.pop("on_disc", lambda *_: None), **kw)


def _disco(n: int, *, libre: bool = False, dueno: str | None = None):
    from app.core.parser_disc import DiscParsed, SubstatParsed
    d = DiscParsed(
        set_name_raw="Monarca del Pináculo", set_name_canon="Monarca del Pináculo",
        slot=(n % 6) + 1, main_stat_raw="DEF", main_stat_canon="DEF", main_valor=184.0,
        main_unidad="flat", nivel=15, rareza="S",
        subs=[SubstatParsed(f"ATK{n}", f"ATK{n}", 38.0, "flat", 1, 0.95)],
        confianza_global=0.95,
    )
    d.equip_libre = libre
    if dueno:
        d.agente_asignado_nombre = dueno
    return d


class _Estado:
    code = "S9"
    slot = None


# --- apertura y ancla -------------------------------------------------------------------------

def test_la_corrida_se_abre_sola_al_censar_el_primer_disco():
    """El roster necesita que el usuario declare el cierre porque no hay contador. Acá sí lo hay,
    así que la corrida puede arrancar sola sin quedarse sin forma de saber si terminó."""
    mon = _mon()
    assert mon.censo_discos is None or not mon.censo_discos.abierta
    mon._censar_disco(_disco(1), _Estado())
    assert mon.censo_discos.abierta
    assert mon.censo_discos.registrados == 1


def test_el_contador_ancla_el_denominador(monkeypatch):
    import app.core.monitor as m
    monkeypatch.setattr(m, "parse_s9_header_counter", lambda f, o: 339)
    mon = _mon()
    mon._anclar_contador_s9(object(), ahora=100.0)
    assert mon.censo_discos.total == 339


def test_el_contador_NO_se_lee_en_cada_frame(monkeypatch):
    """Es un OCR dentro de un handler continuo. Leerlo por frame es justo lo que RNF-06 prohíbe;
    el denominador cambia poquísimo y no necesita esa frecuencia."""
    import app.core.monitor as m
    llamadas = []
    monkeypatch.setattr(m, "parse_s9_header_counter",
                        lambda f, o: (llamadas.append(1), 339)[1])
    mon = _mon()
    for i in range(30):
        mon._anclar_contador_s9(object(), ahora=100.0 + i * 0.1)   # 3 s de frames
    assert len(llamadas) == 1, f"leyó el header {len(llamadas)} veces en 3 s"


def test_pasada_la_cadencia_vuelve_a_leer(monkeypatch):
    """Tiene que releer alguna vez: si farmeás o desmontás durante la pasada, el denominador se
    mueve y quedarse con el viejo daría una cobertura falsa."""
    import app.core.monitor as m
    vals = iter([339, 341])
    monkeypatch.setattr(m, "parse_s9_header_counter", lambda f, o: next(vals, 341))
    mon = _mon()
    mon._anclar_contador_s9(object(), ahora=100.0)
    mon._anclar_contador_s9(object(), ahora=100.0 + m._S9_CONTADOR_PERIODO_S + 0.1)
    assert mon.censo_discos.total == 341
    assert mon.censo_discos.avisos, "un cambio de denominador no puede pasar en silencio"


def test_un_contador_ilegible_no_rompe_la_corrida(monkeypatch):
    import app.core.monitor as m
    monkeypatch.setattr(m, "parse_s9_header_counter", lambda f, o: None)
    mon = _mon()
    mon._anclar_contador_s9(object(), ahora=100.0)
    assert mon.censo_discos.total is None
    assert mon.censo_discos.abierta, "sin ancla el censo sigue contando; sólo no puede medir"


# --- el conteo --------------------------------------------------------------------------------

def test_cada_disco_cuenta_una_sola_vez():
    mon = _mon()
    for _ in range(4):
        mon._censar_disco(_disco(1), _Estado())
    assert mon.censo_discos.registrados == 1


def test_discos_distintos_suman_y_se_separan_libres_de_equipados():
    mon = _mon()
    mon._censar_disco(_disco(1, dueno="Ellen"), _Estado())
    mon._censar_disco(_disco(2, libre=True), _Estado())
    mon._censar_disco(_disco(3), _Estado())
    c = mon.censo_discos
    assert (c.registrados, c.con_dueno, c.libres, c.sin_resolver) == (3, 1, 1, 1)


def test_usa_la_MISMA_identidad_que_el_dedup_de_emision():
    """Dos definiciones de 'mismo disco' en el mismo flujo sería una de más: el censo contaría
    distinto que la persistencia y ninguna de las dos cuentas sería verificable."""
    mon = _mon()
    d = _disco(7, dueno="Ellen")
    mon._censar_disco(d, _Estado())
    assert list(mon.censo_discos._vistos) == [mon._disc_identity(d)]


# --- cierre -----------------------------------------------------------------------------------

def test_cerrar_reporta_cobertura_contra_el_contador(monkeypatch):
    import app.core.monitor as m
    monkeypatch.setattr(m, "parse_s9_header_counter", lambda f, o: 5)
    mon = _mon()
    mon._anclar_contador_s9(object(), ahora=100.0)
    for i in range(3):
        mon._censar_disco(_disco(i), _Estado())
    r = mon.cerrar_censo_discos()
    assert r is not None
    assert r["registrados"] == 3 and r["total_pantalla"] == 5 and r["faltan"] == 2
    assert r["motivo_incompleto"], "una pasada corta tiene que decir que quedó corta"
    assert not mon.censo_discos.abierta


def test_cerrar_sin_corrida_abierta_no_explota():
    assert _mon().cerrar_censo_discos() is None


def test_F8_cierra_el_censo_de_discos_si_es_el_que_esta_abierto():
    """La hotkey es una sola. Con el censo del roster cerrado (o inexistente), F8 tiene que cerrar
    el de discos en vez de responder 'no hay ninguna pasada abierta'."""
    mon = _mon()
    mon._censar_disco(_disco(1), _Estado())
    mon.cerrar_censo()
    assert not mon.censo_discos.abierta


def test_observar_despues_de_cerrar_no_reabre_la_corrida():
    """Volver al inventario después de cerrar no debe empezar a contar sobre lo ya reportado sin
    que se note — el censo del roster tuvo justo ese problema (QA 2026-08-17)."""
    mon = _mon()
    mon._censar_disco(_disco(1), _Estado())
    mon.cerrar_censo_discos()
    mon._censar_disco(_disco(2), _Estado())
    assert mon.censo_discos.registrados == 1


# --- la autoridad de la identidad (bug de campo 2026-08-18) -----------------------------------

class _Res:
    """SyncResult mínimo: al censo sólo le importa `disc_id`, que es la fila que la persistencia
    decidió tocar."""
    def __init__(self, disc_id, trigger="s17_insert"):
        self.disc_id, self.trigger = disc_id, trigger


def test_el_MISMO_disco_con_el_set_leido_distinto_cuenta_UNA_vez():
    """El bug medido en vivo. El OCR lee el nombre del set inconsistente entre pasadas —
    `Firmamento Ilameante` (I mayúscula) vs `Firmamento llameante` (l minúscula)— y el
    normalizador NO los une, porque son caracteres distintos.

    El resolvedor difuso de la persistencia sí los une: devolvió `libre_update id=7`, o sea "este
    disco ya lo tenía". El censo, calculando su propia identidad sobre el string, lo contó como
    nuevo: 8/405 con 7 filas en la DB.

    Quien decide si un disco es nuevo es **la persistencia**, que compara contra el `set_id`
    resuelto. El censo cuenta esa decisión; no la recalcula."""
    mon = _mon()
    d1 = _disco(1); d1.set_name_canon = "Firmamento Ilameante"
    d2 = _disco(1); d2.set_name_canon = "Firmamento llameante"
    mon._censar_disco(d1, _Estado(), _Res(7))
    mon._censar_disco(d2, _Estado(), _Res(7, "libre_update"))
    assert mon.censo_discos.registrados == 1, "es el mismo disco: misma fila en la DB"


def test_dos_filas_distintas_son_dos_discos():
    mon = _mon()
    mon._censar_disco(_disco(1), _Estado(), _Res(7))
    mon._censar_disco(_disco(2), _Estado(), _Res(8))
    assert mon.censo_discos.registrados == 2


def test_sin_persistencia_cae_a_la_identidad_parseada_y_lo_MARCA():
    """En read-only no hay fila que citar, así que el censo vuelve a la identidad del parser — que
    es justamente la que puede desdoblarse. Sigue contando (una pasada en seco tiene que poder
    medirse) pero deja dicho cuántos conteos NO están confirmados contra la DB, en vez de
    presentar un número con más autoridad de la que tiene."""
    mon = _mon()
    mon._censar_disco(_disco(1), _Estado(), None)
    c = mon.censo_discos
    assert c.registrados == 1
    assert c.provisorios == 1


def test_un_disco_confirmado_no_cuenta_como_provisorio():
    mon = _mon()
    mon._censar_disco(_disco(1), _Estado(), _Res(7))
    assert mon.censo_discos.provisorios == 0


def test_un_resultado_sin_fila_real_no_se_toma_como_autoridad():
    """`disc_id=-1` es lo que devuelve el camino de read-only: no es una fila, es un placeholder.
    Tomarlo como identidad colapsaría TODOS los discos en uno."""
    mon = _mon()
    mon._censar_disco(_disco(1), _Estado(), _Res(-1, "readonly"))
    mon._censar_disco(_disco(2), _Estado(), _Res(-1, "readonly"))
    assert mon.censo_discos.registrados == 2
    assert mon.censo_discos.provisorios == 2
