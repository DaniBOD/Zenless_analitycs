# Corrección canónica: "Tasa de Anomalía" ≠ "Maestría de Anomalía"

**Fecha:** 2026-06-03
**Migración:** `db/migrations/2026-06-03_09_correccion_tasa_anomalia.sql`
**Disparador:** QA de extracción S17 (disco equipado), capturas reales del juego.
**RNF:** 01 (backup + transacción + integrity_check), 02 (pantalla = ground truth).

---

## 1. Hallazgo

El modelo de datos (audit Hito 2.0.1 + `stats_vocab.ALIASES`) trataba **"Tasa de
Anomalía"** como un **error de OCR** de **"Maestría de Anomalía"**, y mapeaba una a
la otra. Las capturas reales del juego prueban que son **dos stats distintas**:

| Stat | En pantalla | Tipo | Dónde aparece |
|------|-------------|------|----------------|
| **Maestría de Anomalía** | 27, 18, 92 | **flat** | substat · main slot IV |
| **Tasa de Anomalía** | 30 %, +8 % | **%** | main slot VI · bonus 2pc de set |

Evidencia (capturas `Documentacion/Screenshots_Triggers/Discos_Triggers/04_*`):
- **Ejemplo_8**: slot 6 main = **"Tasa de Anomalía 30 %"**.
- **Ejemplo_9**: slot 4 main = **"Maestría de Anomalía 92"** (flat).
- **Ejemplo_10**: bonus 2pc de set = "Tasa de Anomalía +8 %".

El RF-04 §7.2.1 ya tenía la pista: §209 decía *"No existen como substat: Tasa de
Anomalía… exclusivamente mains"*, pero la tabla de slot VI (§203) escribía
"Maestría de Anomalía" por error.

## 2. Impacto en DB

`inventory_discs`, discos con `slot=6` y `main_stat='Maestría de Anomalía'`:
- **11 filas**, todas con `main_valor = 30.0`.
- Una "Maestría" flat a nivel 15 sería ~92 (cf. slot-4); el valor 30 confirma que
  son **"Tasa de Anomalía 30 %"** mal grabadas.
- Incluye los `id = 54` y `id = 185` que el audit Hito 2.0.1 ya había marcado como
  "Tasa Anomalía 30 %" (y que una corrección posterior reescribió a Maestría).

**NO afectados** (legítimos, intactos):
- 14 discos slot-4 main "Maestría de Anomalía" (valor 92/23 flat).
- Substats "Maestría de Anomalía" (valores 9/18/27/36 flat).

## 3. Cambios aplicados

| Archivo | Cambio |
|---------|--------|
| `db/danibod_zzz_v2.db` | UPDATE 11 filas slot-6 → `main_stat='Tasa de Anomalía'`, `unidad_main='%'` |
| `app/core/stats_vocab.py` | "Tasa de Anomalía" agregada como canónica (main slot VI); removida de slot VI "Maestría de Anomalía"; eliminados aliases erróneos Tasa→Maestría; `normalize_stat_name` ahora insensible a acentos/mayúsculas/espacios |
| `Documentacion/RF_Captura_Discos/RF-Logic_Captura_Discos.md` | §7.2.1 tabla slot VI: "Maestría" → "Tasa de Anomalía (%)" + nota de corrección |

### Verificación ETL (dentro de la transacción)
```
filas actualizadas: 11
foreign_key_check: OK (sin violaciones)
integrity_check: ok
POST: slot6 Tasa=11 (esp 11) | slot6 Maestría=0 (esp 0) | slot4 Maestría=14 (esp 14)
```
Backup previo: `db/danibod_zzz_v2.backup_premig_20260603_003837.db`.

## 4. Pendiente (flag para fase de scoring)

La tabla de arquetipos del RF-04 §7.2.2 (fila `ANOMALY`, columna "Mains VI") aún
dice "Maestría Anomalía"; debería ser "Tasa de Anomalía" para slot VI. NO se tocó
acá porque toca semántica de scoring (fase posterior). Revisar al implementar
`scoring.py` / thresholds de arquetipo ANOMALY.
