# RF-Logic: Captura y evaluación de discos

Documento maestro que describe la lógica completa del sistema de captura, análisis y evaluación de discos en tiempo real. Cubre RF-04 (captura al obtener disco), RF-05 (seguimiento de upgrade) y RF-06 (evaluación y recomendación — nuevo).

> Este documento es la referencia canónica. Los diagramas en `Diagramas de flujos/` son la representación visual; si hay discrepancia, manda este MD.

---

## 1. Propósito y alcance

El sistema debe:

1. Detectar automáticamente cuándo se obtiene, visualiza o mejora un disco.
2. Extraer con OCR los datos estructurales (set, slot, rareza, main stat, substats, rolls, nivel).
3. Persistir ese disco en `inventory_discs` con su score de evaluación y lista de PJs compatibles.
4. Notificar al usuario qué decisión tomar: equipar a PJ X, mantener como reserva tipo Y, o descartar.

El sistema NO:

- Equipa discos automáticamente (Daniel decide siempre).
- Descarta discos automáticamente (aunque el juego tenga Desmontaje automático para A-rank, el sistema no toca la partida).
- Sustituye el criterio del usuario — las recomendaciones son sugerencias basadas en datos.

---

## 2. Actores y fuentes de datos

- **Cliente ZZZ** (ventana del juego, Windows): fuente de todas las capturas.
- **Servicio de captura**: proceso Python que monitoriza la ventana del juego y dispara screenshots.
- **Pipeline de OCR**: Tesseract para texto general, PaddleOCR como fallback para números densos.
- **Catálogo de sets** (`disc_sets`): fuente de verdad para nombres, bonus 2pc/4pc, arquetipos.
- **Builds por PJ** (`agent_discs`): configuración objetivo declarada para cada agente.
- **Thresholds por PJ** (`agent_thresholds`): rangos mín/óptimo/máx por stat.
- **Inventario** (`inventory_discs`): persistencia de todos los discos detectados, equipados o no.

---

## 3. Flujos de obtención — dos ramas paralelas

### 3.A Patrulla de Área (combate)

Flujo más común: Daniel entra a una misión de combate, pelea (posiblemente con combate automático activado), y al terminar ve la pantalla **"RESULTADOS DEL DESAFÍO"** con los drops a la derecha en un grid 2×4.

Propiedades del drop en esta pantalla:

- Visible: emblema del set, borde de rareza (S dorado, A morado), número del slot.
- NO visible aún: main stat, substats exactos, valores.
- Hotkeys: `R` descartar, `T` bloquear (visibles solo en el modal de detalle).

Al abrir un drop, aparece un **modal overlay** con el disco completo a nivel 0. Desde aquí se pueden leer set, slot, main, 3 o 4 substats ya.

Toggle **"Desmontaje automático"**: cuando está activo, los discos de rareza A se descartan sin llegar al inventario. El sistema debe respetarlo: si el toggle está activo y el drop es A-rank, no pre-registrar (se perdería).

### 3.B Tienda de Música — Afinación (currency)

Flujo alternativo: Daniel va con Nana, elige una partición (hexágono 1-6), confirma con `Afinar × 01` o `Afinar × 06`, y aparece la pantalla **"Resultado de afinación"** con un grid 2×3 mostrando los 6 discos obtenidos (siempre 6 cuando se usa ×06).

Diferencias clave respecto a Patrulla:

- Cada tile ya muestra `"Nombre del set (slot)"` textualmente, no solo icono.
- El detalle se muestra en el **panel izquierdo**, no en modal overlay.
- Desde el detalle hay botón **"Detalles"** que abre vista completa a pantalla completa.
- Botón **"Regresar"** cierra la pantalla.

### Implicación para el clasificador

El clasificador de pantalla debe distinguir ambas ramas porque el OCR apunta a ROIs distintos en cada una.

---

## 4. Máquina de estados de pantalla

Estados relevantes que el clasificador debe identificar:

| ID | Nombre | Fuente | Acción |
|----|--------|--------|--------|
| S1 | Patrulla — Selección de misión | Patrulla | Ignorar (solo confirmar que hay farming en curso) |
| S2 | Patrulla — Resultados del Desafío | Patrulla | Trigger: pre-registrar drops |
| S3 | Patrulla — Modal detalle de drop | Patrulla | Trigger: completar datos del disco |
| S4 | Tienda Música — Selector de partición | Música | Ignorar |
| S5 | Tienda Música — Resultado de afinación | Música | Trigger: pre-registrar drops |
| S6 | Tienda Música — Vista detallada (panel) | Música | Trigger: completar datos del disco |
| S7 | Tienda Música — Vista detallada (fullscreen) | Música | Trigger: alta fidelidad |
| S8 | Vista agente — Equipamiento | Cualquiera | Trigger secundario: leer equipados |
| S9 | Inventario discos — Grid + panel | Cualquiera | Trigger: escanear badges NEW! |
| S10 | Modal de upgrade | Cualquiera | Trigger: capturar PRE/POST |
| S11 | Pantalla de Desmontaje | Cualquiera | **Ignorar** — NO capturar aunque haya NEW! |
| S12 | Combate / diálogo / mapa / menú | Cualquiera | Negativos, ignorar |

### Anclas visuales para template matching

- Título **"RESULTADOS DEL DESAFÍO"** (estilizado, único) → S2.
- Header **"Resultado de afinación:"** → S5.
- Header **"Personalización de pistas de disco"** → S9.
- Hexágono central con slot **"DRIVER"** → S8 / S9.
- Botón rojo **"X"** esquina superior derecha + barra EXP verde → S10.
- Header **"Desmontaje"** + grid de tiles con checkbox → S11.

---

## 5. Triggers de captura — polling adaptativo

La captura no debe ser ni demasiado agresiva (costo de CPU) ni demasiado lenta (se pierden ventanas). El sistema usa **polling con cadencia variable según el estado detectado**.

### Cadencia por estado

| Estado detectado | Intervalo de polling | Razón |
|------------------|---------------------|-------|
| Reposo / combate / menú (S1, S4, S12) | 3-5 s | No hay datos que capturar, ahorro de CPU |
| Vista agente / inventario (S8, S9) | 2 s | Escaneo NEW! y lectura de equipados |
| Resultado de desafío / afinación (S2, S5) | 1 s | Ventana breve, el usuario puede pasar rápido |
| Modal detalle (S3, S6, S7) | 500 ms | Crítico — Daniel revisa y decide en segundos |
| Modal de upgrade (S10) | 500 ms | Crítico — captura PRE, animación, POST |
| Desmontaje (S11) | 5 s | Ignorado pero debe detectarse para no capturar |

### Triggers complementarios

1. **Evento de foco (`SetWinEventHook EVENT_SYSTEM_FOREGROUND`)**: cuando la ventana de ZZZ vuelve al foreground tras pérdida, forzar un scan inmediato sin esperar al siguiente tick. Útil cuando Daniel alt-tabea.
2. **Hotkey manual (`F8`)**: fuerza captura + OCR + evaluación sobre el estado actual. Fallback por si el clasificador falla.
3. **Badge NEW! scanner**: al entrar a S9 (inventario), pase ligero sobre todos los tiles buscando badge amarillo "NEW!" — cada uno se marca como pendiente de registrar.
4. **Cambio de nivel en modal de upgrade**: dentro de S10, si la barra EXP cambia de nivel, se toma snapshot PRE y POST.

---

## 6. Pipeline de análisis por disco

Orden de procesamiento una vez disparado un trigger en un estado capturable:

1. **Captura de pantalla** (mss o win32 BitBlt, ~20 ms).
2. **Clasificación de estado** (template matching sobre 3-4 anclas, ~50 ms).
3. **Crop de ROIs fijos** según el estado (ver tabla de ROIs en §7 del catálogo de capturas).
4. **OCR por ROI**:
   - Título del disco: Tesseract `--psm 7` (single line), regex `^(.+) \((\d)\)$` → set + slot.
   - Nivel: Tesseract `--psm 7`, regex `Nivel (\d+)/15`.
   - Main stat: Tesseract `--psm 6` (block), split nombre / valor.
   - Substats x4: Tesseract `--psm 6`, regex por línea `^(.+?)(?: \+(\d+))? (.+)$` → nombre, rolls, valor.
   - Rareza: clasificación por color del borde (hue del tile).
5. **Validación cruzada**:
   - Nombre del set existe en `disc_sets`? Si no, flag `notas='set desconocido'`.
   - Main stat permitida para ese slot? (Slots I-III tienen main fijo, IV-VI variable.)
   - Suma de rolls ≤ 5? (máximo físico de upgrades hasta nivel 15).
6. **Persistencia**: UPSERT en `inventory_discs` por hash `(fecha_obtencion, set_id, slot, main_stat, main_valor)`.
7. **Evaluación** (§7).
8. **Notificación** al usuario: toast o panel con recomendación.

### Presupuesto de tiempo por disco

| Etapa | Objetivo | Margen |
|-------|----------|--------|
| Captura pantalla | 20 ms | |
| Clasificación | 50 ms | |
| Crop + OCR (6 campos) | 250 ms | |
| Validación + persistencia | 30 ms | |
| Evaluación | 50 ms | |
| **Total objetivo** | **~400 ms** | < 1 s en P99 |

Crítico: Daniel puede cerrar la pantalla de detalle en 2-3 s. El pipeline debe terminar antes de que la pantalla cambie para no perder el dato.

---

## 7. Capa de evaluación (RF-06 — nuevo)

Esta es la pieza que convierte un disco capturado en una **recomendación accionable**.

### 7.1 Match por PJ (primario)

Para cada PJ en `agents`, se consulta su build declarado en `agent_discs` y se compara con el disco recién capturado:

```
score_pj = w_set  * match_set(disc.set_id, pj.set_4p_id, pj.set_2p_id)
         + w_main * match_main_slot(disc.slot, disc.main_stat, pj.build_mains)
         + w_subs * score_substats(disc.subs, pj.substats_positivos, pj.substats_perjudiciales)
```

- `match_set`: 1.0 si coincide con el set 4pc objetivo, 0.5 si coincide con el 2pc, 0.0 si no.
- `match_main_slot`: 1.0 si la main stat es exactamente la esperada para ese slot, 0.0 si no. Slots I-III son fijos (HP, ATK, DEF) y no cuentan para match_main; solo IV, V, VI.
- `score_substats`: suma algebraica de las 4 substats contra los dos vectores del PJ — positivos (sumar) y perjudiciales (restar). Los rolls de la substat multiplican el peso: un `Crit DMG +3` con peso 1.0 aporta más que un `Crit DMG +0` con el mismo peso. Los perjudiciales se penalizan igualmente en función de los rolls: una substat perjudicial con muchos rolls hace que el disco sea *peor* que uno "limpio".

Si `score_pj > pj.threshold_equip` → el disco se marca como **"equipable para PJ X"**.
Si `score_pj > pj.threshold_upgrade` → el disco se marca como **"vale la pena mejorar para PJ X"**.

Un disco puede ser candidato para múltiples PJs; se devuelve la lista ordenada por score.

### 7.2 Match por arquetipo (secundario)

Si **ningún PJ** alcanza `threshold_upgrade`, el disco no es directamente útil hoy. Pero puede ser un disco objetivamente bueno para un PJ futuro. Ahí entra el arquetipo.

Cada set tiene uno o más arquetipos asignados en `disc_set_archetype`. Cada arquetipo tiene un perfil ideal en `disc_archetypes`:

- `mains_4`, `mains_5`, `mains_6` — mains válidas por slot para ese arquetipo.
- `substats_positivos` — JSON con pesos por substat (0.0 a 1.0).
- `substats_perjudiciales` — JSON con penalizaciones por substat (valores negativos, -0.0 a -1.0).
- `threshold_stock` — score mínimo para considerar el disco "reserva".

#### 7.2.1 Nomenclatura canónica de stats

**Mains válidos por slot** (slots IV-VI; slots I-III son fijos HP/ATK/DEF flat):

| Slot | Mains posibles |
|------|----------------|
| IV | Prob. Crítica, Daño Crítico, Maestría de Anomalía, HP%, ATK%, DEF%, Tasa de Perforación |
| V | Bono Daño [elemento], HP%, ATK%, DEF%, Tasa de Perforación |
| VI | HP%, ATK%, DEF%, Maestría de Anomalía, Impacto (%), Recarga de Energía (%) |

**Substats válidos** (10 en total):

HP, HP%, ATK, ATK%, DEF, DEF%, Prob. Crítica, Daño Crítico, Perforación (flat), Maestría de Anomalía.

No existen como substat: Tasa de Anomalía, Impacto, Recarga de Energía, Tasa de Perforación, Bono Daño. Esos son exclusivamente mains.

#### 7.2.2 Tabla de arquetipos (corregida)

Tres categorías por substat: **positivo** (pondera hacia arriba el score), **perjudicial** (pondera hacia abajo), **intermedio / neutro** (no suma ni resta — no aparece en ninguna columna). El intermedio es para stats que "no son ideales pero tampoco matan el disco".

| Código | Nombre | Mains IV | Mains V | Mains VI | Substats positivos | Substats perjudiciales | Substats intermedios |
|--------|--------|----------|---------|----------|--------------------|------------------------|----------------------|
| `ATK_DPS` | Atacante ATK-scaler | Crit Rate, Crit DMG, ATK% | Bono Daño, ATK% | Crit DMG, ATK% | Crit Rate, Crit DMG, ATK%, ATK, PEN | DEF, DEF%, HP, HP%, Maestría | — |
| `HP_DISRUPT` | Disruptivo HP-scaler | Crit Rate, Crit DMG, HP% | Bono Daño, HP% | Crit DMG, HP% | Crit Rate, Crit DMG, HP%, HP | DEF, DEF%, Maestría, PEN | ATK, ATK% |
| `ANOMALY` | Anomaly DPS | Maestría Anomalía, ATK% | Bono Daño, ATK% | Maestría Anomalía, ATK% | Maestría Anomalía, ATK%, ATK, PEN | DEF, DEF%, HP, HP%, Crit DMG | Crit Rate |
| `STUN` | Aturdidor | Crit Rate, Crit DMG, ATK% | ATK% | Impacto | ATK%, ATK, Crit Rate, Crit DMG, PEN | DEF, DEF%, HP, HP%, Maestría | — |
| `SUPPORT_ER` | Soporte de energía | ATK%, Crit Rate | ATK%, Bono Daño | Recarga de Energía | ATK%, HP%, Crit Rate, Crit DMG, PEN | DEF, DEF%, Maestría | — |
| `DEFENSE` | Defensor / Tank | DEF%, HP% | DEF%, HP% | Impacto, DEF%, HP% | DEF%, DEF, HP%, HP | ATK, ATK%, PEN, Maestría | Crit Rate, Crit DMG |

Notas:

- En `ATK` / `HP` aparecen tanto la versión % como la plana — ambos existen como substat en ZZZ y ambos contribuyen al scaling, aunque `%` es el más valorado. En el peso del scoring la versión plana pesa típicamente 0.4 y la `%` pesa 1.0.
- `PEN` está en positivos para `ATK_DPS`, `STUN`, `SUPPORT_ER` y `ANOMALY`; en `HP_DISRUPT` es perjudicial porque los disruptivos ya ignoran defensa por diseño de kit y el roll desperdicia stat útil; en `DEFENSE` es perjudicial porque no aporta a la supervivencia del tank.
- En `HP_DISRUPT`, `ATK` y `ATK%` quedan en **intermedio** porque sí escalan su daño pero es marginal comparado con HP% — no vale marcarlos perjudiciales pero tampoco positivos.
- En `DEFENSE`, `Crit Rate` y `Crit DMG` quedan en **intermedio** por la misma razón: pueden sumar algo de daño en defensores que atacan (ej. Caesar, Seth) pero no son la prioridad del arquetipo.
- En `ANOMALY`, `Daño Crítico` es perjudicial porque las reacciones de anomalía no escalan con crit — un roll ahí es roll perdido. `Prob. Crítica` se deja en intermedio porque algunos anomaly PJs (Miyabi, Yanagi) sí hacen daño directo con crits secundarios.
- `Maestría de Anomalía` como substat solo tiene valor real para el arquetipo `ANOMALY`; para los demás es perjudicial porque "ocupa un slot de roll" que debería haber ido a stats útiles.

#### 7.2.3 Ejemplo de scoring con perjudiciales

Disco: Tecno Picado slot V, main "Bono Daño Físico", subs "Daño Crítico +2 (18%)", "Prob. Crítica +1 (2.4%)", "ATK% +1 (3%)", "ATK +0 (19)".

- Set → arquetipo primario: `ATK_DPS`.
- Main (slot V "Bono Daño") → en la lista de `ATK_DPS.mains_5` ✓ → +1.0.
- Substats: Crit DMG (+1.0), Crit Rate (+1.0), ATK% (+1.0), ATK (+0.4) → subtotal subs = 3.4.
- Perjudiciales detectados: ninguno → penalización = 0.
- Score final (normalizado) ≈ 0.92 → supera `threshold_stock=0.7` → **"Reserva: ATK_DPS"**.

Mismo set pero con subs "DEF% +2", "HP% +1", "Maestría +1", "Prob. Crítica +1":

- Main ✓ → +1.0.
- Substats: Crit Rate (+1.0) único positivo; DEF% (−1.0), HP% (−0.5 por ser stat del disruptivo, no directamente perjudicial pero no suma), Maestría (−1.0) → subtotal ≈ −1.5.
- Score final ≈ 0.05 → por debajo de `threshold_stock` → **"Descartar"**, aunque set y main sean perfectos.

Este es justamente el caso que mencionabas: un disco puede tener set y main ideales, pero si los rolls cayeron en substats perjudiciales el sistema debe reconocerlo y no marcarlo como reserva.

### 7.3 Decisión final

```
if existe_pj_con_score > threshold_equip:
    recomendacion = "Equipar a " + pj_top
elif existe_pj_con_score > threshold_upgrade:
    recomendacion = "Mejorar para " + pj_top + " (evaluar tras nivel 15)"
elif existe_arquetipo_con_score > threshold_stock:
    recomendacion = "Reserva: " + arquetipo_top
else:
    recomendacion = "Descartar"
```

La recomendación se persiste en `inventory_discs.notas` y los PJs candidatos en `inventory_discs.agentes_compatibles` (JSON array de agent_id + score).

### 7.4 Re-evaluación post-upgrade

Cuando un disco de nivel 0 se lleva a nivel 15, se re-ejecuta el scoring con las substats completas. La recomendación puede cambiar: un disco marcado "Reserva" en nivel 0 puede convertirse en "Equipar" en nivel 15 si los rolls cayeron bien.

---

## 8. Detección de set activo (texto gris → blanco)

En la vista agente (S8), el bloque "Efecto de conjunto" muestra el texto del bonus 2pc y 4pc. El color del texto cambia:

- **Gris**: el bonus NO está activo (no hay suficientes piezas del set equipadas).
- **Blanco**: el bonus está activo.

Este indicador sirve para detectar "set roto" — por ejemplo, un PJ que debería tener 4pc de Monarca pero solo tiene 3 piezas mostrará el texto de 4pc en gris.

Implementación: crop del bloque "Efecto de conjunto", OCR, y sampling de píxeles en el área de texto. Si el promedio de luminancia > threshold → activo, si no → inactivo.

**Importante**: este comportamiento solo ocurre en la vista agente. En la vista detalle de tienda de música el texto siempre aparece igual.

---

## 9. Reglas de exclusión

Situaciones en las que el sistema debe deliberadamente **no** capturar o no registrar:

1. **Discos de rareza A-rank con Desmontaje automático activado**: se descartan antes de entrar al inventario. El sistema puede leerlos en S2 pero no debe persistirlos (se perdería el dato pero no vale la pena — Daniel descarta A-rank siempre).
2. **Pantalla de Desmontaje (S11)**: aunque los tiles muestren badge "NEW!", son discos ya existentes que Daniel está seleccionando para descartar. El sistema debe detectar S11 y cortar cualquier captura.
3. **Discos ya persistidos con el mismo hash**: el pipeline hace UPSERT por `(fecha_obtencion, set_id, slot, main_stat, main_valor)` para evitar duplicados. Si el hash existe, se actualiza en vez de insertar.
4. **Capturas con OCR confianza < 0.7**: si el OCR no está seguro del valor, el disco se marca `notas='requiere revisión manual'` y no se evalúa automáticamente.

---

## 10. Presupuesto de rendimiento

| Operación | P50 | P95 | P99 | Hardware asumido |
|-----------|-----|-----|-----|------------------|
| Screenshot completo | 20 ms | 40 ms | 60 ms | Monitor primario 2560×1440 |
| Clasificación de estado | 50 ms | 100 ms | 150 ms | Template matching OpenCV |
| OCR completo (6 campos) | 250 ms | 400 ms | 600 ms | Tesseract 5, CPU |
| Evaluación scoring | 50 ms | 80 ms | 100 ms | SQLite indexed |
| **Total pipeline (un disco)** | **~370 ms** | **~620 ms** | **~900 ms** | |

Si el P99 sube por encima de 1 s se activa un downgrade: OCR solo en el ancla crítica (título del disco) y diferir substats al siguiente ciclo. Mejor tener el disco identificado que perderlo.

---

## 11. Modelo de datos

### 11.1 Tablas existentes (se reutilizan)

- `agents` — catálogo de PJs con stats base y build declarado (`set_4p_id`, `set_2p_id`, `disco6_main`).
- `agent_discs` — build objetivo por slot por PJ (cuáles substats idealmente).
- `agent_thresholds` — rangos de stat con `fuente` ('comunidad' vs 'daniel').
- `disc_sets` — catálogo de sets.
- `inventory_discs` — persistencia de todos los discos detectados. Ya tiene `score_evaluacion`, `agentes_compatibles`, `descartado`, `agente_asignado`.

### 11.2 Tablas nuevas propuestas

```sql
-- Catálogo de arquetipos de build
CREATE TABLE disc_archetypes (
    id                    INTEGER PRIMARY KEY,
    code                  TEXT UNIQUE NOT NULL,   -- 'ATK_DPS', 'HP_DISRUPT', ...
    nombre                TEXT NOT NULL,
    descripcion           TEXT,
    mains_4               TEXT,                   -- JSON array: ['ATK%', 'Prob. Crítica']
    mains_5               TEXT,
    mains_6               TEXT,
    substats_positivos    TEXT,                   -- JSON: {'Prob. Crítica': 1.0, 'ATK%': 1.0, 'ATK': 0.4}
    substats_perjudiciales TEXT,                  -- JSON: {'DEF%': -1.0, 'Maestría de Anomalía': -1.0}
    threshold_stock       REAL DEFAULT 0.7
);

-- Relación N:M set ↔ arquetipo
CREATE TABLE disc_set_archetype (
    set_id       INTEGER NOT NULL REFERENCES disc_sets(id),
    archetype_id INTEGER NOT NULL REFERENCES disc_archetypes(id),
    prioridad    INTEGER NOT NULL DEFAULT 1,     -- 1 = primario, 2 = secundario
    PRIMARY KEY (set_id, archetype_id)
);

-- Preferencias de substats ponderadas por PJ (positivo o perjudicial)
-- peso > 0 = substat deseable; peso < 0 = perjudicial; |peso| = intensidad
CREATE TABLE agent_substat_preferences (
    agente_id INTEGER NOT NULL REFERENCES agents(id),
    substat   TEXT NOT NULL,                     -- 'Prob. Crítica', 'ATK%', 'DEF%', ...
    peso      REAL NOT NULL DEFAULT 0.0,         -- -1.0 a +1.0
    PRIMARY KEY (agente_id, substat)
);

-- Thresholds de score por PJ (decisión equipar vs mejorar vs descartar)
CREATE TABLE agent_score_thresholds (
    agente_id        INTEGER PRIMARY KEY REFERENCES agents(id),
    threshold_equip   REAL NOT NULL DEFAULT 0.75,
    threshold_upgrade REAL NOT NULL DEFAULT 0.50,
    fuente            TEXT DEFAULT 'comunidad'   -- 'comunidad' | 'daniel'
);

-- Histórico de evaluaciones (auditoría + trends)
CREATE TABLE inventory_disc_evaluations (
    id                INTEGER PRIMARY KEY,
    inventory_disc_id INTEGER NOT NULL REFERENCES inventory_discs(id),
    fecha             DATETIME DEFAULT CURRENT_TIMESTAMP,
    trigger_evento    TEXT,                      -- 'captura_inicial' | 're_eval_threshold' | 're_eval_upgrade' | 're_eval_manual'
    recomendacion     TEXT,                      -- 'equipar_pj_X' | 'mejorar_pj_Y' | 'reserva_arq_Z' | 'descartar'
    score             REAL,
    detalle_json      TEXT                       -- desglose: set_match, main_match, subs_positivos, subs_perjudiciales, arquetipo, pj_top
);
```

### 11.3 Índices recomendados

```sql
CREATE INDEX idx_inv_set_slot       ON inventory_discs(set_id, slot);
CREATE INDEX idx_inv_agente         ON inventory_discs(agente_asignado);
CREATE INDEX idx_inv_pending        ON inventory_discs(descartado, equipado) WHERE descartado = 0;
CREATE INDEX idx_agent_discs_lookup ON agent_discs(set_id, slot, main_stat);
```

---

## 12. Decisiones cerradas (iteración abril 2026)

Las 6 preguntas abiertas quedaron resueltas tras discusión con Daniel.

### 12.1 Arquetipos por set — cerrado

Los arquetipos se definen orientados a **sets con valor futuro** (cuando salgan PJs que encajen con ellos). Los PJs actuales siguen evaluándose por su build concreto en `agent_discs` + sus preferencias de substat en `agent_substat_preferences`. El arquetipo NO reemplaza el build per-PJ; es capa de fallback cuando ningún PJ reclama el disco.

### 12.2 Substats preferidos por PJ — cerrado

Seed inicial desde [prydwen.gg](https://www.prydwen.gg/zenless/) usando su orden de prioridad por PJ. Formato de carga: scraping o transcripción manual por PJ, guardado en `agent_substat_preferences` con `fuente='prydwen'`. Daniel hace override cuando discrepa, guardado con `fuente='daniel'`.

### 12.3 Thresholds de score por PJ — aclaración + decisión

**Aclaración de qué significan los dos thresholds** (este era el punto que quedó confuso):

- `threshold_equip` (default `0.75`): **cuán bueno tiene que ser un disco en su totalidad** — set + main + subs sin perjudiciales — para que el sistema diga *"este disco es suficiente: equipalo ya a PJ X"*. Alto porque queremos certeza antes de pedir al usuario que haga el swap.
- `threshold_upgrade` (default `0.50`): cuán prometedor tiene que verse un disco **a nivel 0** para que el sistema diga *"vale la pena gastar materiales en llevarlo a nivel 15 y re-evaluar"*. Más bajo porque a nivel 0 tenemos información parcial (3 subs o 4 con rolls bajos).

**Decisión**: todos los PJs arrancan con los defaults (0.75 / 0.50) y Daniel sube el `threshold_equip` manualmente en los PJs que quiere exigir más (ej. core DPS como Miyabi podría ir a 0.85). No se calibra nada caso-por-caso al inicio — arranca uniforme, se afina después con uso real.

### 12.4 Notificación / UX — cerrado → se eleva a RF-11

Se define como programa **standalone tipo .exe** corriendo en segundo plano:

- **UI cerrada**: cuando el sistema detecta un disco farmeado, abre una ventana emergente compacta con el análisis (recomendación + scores + comparativa si aplica).
- **UI abierta**: panel completo con opciones extendidas — análisis contra enemigos, simulación de builds/equipos, comparador de configuraciones, histórico, edición de thresholds y preferencias.

La UX es personal (no hay otros usuarios). Todo este alcance de interfaz se mueve al **RF-11** como requerimiento separado.

### 12.5 Histórico de recomendaciones — cerrado

**Sí** se guarda. Tabla nueva `inventory_disc_evaluations`:

```sql
CREATE TABLE inventory_disc_evaluations (
    id                INTEGER PRIMARY KEY,
    inventory_disc_id INTEGER NOT NULL REFERENCES inventory_discs(id),
    fecha             DATETIME DEFAULT CURRENT_TIMESTAMP,
    trigger           TEXT,                          -- 'captura_inicial' | 're_eval_threshold' | 're_eval_upgrade'
    recomendacion     TEXT,                          -- 'equipar_pj_X' | 'mejorar_pj_Y' | 'reserva_arq_Z' | 'descartar'
    score             REAL,
    detalle_json      TEXT                           -- JSON con desglose: set_match, main_match, subs_positivos, subs_perjudiciales, arquetipo, pj_top
);
```

Permite auditar decisiones pasadas ("¿por qué el sistema me dijo que descartara este disco hace 2 semanas?") y también reconstruir trends si Daniel cambia criterios.

### 12.6 Re-evaluación masiva — cerrado

Cuando Daniel ajusta thresholds o `agent_substat_preferences` la re-evaluación **no** se dispara automáticamente por cada cambio individual (sería lento y redundante si ajusta varios PJs seguidos).

Flujo definido:

1. Daniel edita thresholds/preferencias de N PJs en la UI.
2. Los cambios se acumulan en un buffer pendiente (indicador visual "3 PJs con cambios sin confirmar").
3. Daniel hace click en un botón explícito **"Aplicar cambios y reevaluar inventario"**.
4. El sistema dispara `recompute_all()` sobre `inventory_discs` no descartados y no equipados — recorre cada disco, lo re-scorea con la nueva config, inserta una fila nueva en `inventory_disc_evaluations` con `trigger='re_eval_threshold'`, y actualiza `inventory_discs.score_evaluacion` + `agentes_compatibles` + `notas`.

Los descartados y los equipados no se re-evalúan (ya no son candidatos activos). Si Daniel quiere reevaluar también equipados — caso borde — la UI ofrece un checkbox "Incluir equipados" antes de confirmar.

---

## 13. Referencias

- Iteración 1 de análisis de capturas: [`Analisis_Capturas_Iteracion_1.md`](./Analisis_Capturas_Iteracion_1.md) (misma carpeta).
- Catálogo de screenshots requeridos: [`Catalogo_Screenshots_Requeridos.md`](./Catalogo_Screenshots_Requeridos.md) (misma carpeta).
- Diagramas de flujo: [`../Diagramas de flujos/`](../Diagramas%20de%20flujos/) — versiones v2 post-capturas.
- Screenshots originales: `Screenshots_Triggers/Discos_Triggers/` (raíz del proyecto).
- Schema actual: `db/danibod_zzz_v2.db`.

---

## 14. Historial de cambios

- **2026-04-24 (v1)** — Versión inicial. Integra hallazgos de iteración 1, añade RF-06 (evaluación), define polling adaptativo, propone tablas nuevas para arquetipos y preferencias.
- **2026-04-24 (v1.1)** — Correcciones post-revisión de Daniel:
  - Typo "Desafín" → "Desafío" en toda la documentación.
  - Tabla de arquetipos rehecha con substats válidos (10 reales en ZZZ; se eliminan Tasa Anomalía / Impacto / Recarga Energía / Tasa Perforación / Bono Daño que solo son mains).
  - Agregada columna **Substats intermedios / neutros** (ni positivos ni perjudiciales).
  - Ajustes específicos: `ATK_DPS` ahora considera PEN positivo; `HP_DISRUPT` mueve ATK/ATK% de perjudicial a neutro; `ANOMALY` añade Crit DMG a perjudiciales y deja Crit Rate neutro; `DEFENSE` mueve Crit Rate/Crit DMG a neutro.
  - Agregada tabla `inventory_disc_evaluations` para histórico de recomendaciones.
  - Sección 12 pasa de "preguntas abiertas" a "decisiones cerradas" con las 6 respuestas de Daniel.
  - Se eleva UX/UI a **RF-11** como requerimiento separado.
  - Re-evaluación masiva pasa a modo batch con confirmación explícita del usuario.
