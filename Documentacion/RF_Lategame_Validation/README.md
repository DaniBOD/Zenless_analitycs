# Documentación — Validación Lategame + Tier List Personal Calibrado (RF-13)

Esta carpeta agrupa la documentación del sistema de validación empírica de equipos en contenido lategame (Shiyu Defense Critical, Deadly Assault) y la generación de una tier list personal calibrada a la cuenta de Daniel, comparada contra Prydwen.

## Índice

1. **[RF-Logic_Lategame_Validation.md](./RF-Logic_Lategame_Validation.md)** — Documento maestro. Cubre las 3 capas (registro de runs con OCR del breakdown DMG, tier list calibrada vs Prydwen, retro-feedback bayesiano sobre RF-12), modelo de datos (8 tablas nuevas: `enemies`, `enemy_resistances`, `shiyu_cycles`, `da_cycles`, `lategame_runs`, `lategame_run_damage`, `tier_list_personal`, `prydwen_tier_snapshots`, `team_synergy_adjustments`), pipeline de captura manual con hotkey F11, algoritmo del tier list con buckets fijos, ajuste bayesiano de confianza, scrapers de Hakush.in + Prydwen, performance esperada, output JSON de ejemplo y log de decisiones cerradas. **Empezar por aquí.**

## Diagramas de flujo (segmentados v4)

- **[RF-13_01_captura.svg](../Diagramas%20de%20flujos/RF-13_01_captura.svg)** ([PNG](../Diagramas%20de%20flujos/RF-13_01_captura.png)) — **CAPTURA manual**: F11 → 2 screenshots (resumen + Battle Stats) → OCR híbrido → validación de consistencia (ΣDMG≈100, PJs match, ciclo activo) → INSERT en `lategame_runs` + `lategame_run_damage` → toast confirma → contador para trigger de tier + bayesiano.
- **[RF-13_02_tierlist.svg](../Diagramas%20de%20flujos/RF-13_02_tierlist.svg)** ([PNG](../Diagramas%20de%20flujos/RF-13_02_tierlist.png)) — **TIER LIST recálculo**: trigger (N=3/on-demand/semanal) → snapshot atómico → agregación K=20 runs → score normalizado (3★ 0.45 + win 0.20 + dmg 0.20 + tiempo 0.15) → buckets fijos S+/S/A/B/C/D → lookup Prydwen + delta → justificación textual → INSERT con `snapshot_id`.
- **[RF-13_03_bayesiano.svg](../Diagramas%20de%20flujos/RF-13_03_bayesiano.svg)** ([PNG](../Diagramas%20de%20flujos/RF-13_03_bayesiano.png)) — **RETRO-FEEDBACK BAYESIANO**: cada run nuevo → match con par de `team_synergies` → acumular evidencia ≥3 runs → likelihood capada en 1.5 → peso prior decreciente → `confianza_post` clipped → respeta flag `congelado` → UPDATE + audit → si confianza<0.7 marca override RF-12 como no aplicable → badge ±RF-13 en panel.

## Recursos relacionados

- Optimizador team-aware: `../RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md` (RF-12) — RF-13 cierra el loop bayesiano sobre `team_synergies.confianza`
- Optimizador base: `../RF_Optimizador/RF-Logic_Optimizador_Build.md` (RF-06)
- Backend OCR: `app/core/ocr_backend.py` (compartido con RF-09)
- Schema base: `../../db/migrations/2026-04-24_01_archetypes_and_scoring.sql`
- README del proyecto: `../../README.md` §3.1 RF-13, §10 (próximos pasos)

## Fuentes externas usadas

- [Hakush.in — Boss DB](https://zzz3.hakush.in/boss) — datamine cuantitativo (HP base, escalado, resistencias)
- [Prydwen Shiyu Defense Analytics](https://www.prydwen.gg/zenless/shiyu-defense/) — ciclos activos, tier list general
- [Game8 Deadly Assault Guide](https://game8.co/games/Zenless-Zone-Zero/archives/489103) — fechas de reset, mecánicas
- [Icy Veins Shiyu Critical Node](https://www.icy-veins.com/zenless-zone-zero/shiyu-defense-critical-node) — mecánicas avanzadas
- [Fandom Wiki — Deadly Assault](https://zenless-zone-zero.fandom.com/wiki/Deadly_Assault) — fallback general
