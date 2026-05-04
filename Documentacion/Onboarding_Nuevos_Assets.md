# Onboarding de assets nuevos (Engines / Sets / Facciones)

**Última actualización:** 2026-04-26
**Documento hermano:** [`Onboarding_Nuevo_PJ.md`](./Onboarding_Nuevo_PJ.md) (cubre PJs).
**Trigger típico:** cada patch de ZZZ trae 1-3 W-Engines nuevos, 0-1 sets nuevos y ocasionalmente facciones nuevas.

Este doc complementa al onboarding de PJs y materializa el RNF-05 (extensibilidad por patches) para los **otros 3 tipos de assets** que el sistema maneja: armas (W-Engines), sets de discos, y facciones.

---

## §1 — Onboarding de W-Engine nuevo

### 1.1 — Detección

| Trigger | Cómo |
|---------|------|
| **Manual** | El usuario sabe que salió Lyra Cannon y abre el wizard "Agregar W-Engine" en pestaña Configuración |
| **Auto desde RF-04** | Cuando RF-04 captura un disco/PJ con `weapon_id` que no está en DB (la captura del agente menciona un arma desconocida) → toast "Arma nueva detectada: 'Lyra Cannon'. ¿Catalogar?" |
| **Auto desde scraper Prydwen** | Job semanal de `scrape_prydwen_weapons.py` detecta una recomendación con un weapon_id desconocido |

### 1.2 — Pasos (4 acciones)

```
□ 1. INSERT en weapons con stats base
□ 2. Modelar pasiva en weapon_passives_structured (RF-14)
□ 3. Descargar logo y renombrar al slug español
□ 4. Encolar recálculo de weapon_evaluations para los 45 PJs
```

### 1.3 — SQL templates

```sql
-- Paso 1: catálogo base
INSERT INTO weapons (
    nombre, nombre_en, rareza, tipo_especialidad,
    atk_base, stat_secundario, stat_secundario_valor,
    pasiva_tipo, pasiva_condicion, pasiva_valor, pasiva_descripcion,
    pasiva_modelada, sensibilidad_contexto
) VALUES (
    'Cañón de Lira', 'Lyra Cannon', 'S', 'Ataque',
    684, 'Daño Crítico', 18.0,
    'crit', 'on_chain_attack', '12% CRIT',
    'Al hacer Chain Attack, +12% CRIT durante 8s. Apilable hasta 3 veces.',
    1, 'media'
);

-- Paso 2: modelar pasiva (RF-14)
INSERT INTO weapon_passives_structured (
    weapon_id, trigger_tipo, trigger_params,
    modifier_stat, modifier_value_r1, modifier_value_r5,
    modifier_stack_max, uptime_base, descripcion_breve, fuente
) VALUES (
    (SELECT id FROM weapons WHERE nombre='Cañón de Lira'),
    'on_chain_attack', '{"duration_s": 8, "stack_max": 3}',
    'crit_rate', 12.0, 18.0,
    3, 0.6, 'CRIT% por chain attack', 'manual'
);
```

### 1.4 — Logo

Editar `Documentacion/Interfaz/Engines_Animation/README.md` para agregar el slug nuevo + descargar manualmente desde Hakush.in o Fandom Wiki + guardar como `canon_de_lira.webp` en la misma carpeta.

### 1.5 — Recálculo automático

```python
# Encolado (lo dispara el sistema, no manual)
from app.core.weapon_optimizer import enqueue_recalc_for_new_weapon
enqueue_recalc_for_new_weapon(weapon_id_nuevo)
# Recalcula weapon_evaluations para 45 PJs × 4 contenidos = 180 filas
# Latencia esperada: ~3 s
```

**Costo:** $0 (puro determinista, sin IA).

---

## §2 — Onboarding de Set de discos nuevo

### 2.1 — Detección

| Trigger | Cómo |
|---------|------|
| **Manual** | El usuario sabe que salió "Punk Sinfónico" y abre el wizard |
| **Auto desde RF-04** | Cuando captura un disco con `set_id` desconocido en `disc_sets` |
| **Scraper Prydwen** | Job semanal detecta un set nuevo en sus tier lists |

### 2.2 — Pasos (5 acciones)

```
□ 1. INSERT en disc_sets con bonuses 2pc/4pc
□ 2. Clasificar arquetipo en disc_set_archetype (RF-06)
□ 3. Descargar logo y renombrar al slug español
□ 4. Re-evaluar inventory_discs del set (si ya capturaste alguno)
□ 5. Encolar recatalogación RF-12 (si el set introduce nueva sinergia de equipo)
```

### 2.3 — SQL templates

```sql
-- Paso 1: catálogo
INSERT INTO disc_sets (nombre, nombre_en, bonus_2p_stat, bonus_2p_valor, bonus_4p_desc)
VALUES ('Punk Sinfónico', 'Symphonic Punk', 'Maestría de Anomalía', 30,
        'Cuando el equipo aplica anomalía, +12% Anomaly Buildup durante 8s.');

-- Paso 2: arquetipo (puede ser N:M con prioridad)
INSERT INTO disc_set_archetype (set_id, archetype_id, prioridad)
SELECT (SELECT id FROM disc_sets WHERE nombre='Punk Sinfónico'),
       (SELECT id FROM disc_archetypes WHERE code='ANOMALY'),
       1;
```

### 2.4 — Logo

Misma convención: descargar manual de Fandom + guardar como `punk_sinfonico.webp` en `Documentacion/Interfaz/Set_Discos_Logo/`.

### 2.5 — Re-evaluación

Si tenés inventory_discs del set nuevo (Daniel los capturó pre-onboarding y quedaron como `set_id=NULL`), hacer:

```sql
UPDATE inventory_discs
SET set_id = (SELECT id FROM disc_sets WHERE nombre='Punk Sinfónico')
WHERE notas LIKE '%Punk Sinfonico%';
```

Después, encolar `recompute_evaluations(disc_id)` para cada uno → re-poblará `inventory_disc_evaluations` con scores correctos.

---

## §3 — Onboarding de Facción nueva

### 3.1 — Cuándo aplica

Las facciones se agregan **menos frecuentemente** que PJs/sets. Pero cuando sale una facción nueva (típicamente con su primer PJ), hay que registrarla:

- Modificar el `CHECK` constraint de `team_synergies.tipo` si la sinergia introduce un tipo nuevo
- Descargar logo
- Si es facción canónica, considerar agregarla como columna virtual derivada de `agents.faccion`

### 3.2 — Pasos (3 acciones)

```
□ 1. La facción se "crea" implícitamente al asignar el primer PJ con UPDATE agents SET faccion='Nueva Faccion' WHERE ...
□ 2. Descargar logo oficial y renombrar (ej. nueva_faccion.webp)
□ 3. Actualizar Facciones_Logos/README.md con el nuevo mapeo
```

No hay SQL adicional necesario — `agents.faccion` es TEXT libre.

### 3.3 — Validación

```sql
-- Verificar que cada faccion tenga al menos 1 PJ
SELECT faccion, COUNT(*) FROM agents GROUP BY faccion;

-- Verificar que cada PJ con faccion tenga su logo (asumir convención de slugs)
-- (esto se valida en código, no SQL)
```

---

## §4 — Wizard unificado de onboarding (RF-11)

El wizard de la pestaña Configuración tiene **4 modos**:

```
[Agregar PJ nuevo]  [Agregar W-Engine]  [Agregar Set]  [Agregar Facción]
```

Cada uno dispara su sub-flujo correspondiente (ver §1 / §2 / §3 acá; PJs en `Onboarding_Nuevo_PJ.md`).

Todos los wizards comparten:

- Campo "Versión del juego" (ej. v2.9)
- Botón "Importar desde HoYoLAB screenshot" (cuando aplica)
- Validación bloqueante post-onboarding
- Toast resumen al completar

---

## §5 — Checklist por patch (TL;DR)

Cada vez que sale un patch (~6 semanas):

```
□ 1. Esperar ~24-48 h post-release a que Prydwen + Hakush publiquen data
□ 2. Por cada PJ nuevo: ver Onboarding_Nuevo_PJ.md (§13)
□ 3. Por cada W-Engine nuevo: ver §1 acá
□ 4. Por cada Set nuevo: ver §2 acá
□ 5. Por cada Facción nueva: ver §3 acá
□ 6. Descargar logos correspondientes (3 carpetas: Facciones_Logos, Set_Discos_Logo, Engines_Animation)
□ 7. Renombrar a slugs españoles
□ 8. Validar integridad: PRAGMA integrity_check; PRAGMA foreign_key_check;
```

Tiempo estimado por patch completo (con 2 PJs + 2 W-Engines + 1 set): **30-45 minutos** + ~$1 en IA (RF-12 catalogación de 2 PJs).

---

## §6 — Decisiones cerradas (log)

| Fecha | Decisión | Justificación |
|-------|----------|---------------|
| 2026-04-26 | **Logos descargados manualmente, no automatizados** | El sandbox de Claude bloquea fetching de imágenes. Daniel los descarga del wiki con su browser y los pone en la carpeta correspondiente. |
| 2026-04-26 | **Convención slug español para todos los logos** | Permite resolver `nombre_es → ruta_logo` con función trivial sin tabla de mapeo intermedia. |
| 2026-04-26 | **Backup en inglés mantenido** | Los archivos `Drive_Disc_*` y `W-Engine_*` originales se mantienen como backup. Limpieza opcional cuando Daniel valide. |
| 2026-04-26 | **Facciones como TEXT libre, no FK** | `agents.faccion` no apunta a tabla `factions` porque las facciones son metadata simple. La tabla `factions` se evita para mantener el schema mínimo. |
| 2026-04-26 | **Recálculo automático tras onboarding** | Los 4 tipos de assets disparan recálculos sin intervención manual: weapon_evaluations (RF-14), inventory_disc_evaluations (RF-06), team_synergies (RF-12 IA). |
