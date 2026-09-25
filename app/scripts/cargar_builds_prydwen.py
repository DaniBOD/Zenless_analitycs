"""Carga los builds recomendados por PJ (mig 43) desde una captura de las guías de Prydwen.

Daniel, 2026-09-25: el motor mandaba Armonía umbría a Ye Shunguang y Balada de la rama y la espada a
Nangong Yu porque el set sólo entraba por ROL (SPEC, casos 12-13; R18-R20). Esto llena el
conocimiento POR PJ: los 4pc y 2pc de cada guía, los principales de los discos 4-6 y los substats
por niveles. No decide nada: el motor los usa aparte.

La captura (`audit/prydwen/<fecha>_captura_prydwen.jsonl`) son las líneas de la sección "Best Disk
Drives" de cada guía, leídas con el navegador (Prydwen responde 403 a un cliente HTTP), sin la
prosa de las notas. Una línea por guía: `{"u": slug, "i": "Elemento/Rol", "b": "Patch X",
"s": "línea|línea|…"}`. El parser es de este módulo para que tenga tests: la captura es evidencia,
no se interpreta a mano.

Escritura con RNF-01: backup, transacción, FK activas, `foreign_key_check` e `integrity_check`.
Reemplaza TODO lo de fuente 'prydwen' (una captura nueva es la foto entera, no un parche).

Uso:
    python app/scripts/cargar_builds_prydwen.py audit/prydwen/2026-09-25_captura_prydwen.jsonl \
        --capturado 2026-09-25 [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.db.connection import get_db_path, respaldar_db  # noqa: E402

FUENTE = "prydwen"
URL_BASE = "https://www.prydwen.gg/zenless/characters/"

#: slug de Prydwen → `agents.nombre`. Los que difieren del inglés son los mismos alias de
#: `asset_resolver` (Sporos → Seed, Gatillo → Trigger, …).
AGENTE_POR_SLUG: dict[str, str] = {
    "burnice": "Burnice", "miyabi": "Miyabi", "lycaon": "Lycaon", "koleda": "Koleda",
    "caesar": "César", "soldier-11": "N.º 11", "manato": "Manato", "piper": "Piper",
    "lucy": "Lucy", "pan-yinhu": "Pan Yinhu", "pulchra": "Pulchra", "billy-kid": "Billy",
    "soukaku": "Soukaku", "nicole-demara": "Nicole", "anby-demara": "Anby",
    "harumasa": "Harumasa", "seth": "Seth", "corin": "Corin", "anton": "Antón", "ben": "Ben",
    "sunna": "Sunna", "lucia": "Lucía", "ye-shunguang": "Ye Shunguang",
    "ukinami-yuzuha": "Yuzuha", "alice": "Alice", "nangong-yu": "Nangong Yu",
    "dialyn": "Dialyn", "seed": "Sporos", "ju-fufu": "Ju Fufu",
    "anby-demara-soldier-0": "N.º 0: Anby", "yixuan": "Yixuan", "trigger": "Gatillo",
    "zhao": "Zhao", "vivian": "Vivian", "evelyn": "Evelyn", "astra-yao": "Astra Yao",
    "orphie-and-magus": "Orfia y Magas", "jane-doe": "Jane", "qingyi": "Qingyi",
    "zhu-yuan": "Zhu Yuan", "grace-howard": "Grace", "rina": "Rina", "yanagi": "Yanagi",
    "ellen": "Ellen", "nekomata": "Nekomata", "cissia": "Cissia",
    "billy-starlight": "Billy Estelar", "velina": "Velina", "pyrois": "Pyrois",
    "remielle": "Remielle Dan", "aria": "Aria", "claret": "Claret Flint",
}

_ELEMENTO = {"physical": "Físico", "fire": "Fuego", "ice": "Hielo", "electric": "Eléctrico",
             "ether": "Éter", "wind": "Viento"}

#: Rótulo de la guía → nombre canónico del proyecto (`stats_vocab`). En el juego, "Anomaly
#: Proficiency" es la línea plana (9 por mejora) que la DB llama "Maestría de Anomalía", y "Anomaly
#: Mastery" el principal % del disco 6 que la DB llama "Tasa de Anomalía".
_STAT: dict[str, str] = {
    "crit rate": "Prob. Crítica", "crit dmg": "Daño Crítico",
    "atk%": "ATK%", "atk": "ATK", "hp%": "HP%", "hp": "HP", "def%": "DEF%", "def": "DEF",
    "pen": "Perforación", "pen ratio": "Tasa de Perforación",
    "anomaly proficiency": "Maestría de Anomalía", "anomaly mastery": "Tasa de Anomalía",
    "energy regen": "Recarga de Energía", "impact": "Impacto",
}

LINEAS = {"d4": "principal_4", "d5": "principal_5", "d6": "principal_6", "subs": "substat"}


def canon_stat(texto: str) -> str | None:
    """Un rótulo de la guía ("CRIT Rate%", "Flat PEN", "Ice DMG%", "Anomaly Profiency") → el
    nombre canónico, o None si no se reconoce (el llamador lo reporta; no se adivina, RNF-02)."""
    t = re.sub(r"\(.*?\)", "", texto).strip().lower()
    t = t.replace("profiency", "proficiency")          # errata de la guía (César, Pulchra)
    t = re.sub(r"^flat\s+", "", t)
    t = re.sub(r"\s*%\s*$", "%", t)                     # "ATK %" → "atk%"
    m = re.fullmatch(r"(physical|fire|ice|electric|ether|wind) dmg%?", t)
    if m:
        return "Bono Daño " + _ELEMENTO[m.group(1)]
    if t in _STAT:
        return _STAT[t]
    sin_pct = t.rstrip("%")
    if sin_pct in ("crit rate", "crit dmg", "pen ratio"):
        return _STAT[sin_pct]
    return None


def niveles(expr: str) -> tuple[list[tuple[int, str, str]], list[str]]:
    """"A = B > C >= D" → [(1, A), (1, B), (2, C), (3, D)] y los rótulos no reconocidos.

    '=' comparte nivel; '>', '>=' y '>>>' bajan uno. "ATK%/Flat ATK" son dos stats del mismo
    nivel. Un stat repetido en la misma expresión se queda con su primer (mejor) nivel.
    """
    partes = re.split(r"\s*(>>>|>=|>|=)\s*", expr.strip())
    out: list[tuple[int, str, str]] = []
    vistos: set[str] = set()
    desconocidos: list[str] = []
    nivel = 1
    for i, parte in enumerate(partes):
        if i % 2 == 1:
            if parte != "=":
                nivel += 1
            continue
        for alt in parte.split("/"):
            c = canon_stat(alt)
            if c is None:
                desconocidos.append(alt.strip())
            elif c not in vistos:
                vistos.add(c)
                out.append((nivel, c, parte.strip()))
    return out, desconocidos


@dataclass
class Guia:
    slug: str
    info: str
    version: str | None
    sets: list[dict] = field(default_factory=list)       # {orden, set, rango, puntaje, dos: [{sets, rec}]}
    variantes: list[dict] = field(default_factory=list)  # {variante, d4, d5, d6, subs}
    problemas: list[str] = field(default_factory=list)


def parsear(linea: dict) -> Guia:
    """Una línea de la captura → la guía estructurada. Lo que no encaja va a `problemas`."""
    g = Guia(slug=linea["u"], info=linea.get("i", ""), version=linea.get("b"))
    toks = [t for t in linea["s"].split("|") if t]
    corte = toks.index("BEST DISK DRIVES STATS") if "BEST DISK DRIVES STATS" in toks else len(toks)
    actual = grupo = None
    rango = puntaje = None
    for t in toks[:corte]:
        if re.fullmatch(r"\d+(\.\d+)?%", t):
            puntaje, rango = float(t[:-1]), None
        elif re.fullmatch(r"\d+", t):
            puntaje, rango = None, int(t)
        elif m := re.fullmatch(r"(.+) \(4-PC\)", t):
            actual = {"orden": len(g.sets) + 1, "set": m.group(1), "rango": rango,
                      "puntaje": puntaje, "dos": []}
            g.sets.append(actual)
            grupo = None
        elif t == "2P" and actual is not None:
            grupo = {"sets": [], "rec": False}
            actual["dos"].append(grupo)
        elif t == "(Recommended)" and grupo is not None:
            grupo["rec"] = True
        elif grupo is not None:
            grupo["sets"].append(t)
        else:
            g.problemas.append(f"token suelto en sets: {t!r}")

    resto = toks[corte + 1:]
    cuerpo = resto[:resto.index("END")] if "END" in resto else resto
    var: dict = {"variante": None}
    k = 0
    while k < len(cuerpo):
        t = cuerpo[k]
        if (m := re.fullmatch(r"Disk ([456])", t)) and k + 1 < len(cuerpo):
            clave = f"d{m.group(1)}"
            if clave in var:                     # segunda build sin rótulo (César)
                g.variantes.append(var)
                var = {"variante": None}
            var[clave] = cuerpo[k + 1]
            k += 2
            continue
        if t.startswith("Substats:"):
            var["subs"] = t[len("Substats:"):].strip()
        else:                                    # rótulo de variante ("CRIT Build")
            if len(var) > 1:
                g.variantes.append(var)
            var = {"variante": t}
        k += 1
    if len(var) > 1:
        g.variantes.append(var)
    if len(g.variantes) == 1:
        g.variantes[0]["variante"] = "única"
    else:
        for i, v in enumerate(g.variantes, 1):
            v["variante"] = v["variante"] or f"variante {i}"
    if not g.sets:
        g.problemas.append("sin sets 4pc")
    if not g.variantes:
        g.problemas.append("sin stats")
    return g


@dataclass
class Filas:
    sets_4pc: list[tuple] = field(default_factory=list)
    sets_2pc: list[tuple] = field(default_factory=list)
    stats: list[tuple] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)


def armar_filas(guias: list[Guia], agentes: dict[str, int], sets_en: dict[str, int],
                capturado: str) -> Filas:
    """Las guías → filas de las tres tablas. Un PJ, set o stat que no se reconoce NO entra y se
    reporta (RNF-02: no se adivina)."""
    f = Filas()
    for g in guias:
        nombre = AGENTE_POR_SLUG.get(g.slug)
        agente = agentes.get(nombre) if nombre else None
        if agente is None:
            f.problemas.append(f"{g.slug}: sin PJ en la DB ({nombre!r})")
            continue
        f.problemas += [f"{g.slug}: {p}" for p in g.problemas]
        url = URL_BASE + g.slug
        for o in g.sets:
            s4 = sets_en.get(o["set"])
            if s4 is None:
                f.problemas.append(f"{g.slug}: 4pc desconocido {o['set']!r}")
                continue
            f.sets_4pc.append((agente, s4, o["orden"], o["rango"], o["puntaje"], FUENTE, url,
                               g.version, capturado))
            for n, gr in enumerate(o["dos"], 1):
                for nombre_set in gr["sets"]:
                    s2 = sets_en.get(nombre_set)
                    if s2 is None:
                        f.problemas.append(f"{g.slug}: 2pc desconocido {nombre_set!r}")
                    elif s2 != s4:
                        f.sets_2pc.append((agente, s4, s2, n, int(gr["rec"])))
        for v in g.variantes:
            for clave, linea in LINEAS.items():
                if clave not in v:
                    continue
                niv, desconocidos = niveles(v[clave])
                f.problemas += [f"{g.slug}: {linea} no reconocido {d!r}" for d in desconocidos]
                for nivel, stat, texto in niv:
                    f.stats.append((agente, v["variante"], linea, nivel, stat, texto, FUENTE, url,
                                    g.version, capturado))
    return f


def cargar(db: Path, captura: Path, capturado: str, dry_run: bool = False) -> tuple[Filas, Path | None]:
    guias = [parsear(json.loads(l)) for l in captura.read_text(encoding="utf-8").splitlines() if l.strip()]
    con = sqlite3.connect(db)
    try:
        agentes = {n: i for i, n in con.execute("SELECT id, nombre FROM agents")}
        sets_en = {n: i for i, n in con.execute("SELECT id, nombre_en FROM disc_sets") if n}
        filas = armar_filas(guias, agentes, sets_en, capturado)
    finally:
        con.close()
    if dry_run:
        return filas, None
    backup = respaldar_db(db, "prebuilds")
    con = sqlite3.connect(db, isolation_level=None)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("BEGIN")
        con.execute("DELETE FROM pj_sets_2pc WHERE (agente_id, set_4p_id) IN "
                    "(SELECT agente_id, set_id FROM pj_sets_4pc WHERE fuente = ?)", (FUENTE,))
        con.execute("DELETE FROM pj_sets_4pc WHERE fuente = ?", (FUENTE,))
        con.execute("DELETE FROM pj_stats_recomendados WHERE fuente = ?", (FUENTE,))
        con.executemany("INSERT INTO pj_sets_4pc (agente_id, set_id, orden, rango_fuente, "
                        "puntaje_fuente, fuente, url, version_guia, capturado) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", filas.sets_4pc)
        con.executemany("INSERT INTO pj_sets_2pc (agente_id, set_4p_id, set_id, grupo, recomendado) "
                        "VALUES (?, ?, ?, ?, ?)", filas.sets_2pc)
        con.executemany("INSERT INTO pj_stats_recomendados (agente_id, variante, linea, nivel, stat, "
                        "texto_guia, fuente, url, version_guia, capturado) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", filas.stats)
        rotas = con.execute("PRAGMA foreign_key_check").fetchall()
        if rotas:
            raise RuntimeError(f"FK rotas: {rotas[:5]}")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
    if integridad != "ok":
        raise RuntimeError(f"integrity_check: {integridad}")
    return filas, backup


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("captura", type=Path)
    ap.add_argument("--capturado", required=True, help="fecha de la captura, AAAA-MM-DD")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    filas, backup = cargar(a.db or get_db_path(), a.captura, a.capturado, a.dry_run)
    print(f"4pc: {len(filas.sets_4pc)} · 2pc: {len(filas.sets_2pc)} · stats: {len(filas.stats)}")
    print(f"PJs: {len({f[0] for f in filas.sets_4pc})}")
    for p in filas.problemas:
        print(f"  ⚠️ {p}")
    print("dry-run: no se escribió nada" if backup is None else f"backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
