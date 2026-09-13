# FIX · Los arquetipos hablaban el vocabulario de antes de junio

> **Fecha:** 2026-09-12 · **Tipo:** FIX (datos + contrato) · **Migración:** `_32`
> **Viene de:** [DIAG filtro de mains](2026-09-12_DIAG_El_filtro_de_mains_excluye_el_30_por_ciento_de_lo_equipado.md) §4 — categoría A
> **Reporte RNF-01:** `audit/migracion_32_disc_archetypes_tasa_anomalia_20260912.md`
> **Prácticas en juego:** B1, B2 (un pendiente sin salida), A3, RNF-01

---

## 1. Qué se arregló

- `ANOMALY.mains_6`: `Maestría de Anomalía` → **`Tasa de Anomalía`**. El main de anomalía de slot 6 es
  el porcentual. La entrada vieja no la cumplía ningún disco.
- `Bono Daño Viento` agregado a `mains_5` de los cinco arquetipos que ya listaban los otros bonos
  elementales (DEFENSE no lista ninguno y no cambió).
- Tabla de RF-04 §7.2.2 alineada con la DB. Arrastraba también lo que la migración `_08` ya había
  corregido en mayo (`Crit DMG` en Mains VI, STUN sin bonos elementales).

**No** se tocó qué mains le sirven a cada arquetipo (categoría C del diagnóstico: 37 discos, Miyabi
incluida). Es decisión de diseño con fuente por PJ.

## 2. El contrato — por qué esto no vuelve a pasar

`app/tests/unit/test_disc_archetypes_contrato.py`, sobre la DB de dominio en solo lectura:

1. **Todo `mains_N` existe en su slot** según `stats_vocab.CANONICAL_MAINS_VARIABLE`. El vocabulario
   tiene una sola autoridad (B1). El arquetipo elige entre mains que existen; no puede nombrar uno
   que no existe.
2. **Un arquetipo que admite bonos elementales admite todos.** Elegir cuáles mains sirven es diseño;
   aceptar cuatro elementos y no el quinto es una lista que no se actualizó cuando salió el elemento.

El test se escribió **antes** de la migración y falló con exactamente los dos defectos del
diagnóstico, sin nada más. Después de migrar pasa, y **apuntado al backup previo vuelve a fallar**
con los dos (A3).

La causa de fondo es la de B2: la migración 09 dejó escrito *"revisar al implementar scoring.py"*.
Esa nota no tenía dueño ni nada que la hiciera saltar. El contrato es ese disparador: la próxima vez
que `stats_vocab` cambie un nombre de main, este test falla hasta que los arquetipos lo sigan.

## 3. Cómo se aplicó (RNF-01)

1. App cerrada (sin procesos `python`/DaniBOD).
2. Ensayo sobre una copia: smoke checks OK, segunda corrida idempotente, y `iterdump` contra el
   original con **solo 5 filas de `disc_archetypes`** distintas.
3. `app/scripts/qa/apply_migration.py` sobre la DB real: backup automático, transacción,
   `foreign_key_check` e `integrity_check` OK. El resultado es idéntico al ensayo (`iterdump`).

Detalle y sha256 en el reporte de `audit/`.

## 4. Efecto medido

| | antes | después |
|---|---|---|
| discos equipados excluidos por el arquetipo de su propio PJ | 46 | **37** |
| PJs afectados | 29 | **23** |
| PJs ANOMALY con `Tasa de Anomalía` en slot 6 de su mejor build | 0 / 11 | **10 / 11** |
| `score_actual` | — | +1.0 exacto en 9 PJs ANOMALY (8 por Tasa, Velina por Viento) |

El +1.0 es el `peso_main` que `score_disco` no les daba. Por eso esto también corrige el scoring
compartido (el recomendador de RF-04), no solo el optimizador.

## 5. Queda abierto

- **La DB del `.exe`** (`%LOCALAPPDATA%\DaniBOD_ZZZ_Analytics\db\`, copia del 2026-08-18) sigue con
  los arquetipos viejos: verificado en solo lectura. Esta migración tocó solo la del repo.
- **Categoría C** (37 discos, 23 PJs) y la contradicción de Miyabi (§5.1 del diagnóstico).
- **Filtro duro vs. blando** entre optimizador y scoring (RF-06 §5).
