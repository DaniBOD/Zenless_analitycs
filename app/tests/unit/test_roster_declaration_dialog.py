"""El diálogo de declaración del roster — que construya, y que respete el bloqueo.

Lo que se testea acá no es la estética (esa la define Claude Design), sino las dos reglas que el
diálogo tiene que hacer cumplir aunque el diseño cambie: un confirmado no se puede destildar, y el
contador refleja lo que está tildado.
"""
from __future__ import annotations

import pytest

from app.core.roster_declaration import CONFIRMADO, DECLARADO, NO_OBTENIDO, PersonajeDeclarable

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    inst = QApplication.instance()
    # Ver la nota extensa en test_toast_reemplazado: QCoreApplication y QApplication no coexisten.
    if inst is not None and not isinstance(inst, QApplication):
        pytest.skip("ya existe una QCoreApplication en el proceso")
    app = inst or QApplication([])
    yield app


_CATALOGO = [
    PersonajeDeclarable("Ellen", True, CONFIRMADO, "6 disco(s) asignado(s) — es prueba de posesión",
                        rango="S", elemento="Hielo", rol="Ataque", discos=6),
    PersonajeDeclarable("Aria", True, DECLARADO, "declarado por vos · sin datos aún",
                        rango="S", elemento="Éter", rol="Anomalía"),
    PersonajeDeclarable("Hugo", False, NO_OBTENIDO),
]


def _dlg():
    from app.ui.roster_declaration_dialog import RosterDeclarationDialog
    return RosterDeclarationDialog(catalogo=_CATALOGO)


def test_construye_una_casilla_por_personaje(qapp):
    d = _dlg()
    assert set(d._checks) == {"Ellen", "Aria", "Hugo"}


def test_los_que_ya_estan_en_agents_vienen_tildados(qapp):
    """El diálogo arranca mostrando lo que la DB cree HOY; el usuario corrige desde ahí."""
    d = _dlg()
    assert d.seleccionados() == {"Ellen", "Aria"}


def test_un_confirmado_llega_declarado_aunque_su_casilla_se_destilde(qapp):
    """Su build es la prueba: declararlo como no poseído sería afirmar algo que la evidencia
    contradice.

    El check deshabilitado es la *afordancia*, no la garantía — `setEnabled(False)` frena el click
    del usuario pero no un `setChecked` programático. Lo que tiene que ser inviolable es lo que se
    ESCRIBE, así que el bloqueo vive en `seleccionados()`."""
    d = _dlg()
    chk = d._checks["Ellen"]
    assert chk.isEnabled() is False, "la casilla tiene que verse bloqueada"
    chk.setChecked(False)
    assert "Ellen" in d.seleccionados()


def test_el_motivo_del_bloqueo_esta_a_la_vista(qapp):
    """Un check deshabilitado sin explicación se lee como un bug."""
    d = _dlg()
    assert "disco" in d._checks["Ellen"].toolTip().lower()


def test_el_contador_sigue_a_lo_tildado(qapp):
    """Formato del diseño: los declarados contra las FILAS de `agents`, no contra el catálogo.

    Son dos denominadores distintos y el header muestra el que pide acción: cuántas filas hay en
    la DB frente a cuántas el usuario reconoce como suyas."""
    d = _dlg()
    assert d._contador.text() == "2 DECLARADOS · 2 FILAS EN AGENTS"
    d._checks["Hugo"].setChecked(True)          # declara uno que no está en agents
    assert d._contador.text().startswith("3 DECLARADOS")
    d._checks["Aria"].setChecked(False)
    assert d._contador.text().startswith("2 DECLARADOS")


def test_en_readonly_avisa_que_no_escribio_en_vez_de_cerrar(qapp, monkeypatch):
    """El fallo que ya nos pasó una vez fue un QA cuyo 'pass' era el silencio: el diálogo tiene que
    decir que no escribió, no simular éxito y cerrarse."""
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    avisos: list[str] = []
    monkeypatch.setattr(
        "app.ui.roster_declaration_dialog.QMessageBox.warning",
        lambda *a, **k: avisos.append(a[2] if len(a) > 2 else ""),
    )
    d = _dlg()
    d._guardar()
    assert d.resultado is not None and d.resultado.escribio is False
    assert avisos and "solo lectura" in avisos[0].lower()
    assert d.result() == 0, "no debe aceptar: no guardó nada"
