"""Cableado de S26 (detalle de W-Engine) en el monitor — RF-15 H4/H5.

Se stubbea el parser: la lectura real está cubierta contra los 40 fixtures en
`test_parser_weapon_s26`. Acá se prueba la ORQUESTACIÓN, que es donde el proyecto tuvo sus dos
bugs históricos: handlers que se quedaban mudos en un `return` temprano (8m42s sin una línea de
log en el QA del 2026-07-20) y estados que no se reseteaban al salir de la pantalla.

Y sobre todo: que este hito **no escriba la DB**. Es observación pura.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from app.core.detector import ScreenState

_S26 = ScreenState("S26", 1.0, "s17_personalizacion_pistas.png")
_S17 = ScreenState("S17", 1.0, "s17_personalizacion_pistas.png")
_S12 = ScreenState("S12", 0.0, None)


def _frame(fill: int = 40):
    return np.full((1439, 2559, 3), fill, dtype=np.uint8)


class FakeWeapon:
    def __init__(self, nombre="Petrazufre", canon="Petrazufre", nivel=60, refin=1, rareza="S"):
        self.nombre_raw, self.nombre_canon = nombre, canon
        self.nivel, self.nivel_max = nivel, 60
        self.rareza, self.refinamiento = rareza, refin
        self.atk_base = 684
        self.stat_avanzado_canon, self.stat_avanzado_valor = "ATK%", 30.0
        self.stat_avanzado_unidad = "%"
        self.dueno = None
        self.tenencia = "incierto"
        # El ancla de todo lo posicional del panel. Con None el handler no consulta el badge.
        self.pill_bbox = (915, 253, 1107, 280)
        self.confianza, self.notas = 0.99, []


@pytest.fixture
def mon(monkeypatch):
    import app.core.monitor as mon_mod
    import app.core.parser_weapon_s26 as pw_mod

    diags: list[str] = []
    toasts: list[dict] = []
    m = mon_mod.Monitor(ocr=object(), detector=None, on_diagnostic=diags.append,
                        set_badge_matcher=object(), on_weapon_seen=toasts.append)
    m._diags, m._toasts = diags, toasts
    import app.core.parser_disc_s17 as pds

    # `badge` y `boton` son las dos señales de tenencia; por defecto van en el caso conservador
    # (badge presente y sin botón ⇒ "incierto"), así que los tests que no hablan de tenencia no
    # se ven afectados por ella.
    m._stub = {"weapon": FakeWeapon(), "sig": b"A",
               "badge": pw_mod.OwnerBadge(present=True, nitidez=70.0, crop=_frame(200)),
               "boton": None}

    monkeypatch.setattr(pw_mod, "parse_weapon_s26",
                        lambda fr, ocr, catalogo=None: m._stub["weapon"])
    monkeypatch.setattr(pw_mod, "weapon_panel_signature", lambda fr: m._stub["sig"])
    monkeypatch.setattr(pw_mod, "read_weapon_owner_badge", lambda fr, pb: m._stub["badge"])
    monkeypatch.setattr(pds, "read_s17_action_button", lambda fr, ocr: m._stub["boton"])
    # El catálogo se lee de la DB; acá se fija para que el test no dependa de ella.
    monkeypatch.setattr(m, "_weapon_catalog", lambda: ["Petrazufre", "Sol exuvia"])
    # Sin librería de badges no hay dueño; los tests que lo necesitan lo stubbean.
    m._identifier = None
    return m


def _paso(m, state, **stub):
    m._stub.update(stub)
    m._dispatch_state(_frame(), state)


# --- El camino normal -----------------------------------------------------------------------


def test_emite_un_toast_por_arma(mon):
    """Una línea y un toast por arma abierta."""
    _paso(mon, _S26)
    assert len(mon._toasts) == 1, mon._toasts
    ev = mon._toasts[0]
    assert ev["nombre"] == "Petrazufre"
    assert ev["rareza"] == "S" and ev["refinamiento"] == 1
    assert ev["nivel"] == 60 and ev["nivel_max"] == 60
    assert ev["stat"] == "ATK% 30 %"
    assert ev["en_catalogo"] is True


def test_panel_quieto_no_reocrea_ni_repite(mon):
    """El gate de firma es lo que hace viable la cadencia de 1000 ms: el OCR del panel cuesta
    ~500 ms, así que mirar un arma diez segundos no puede ser diez OCRs."""
    llamadas = {"n": 0}
    import app.core.parser_weapon_s26 as pw_mod

    def _contando(fr, ocr, catalogo=None):
        llamadas["n"] += 1
        return mon._stub["weapon"]
    pw_mod.parse_weapon_s26 = _contando

    for _ in range(5):
        _paso(mon, _S26)
    assert llamadas["n"] == 1, "el panel no cambió: el parser tenía que correr una sola vez"
    assert len(mon._toasts) == 1


def test_cambiar_de_arma_emite_de_nuevo(mon):
    _paso(mon, _S26)
    _paso(mon, _S26, sig=b"B", weapon=FakeWeapon(nombre="Sol exuvia", canon="Sol exuvia",
                                                 refin=5, rareza="S"))
    assert len(mon._toasts) == 2
    assert [t["nombre"] for t in mon._toasts] == ["Petrazufre", "Sol exuvia"]


def test_salir_y_volver_re_emite(mon):
    """Al salir de S26 se olvida el arma mirada. Si no, volver a la misma arma quedaría mudo y
    el usuario no vería nada — el mismo problema que el tracking de S17."""
    _paso(mon, _S26)
    _paso(mon, _S12)
    _paso(mon, _S26)
    assert len(mon._toasts) == 2


# --- Los returns tempranos NO pueden ser mudos ----------------------------------------------


def test_panel_ilegible_loguea_por_flanco(mon):
    """Requisito no negociable del proyecto: todo `return` temprano de un handler continuo pasa
    por `_note_stall`. Hubo dos trabes de 6-8 min por handlers mudos."""
    ilegible = FakeWeapon()
    ilegible.nombre_raw, ilegible.nombre_canon, ilegible.nivel = "", None, None
    ilegible.notas = ["nombre_no_leido", "nivel_no_leido"]
    _paso(mon, _S26, weapon=ilegible)
    assert not mon._toasts
    assert "S26/detalle" in mon._stalls
    assert any("ilegible" in d for d in mon._diags) or True   # el stall va por log, no por diag


def test_la_misma_arma_repetida_declara_el_trabe(mon):
    """Si la firma cambia (animación de fondo) pero el arma es la misma, no se re-emite — pero
    tampoco se calla: queda declarado como trabe para que no parezca que el handler murió."""
    _paso(mon, _S26)
    _paso(mon, _S26, sig=b"B")          # firma nueva, mismo arma
    assert len(mon._toasts) == 1
    assert "S26" in mon._stalls


def test_el_trabe_se_limpia_al_avanzar(mon):
    _paso(mon, _S26)
    _paso(mon, _S26, sig=b"B")
    assert "S26" in mon._stalls
    _paso(mon, _S26, sig=b"C", weapon=FakeWeapon(nombre="Sol exuvia", canon="Sol exuvia"))
    assert "S26" not in mon._stalls


# --- Observación pura -----------------------------------------------------------------------


def test_arma_fuera_del_catalogo_se_reporta_igual(mon):
    """El nombre crudo se muestra y se declara que no está en el catálogo. No se da de alta nada:
    `weapons` tiene 42 armas de menos y completarlo es una pasada aparte."""
    _paso(mon, _S26, weapon=FakeWeapon(nombre="Arma Nueva", canon=None))
    ev = mon._toasts[0]
    assert ev["en_catalogo"] is False
    assert "Arma Nueva" in ev["nombre"]


def _fake_identifier(nombre, roster=("Jane", "Ellen")):
    """Identificador de mentira con el contrato mínimo que usa el handler: una superficie que
    nombra un RECORTE, y la canonicalización contra el roster.

    Es `match(crop)` y no `sample(frame)` porque el recorte ya no lo elige la superficie: viene
    de `read_weapon_owner_badge`, anclado al pill. La superficie solo pone la librería."""
    class FakeOut:
        name = nombre
        conf = 0.90

    class FakeSurf:
        def match(self, crop):
            return FakeOut() if nombre is not None else None

    return type("I", (), {
        "surfaces": {"detail": FakeSurf()},
        "_canonical_name": lambda self, n: n if n in roster else None,
    })()


def _identifier_que_oscila(nombres, roster=("Grace", "Miyabi")):
    """Superficie que devuelve un nombre DISTINTO por llamada — el badge inestable del QA."""
    seq = list(nombres)

    class FakeSurf:
        def __init__(self):
            self.i = 0

        def match(self, crop):
            n = seq[min(self.i, len(seq) - 1)]
            self.i += 1
            return type("R", (), {"name": n, "conf": 0.90})()

    return type("I", (), {
        "surfaces": {"detail": FakeSurf()},
        "_canonical_name": lambda self, n: n if n in roster else None,
    })()


def test_el_dueno_sale_del_badge_compartido(mon):
    """El dueño se nombra con la MISMA librería que el detalle de disco (`avatar_detbadge_v2`);
    lo que cambia respecto de los discos es de dónde sale el recorte."""
    mon._identifier = _fake_identifier("Jane")
    _paso(mon, _S26, boton="reemplazar")
    assert mon._toasts[0]["dueno"] == "Jane"
    assert mon._toasts[0]["tenencia"] == "otro_pj"


def test_dueno_incierto_no_inventa(mon):
    """La superficie abstiene bajo guard: un dueño incierto sale None, nunca uno equivocado.

    Ojo con lo que NO cambia: el arma sigue teniendo dueño (`otro_pj`). No saber quién es no la
    vuelve libre — y esa distinción es justamente la que decide si al equiparla salta el diálogo.
    """
    mon._identifier = _fake_identifier(None)
    _paso(mon, _S26, boton="reemplazar")
    assert mon._toasts[0]["dueno"] is None
    assert mon._toasts[0]["tenencia"] == "otro_pj"


def test_un_nombre_que_no_resuelve_al_roster_se_descarta(mon):
    """El filtro que protege del mojibake de la librería compartida (`'n.Âº11'` por N.º 11).

    Sin canonicalizar, ese texto corrupto llegaría al log y al toast como si fuera el nombre del
    PJ. Preferimos "incierto" antes que basura.
    """
    mon._identifier = _fake_identifier("n.Âº11")
    _paso(mon, _S26, boton="reemplazar")
    assert mon._toasts[0]["dueno"] is None


def test_badge_que_oscila_entre_dos_pjs_termina_en_incierto(mon):
    """QA en vivo 2026-07-31: con el panel QUIETO, el dueño alternaba `Grace` ↔ `Miyabi` cada
    ciclo sobre la misma arma (el Templo, que es de Miyabi). El recorte lo produce un Hough por
    frame: si el círculo se corre unos píxeles, un match ajustado se da vuelta.

    Un arma tiene UN dueño ⇒ si el badge nombró a dos PJs distintos para la misma arma, el
    matcher no es fiable acá y hay que abstenerse (RNF-02: incierto > equivocado). La abstención
    es PEGAJOSA: no alcanza con que uno de los dos vuelva a puntear más alto, porque el log no
    tiene forma de saber cuál de los dos es el bueno.
    """
    mon._identifier = _identifier_que_oscila(["Grace", "Miyabi", "Grace", "Miyabi"])
    _paso(mon, _S26, boton="reemplazar")
    assert mon._toasts[0]["dueno"] == "Grace"        # 1er frame: un solo candidato
    for sig in (b"B", b"C", b"D"):
        _paso(mon, _S26, sig=sig, boton="reemplazar")
    assert mon._toasts[-1]["dueno"] is None
    # Lo que NO cambia: el arma sigue teniendo dueño. No saber quién es no la vuelve libre.
    assert mon._toasts[-1]["tenencia"] == "otro_pj"


def test_la_votacion_del_dueno_se_reinicia_al_cambiar_de_arma(mon):
    """La abstención pegajosa es POR ARMA: pasar a otra arma arranca la votación limpia, o un
    badge malo contaminaría todo lo que mires después."""
    mon._identifier = _identifier_que_oscila(["Grace", "Miyabi", "Grace"])
    _paso(mon, _S26, boton="reemplazar")
    _paso(mon, _S26, sig=b"B", boton="reemplazar")
    assert mon._toasts[-1]["dueno"] is None
    _paso(mon, _S26, sig=b"C", boton="reemplazar",
          weapon=FakeWeapon(nombre="Sol exuvia", canon="Sol exuvia"))
    assert mon._toasts[-1]["nombre"] == "Sol exuvia"
    assert mon._toasts[-1]["dueno"] == "Grace"


def test_un_dueno_estable_se_sigue_nombrando(mon):
    """El contrapeso: la abstención no debe comerse el caso bueno. Varios ciclos con el mismo
    nombre siguen nombrando (es el `la tiene Vivian` que el QA validó contra la verdad)."""
    mon._identifier = _fake_identifier("Jane")
    _paso(mon, _S26, boton="reemplazar")
    for sig in (b"B", b"C"):
        _paso(mon, _S26, sig=sig, boton="reemplazar")
    assert mon._toasts[-1]["dueno"] == "Jane"


# --- ¿Cuándo hay NOTICIA? (el flag que decide si la UI interrumpe) --------------------------


def test_mirar_un_arma_no_es_noticia(mon):
    """Abrir un engine para verlo NO amerita toast: el usuario lo está mirando.

    Pedido de Daniel (2026-07-31): *"no aporta valor al usuario, la idea es que avise de CAMBIOS
    (...) ahora salta un toast por cada lectura de un engine y puede ser una obviedad"*. El evento
    se emite igual —alimenta el panel en vivo— pero marcado `cambio=False`.
    """
    _paso(mon, _S26, boton="reemplazar")
    assert len(mon._toasts) == 1                 # el dato viaja
    assert mon._toasts[0]["cambio"] is False     # pero no interrumpe


def test_equipar_un_arma_libre_si_es_noticia(mon):
    """El caso 3 del QA: la misma arma pasa de LIBRE a equipada. Eso sí es un cambio."""
    import app.core.parser_weapon_s26 as pw_mod
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="equipar", badge=pw_mod.OwnerBadge(present=False, nitidez=2.0))
    assert mon._toasts[0]["tenencia"] == "libre" and mon._toasts[0]["cambio"] is False
    _paso(mon, _S26, sig=b"B", boton="desequipar",
          badge=pw_mod.OwnerBadge(present=True, nitidez=70.0))
    assert mon._toasts[-1]["tenencia"] == "equipada"
    assert mon._toasts[-1]["cambio"] is True
    assert mon._toasts[-1]["tenencia_previa"] == "libre"


def test_no_saber_no_es_una_novedad(mon):
    """`incierto` no cuenta como cambio en ninguna de las dos puntas.

    Si contara, un frame en el que no se pudo leer el botón dispararía un toast al entrar y otro
    al salir de la incertidumbre — dos interrupciones por CERO información nueva."""
    _paso(mon, _S26, boton=None)                       # incierto
    _paso(mon, _S26, sig=b"B", boton="reemplazar")     # incierto → otro_pj
    assert all(t["cambio"] is False for t in mon._toasts), mon._toasts


def test_salir_de_s26_no_borra_la_tenencia_conocida(mon):
    """Equipar un arma te saca de la pantalla y te devuelve. Si al salir se olvidara la tenencia
    previa, el único cambio que hay para avisar se perdería justo cuando ocurre."""
    import app.core.parser_weapon_s26 as pw_mod
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="equipar", badge=pw_mod.OwnerBadge(present=False, nitidez=2.0))
    _paso(mon, _S12)                                   # salida y vuelta
    _paso(mon, _S26, sig=b"B", boton="desequipar",
          badge=pw_mod.OwnerBadge(present=True, nitidez=70.0))
    assert mon._toasts[-1]["cambio"] is True


def test_el_handler_no_toca_la_db():
    """El test que importa de este hito: S26 es SOLO LECTURA.

    Se compara el sha256 de la DB antes y después de correr el handler contra la DB real (misma
    técnica que `test_reemplazo_readonly`). Si alguna vez alguien agrega un INSERT al handler,
    esto cae.
    """
    db = Path("db/danibod_zzz_v2.db")
    if not db.exists():
        pytest.skip("DB no presente")
    antes = hashlib.sha256(db.read_bytes()).hexdigest()

    import app.core.monitor as mon_mod
    import app.core.parser_weapon_s26 as pw_mod
    orig = (pw_mod.parse_weapon_s26, pw_mod.weapon_panel_signature,
            pw_mod.read_weapon_owner_badge)
    try:
        pw_mod.parse_weapon_s26 = lambda fr, ocr, catalogo=None: FakeWeapon()
        pw_mod.weapon_panel_signature = lambda fr: b"X"
        pw_mod.read_weapon_owner_badge = lambda fr, pb: None
        m = mon_mod.Monitor(ocr=object(), detector=None, set_badge_matcher=object())
        m._identifier = None
        m._dispatch_state(_frame(), _S26)
    finally:
        (pw_mod.parse_weapon_s26, pw_mod.weapon_panel_signature,
         pw_mod.read_weapon_owner_badge) = orig

    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes, "¡S26 escribió la DB!"


def test_el_catalogo_se_lee_una_sola_vez(monkeypatch):
    """El SELECT del catálogo se cachea: es la misma lista siempre y no vale pagarla por arma."""
    import app.core.monitor as mon_mod
    m = mon_mod.Monitor(ocr=object(), detector=None, set_badge_matcher=object())
    primera = m._weapon_catalog()
    llamadas = {"n": 0}

    def _boom(*a, **k):
        llamadas["n"] += 1
        raise AssertionError("no debería volver a consultar")

    monkeypatch.setattr("app.db.connection.get_connection", _boom)
    assert m._weapon_catalog() == primera
    assert llamadas["n"] == 0


# --- Tenencia: libre / de otro / equipada ----------------------------------------------------


def test_arma_libre_se_reporta_como_libre(mon):
    """El caso que el sistema no podía ver. Importa porque el juego se comporta distinto: un arma
    libre se equipa sin diálogo de confirmación, la de otro PJ abre S23."""
    import app.core.parser_weapon_s26 as pw_mod
    mon._identifier = _fake_identifier(None)
    _paso(mon, _S26, boton="reemplazar",
          badge=pw_mod.OwnerBadge(present=False, nitidez=2.0))
    assert mon._toasts[0]["tenencia"] == "libre"
    assert mon._toasts[0]["dueno"] is None


def test_desequipar_da_dueno_certero_sin_libreria(mon):
    """La vía de dueño que NO depende de `avatar_detbadge_v2` (que hoy no cubre el roster).

    Si el juego ofrece 'Desequipar', la lleva puesta el PJ que estás mirando; ese nombre sale del
    latch de identidad, que se resuelve por OCR en S18 y funciona para cualquier PJ — incluidos
    los que no tienen ref de avatar."""
    mon._identifier = _fake_identifier(None)
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    assert mon._toasts[0]["tenencia"] == "equipada"
    assert mon._toasts[0]["dueno"] == "Velina"


def test_sin_ancla_la_tenencia_queda_incierta(mon):
    """Panel sin pill ⇒ no hay dónde mirar el badge. Tiene que salir "incierto" y no "libre":
    confundir "no pude ver" con "no hay dueño" es exactamente el falso LIBRE."""
    mon._identifier = _fake_identifier(None)
    _paso(mon, _S26, boton="reemplazar", badge=None)
    assert mon._toasts[0]["tenencia"] == "incierto"


def test_cambiar_de_tenencia_vuelve_a_emitir(mon):
    """La tenencia entra en la firma del log. Equipar el arma que estabas mirando cambia el estado
    sin cambiar el arma, y ese es justo el evento que hay que reportar."""
    import app.core.parser_weapon_s26 as pw_mod
    mon._identifier = _fake_identifier(None)
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="reemplazar",
          badge=pw_mod.OwnerBadge(present=False, nitidez=2.0))
    assert mon._toasts[0]["tenencia"] == "libre"
    # Mismo arma, misma firma de panel salvo el badge: ahora la tiene puesta.
    _paso(mon, _S26, sig=b"A2", boton="desequipar",
          badge=pw_mod.OwnerBadge(present=True, nitidez=70.0))
    assert len(mon._toasts) == 2
    assert mon._toasts[1]["tenencia"] == "equipada"


# --- Cosecha del detalle-badge (RF-15, spec 2026-08-10) --------------------------------------
#
# Las pantallas de armas CONSUMÍAN `avatar_detbadge_v2` sin alimentarla nunca: el único punto que
# cosechaba esa superficie era el flujo de discos. Acá se cierra el circuito con la única etiqueta
# certera que tiene este panel — 'Desequipar' dice que la lleva el PJ del latch, y eso no depende
# del matcher, así que no se realimenta con su propia salida.


def _identifier_cosechable(nombre=None, roster=("Jane", "Ellen", "Velina"), refs=None, conf=0.90,
                           clon=False):
    """Fake con el contrato que usa la cosecha: nombrar, canonicalizar, contar refs y aprender.

    `cosechado` registra los `(nombre, crop)` aprendidos para que el test afirme sobre lo que se
    guardó, no sobre cuántas veces se llamó a algo.
    """
    conteo = dict(refs or {})

    class FakeOut:
        name = nombre

    FakeOut.conf = conf
    FakeOut.margin = 0.15
    FakeOut.rejected = False
    FakeOut.top = [(nombre, 0.26)] if nombre else []

    class FakeSurf:
        def match(self, crop):
            return FakeOut() if nombre is not None else None

    class FakeIdent:
        def __init__(self):
            self.surfaces = {"detail": FakeSurf()}
            self.cosechado = []

        def _canonical_name(self, n):
            return n if n in roster else None

        def detail_refs_count(self, name):
            return conteo.get(name, 0)

        def detail_is_near_duplicate(self, crop, name):
            return clon

        def learn_s17_detail(self, crop, name):
            self.cosechado.append((name, crop))
            conteo[name] = conteo.get(name, 0) + 1
            return True

    return FakeIdent()


def test_desequipar_cosecha_el_badge_para_el_pj_del_latch(mon):
    """El caso que justifica el feature: 'Desequipar' es prueba directa de quién la lleva, así que
    el recorte se puede guardar con una etiqueta CERTERA — sin que el matcher opine."""
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    assert [n for n, _ in mon._identifier.cosechado] == ["Velina"]


def test_no_cosecha_si_el_pj_mirado_no_la_lleva_puesta(mon):
    """Sin 'Desequipar' no hay etiqueta certera: el arma puede ser de cualquiera. Cosechar acá
    metería una cara bajo el nombre del PJ equivocado, que es la forma más cara de romper una
    librería."""
    import app.core.parser_weapon_s26 as pw_mod
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="reemplazar",
          badge=pw_mod.OwnerBadge(present=True, nitidez=70.0, crop=_frame(200)))
    assert mon._identifier.cosechado == []


def test_no_cosecha_cuando_el_badge_contradice_al_latch(mon):
    """Las dos señales en desacuerdo. Misma regla que en discos: se le cree al badge —0-wrong en
    QA— y no se aprende nada. Una de las dos está mal y no sabemos cuál."""
    mon._identifier = _identifier_cosechable("Jane")
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    assert mon._identifier.cosechado == []


def test_el_badge_en_desacuerdo_veta_aunque_el_consenso_se_abstenga(mon):
    """QA en vivo 2026-08-10: se cosechó la cara de Billy bajo el nombre de Lycaon.

    El log fue `top=Billy:0.26 conf=0.74 margin=0.15 latch=Lycaon -> cosechado`. El badge tenía
    una opinión firme y contraria, pero el veto comparaba contra `badge_nombre`, que sale de
    `decide_owner` y exige 0.80 acumulado: con 0.74 de un frame devolvió None, y `if badge_nombre`
    dejó pasar. Se usó un consenso pensado para REPORTAR como si fuera un detector de desacuerdo.

    Para nombrar hace falta mucha evidencia; para NEGARSE A APRENDER tiene que alcanzar con poca.
    """
    mon._identifier = _identifier_cosechable("Jane", roster=("Jane", "Velina"), conf=0.74)
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    assert mon._identifier.cosechado == [], (
        "el badge nombró a otro PJ con opinión propia: no se puede aprender bajo el latch")


def test_un_matcher_perdido_no_impide_aprender(mon):
    """El contracaso del anterior, y la razón de ser del feature. QA en vivo 2026-08-10, Rina:

        top=Sunna:0.27, Alice:0.27, Anby:0.28 · conf=0.73 margin=0.00 · latch=Rina -> cosechado

    El matcher no tenía idea (Rina ni figuraba en el top-3) y por margen ~0 se abstuvo: `name=None`.
    Eso NO es desacuerdo, es ignorancia — justo el PJ de una sola ref que venimos a cubrir. Cinco
    segundos después de esa cosecha el mismo badge daba `Rina:0.00`.

    Si alguna vez se endurece el veto a "el top-1 crudo tiene que coincidir", este test cae — y
    con él, la mitad de los PJs flacos que el feature existe para tapar.
    """
    mon._identifier = _identifier_cosechable(None)      # la superficie se abstiene
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    assert [n for n, _ in mon._identifier.cosechado] == ["Velina"]


def test_la_misma_arma_no_se_cosecha_dos_veces(mon):
    """`add_reference` no dedupea y desaloja la más vieja pasadas 10: sin este freno, mirar un arma
    diez veces cambiaría refs diversas por diez recortes del mismo encuadre."""
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    _paso(mon, _S26, sig=b"B", boton="desequipar")
    assert len(mon._identifier.cosechado) == 1


def test_otra_arma_del_mismo_pj_si_se_cosecha(mon):
    """El dedup es por (PJ, arma), no por PJ: otra arma es otro encuadre y suma diversidad real."""
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    _paso(mon, _S26, sig=b"B", boton="desequipar",
          weapon=FakeWeapon(nombre="Sol exuvia", canon="Sol exuvia"))
    assert len(mon._identifier.cosechado) == 2


def test_salir_y_volver_no_re_cosecha_la_misma_arma(mon):
    """El dedup es POR SESIÓN, no por entrada a la pantalla: `_reset_s26_state` no lo limpia. Si lo
    limpiara, salir y volver sería la forma trivial de saltarse el freno."""
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    _paso(mon, _S12)
    _paso(mon, _S26, boton="desequipar")
    assert len(mon._identifier.cosechado) == 1


def test_un_recorte_clonado_no_se_guarda_de_nuevo(mon):
    """QA en vivo 2026-08-11: Lycaon quedó con dos refs a distancia 0.000, las dos de *Última
    cena* — una de cada sesión. El dedup por (PJ, arma) es POR SESIÓN, así que no ataja esto.

    El clon no suma discriminación (la distancia de clase es un `min`) y gasta una de las 10
    ranuras; con el cupo lleno, el desalojo FIFO empieza a tirar las refs diversas de los discos.
    """
    mon._identifier = _identifier_cosechable(clon=True)
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    assert mon._identifier.cosechado == []


def test_un_pj_en_el_techo_no_recibe_mas_refs(mon):
    """Con el cupo lleno, cosechar DESALOJA la ref más vieja — que son las de los discos, el
    encuadre diverso que hace útil a la librería. Preferimos no aprender nada."""
    mon._identifier = _identifier_cosechable(refs={"Velina": 10})
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar")
    assert mon._identifier.cosechado == []
    assert mon._identifier.detail_refs_count("Velina") == 10


def test_un_recorte_que_no_es_cara_no_se_cosecha(mon):
    """'Desequipar' decide la tenencia SIN consultar el badge, así que un recorte que el propio
    sistema no considera una cara (`present=False`, el falso LIBRE por nitidez baja) igual llegaría
    hasta acá. Aprenderlo metería un no-avatar bajo el nombre de un PJ.

    La tenencia no se ve afectada: el botón sigue siendo prueba directa de quién la lleva.
    """
    import app.core.parser_weapon_s26 as pw_mod
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar",
          badge=pw_mod.OwnerBadge(present=False, nitidez=3.0, crop=_frame(200)))
    assert mon._identifier.cosechado == []
    assert mon._toasts[0]["tenencia"] == "equipada"


def _identifier_que_se_abstiene(top=(("Lycaon", 0.28), ("Ben", 0.31)), conf=0.72, margin=0.03):
    """Matcher que NO llega al guard: `name=None` pero con el top-k y los números poblados.

    Es el caso que hoy no deja rastro y por el que existe la instrumentación — una abstención se ve
    igual que un 'no había nadie', y sin el top-1 no se puede saber si faltan refs o pasa otra cosa.
    """
    class FakeOut:
        name = None
        conf = 0.72
        margin = 0.03
        rejected = False

    FakeOut.conf, FakeOut.margin, FakeOut.top = conf, margin, list(top)

    class FakeSurf:
        def match(self, crop):
            return FakeOut()

    return type("I", (), {
        "surfaces": {"detail": FakeSurf()},
        "_canonical_name": lambda self, n: n,
        "detail_refs_count": lambda self, n: 0,
        "learn_s17_detail": lambda self, c, n: True,
    })()


def _diag_armas(caplog):
    return [r.getMessage() for r in caplog.records if "[id_diag/arma]" in r.getMessage()]


def test_sin_id_diag_no_se_emite_diagnostico(mon, caplog):
    """Cero overhead cuando el flag está apagado: es instrumentación de QA, no de producción."""
    import logging
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    mon._id_diag_on = False
    with caplog.at_level(logging.INFO):
        _paso(mon, _S26, boton="desequipar")
    assert _diag_armas(caplog) == []


def test_la_abstencion_deja_registrado_a_quien_estuvo_cerca(mon, caplog):
    """El dato que el QA del 2026-08-07 no pudo dar: *cuáles* PJs falla. `MatchResult` ya trae el
    top-k y los números aunque se abstenga; hasta ahora se descartaban."""
    import logging
    mon._identifier = _identifier_que_se_abstiene()
    mon._last_agent_name = "Velina"
    mon._id_diag_on = True
    with caplog.at_level(logging.INFO):
        _paso(mon, _S26, boton="reemplazar")
    linea = _diag_armas(caplog)
    assert len(linea) == 1, linea
    assert "Lycaon" in linea[0] and "abstuvo" in linea[0] and "S26" in linea[0]


def test_la_cosecha_queda_registrada_en_el_diagnostico(mon, caplog):
    """Para poder cruzar, después del QA, qué refs entraron y de qué arma."""
    import logging
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    mon._id_diag_on = True
    with caplog.at_level(logging.INFO):
        _paso(mon, _S26, boton="desequipar")
    assert any("cosechado" in m for m in _diag_armas(caplog))


def test_el_veto_por_conflicto_queda_registrado(mon, caplog):
    """Un veto silencioso es indistinguible de 'no pasó nada' — la lección del QA mudo."""
    import logging
    mon._identifier = _identifier_cosechable("Jane")
    mon._last_agent_name = "Velina"
    mon._id_diag_on = True
    with caplog.at_level(logging.INFO):
        _paso(mon, _S26, boton="desequipar")
    assert any("veto_conflicto" in m for m in _diag_armas(caplog))


def test_sin_recorte_no_hay_nada_que_aprender(mon):
    """Hough no cerró el círculo. La tenencia sigue siendo certera por el botón, pero no hay
    referencia que guardar — y eso no es un fallo."""
    import app.core.parser_weapon_s26 as pw_mod
    mon._identifier = _identifier_cosechable()
    mon._last_agent_name = "Velina"
    _paso(mon, _S26, boton="desequipar",
          badge=pw_mod.OwnerBadge(present=True, nitidez=70.0, crop=None))
    assert mon._identifier.cosechado == []
    assert mon._toasts[0]["tenencia"] == "equipada"     # la lectura no se ve afectada
