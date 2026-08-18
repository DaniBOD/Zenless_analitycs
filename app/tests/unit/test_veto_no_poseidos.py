"""El veto del latch: un PJ que declaraste NO tener no puede identificarse como uno tuyo.

El matcher elige *el más parecido del roster*, y el roster es `agents` — o sea, solo lo que sí
tenés. Frente a un personaje ajeno no existe la opción correcta, así que gana un parecido
coincidental: medido el 2026-08-17, `Norma→Nekomata 0.615` y `Lichter→Alice 0.667`, los dos por
encima del umbral de 0.55. Pararte sobre un gris del menú no deja al sistema en "no sé": lo deja
convencido de que estás en otro personaje, y el latch le atribuye a ése los discos que vengan.

Subir el umbral no sirve: 0.55 existe para tolerar lecturas sucias de PJs que SÍ tenés, y subirlo
las rompería. Lo que faltaba no era rigor, era **el nombre ausente** — y eso lo aporta la
declaración del roster, que es la primera lista autoritativa de lo que no poseés.

Así que los no poseídos entran a la comparación como **señuelos**: no se pueden identificar (no
son tuyos), pero pueden GANAR, y cuando ganan el matcher se abstiene.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core import parser_agent_stats as p
from app.core.roster_declaration import no_poseidos_declarados

_AGENTS = [
    ("Nekomata", "Ataque", "Físico"),
    ("Alice", "Anomalía", "Físico"),
    ("Zhao", "Defensa", "Fuego"),
]


def _crear_db(tmp_path, *, tandas=((("Norma", 0), ("Lichter", 0), ("Nekomata", 1)),)):
    db = tmp_path / "veto.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE agents (nombre TEXT, rol TEXT, elemento TEXT, pv REAL, "
                "ataque REAL, defensa REAL, prob_critico REAL, dano_critico REAL)")
    con.executemany("INSERT INTO agents (nombre, rol, elemento) VALUES (?,?,?)", _AGENTS)
    con.execute("CREATE TABLE roster_declarations (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts TEXT NOT NULL, nombre TEXT NOT NULL, poseido INTEGER NOT NULL, "
                "fuente TEXT NOT NULL DEFAULT 'usuario')")
    for i, tanda in enumerate(tandas):
        ts = f"2026-08-{17 + i:02d}T10:00:00.000000"
        con.executemany("INSERT INTO roster_declarations (ts, nombre, poseido) VALUES (?,?,?)",
                        [(ts, n, v) for n, v in tanda])
    con.commit(); con.close()
    return db


@pytest.fixture
def dominio(tmp_path, monkeypatch):
    db = _crear_db(tmp_path)
    monkeypatch.setenv("DANIBOD_DB_PATH", str(db))
    monkeypatch.setattr(p, "_ROSTER_CACHE", None, raising=False)
    monkeypatch.setattr(p, "_NO_POSEIDOS_CACHE", None, raising=False)
    yield db
    monkeypatch.setattr(p, "_ROSTER_CACHE", None, raising=False)
    monkeypatch.setattr(p, "_NO_POSEIDOS_CACHE", None, raising=False)


# --- el lector de la declaración ---------------------------------------------------------------

def test_lee_los_no_poseidos_de_la_declaracion(dominio):
    assert no_poseidos_declarados(dominio) == {"Norma", "Lichter"}


def test_solo_cuenta_la_ULTIMA_tanda(tmp_path, monkeypatch):
    """El usuario puede sacar a un PJ que no tenía. Si la declaración vieja siguiera pesando, ese
    PJ quedaría vetado para siempre — imposible de identificar justo cuando empieza a importar."""
    db = _crear_db(tmp_path, tandas=(
        (("Norma", 0), ("Lichter", 0)),      # ayer no tenía a ninguno
        (("Norma", 1), ("Lichter", 0)),      # hoy sacó a Norma
    ))
    assert no_poseidos_declarados(db) == {"Lichter"}


def test_sin_declaracion_no_hay_senuelos(tmp_path):
    """Nunca puede ser un requisito duro: sin declaración el sistema queda como antes, no roto."""
    db = tmp_path / "vacia.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE agents (nombre TEXT)")
    con.commit(); con.close()
    assert no_poseidos_declarados(db) == set()


def test_una_db_inexistente_devuelve_vacio_y_no_explota(tmp_path):
    assert no_poseidos_declarados(tmp_path / "no_existe.db") == set()


# --- el veto -----------------------------------------------------------------------------------

def test_un_no_poseido_ya_no_se_hace_pasar_por_un_pj_propio(dominio):
    """El caso que motivó todo: sin señuelos, 'Norma' devolvía Nekomata con 0.615."""
    nombre, _rol, _elem, cand, sim = p._match_agent_scored("Norma")
    assert nombre is None, "no puede identificar a un PJ que declaraste no tener"
    assert cand == "Norma" and sim == pytest.approx(1.0), \
        "y tiene que decir a QUIÉN reconoció: 'no sé' y 'sé que no es tuyo' no son lo mismo"


def test_el_veto_no_toca_a_los_que_si_tenes(dominio):
    nombre, _r, _e, _c, sim = p._match_agent_scored("Nekomata")
    assert nombre == "Nekomata" and sim == pytest.approx(1.0)


def test_una_lectura_SUCIA_de_un_pj_propio_sobrevive_al_veto(dominio):
    """Es lo que se rompería subiendo el umbral, que era la otra salida posible. 'Nekomat' es un
    misread real de OCR y tiene que seguir resolviendo a Nekomata."""
    nombre, _r, _e, _c, _s = p._match_agent_scored("Nekomat")
    assert nombre == "Nekomata"


def test_el_senuelo_tiene_que_GANAR_para_vetar(dominio):
    """Empatar no alcanza. Un señuelo que vetara por parecerse *tanto como* el propio convertiría
    la declaración en una forma de apagar la identificación de un PJ con build."""
    ganado = p._name_similarity({"nekomata"}, "nekomata", {"norma"}, "norma")
    propio = p._name_similarity({"nekomata"}, "nekomata", {"nekomata"}, "nekomata")
    assert ganado < propio
    assert p._match_agent_scored("Nekomata")[0] == "Nekomata"


def test_un_declarado_que_ADEMAS_esta_en_agents_no_se_veta(tmp_path, monkeypatch):
    """Conflicto: la declaración dice que no lo tenés y la fila con datos dice que sí. Vetar
    dejaría un PJ con build imposible de identificar, en silencio. La fila manda; el sobrante ya
    se marca en `notas` por el flujo de la declaración, que es donde ese conflicto se resuelve."""
    db = _crear_db(tmp_path, tandas=((("Nekomata", 0), ("Norma", 0)),))
    monkeypatch.setenv("DANIBOD_DB_PATH", str(db))
    monkeypatch.setattr(p, "_ROSTER_CACHE", None, raising=False)
    monkeypatch.setattr(p, "_NO_POSEIDOS_CACHE", None, raising=False)
    assert p._match_agent_scored("Nekomata")[0] == "Nekomata"
    monkeypatch.setattr(p, "_ROSTER_CACHE", None, raising=False)
    monkeypatch.setattr(p, "_NO_POSEIDOS_CACHE", None, raising=False)


def test_ninguno_de_los_no_poseidos_REALES_veta_a_un_pj_propio():
    """Guarda sobre los datos de verdad, no sobre el fixture: si alguno de los nombres declarados
    fuera subconjunto de token de un PJ propio (el caso `Billy` ⊂ `Billy Estelar`), el señuelo se
    llevaría 0.85+ y apagaría a ese PJ para siempre. Hoy no pasa — y si un patch trae un nombre
    así, este test avisa antes de que el latch se quede mudo."""
    from app.db.connection import get_db_path
    db = get_db_path()
    if not db.exists():
        pytest.skip("sin DB de dominio")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        tablas = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "roster_declarations" not in tablas:
            pytest.skip("todavía no se declaró el roster")
        propios = [p._norm_name(r[0]) for r in con.execute(
            "SELECT nombre FROM agents")]
        ajenos = [p._norm_name(n) for n in no_poseidos_declarados(db)]
    finally:
        con.close()
    for a in ajenos:
        for pr in propios:
            if a == pr:
                continue
            sim = p._name_similarity(set(pr.split()), pr, set(a.split()), a)
            assert sim < 0.85, f"el señuelo {a!r} apagaría a {pr!r} (sim {sim:.3f})"
