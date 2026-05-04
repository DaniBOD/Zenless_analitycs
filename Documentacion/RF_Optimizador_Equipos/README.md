# Documentación — Optimizador de Build con Contexto de Equipo (RF-12)

Esta carpeta agrupa la documentación de la lógica del optimizador *team-aware*, donde la composición del equipo modifica los pesos de substats y/o el set recomendado por personaje.

## Índice

1. **[RF-Logic_Optimizador_Equipos.md](./RF-Logic_Optimizador_Equipos.md)** — Documento maestro. Define alcance v1 (3 capas: pesos, override de set, sugerir equipo), modelo de datos (`team_synergies`, `team_compositions`, `ai_catalog_runs`), algoritmo runtime, prompts a Claude API (catalogadora), trigger on-demand + automático, performance/costos esperados (~$10/mes), output JSON de ejemplo (caso Ellen + Dialyn → Puffer Electro) y log de decisiones cerradas. **Empezar por aquí.**

## Diagramas de flujo (segmentados v4)

- **[RF-12_01_runtime.svg](../Diagramas%20de%20flujos/RF-12_01_runtime.svg)** ([PNG](../Diagramas%20de%20flujos/RF-12_01_runtime.png)) — **flujo runtime determinista**: usuario abre optimizador con team_context → lookup `team_synergies` → 3 capas (A: pesos / B: set / C: composiciones top-N) → invoca RF-06 con pesos/set ajustados.
- **[RF-12_02_catalogacion.svg](../Diagramas%20de%20flujos/RF-12_02_catalogacion.svg)** ([PNG](../Diagramas%20de%20flujos/RF-12_02_catalogacion.png)) — **flujo de catalogación offline**: trigger (on-demand / PJ nuevo / set nuevo) → cap de costo → encolar batch (prompt cache) → Claude sonnet/opus → validar JSON con retry → INSERT + auditoría en `ai_catalog_runs` → confianza inicial. Alimenta los lookups del runtime.

## Recursos relacionados

- Optimizador base (sin equipo): `../RF_Optimizador/RF-Logic_Optimizador_Build.md` (RF-06)
- Lógica de captura/evaluación: `../RF_Captura_Discos/RF-Logic_Captura_Discos.md` §11 (scoring engine compartido)
- Schema base: `../../db/migrations/2026-04-24_01_archetypes_and_scoring.sql` (arquetipos + scoring tables)
- README del proyecto: `../../README.md` §3.1 RF-12 (descripción corta + estado), §8 (Optimizador de Equipos por Personaje)
- IA catalogadora: integración con Claude API (sonnet/opus) + RAG sobre Prydwen.gg
