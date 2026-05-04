# Informe de Discrepancias DB ↔ Screenshots — Roster Completo

**Fecha:** 2026-04-22
**UID:** 1000860143 (DaniBOD)
**Universo:** 45 agentes · 49 weapons · 27 disc_sets
**Fuente de verdad:** 45 screenshots en `Pj_stats/` (2026-04-21)
**DB:** `danibod_zzz_v2.db` (integrity_check = ok, 0 FK issues)
**Backups pre-corrección:** `audit/danibod_zzz_v2.backup_20260422_011139.db`

---

## Resumen ejecutivo

Se verificó el 100% del roster (45/45). Se detectaron y corrigieron tres clases de discrepancia: (1) `weapon_nivel` sistemáticamente incorrecto mostrando valores de fase de refinamiento (3/4/5) en lugar del nivel real 60; (2) IDs de `set_4p_id` y `set_2p_id` invertidos en varios agentes; y (3) builds mix (3+2+1 o 3+3) incorrectamente clasificadas como 4pc. También se corrigió un caso estructural de `disc_sets` (id=47 con metadata corrupta, merged a id=40 Puffer Electro). La base ahora refleja fielmente los screenshots.

---

## Correcciones schema a nivel tabla

### disc_sets — Merge id=47 → id=40 (Puffer Electro)

El registro id=47 contenía metadata inconsistente entre columnas: `nombre='Tecno tetraodóntido'` (Puffer Electro en español) pero `nombre_en='Branch & Blade Song (Woodpecker)'` y `bonus_2p='CRIT DMG +16%'` copiados desde id=25 (Balada rama/espada). Verificación externa (Prydwen / SenpaiLife) confirma que Puffer Electro real es 2p PEN Ratio +8% / 4p Ult DMG +20% + ATK +15% 12s tras Ult, coincidiendo exactamente con id=40.

Acción ejecutada: tres agentes reapuntados a id=40 (Zhu Yuan `set_4p_id` 47→40, Ye Shunguang `set_2p_id` 47→40, Rina `set_2p_id` 47→40) y `DELETE FROM disc_sets WHERE id=47`. `integrity_check = ok`, 0 huérfanos.

### disc_sets — Flag pendiente id=50 (Nana a la luz cenicienta)

El registro id=50 muestra `nombre_en='White Water Ballad (custom)'` — el sufijo "(custom)" sugiere metadata manual no validada. Afecta a 6 agentes (Yuzuha, Orfia y Magas, Sunna, Lucía, Nicole, y el 4pc principal de Miyabi). No se merged porque no hay conflicto estructural evidente, solo flag documental. Todos los agentes afectados llevan la nota "FLAG: id=50 tiene nombre_en='(custom)' - verificar set real externo" en su campo `notas`.

---

## Correcciones por agente

### S-rank Ataque (11 agentes + Harumasa)

Harumasa confirmado con W-Engine vacío (EMPTY) — sin cambios estructurales, solo slot precision. Nekomata fix estructural: el screenshot muestra slot 5 vacío con 3 Metal Colmilludo + 2 Balada, por lo que no existe bonus 4pc activo; `set_4p_id` pasó a NULL. N.º 11 aclarado: 4pc Tecno Pícido + piezas sueltas (1pc Floración + 1pc Balada) sin bonus adicional. Orfia y Magas, Yixuan, N.º 0 Anby, Sporos, Dialyn: `weapon_nivel` corregido (5/3 → 60). Yixuan además exhibe las stats 2.x "Fuerza Bruta 2296" y "Acumulación Automática 2.00" no mapeadas en el schema actual — anotado en notas para futura extensión del schema. Zhu Yuan, Evelyn, Ellen, Miyabi, Burnice, Manato ya se habían corregido en sesión previa (Manato incluyó rank S → A).

### S-rank Aturdimiento (4 agentes)

Koleda, Lycaon, Qingyi, Gatillo. Qingyi y Gatillo tenían `weapon_nivel` erróneo (4/5 → 60). Gatillo además tenía `weapon_id=47 (Hellfire Gears)` incorrecto — el screenshot muestra Última cena (id=5), y la nota decía "1pc Tecno Pícido" cuando en realidad son 2pc. Koleda y Lycaon solo recibieron mejora de precisión de slots.

### S-rank Anomalía (7 agentes)

Piper, Grace, Jane, Vivian, Alice, Nangong Yu, Yuzuha (además de Miyabi/Burnice/Yanagi ya procesados). Piper fue un caso 3+3 mix sin 4pc real → `set_4p_id=NULL`. Jane, Vivian y Yuzuha tenían `set_4p_id` y `set_2p_id` invertidos (el texto de notas era correcto pero los FKs estaban swapped). Nangong Yu: 1pc Jazz reclasificado como 2pc Jazz tras re-revisión. Los restantes solo corrección de `weapon_nivel`.

### S-rank Soporte (4 agentes)

Rina, Astra Yao, Ju Fufu, Sunna. Ju Fufu tenía IDs invertidos (notas decía "2pc Voz Astral + 4pc Monarca" pero FKs apuntaban a 4pc Voz Astral + 2pc Monarca). Los cuatro recibieron corrección de `weapon_nivel`. Rina con Puffer Electro ya correctamente apuntada a id=40 tras merge.

### S-rank Defensa (3 agentes) + Ye Shunguang reclasificado a Ataque

César, Zhao, Lucía. César tenía `set_2p_id=NULL` cuando debía ser 43 (Disco Sacudestrellas) — las notas texto lo mencionaban pero el FK faltaba; también se confirmó M2 (antes "?" en mapping). Zhao, Lucía: `weapon_nivel` 5→60.

**Post-informe (2026-04-22 tarde):** Ye Shunguang reclasificada de Defensa a **Ataque** tras indicación del usuario. Su stat profile (Tasa Perforación 32%, CRIT Rate 48.2%, CRIT DMG 208.4%, Perforación 9) confirma perfil DPS no defensor. `weapon_nivel` 5→60 se mantiene. `image_mapping.md` actualizado en consecuencia.

### A-rank (11 agentes)

Corin, Antón, Ben, Seth, Anby, Nicole, Billy, Soukaku, Lucy, Pulchra, Pan Yinhu. Antón y Ben confirmados sin discos equipados (correcto). Seth: 3pc Jazz disperso no da bonus 4pc → `set_4p_id=NULL`. Anby: solo tenía 1pc Metal Infernal + 1pc Tecno Pícido como piezas sueltas → `set_2p_id=NULL`. Nicole: fix estructural importante — `set_4p_id` 37 (Melodía Faetón) → 50 (Nana a la luz cenicienta) tras lectura del screenshot. Lucy y Pan Yinhu: las notas decían "3pc Voz Astral" pero son builds 4pc completos, corregidas. Los demás solo precisión de slots.

---

## Campos actualizados por agente (síntesis)

Se modificó el campo `notas` en 42 de los 45 agentes para añadir precisión de slot numérico (p.ej. "4pc Monarca del Pináculo **(slots 1,3,4,6)** + 2pc Tecno Pícido **(slots 2,5)**"). Esto facilita futuras verificaciones sin tener que volver a consultar screenshots. `weapon_nivel` se corrigió en 22 agentes (mostraban fase 3/4/5 en lugar del nivel real). `set_4p_id` se modificó estructuralmente en 8 agentes (swap, NULL por falta de 4pc real, o reasignación). `set_2p_id` se modificó en 6 agentes.

---

## Estado post-corrección

DB danibod_zzz_v2.db integra los 45 agentes con sus 45 screenshots correspondientes. `PRAGMA integrity_check = ok`. `PRAGMA foreign_key_check = 0 issues`. Zero agents con `weapon_id NULL`. Dos agents (Antón, Ben) legítimamente sin discos equipados (`set_4p_id` y `set_2p_id` ambos NULL con notas explicativas). Cuatro agents con `set_4p_id=NULL, set_2p_id != NULL` representando builds mix sin bonus 4pc real (Piper, Nekomata, Seth, Nangong Yu equivalente). 4pc faltante en builds mix se documenta consistentemente como `set_4p_id=NULL` y notas detallan la distribución real (ETL policy establecida).

---

## Pendientes y next steps

Primero, el usuario mencionó que hay un personaje no subido al final que queda por revisar (no está entre los 45 screenshots actuales). Esperando identificación.

Segundo, schema extension para 2.x stats: `Fuerza Bruta` (Sheer Force — Yixuan) y `Acumulación Automática` (Auto-Buildup — Yixuan) son mecánicas de la versión 2.x no mapeadas en `agents`. Requiere añadir columnas o una tabla `agent_mechanics`.

Tercero, verificación externa de id=50 (Nana a la luz cenicienta): el marker "(custom)" en `nombre_en` debe resolverse contra documentación canónica (Prydwen / HoyoWiki) antes de usar estos sets en análisis de thresholds.

Cuarto, tras validar los tres puntos anteriores, proceder con el trabajo de **thresholds** (pospuesto explícitamente hasta limpieza de datos — citando al usuario: "luego vemos el tema de los threshold eso sera cuando este bien establecidos los datos").
