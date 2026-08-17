"""Cierre de una pasada: el reporte y la única escritura al dominio.

El cierre es el momento en que el censo pasa de observar a **afirmar**. Por eso es lo único que
fabrica huérfanos, y lo único que toca `danibod_zzz_v2.db`.

Dos cosas se protegen acá:

1. **Que el reporte diga qué NO prueba.** Un censo cuya salida se lee como "estos 3 no los tenés"
   cuando en realidad dice "el recorrido no pasó por estos 3" es peor que no tener censo.
2. **Que la marca en el dominio respete RNF-01 y el gate de readonly.** Es una escritura chica,
   pero es escritura: backup, transacción, y los dos PRAGMA.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.core.census import MenuSighting, RosterCensus, write_census_report
from app.core.census_store import marcar_huerfanos_en_dominio

_ROSTER = [(1, "Ellen"), (2, "Astra Yao"), (3, "Nicole"), (4, "Aria")]


def _ok(nombre: str) -> MenuSighting:
    return MenuSighting(nombre, nombre, 0.97, nombre, 0.95, "ok")


def _censo():
    c = RosterCensus(_ROSTER, catalogo={"Ellen", "Astra Yao", "Nicole", "Aria", "Hugo"})
    c.ensure_open(ts=0.0)
    return c


@pytest.fixture
def audit(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "audit"))
    return tmp_path / "audit"


@pytest.fixture
def dominio(tmp_path, monkeypatch):
    """DB de dominio mínima, con la columna `notas` que la marca de huérfano usa."""
    p = tmp_path / "danibod_zzz_v2.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, notas TEXT)")
    con.executemany("INSERT INTO agents (id, nombre, notas) VALUES (?,?,?)",
                    [(1, "Ellen", None), (2, "Astra Yao", "nota previa"), (3, "Nicole", None),
                     (4, "Aria", None)])
    con.commit(); con.close()
    monkeypatch.setenv("DANIBOD_DB_PATH", str(p))
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    return p


def _notas(p) -> dict[str, str | None]:
    con = sqlite3.connect(p)
    try:
        return {n: t for n, t in con.execute("SELECT nombre, notas FROM agents")}
    finally:
        con.close()


# --- reporte ---------------------------------------------------------------------------------

def test_el_reporte_deja_json_y_markdown_sin_temporales(audit):
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    js, md = write_census_report(c.cerrar(ts=2.0))
    assert js.exists() and md.exists()
    assert list(js.parent.glob("*.tmp")) == []
    assert json.loads(js.read_text(encoding="utf-8"))["schema"] == "censo_roster/1"


def test_el_reporte_dice_explicitamente_que_NO_prueba(audit):
    """Es parte del entregable, no adorno: sin esa sección, 'huérfano' se lee como 'no lo tenés'
    cuando significa 'el recorrido no pasó por ahí'."""
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    _js, md = write_census_report(c.cerrar(ts=2.0))
    texto = md.read_text(encoding="utf-8")
    assert "NO prueba" in texto
    assert "no se borran" in texto.lower() or "no se borra" in texto.lower()


def test_el_reporte_separa_las_cinco_categorias(audit):
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    c.observe(MenuSighting("Nicole", "Nicole", 0.40, "Nicole", 0.95, "ok"), ts=2.0)
    c.observe(MenuSighting(None, "Hugo", 0.96, None, 0.12, "sin_match"), ts=3.0)
    for ts in (4.0, 5.0):
        c.observe(MenuSighting(None, "Zzzarel", 0.95, None, 0.10, "sin_match"), ts=ts)
    js, md = write_census_report(c.cerrar(ts=6.0))
    reg = json.loads(js.read_text(encoding="utf-8"))
    assert reg["vistos"] == ["Ellen"]
    assert reg["dudosos"] == ["Nicole"]
    assert reg["no_poseidos"] == ["Hugo"]
    assert [n["clave"] for n in reg["nuevos"]] == ["zzzarel"]
    assert set(reg["huerfanos"]) == {"Astra Yao", "Aria"}
    texto = md.read_text(encoding="utf-8")
    assert "Hugo" in texto and "Zzzarel" in texto


def test_un_no_reconocido_se_reporta_con_las_dos_lecturas_posibles(audit):
    """El catálogo de arte va por delante de la posesión pero no lo cubre todo (~9 grises en una
    sola pantalla contra 5 de diferencia). Así que un nombre desconocido puede ser un PJ nuevo o
    uno que no poseés, y el sistema no puede separarlos desde el nombre. Decirlo es RNF-02."""
    c = _censo()
    for ts in (1.0, 2.0):
        c.observe(MenuSighting(None, "Zzzarel", 0.95, None, 0.10, "sin_match"), ts=ts)
    _js, md = write_census_report(c.cerrar(ts=3.0))
    texto = md.read_text(encoding="utf-8").lower()
    assert "no poseés" in texto or "no posees" in texto
    assert "nuevo" in texto


def test_una_corrida_abandonada_no_produce_reporte(audit):
    """Vencerse no es terminar: no hay nada que declarar y, sobre todo, no hay huérfanos."""
    c = _censo()
    c.observe(_ok("Ellen"), ts=1.0)
    c.drop("expirada")
    assert c.cerrar(ts=2.0) is None
    assert write_census_report(None) is None


# --- la única escritura al dominio ------------------------------------------------------------

def test_marcar_huerfanos_deja_la_nota_con_fecha_y_conserva_lo_previo(dominio):
    n = marcar_huerfanos_en_dominio(["Astra Yao", "Aria"], fecha="2026-08-16")
    assert n == 2
    notas = _notas(dominio)
    assert "no_visto_en_censo_2026-08-16" in notas["Astra Yao"]
    assert "nota previa" in notas["Astra Yao"], "no se pisa lo que ya había"
    assert notas["Ellen"] is None, "los vistos no se tocan"


def test_marcar_huerfanos_dos_veces_no_duplica_la_marca(dominio):
    marcar_huerfanos_en_dominio(["Aria"], fecha="2026-08-16")
    marcar_huerfanos_en_dominio(["Aria"], fecha="2026-08-16")
    assert _notas(dominio)["Aria"].count("no_visto_en_censo_2026-08-16") == 1


def test_marcar_huerfanos_deja_backup_previo(dominio):
    """RNF-01: nada toca la DB de dominio sin copia previa."""
    marcar_huerfanos_en_dominio(["Aria"], fecha="2026-08-16")
    assert list(dominio.parent.glob("*.backup_precenso_*.db")), "falta el backup RNF-01"


def test_en_readonly_no_se_marca_nada(dominio, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    assert marcar_huerfanos_en_dominio(["Aria"], fecha="2026-08-16") == 0
    assert _notas(dominio)["Aria"] is None


def test_marcar_sin_huerfanos_no_abre_la_db_ni_deja_backup(dominio):
    """Una pasada completa no tiene huérfanos: no hay motivo para tocar el dominio ni para
    ensuciar el disco con un backup."""
    assert marcar_huerfanos_en_dominio([], fecha="2026-08-16") == 0
    assert list(dominio.parent.glob("*.backup_precenso_*.db")) == []


def test_un_nombre_que_no_esta_en_agents_no_rompe_el_cierre(dominio):
    n = marcar_huerfanos_en_dominio(["Aria", "Fulano Inexistente"], fecha="2026-08-16")
    assert n == 1
    assert "no_visto_en_censo" in _notas(dominio)["Aria"]
