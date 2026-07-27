"""Auditoría read-only del catálogo `weapons` contra la lista canónica de W-Engines.

NO toca la DB. Compara cada fila por su `nombre_en` contra la referencia y reporta:
  - nombres EN que NO existen en el juego (mapeo roto / desambiguación inventada),
  - rareza y tipo que no coinciden con la referencia,
  - W-Engines de la referencia que faltan en el catálogo.

Referencia: Game8 (fuente autorizada por CLAUDE.md RNF-02), lista completa de W-Engines
consultada el 2026-07-26. La rareza y el tipo salen de ahí; los nombres en ESPAÑOL NO —
esos vienen del juego del usuario y no se inventan (RNF-02).
"""
from __future__ import annotations

import sqlite3
import sys
import unicodedata
from pathlib import Path

# --- Referencia canónica: NOMBRE_EN | RAREZA | TIPO (Game8, 2026-07-26) -------------------------
REFERENCIA: list[tuple[str, str, str]] = [
    # S (44)
    ("Sol Exuvia", "S", "Ataque"), ("Chief Sidekick", "S", "Aturdimiento"),
    ("Joyau Dore", "S", "Anomalía"), ("Frostfall Sickle", "S", "Anomalía"),
    ("Starlight Rider Faceplate", "S", "Ruptura"), ("Serpentine Seeker", "S", "Ataque"),
    ("Angel in the Shell", "S", "Anomalía"), ("Thoughtbop", "S", "Soporte"),
    ("Cloudcleave Radiance", "S", "Ataque"), ("Half-Sugar Bunny", "S", "Defensa"),
    ("Wrathful Vajra", "S", "Ruptura"), ("Yesterday Calls", "S", "Aturdimiento"),
    ("Kraken's Cradle", "S", "Ruptura"), ("Dreamlit Hearth", "S", "Soporte"),
    ("Bellicose Blaze", "S", "Ataque"), ("Cordis Germina", "S", "Ataque"),
    ("Practiced Perfection", "S", "Anomalía"), ("Metanukimorphosis", "S", "Soporte"),
    ("Qingming Birdcage", "S", "Ruptura"), ("Roaring Fur-nace", "S", "Aturdimiento"),
    ("Myriad Eclipse", "S", "Ataque"), ("Flight of Fancy", "S", "Anomalía"),
    ("Severed Innocence", "S", "Ataque"), ("Spectral Gaze", "S", "Aturdimiento"),
    ("Elegant Vanity", "S", "Soporte"), ("Heartstring Nocturne", "S", "Ataque"),
    ("Zanshin Herb Case", "S", "Ataque"), ("Hailstorm Shrine", "S", "Anomalía"),
    ("Blazing Laurel", "S", "Aturdimiento"), ("Timeweaver", "S", "Anomalía"),
    ("Flamemaker Shaker", "S", "Anomalía"), ("Tusks of Fury", "S", "Defensa"),
    ("Sharpened Stinger", "S", "Anomalía"), ("Ice-Jade Teapot", "S", "Aturdimiento"),
    ("Riot Suppressor Mark VI", "S", "Ataque"), ("Deep Sea Visitor", "S", "Ataque"),
    ("Hellfire Gears", "S", "Aturdimiento"), ("The Restrained", "S", "Aturdimiento"),
    ("Steel Cushion", "S", "Ataque"), ("The Brimstone", "S", "Ataque"),
    ("Weeping Cradle", "S", "Soporte"), ("Fusion Compiler", "S", "Anomalía"),
    ("Neon Fantasies", "S", "Aturdimiento"), ("Ode of Resurrected Wings", "S", "Anomalía"),
    # A (36)
    ("Boisterous Echoes", "A", "Anomalía"), ("The Simmering Pot", "A", "Aturdimiento"),
    ("Cauldron of Clarity", "A", "Ruptura"), ("Grill O'Wisp", "A", "Ruptura"),
    ("Reel Projector", "A", "Defensa"), ("Radiowave Journey", "A", "Ruptura"),
    ("Puzzle Sphere", "A", "Ruptura"), ("Tremor Trigram Vessel", "A", "Defensa"),
    ("Box Cutter", "A", "Aturdimiento"), ("Marcato Desire", "A", "Ataque"),
    ("Gilded Blossom", "A", "Ataque"), ("Peacekeeper - Specialized", "A", "Defensa"),
    ("Kaboom the Cannon", "A", "Soporte"), ("Roaring Ride", "A", "Anomalía"),
    ("Big Cylinder", "A", "Defensa"), ("Starlight Engine Replica", "A", "Ataque"),
    ("Housekeeper", "A", "Ataque"), ("The Vault", "A", "Soporte"),
    ("Demara Battery Mark II", "A", "Aturdimiento"), ("Drill Rig - Red Axis", "A", "Ataque"),
    ("Street Superstar", "A", "Ataque"), ("Slice of Time", "A", "Soporte"),
    ("Rainforest Gourmet", "A", "Anomalía"), ("Starlight Engine", "A", "Ataque"),
    ("Steam Oven", "A", "Aturdimiento"), ("Precious Fossilized Core", "A", "Aturdimiento"),
    ("Original Transmorpher", "A", "Defensa"), ("Weeping Gemini", "A", "Anomalía"),
    ("Bunny Band", "A", "Defensa"), ("Cannon Rotor", "A", "Ataque"),
    ("Six Shooter", "A", "Aturdimiento"), ("Electro-Lip Gloss", "A", "Anomalía"),
    ("Unfettered Game Ball", "A", "Soporte"), ("Spring Embrace", "A", "Defensa"),
    ("Bashful Demon", "A", "Soporte"), ("Knight's Extolment", "A", "Ataque"),
    # B (15)
    ("Cinder - Cobalt", "B", "Ruptura"), ("Vortex - Revolver", "B", "Aturdimiento"),
    ("Vortex - Arrow", "B", "Aturdimiento"), ("Magnetic Storm - Bravo", "B", "Anomalía"),
    ("Reverb - Mark I", "B", "Soporte"), ("Reverb - Mark II", "B", "Soporte"),
    ("Reverb - Mark III", "B", "Soporte"), ("Vortex - Hatchet", "B", "Aturdimiento"),
    ("Lunar - Decrescent", "B", "Ataque"), ("Lunar - Pleniluna", "B", "Ataque"),
    ("Lunar - Noviluna", "B", "Ataque"), ("Magnetic Storm - Alpha", "B", "Anomalía"),
    ("Magnetic Storm - Charlie", "B", "Anomalía"), ("Identity - Inflection", "B", "Defensa"),
    ("Identity - Base", "B", "Defensa"),
]


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace("-", " ").replace("'", "").split())


def main() -> int:
    db = Path(sys.argv[1] if len(sys.argv) > 1 else "db/danibod_zzz_v2.db")
    con = sqlite3.connect(db)
    filas = list(con.execute(
        "select id, nombre, nombre_en, rareza, tipo_especialidad, atk_base from weapons order by id"))
    ref = {norm(en): (en, rar, tipo) for en, rar, tipo in REFERENCIA}

    rotos, rareza_mal, tipo_mal, ok = [], [], [], []
    usados: set[str] = set()

    for wid, es, en, rar, tipo, atk in filas:
        if es == "Sin arma":
            continue
        k = norm(en)
        if k not in ref:
            rotos.append((wid, es, en, rar, tipo))
            continue
        usados.add(k)
        ren, rrar, rtipo = ref[k]
        if rar != rrar:
            rareza_mal.append((wid, es, en, rar, rrar))
        if (tipo or "") != rtipo:
            tipo_mal.append((wid, es, en, tipo, rtipo))
        if rar == rrar and (tipo or "") == rtipo:
            ok.append((wid, es, en))

    faltan = [(en, rar, tipo) for en, rar, tipo in REFERENCIA if norm(en) not in usados]

    print(f"# Auditoría del catálogo `weapons`\n")
    print(f"Filas (sin 'Sin arma'): **{len(filas) - 1}** · Referencia: **{len(REFERENCIA)}** W-Engines\n")

    print(f"## ✅ Coinciden en rareza y tipo — {len(ok)}\n")
    for wid, es, en in ok:
        print(f"- `{wid:3d}` {es} · {en}")

    print(f"\n## ⚠️ Rareza distinta a la referencia — {len(rareza_mal)}\n")
    print("| id | nombre (ES) | nombre_en | DB | referencia |")
    print("|---|---|---|---|---|")
    for wid, es, en, rar, rrar in rareza_mal:
        print(f"| {wid} | {es} | {en} | **{rar}** | **{rrar}** |")

    print(f"\n## ⚠️ Tipo distinto a la referencia — {len(tipo_mal)}\n")
    print("| id | nombre (ES) | nombre_en | DB | referencia |")
    print("|---|---|---|---|---|")
    for wid, es, en, tipo, rtipo in tipo_mal:
        print(f"| {wid} | {es} | {en} | {tipo} | {rtipo} |")

    print(f"\n## ❌ `nombre_en` que NO existe en el juego — {len(rotos)}\n")
    print("Mapeo español↔inglés roto. La rareza de estas filas no es confiable: se derivó de un\n"
          "match contra un arma que no existe. **El nombre ES es la única pista buena** — viene\n"
          "del juego del usuario.\n")
    print("| id | nombre (ES) | nombre_en inventado | rareza DB | tipo DB |")
    print("|---|---|---|---|---|")
    for wid, es, en, rar, tipo in rotos:
        print(f"| {wid} | {es} | `{en}` | {rar} | {tipo} |")

    print(f"\n## 🔍 En la referencia pero NO en el catálogo — {len(faltan)}\n")
    print("Ojo: algunas pueden estar presentes bajo un `nombre_en` roto de la tabla de arriba.\n")
    print("| nombre_en | rareza | tipo |")
    print("|---|---|---|")
    for en, rar, tipo in sorted(faltan, key=lambda x: (x[1], x[0])):
        print(f"| {en} | {rar} | {tipo} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
