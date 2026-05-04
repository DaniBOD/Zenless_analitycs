# Documentación — Optimizador de Build (RF-06)

Esta carpeta agrupa la documentación de la lógica del optimizador de discos por personaje.

## Índice

1. **[RF-Logic_Optimizador_Build.md](./RF-Logic_Optimizador_Build.md)** — Documento maestro. Define alcance, modelo de datos consumido, algoritmo greedy + bonus pass, scoring engine compartido con RF-04 §11, triggers manual y automático, performance esperada, output de ejemplo y log de decisiones cerradas. **Empezar por aquí.**

## Diagramas de flujo (segmentados v4)

- **[RF-06_01_overview.svg](../Diagramas%20de%20flujos/RF-06_01_overview.svg)** ([PNG](../Diagramas%20de%20flujos/RF-06_01_overview.png)) — vista de alto nivel: triggers (manual/automático con debounce 2s), carga de inputs, **algoritmo (abstracto)**, top 3 builds, persistencia y notificación.
- **[RF-06_02_algoritmo.svg](../Diagramas%20de%20flujos/RF-06_02_algoritmo.svg)** ([PNG](../Diagramas%20de%20flujos/RF-06_02_algoritmo.png)) — profundización: greedy por slot (top-K=8), bonus pass (4pc / 2+2+2 / 3+3), score conjunto con thresholds del PJ, delta vs build actual y detección de swaps inter-PJs.

## Recursos relacionados

- Lógica de captura/evaluación: `../RF_Captura_Discos/RF-Logic_Captura_Discos.md` §11 (scoring engine compartido)
- Schema base: `../../db/migrations/2026-04-24_01_archetypes_and_scoring.sql` (arquetipos + scoring tables)
- README del proyecto: `../../README.md` §3.1 RF-06 (descripción corta + estado)
