"""Persistencia de la bitácora de desmontaje: resolución de ruta + escritura atómica.

La bitácora es lo único que el feature deja detrás, y **no toca la DB** (el proyecto está en
read-only). Por eso hay dos cosas que probar: que el archivo caiga donde corresponde también
cuando la app corre empaquetada, y que la DB quede con el mismo sha256 antes y después.

Hoy el único precedente de escritura a `audit/` en runtime (`_dump_s23_fallo`) usa `Path("audit")`
relativo al CWD, que en el `.exe` apunta a donde se lanzó el acceso directo. `resolve_audit_dir()`
es el espejo de `_resolve_db_path`: override por env → `%LOCALAPPDATA%` si está congelado → el
`audit/` del repo en desarrollo.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.core.audit_paths import reservar_rutas, resolve_audit_dir
from app.core.teardown_batch import TeardownBatch, write_teardown_record


def test_el_override_por_env_gana(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "mi_audit"))
    assert resolve_audit_dir() == tmp_path / "mi_audit"


def test_env_vacia_se_ignora(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", "")
    assert resolve_audit_dir().name == "audit"


def test_en_desarrollo_apunta_al_audit_del_repo(monkeypatch):
    monkeypatch.delenv("DANIBOD_AUDIT_DIR", raising=False)
    monkeypatch.setattr("sys.frozen", False, raising=False)
    assert resolve_audit_dir().name == "audit"


def test_congelado_usa_localappdata(tmp_path, monkeypatch):
    """En el `.exe` el CWD es el del acceso directo, así que `Path("audit")` sería impredecible."""
    monkeypatch.delenv("DANIBOD_AUDIT_DIR", raising=False)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    d = resolve_audit_dir()
    assert tmp_path in d.parents or d.parent == tmp_path, d
    assert d.name == "audit"


# --- Escritura -------------------------------------------------------------------------------

def _registro(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path))
    from types import SimpleNamespace
    sub = SimpleNamespace(nombre_canon="DEF%", nombre_raw="Defensa", valor=4.8,
                          unidad="%", rolls=0, confianza=1.0)
    disco = SimpleNamespace(set_name_raw="Firmamento llameante", set_name_canon=None, slot=2,
                            nivel=0, rareza="S", main_stat_canon="ATK", main_stat_raw="Ataque",
                            main_valor=79.0, main_unidad="flat", subs=[sub],
                            confianza_global=0.95, notas=[])
    b = TeardownBatch()
    b.ensure_open(ts=0.0)
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), disco, set_id=12)
    return b.commit(materiales=[("Disco original", 1)], ts=2.0)


def test_escribe_json_valido_en_la_carpeta_resuelta(tmp_path, monkeypatch):
    reg = _registro(tmp_path, monkeypatch)
    p = write_teardown_record(reg)
    assert p is not None and p.exists()
    assert p.parent == tmp_path / "desmontajes"
    datos = json.loads(p.read_text(encoding="utf-8"))
    assert datos["schema"] == "desmontaje/1"
    assert datos["discos"][0]["set_raw"] == "Firmamento llameante"
    assert datos["discos"][0]["subs"][0]["valor"] == 4.8


def test_no_deja_archivo_temporal(tmp_path, monkeypatch):
    """Escritura atómica: `tmp` + `os.replace`, mismo patrón que `FarmSession._persist`. Un JSON
    a medio escribir sería peor que ninguno."""
    reg = _registro(tmp_path, monkeypatch)
    write_teardown_record(reg)
    assert list((tmp_path / "desmontajes").glob("*.tmp")) == []


def test_dos_tandas_en_el_mismo_tick_del_reloj_no_se_pisan(
        tmp_path, monkeypatch, reloj_de_pared_congelado):
    """El sello de tiempo **no** es un discriminador, y la unicidad no puede depender de él.

    El reloj de pared solo separa dos escrituras si alcanza a avanzar entre una y otra, y cuánto
    tarda en avanzar no lo decide esta app: es la resolución global del timer de Windows (15,625
    ms por defecto). Con el reloj congelado esto falla siempre; sin congelar, fallaba a veces —
    que es peor, porque parece que anda.
    """
    reg = _registro(tmp_path, monkeypatch)
    p1 = write_teardown_record(reg)
    p2 = write_teardown_record(reg)
    assert p1 != p2, "dos tandas cayeron en el mismo archivo"
    assert len(list((tmp_path / "desmontajes").glob("*.json"))) == 2


def test_la_segunda_tanda_no_borra_el_contenido_de_la_primera(
        tmp_path, monkeypatch, reloj_de_pared_congelado):
    """El daño real no es el nombre repetido: es que `os.replace` pisa en silencio. Lo que se
    pierde es una tanda entera de auditoría, sin error ni aviso."""
    reg = _registro(tmp_path, monkeypatch)
    primera = dict(reg, modo="TANDA_A")
    segunda = dict(reg, modo="TANDA_B")
    p1 = write_teardown_record(primera)
    write_teardown_record(segunda)
    assert p1.exists(), "la segunda tanda borró el archivo de la primera"
    assert json.loads(p1.read_text(encoding="utf-8"))["modo"] == "TANDA_A"


def test_registro_none_no_escribe_nada(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path))
    assert write_teardown_record(None) is None
    assert not (tmp_path / "desmontajes").exists()


def test_la_db_no_se_toca(tmp_path, monkeypatch):
    """RNF-01. El feature es observacional: la bitácora va a un archivo, nunca a la DB."""
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    if not db.exists():
        pytest.skip("DB no presente")
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    write_teardown_record(_registro(tmp_path, monkeypatch))
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes


# --- Reserva del nombre ----------------------------------------------------------------------
# `reservar_rutas` es la autoridad única sobre "cómo se llama un artefacto de audit/ sin pisar a
# otro". Antes esa decisión estaba escrita dos veces (bitácora y censo) y mal las dos.

def test_la_reserva_ocupa_el_nombre_en_el_disco(tmp_path, reloj_de_pared_congelado):
    """La reserva no es un cálculo, es un hecho en el filesystem: el archivo queda creado (vacío)
    en el mismo paso en que se elige el nombre. Eso es lo que hace que un segundo escritor —otro
    hilo, u otro proceso— no pueda elegir el mismo."""
    (ruta,) = reservar_rutas(tmp_path / "d", "desmontaje")
    assert ruta.exists() and ruta.read_bytes() == b""


def test_el_juego_de_hermanos_se_toma_entero_o_ninguno(tmp_path, reloj_de_pared_congelado):
    """El censo escribe `.json` y `.md` bajo un mismo sello. Si el `.md` del primer candidato ya
    está tomado, el par entero se corre al siguiente número: repartirse el par dejaría dos
    reportes a medias, cada uno con la mitad del otro."""
    carpeta = tmp_path / "c"
    carpeta.mkdir()
    # Tomamos de antemano solo el hermano `.md` del primer candidato.
    sello = f"{reloj_de_pared_congelado.now():%Y%m%d_%H%M%S_%f}"
    ocupado = carpeta / f"{sello}_censo_roster.md"
    ocupado.write_text("reporte previo", encoding="utf-8")

    js, md = reservar_rutas(carpeta, "censo_roster", ("json", "md"))

    assert js.stem == md.stem, "los hermanos deben compartir sello"
    assert md != ocupado, "el par pisó un reporte que ya existía"
    assert ocupado.read_text(encoding="utf-8") == "reporte previo"
    assert not (carpeta / f"{sello}_censo_roster.json").exists(), \
        "quedó reservado el .json del candidato que se descartó"


def test_la_reserva_se_rinde_en_vez_de_girar_para_siempre(
        tmp_path, monkeypatch, reloj_de_pared_congelado):
    """Con todos los nombres ocupados el lazo tiene que terminar. Un bucle infinito acá cuelga el
    cierre de una tanda, que es justo el momento en que el usuario está esperando el toast."""
    monkeypatch.setattr("app.core.unique_paths.MAX_INTENTOS", 2)  # el tope vive en la primitiva compartida
    carpeta = tmp_path / "d"
    carpeta.mkdir()
    sello = f"{reloj_de_pared_congelado.now():%Y%m%d_%H%M%S_%f}"
    for n in ("", "_2"):
        (carpeta / f"{sello}_desmontaje{n}.json").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        reservar_rutas(carpeta, "desmontaje")
