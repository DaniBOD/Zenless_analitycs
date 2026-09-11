# Patch v3.2 "Their Secret Histories" — notas de regresión (QA-07)

**Publicado:** 2026-09-09 · **Fase A aplicada:** 2026-09-10
**Backup pre-patch:** `db/danibod_zzz_v2.backup_prepatch_20260910_220830.db` (gitignoreado)
**Snapshot de filas:** `Documentacion/QA/evidencia/baseline_prepatch_3.2_20260910_220830.json`
**Smoke L1:** `integrity_check` ok · `foreign_key_check` 0 filas · 32 tablas

> ⚠️ **Nada de lo que sigue está confirmado contra la pantalla** (RNF-02). Las fuentes se
> contradicen en datos básicos, y en este proyecto el catálogo se audita contra la pantalla, no
> contra la wiki. Por eso ningún dato de acá se escribió en la DB.

## Cambios identificados

### Agentes nuevos

| agente | lo que dicen las fuentes | contradicción |
|---|---|---|
| **Claret** | S · facción **Flint Workshop** · banner fase 1 (09-09 → 09-30) | **Eléctrico · Armorer** (Game8 builds, Gamefragger, Icy Veins) contra **Fuego · Ataque** (resumen de la página de livestream de Game8). El segundo sale de un resumidor automático y probablemente esté mal — pero "probablemente" no alcanza |
| **Roxy** | banner fase 2 (09-30 → 10-20) · Flint Workshop | "S · Viento · Aturdimiento" en unas fuentes; el título de Gamefragger la llama **Armorer** |

### Especialidad nueva: Armorer

La primera especialidad nueva del juego. Según las fuentes: escala el daño por **DEF**, todo su daño
es **Sharp DMG**, mecánicas **Maim** y **Gash**, multi-CRIT. **Su etiqueta en la pantalla en español
es desconocida.**

### W-Engines nuevas

| nombre (inglés, de las fuentes) | rango | nota |
|---|---|---|
| Crimson Thirst | S | firma de Claret |
| Crimson Moon Casket | S | firma de Roxy |
| Bloodmarrow Coffer | ? | beneficio de City Fund, canjeable en versiones futuras |

**Los nombres españoles son desconocidos.** `weapons.nombre` es el nombre español de pantalla, así
que son la misma brecha que documentó `audit/censo_armas_20260908.md`: se capturan cuando aparecen,
no se traducen.

### Sets de discos nuevos

Ninguno mencionado en las fuentes consultadas.

### UI y sistema

Recomendaciones de discos más accesibles, ajustes al filtro de agentes (con filtros guardables),
Perfect Assist con aviso en rojo, y la tienda de Hollow Zero muestra primero los materiales nuevos.
Ninguno toca a priori las pantallas que el detector reconoce — **se verifica en la Fase H**, no se
supone.

## Impacto en el código (medido el 2026-09-10)

| lugar | qué pasa con un rol nuevo | severidad |
|---|---|---|
| `agents.rol` / `elemento` / `faccion` | **sin CHECK**: Armorer y Flint Workshop entran sin migración (a diferencia de viento/lumen, migración `_14`) | ninguna |
| `parser_agent_stats._canon_rol` / `_normalizar_rol` | devuelven **`None`** para una etiqueta fuera del mapa | ⚠️ |
| `parser_agent_stats`, línea 316 | el layout de stats cae a `_STATS_RESTO` (Perforación + Recuperación de Energía) **por descarte**, no por conocimiento. Si un Armorer muestra otro par, el gate de completitud 11/11 de S18 **no se cumple nunca y los stats no se registran, sin error** | ⚠️ **alta** — se verifica con una captura de S18 |
| `AgentRepo._load` (`repositories.py:340`) | `archetypes_by_role.get(rol, "ATK_DPS")`: **no rompe el roster** (verificado: `.get`, no `[]`), pero **le asigna ATK_DPS en silencio** a un Armorer que escala por DEF. Es un default que inventa, contra RNF-02 | media — pertenece al tramo 4 (thresholds); no bloquea la captura |
| `agents.faccion` | la DB mezcla inglés (`'Sons of Calydon'`, 15 facciones) y español (`'Faetón'`, 1). Flint Workshop va en inglés por mayoría, salvo decisión contraria | baja |

Dos falsos positivos de mi primer grep, anotados para que nadie los tome como riesgo: en
`app/config/rois.toml` y `app/core/stats_vocab.py`, "Defensa" y "Ataque" son **nombres de stat**,
no roles.

## Lo que sólo resuelve la pantalla

1. Elemento y especialidad reales de Claret (y de Roxy en la fase 2).
2. **La etiqueta española de Armorer** — va a `_ROL_SCREEN_MAP` y `_ROL_OCR_MAP`.
3. **Qué par de stats muestra un Armorer en S18** — decide si hace falta un tercer layout junto a
   `_STATS_DISRUPTIVO` y `_STATS_RESTO`.
4. Los nombres españoles de las tres armas nuevas.

## Estado del checklist QA-07

- [x] **A** — backup, snapshot de filas, smoke L1
- [x] **B** — lectura del patch (con las contradicciones de arriba)
- [ ] **C** — onboarding de Claret: depende de que Daniel la tenga
- [ ] **D** — rebalance de stats: ninguno detectado en las fuentes
- [ ] **E / F** — **no aplican**: los scrapers de Prydwen, `tier_list_calculator`,
      `weapon_optimizer` y `ai_catalog` son de las Fases 3-5 y no existen
- [ ] **G** — smoke L1 post-patch + diff de snapshots
- [ ] **H** — L4: que el detector reconozca la UI de la 3.2 en la primera sesión
- [ ] **I** — docs

## Fuentes

| fuente | ¿autorizada por RNF-02? | resultado |
|---|---|---|
| [Game8 — 3.2 Livestream Summary](https://game8.co/games/Zenless-Zone-Zero/archives/616585) | sí | leída |
| [Game8 — Claret Builds](https://game8.co/games/Zenless-Zone-Zero/archives/597662) | sí | sólo el extracto de búsqueda |
| [Icy Veins — 3.2 new class](https://www.icy-veins.com/zenless-zone-zero/news/zenless-zone-zero-3-2-just-shook-up-combat-with-a-new-class/) | sí | HTTP 403; sólo el extracto |
| [Prydwen — 3.2 Special Program](https://blog.prydwen.gg/2026/08/28/zenless-zone-zero-version-3-2-special-program-summary/) | sí | 301 a la portada: el post se movió |
| [Fandom — Version/3.2](https://zenless-zone-zero.fandom.com/wiki/Version/3.2) | sí | HTTP 402 |
| [Gematsu](https://www.gematsu.com/2026/08/zenless-zone-zero-version-3-2-update-their-secret-histories-launches-september-9), [Gamefragger](https://gamefragger.com/multiplatform/role_playing/zenless-zone-zero-version-32-adds-armorer-agents-claret-and-roxy-in-september-a29699) | **no** | extractos; sólo para fechas y contexto |

**De cinco fuentes autorizadas, sólo una se pudo leer entera.** Es otra razón para que decida la
pantalla.
