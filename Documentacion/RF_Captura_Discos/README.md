# Documentación — Captura y evaluación de discos

Esta carpeta agrupa toda la documentación de la lógica de captura y evaluación automática de discos (RF-04 captura, RF-05 upgrade, RF-06 evaluación).

## Índice

1. **[RF-Logic_Captura_Discos.md](./RF-Logic_Captura_Discos.md)** — Documento maestro. Define actores, máquina de estados, polling adaptativo, pipeline de análisis, capa de evaluación con match por PJ y por arquetipo, modelo de datos y decisiones cerradas. **Empezar por aquí.**
2. **[Analisis_Capturas_Iteracion_1.md](./Analisis_Capturas_Iteracion_1.md)** — Hallazgos de la primera tanda de screenshots reales de Daniel. Anclas visuales confiables, formato de datos en UI, peculiaridades del juego.
3. **[Catalogo_Screenshots_Requeridos.md](./Catalogo_Screenshots_Requeridos.md)** — Lista exhaustiva de screenshots necesarios por tipo de pantalla para calibrar ROIs de OCR.

## Recursos relacionados

- Diagramas de flujo (RF-04, RF-05, arquitectura): `../Diagramas de flujos/`
- Screenshots originales: raíz del proyecto → `Screenshots_Triggers/Discos_Triggers/`
- Schema de base de datos: raíz del proyecto → `db/danibod_zzz_v2.db`
