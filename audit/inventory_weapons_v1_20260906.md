# `inventory_weapons` v1 — la tabla que nadie escribió nunca

**2026-09-06.** Primer paso del censo de W-Engines. La tabla existía desde la Fase 1 (abril 2026),
**sin migración propia** —no está en `db/migrations/`, sólo la mencionan de costado la `_11` y la
`_13` para decir que no la tocan— con **0 filas** y sin un solo repo ni syncer que la escriba en
todo `app/`.

## Por qué había que tocarla ANTES de la primera fila

Con la tabla vacía el rebuild es gratis. Con filas adentro cuesta un rebuild con un índice parcial
en el medio, y SQLite no puede sacar un `DEFAULT` ni un `CHECK` con `ALTER`.

### 1. Los DEFAULT convertían "no pude leer" en un dato plausible

```
nivel        INTEGER DEFAULT 0
refinamiento INTEGER DEFAULT 1 CHECK(refinamiento BETWEEN 1 AND 5)
```

`read_refinamiento` (`app/core/parser_weapon_s26.py:333`) **se abstiene a propósito** cuando no
encuentra las 5 estrellas: sin las 5 no se distingue una estrella gris de un recorte corrido.
Devuelve `None` y lo anota como `refinamiento_no_leido`.

#### ⚠️ Una de mis dos razones era falsa, y la destapó un sabotaje que pasó en verde

Escribí que el CHECK viejo **impedía guardar** ese `None`. No es cierto: en SQL un CHECK que evalúa
a NULL se considera **satisfecho** —sólo rechaza cuando da FALSE—, así que
`CHECK(refinamiento BETWEEN 1 AND 5)` aceptaba NULL sin chistar. Lo medí sobre el esquema viejo:

```
INSERT INTO viejo (weapon_id, refinamiento, nivel) VALUES (1, NULL, NULL)  -> pasa
INSERT INTO viejo (weapon_id) VALUES (2)                                   -> nivel=0, refinamiento=1
```

Lo que inventa es el **DEFAULT**, y sólo cuando la columna se **OMITE** del INSERT. El riesgo real
era más chico del que dije, pero existe: cualquier caller que omita la columna —un script, un
INSERT a mano— se lleva un 0 y un P1 indistinguibles de una lectura de verdad, porque los dos son
valores legítimos. Sin DEFAULT ese caller se lleva NULL, que es la respuesta honesta.

El `IS NULL OR` del CHECK nuevo, entonces, **no cambia la conducta**: documenta la intención.

Cómo se destapó: los dos tests que escribí primero (`test_refinamiento_ilegible_queda_NULL` y
`test_nivel_ilegible_queda_NULL_y_no_cero`) pasan las columnas **explícitas**, y un DEFAULT sólo
actúa cuando se omiten. Restaurar `DEFAULT 1`/`DEFAULT 0` en la migración los dejaba en verde a los
dos. Hizo falta un tercero —`test_omitir_las_columnas_las_deja_en_NULL_y_no_las_inventa`— que
inserta omitiendo. **A3 otra vez: verificar el efecto, no la intención.**

### 2. La clave natural pasó de premisa a restricción

*"Un PJ equipa exactamente un W-Engine"* es el equivalente de `(PJ, slot)` en discos. Como índice
único parcial, un error del matcher de badges deja de ser dos filas peleándose en silencio:

```sql
CREATE UNIQUE INDEX idx_invw_pj_equipada ON inventory_weapons(agente_asignado)
 WHERE equipado = 1 AND agente_asignado IS NOT NULL AND descartado = 0;
```

Verificado sobre la copia de ensayo, las cuatro esquinas:

| caso | resultado |
|---|---|
| 2ª fila equipada del mismo PJ | `IntegrityError: UNIQUE constraint failed` ✅ |
| mismo PJ con `equipado=0` (su arma vieja desequipada) | permitido ✅ |
| dos armas libres sin dueño | permitido ✅ |
| `refinamiento = 9` | `CHECK constraint failed` ✅ |
| `refinamiento = NULL` | permitido ✅ |

Las tres del medio importan tanto como la primera: un índice sin el `WHERE` habría prohibido lo
legítimo.

### 3. `descartado` y `origen_evidencia`, ahora que salen gratis

- **`descartado`** — las armas salen de la cuenta: los duplicados se consumen como material de
  refinamiento, que es *la razón* por la que hay copias repetidas. Nada la escribe en v1; se agrega
  porque la tabla está vacía hoy.
- **`origen_evidencia`** — de qué se fía cada fila, que ninguna otra cosa permite reconstruir
  después:

  | valor | qué lo respalda |
  |---|---|
  | `s26_desequipar` | el juego lo **afirma** (el botón dice "Desequipar" sobre el PJ en pantalla). No pasa por la librería de badges |
  | `s30_badge` | el matcher de avatares. Medido: **8/10**, con un LIBRE falso |
  | `s29_swap` | el diálogo de sustitución, que el juego escribe en texto |

## El choque B1 que casi pasa desapercibido

`agents.weapon_id` / `weapon_nivel` / `weapon_rango` existen, están **0 de 51** con dato y tienen
**cero lectores** en `app/`. Estaban listadas en `AGENTS_NULL` de `rebuild_account_db.py`, cuya
docstring promete:

> *"Exactamente lo que `sync_agent_stats._STAT_MAP` sabe re-leer de pantalla"*

En cuanto `inventory_weapons` pasa a ser la autoridad, eso es falso para las tres: un reconstruir
las vaciaría prometiendo que el censo las rellena, y el censo llena la otra tabla.

**No se dropearon** (criterio conservador, CLAUDE.md §5). Se movieron a `AGENTS_MUERTAS_ARMA`, y esa
tupla **se suma explícitamente al vaciado** — si no, moverlas las habría convertido en silencio en
columnas que se arrastran, o sea datos de la cuenta vieja sobreviviendo a un reconstruir.

Verificado por sabotaje: sacando la tupla del vaciado, se ponen rojos
`test_las_columnas_de_arma_se_siguen_vaciando` (nuevo) **y**
`test_los_stats_observables_quedan_en_NULL` (que ya existía — la red estaba puesta desde antes; el
test nuevo aporta el motivo documentado, no la cobertura).

## RNF-01

| | |
|---|---|
| App corriendo | **verificada cerrada con `tasklist` ANTES de escribir**, no después |
| Ensayo | contra copia en `$TEMP/ensayo_armas.db`, dos veces (la primera destapó un smoke check mal contado: decía 9 columnas y son 10) |
| Backup | `db/danibod_zzz_v2.backup_premig_20260906_224003.db` |
| Transacción | única (`BEGIN … COMMIT`) |
| Smoke checks | 7 en verde |
| `PRAGMA foreign_key_check` | ok |
| `PRAGMA integrity_check` | ok |

## Queda abierto

- Nada escribe la tabla todavía: eso es el paso 2 (repos) y 3 (`WeaponSyncer`).
- `descartado` queda dormida hasta que exista el flujo de reciclaje (no hay estado de detector ni
  fixtures para el botón "Reciclar").
