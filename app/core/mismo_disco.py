"""¿Es el mismo disco? — la única regla (SPEC 2026-10-02 "El Obtenido guarda los discos", puntos 4 y 6).

Dos lugares se hacían esta pregunta mirando sólo el set (y el slot):

- la confirmación de una mejora (`sync_upgrade`): otro disco del mismo set y slot confirmaba la
  mejora y le escribía sus stats a la fila mejorada;
- el refresco de S17 (`sync_equip`): cambiar un disco por OTRO del mismo set se tomaba como
  "subió de nivel" y pisaba la fila.

Visto tres veces en el QA en vivo del farmeo de Claret (2026-10-02). Quien llama ya comprobó el set
y el slot, cada uno con su resolver; acá se mira lo que separa dos discos del mismo set y slot. La
regla sale de cómo sube un disco en el juego: el main no cambia, el nivel no baja, los substats
sólo se suman (el 4.º aparece en +3) y sus rolls sólo crecen.
"""
from __future__ import annotations

from app.core.stats_vocab import _norm_key


def _huella(d) -> tuple[str, int | None, dict[str, int]]:
    """(main, nivel, {substat: rolls}) de un `DiscParsed` o de un `Disc` de la DB."""
    if hasattr(d, "main_stat_canon"):   # DiscParsed
        main = d.main_stat_canon or d.main_stat_raw or ""
        subs = {_norm_key(s.nombre_canon or s.nombre_raw or ""): s.rolls or 0
                for s in (d.subs or []) if (s.nombre_canon or s.nombre_raw)}
    else:                                # Disc
        main = d.main_stat or ""
        subs = {_norm_key(n): r or 0 for n, _v, _u, r in (d.subs or []) if n}
    return _norm_key(main), d.nivel, subs


def es_el_mismo_disco(antes, ahora) -> bool:
    """True si `ahora` puede ser `antes` (igual o mejorado). Set y slot los compara quien llama."""
    main_a, nivel_a, subs_a = _huella(antes)
    main_b, nivel_b, subs_b = _huella(ahora)
    if main_a != main_b:
        return False
    if nivel_a is not None and nivel_b is not None:
        if nivel_b < nivel_a:
            return False
        if nivel_b == nivel_a:
            return subs_a == subs_b          # sin subir de nivel no pudo cambiar nada
    if not set(subs_a) <= set(subs_b):
        return False
    return all(subs_b[n] >= r for n, r in subs_a.items())


def crecimiento(d) -> int:
    """#substats + Σrolls − nivel//3 de un `DiscParsed` o un `Disc`. Cada 3 niveles el disco gana un
    substat (si tiene 3) o un roll, así que este número NO cambia al subir: 3 o 4, según con
    cuántos substats cayó. Medido sobre la DB el 2026-10-02: 426 de 427 discos (el otro, un Nv 0
    con 2 substats)."""
    _main, nivel, subs = _huella(d)
    return len(subs) + sum(subs.values()) - (nivel or 0) // 3


def es_el_mismo_disco_subido(antes, ahora) -> bool:
    """`es_el_mismo_disco` + exactamente lo que dan los umbrales de nivel cruzados. Es la prueba
    de que `ahora` es `antes` mejorado Y bien leído: un "+N" perdido o un frame de animación rompe
    la cuenta."""
    return es_el_mismo_disco(antes, ahora) and crecimiento(antes) == crecimiento(ahora)
