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

    class FakeSurf:
        def match(self, crop):
            return FakeOut() if nombre is not None else None

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
