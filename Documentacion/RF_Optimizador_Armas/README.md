# Documentación — Optimizador de Armas (W-Engines) (RF-14)

Esta carpeta agrupa la documentación del optimizador de W-Engines por personaje, con scoring contextual sensible al contenido (Shiyu / DA / Hollow Zero / general) y delta vs Prydwen.

## Índice

1. **[RF-Logic_Optimizador_Armas.md](./RF-Logic_Optimizador_Armas.md)** — Documento maestro. Cubre alcance v1 (ranking ideal del catálogo + ranking de inventario disponible + build full coordinada con RF-06), modelado híbrido de pasivas (`weapon_passives_structured` con triggers/modifiers/uptime + texto fallback), perfiles de contenido (`content_profiles` con TTL boss, uptime HP>50%, chain attacks/min, etc.), algoritmo de scoring con uptime contextual (caso paradigmático: "la roca" / Núcleo Fosilizado Precioso → S+ en DA, A en Shiyu, B en HZ), build full RF-06+RF-14, integración con RF-12 (uptime de triggers `team_has_*`) y RF-13 (recalibración bayesiana de `content_profiles` y tier personal), pipeline de scraping Prydwen, output JSON de ejemplo y log de decisiones cerradas. **Empezar por aquí.**

## Diagramas de flujo (segmentados v4)

- **[RF-14_01_overview.svg](../Diagramas%20de%20flujos/RF-14_01_overview.svg)** ([PNG](../Diagramas%20de%20flujos/RF-14_01_overview.png)) — vista de alto nivel: cache check `weapon_evaluations` → carga `content_profiles` + `pj_weapon_synergy` → loop por arma (ATK + stat₂ + pasivas con uptime contextual + textual + synergy) → lookup Prydwen + delta → rankings IDEAL/DISPONIBLE → toggle **Build Full (abstracto)**.
- **[RF-14_02_buildfull.svg](../Diagramas%20de%20flujos/RF-14_02_buildfull.svg)** ([PNG](../Diagramas%20de%20flujos/RF-14_02_buildfull.png)) — profundización: top 3 armas → invoca RF-06 por cada una (referencia a RF-06_01) → score conjunto con interacciones (ATK total vs caps, CRIT cap 100%, thresholds soporte Astra/Ju Fufu, ER awakenings Burnice) → ordenar 9 combinaciones → top 3 finales con desglose.

## Recursos relacionados

- Optimizador de discos: `../RF_Optimizador/RF-Logic_Optimizador_Build.md` (RF-06) — coordina con RF-14 para build full
- Optimizador team-aware: `../RF_Optimizador_Equipos/RF-Logic_Optimizador_Equipos.md` (RF-12) — modifica uptime de triggers contextuales
- Validación lategame: `../RF_Lategame_Validation/RF-Logic_Lategame_Validation.md` (RF-13) — recalibra `content_profiles` y ajusta tier personal de armas con runs reales
- Schema base: `../../db/migrations/2026-04-24_01_archetypes_and_scoring.sql` (arquetipos + scoring tables que comparten `STAT_IMPACT_PER_ROL`)
- README del proyecto: `../../README.md` §3.1 RF-14, §10 (próximos pasos)

## Fuentes externas usadas

- [Prydwen — Builds y W-Engines por PJ](https://www.prydwen.gg/zenless/) — tier list general de armas, refresh semanal vía `scrape_prydwen_weapons.py`
- Catálogo `weapons` (49 entradas) — ya cargado en RF-03 (abril 2026), con `pasiva_tipo` semi-estructurado como base del modelado formal
