"""El reporte de cierre del censo de armas.

El censo de discos no produce archivo —sólo loguea— y acá sí hace falta, por una razón concreta:
**la pasada descubre las armas que el catálogo no tiene, con su nombre español leído de pantalla**.
Ese dato no está en ninguna wiki accesible (`audit/weapons_catalog_20260728.md`), así que el
reporte es la entrada de la migración curada que después las da de alta. Perderlo significa volver
a recorrer los 57 tiles.
"""
from __future__ import annotations

import json

import pytest

from app.core.census_inventario import (
    InventoryCensus,
    Sighting,
    write_weapon_census_report,
)


@pytest.fixture
def audit(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path))
    return tmp_path / "censos"


def _censo(total=4, *, fuera=1):
    c = InventoryCensus(entidad="armas")
    c.ensure_open(ts=1.0)
    c.anclar_total(total, ts=1.0)
    c.observe(Sighting(identidad=("fila", 1), dueno="Jane"), ts=1.0)
    for i in range(fuera):
        c.observe(Sighting(identidad=("arma", f"X{i}", 0, 1),
                           en_catalogo=False, confirmada=False), ts=1.0)
    c.cerrar(ts=2.0)
    return c


_FUERA = [{"nombre_raw": "Cilindro neumático", "rareza": "B", "nivel": 0,
           "nivel_max": 60, "atk_base": 32, "stat": "Impacto 6%"}]


def test_escribe_json_y_markdown(audit):
    rutas = write_weapon_census_report(_censo().resumen(), _FUERA)
    assert rutas is not None
    j, md = rutas
    assert j.suffix == ".json" and md.suffix == ".md"
    assert not list(audit.glob("*.tmp")), "quedó un temporal a medio escribir"
    reg = json.loads(j.read_text(encoding="utf-8"))
    assert reg["schema"] == "censo_armas/1"
    assert reg["resumen"]["entidad"] == "armas"


def test_el_arma_fuera_de_catalogo_queda_con_todo_lo_que_se_leyo(audit):
    """Es LA razón del reporte: el nombre español de pantalla no se puede sacar de ningún otro
    lado, y con él van los campos que la migración curada necesita para dar de alta la fila."""
    _j, md = write_weapon_census_report(_censo().resumen(), _FUERA)
    texto = md.read_text(encoding="utf-8")
    for esperado in ("Cilindro neumático", "0/60", "32", "Impacto 6%"):
        assert esperado in texto, f"falta {esperado!r} en el reporte"


def test_dice_que_nada_se_da_de_alta_solo(audit):
    """El reporte es material para revisar a mano. Auto-insertar con lo que devuelva el OCR
    repetiría el pecado original del catálogo, que fue emparejar por parecido — y el archivo tiene
    que decirlo, porque es lo que va a leer quien lo use dentro de seis meses."""
    _j, md = write_weapon_census_report(_censo().resumen(), _FUERA)
    assert "nada se da de alta automáticamente" in md.read_text(encoding="utf-8").lower()


def test_declara_lo_que_la_pasada_NO_prueba(audit):
    """Misma doctrina que el reporte del roster: un censo que no dice qué NO vio es peor que no
    tener censo. Acá lo que no prueba es justo lo que v1 decidió no escribir."""
    _j, md = write_weapon_census_report(_censo().resumen(), _FUERA)
    texto = md.read_text(encoding="utf-8")
    assert "NO prueba" in texto
    assert "LIBRES" in texto and "copias duplicadas" in texto


def test_el_reporte_ya_no_dice_que_las_libres_no_se_escriben(audit):
    """Regresión del 2026-09-11: desde que S30 mide el lugar del dueño, las libres se escriben. Un
    reporte que siga diciendo "nada sobre las libres" explica una brecha que ya no existe."""
    _j, md = write_weapon_census_report(_censo().resumen(), _FUERA)
    texto = md.read_text(encoding="utf-8")
    assert "Nada sobre las armas LIBRES" not in texto
    assert "se escriben sin dueño" in texto


def test_sin_armas_fuera_de_catalogo_lo_dice_explicito(audit):
    _j, md = write_weapon_census_report(_censo(fuera=0).resumen(), [])
    assert "Ninguna" in md.read_text(encoding="utf-8")


def test_la_brecha_de_armas_no_habla_de_gemelos(audit):
    """En discos la causa probable son gemelos que la deduplicación colapsa; en armas, copias del
    mismo W-Engine vistas sin posición de selección localizable. Nombrar la causa de discos sería
    nombrar la equivocada."""
    _j, md = write_weapon_census_report(_censo().resumen(), _FUERA)
    texto = md.read_text(encoding="utf-8")
    assert "W-Engine" in texto and "gemelos" not in texto


def test_sin_resumen_no_escribe_nada(audit):
    assert write_weapon_census_report(None) is None
    assert write_weapon_census_report({}) is None


def test_un_fallo_al_escribir_no_tumba_el_cierre(audit, monkeypatch):
    """El reporte nunca puede tumbar el cierre de la pasada — mismo contrato que el del roster."""
    import app.core.audit_paths as ap

    def _explota(*_a, **_k):
        raise OSError("disco lleno")
    monkeypatch.setattr(ap, "reservar_rutas", _explota)
    assert write_weapon_census_report(_censo().resumen(), _FUERA) is None


def test_el_reporte_no_dice_que_las_copias_son_invisibles(audit):
    """Regresión del 2026-09-10. El reporte afirmaba que la firma del panel no distinguía dos
    copias del mismo W-Engine y que ni siquiera volvía a disparar el parser. Desde el arreglo por
    posición de la selección eso es falso — y el primer reporte tras el arreglo lo seguía diciendo,
    sobre una pasada donde las dos Última cena libres de Daniel SÍ se contaron por separado.

    Un reporte que explica la brecha con una causa que ya no existe manda a buscar el problema al
    lugar equivocado. Por eso se fija también la contracara: tiene que decir qué separa a las copias.
    """
    _j, md = write_weapon_census_report(_censo().resumen(), _FUERA)
    texto = md.read_text(encoding="utf-8")
    assert "ni siquiera vuelve a disparar" not in texto
    assert "no las distingue" not in texto
    assert "selección" in texto, "el reporte tiene que decir qué separa a las copias"
