# Análisis de Capturas — Iteración 1 (abril 2026)

Revisión detallada de las ~35 capturas que subió Daniel para calibrar RF-04 / RF-05 / arquitectura.

---

## 1. Fuentes de obtención de discos (ACTUALIZADO)

Ahora tenemos confirmado que existen **dos** flujos de farmeo, no uno:

### 1.A Patrulla de Área (combate)

- **Pantalla:** "Resultados del Desafío" (título central estilizado).
- **Toggle nuevo descubierto:** "Desmontaje automático" arriba a la derecha. Cuando está activo, algunos discos pueden ser auto-descartados sin llegar al inventario — esto es relevantísimo para tracking: hay que detectar su estado.
- **Grid de drops:** visible a la derecha, 2x4 máx. Cada tile muestra:
  - Emblema del set (icono miniatura).
  - Borde de color por rareza (S dorado, A morado).
  - **Número del slot visible sobre el tile** (dato nuevo vs. lo que creíamos).
- **Detalle:** abre un modal superpuesto (overlay sobre la pantalla de resultados), no una pantalla completa.
- **Bottom buttons:** "Volver a intentar" + "Completar" + contador de stamina ("110/60").
- **Hotkeys visibles:** `R` descartar, `T` bloquear (mostrados en la parte inferior del modal de detalle).

### 1.B Tienda de Música — Afinación (currency)

- **NPC:** Nana (atención al cliente).
- **Pantalla entry:** selector hexagonal 1-6 con el título "Pulsa los números para seleccionar la partición de las pistas de disco" y opciones `Afinar × 01` / `Afinar × 06`.
- **Pantalla resultados:** "Resultado de afinación" con grid 2x3. Cada tile muestra `"Nombre del set (slot)"` textualmente, no solo icono. Tiles vacíos se rotulan como "EMPTY".
- **Detalle:** se muestra en el PANEL IZQUIERDO (no modal). Click en tile → panel cambia. Hay un botón "Detalles" que abre la vista completa a pantalla completa.
- **Botón "Regresar":** cierra la pantalla.

---

## 2. Hallazgos cruciales que impactan el diseño técnico

### 2.1 Rolls explícitos en el UI

El UI muestra los rolls directamente como `+N` al lado del nombre del sub. Ejemplos reales vistos:

- `Daño Crítico +1 9.6%` → 1 roll aplicado.
- `Maestría de Anomalía +2 27` → 2 rolls.
- `Ataque +3 76` → 3 rolls.
- `Ataque 19` (sin `+N`) → 0 rolls, valor inicial.

**Implicación:** el OCR no necesita inferir rolls desde el valor. Regex directo `\+(\d+)` sobre el texto del sub lo resuelve. Gran simplificación vs. lo que habíamos planeado.

### 2.2 Sub4 puede estar desbloqueada desde nivel 0

Antes asumía que todo disco dropea con 3 subs y desbloquea sub4 al nivel 3. Falso: hay discos que dropean con las 4 subs ya visibles (ej. Nana slot 6 Ejemplo 2 con 4 subs a nivel 0; Fábula Yunkui slot 1 con 3 subs a nivel 0). Es un coinflip por drop.

**Implicación RF-05:** el diff PRE vs POST para un upgrade 0→3 puede ser:

- **Caso A (sub4 bloqueada):** POST muestra 4 subs donde había 3 → identificar qué sub se desbloqueó + su valor inicial.
- **Caso B (sub4 ya desbloqueada):** POST muestra 4 subs con algún `+1` nuevo → identificar cuál sub recibió el roll.

### 2.3 Formato del nombre en vista detalle

Todos los lugares (modal desde resultados, vista detalle inventario, vista tienda música) usan la misma convención:

```
"Nombre del set (N)"  ← N es el slot, 1-6
```

Ejemplos vistos: "Fábula Yunkui (1)", "Monarca del Pináculo (5)", "Floración del alba (4)", "Nana a la luz cenicienta (6)", "Jazz caótico (1)".

**Implicación:** regex `^(.+) \((\d)\)$` extrae nombre + slot en una pasada.

### 2.4 Badge "NEW!" en inventario

Confirmado (Ejemplo 3 del inventario individual): los discos obtenidos recientemente llevan una etiqueta amarilla "NEW!" sobre el tile del inventario grid. Útil como trigger secundario: si el bot detecta un "NEW!" en el scan del inventario, sabe que hay un drop sin registrar.

### 2.5 Avatar del agente equipado en tiles del grid

Confirmado: los discos equipados muestran la cabeza del agente en la esquina superior derecha del tile del inventario. El agente también aparece al lado del nombre en la vista detalle (círculo pequeño a la derecha de `"Nombre del set (N)"`).

### 2.6 Flujo de upgrade: dos comportamientos post-nivel 15

| Origen del upgrade | Comportamiento al llegar a nivel 15 |
|---|---|
| Modal desde vista agente/inventario | Modal se cierra automáticamente → vuelve a vista general del inventario |
| Vista detalle de la tienda de música | Permanece en la pantalla detallada (disco grande a la izquierda) |

**Implicación RF-05:** el detector POST debe saber de qué origen viene el upgrade, porque el "snapshot final" se captura en pantallas distintas.

### 2.7 Materiales del upgrade (3 tiers)

El modal de upgrade muestra 3 iconos de material con contador `N/M` cada uno. No necesitamos leer exactamente cuáles, pero es un marcador visual útil para el clasificador de pantalla.

### 2.8 Nivel de proxy vs nivel del disco

En Resultados del Desafío aparece "Nivel de proxy 60 MAX/MAX + 600 EXP". Es el pase/batalla del usuario, NO el nivel del disco. Ignorar al extraer datos de discos.

### 2.9 Combate automático

Existe toggle "Combate automático" en la pantalla de selección de Patrulla de Área. Útil: cuando el usuario tiene esto activo, va a farmear sin supervisión y los triggers de polling se vuelven críticos (no habrá hotkey manual).

### 2.10 Botón "Reemplazar" vs "Mejorar"

En la vista detalle individual (Ejemplo_1 nivel 15): el botón principal a la derecha es "Mejorar" cuando el disco aún puede subir; cambia a "Reemplazar" cuando ya está a nivel 15 (Ejemplo_1 del folder 07). Otro marcador para el clasificador.

---

## 3. Capas revisadas con la info real

### 3.1 Clasificador de pantalla

Ahora necesita distinguir al menos estos estados (antes eran 3-4, ahora son ~10):

1. Patrulla de Área — pantalla de selección de misión.
2. Patrulla — Resultados del Desafío (lista de drops visible).
3. Patrulla — Modal detalle de drop (overlay).
4. Tienda de Música — selector de partición.
5. Tienda de Música — Resultado de afinación.
6. Tienda de Música — Vista detallada (Detalles).
7. Vista agente — Equipamiento (hexágono con 6 slots + DRIVER).
8. Inventario discos — Grid + panel derecho.
9. Upgrade modal — con materiales y botón Mejorar.
10. Otros (combate, diálogo, mapa, menú) — negativos.

Anclas visuales confiables para template matching:

- "RESULTADOS DEL DESAFÍN" (título muy estilizado, único).
- "Resultado de afinación:" (header del panel derecho).
- "Personalización de pistas de disco" (header derecho en inventario).
- Hexágono central con slot "DRIVER" (visible en vista agente e inventario).
- Botón rojo "X" esquina superior derecha (modal de upgrade).
- Bar horizontal tipo "N / NNN" con color verde (EXP bar del upgrade modal).

### 3.2 Extractor de datos de disco

ROI fijos que puedo calibrar desde ahora:

| ROI | Contenido | Regex / parse |
|-----|-----------|---------------|
| Título del disco | `"Set (N)"` | `^(.+) \((\d)\)$` |
| Nivel | `"Nivel NN/15"` | `Nivel (\d+)/15` |
| Rarity | Badge S/A/B | color-based classification |
| Atributo principal | `Nombre`  `Valor[%]` | tabla de stats |
| Substats x4 | `Nombre[ +N] Valor[%]` | `^(.+?)(?: \+(\d+))? (.+)$` |
| Avatar agente | círculo a la derecha del título | face recognition o color-match del pelo |
| Efecto conjunto | bloque descriptivo | literal match contra tabla de sets |

### 3.3 Trigger extendido: "NEW!" badge scanner

Añadir a la capa de detección: un pase ligero que, al entrar al inventario, busca todos los tiles con badge "NEW!" y los marca como pendientes de registrar.

---

## 4. Cambios propuestos al diagrama RF-04

1. Agregar rama separada para Tienda de Música con su propio flujo de captura.
2. Agregar nodo para el toggle "Desmontaje automático" como consideración.
3. Agregar trigger secundario: "NEW! badge scan" al entrar a inventario.
4. Agregar discriminación del modal overlay (con/sin).

## 5. Cambios propuestos al diagrama RF-05

1. Bifurcar desde el inicio: origen agente/inventario vs origen tienda música.
2. En cada rama, el snapshot POST se lee de una pantalla distinta.
3. Agregar nodo de decisión: "¿PRE tenía 3 o 4 subs?" para el caso de upgrade 0→3.

---

## 6. Preguntas abiertas tras esta iteración

1. El toggle **"Desmontaje automático"** en Resultados del Desafío — ¿qué descarta? ¿B siempre? ¿A veces? ¿Lo configuraste manualmente con reglas? Esto afecta al tracking porque los discos auto-descartados nunca llegan al inventario y no deberíamos pre-registrarlos.
2. **"Afinar × 06"** en la tienda de música — ¿eso siempre devuelve 6 discos del slot seleccionado, o a veces devuelve menos (por eso los "EMPTY" en el grid)?
3. Cuando un disco está equipado, vi el avatar del agente en la vista individual. **¿El juego tiene un filtro en el inventario para ver "solo no equipados"?** Sería útil para RF-02.
4. En la vista detalle del inventario, vi un botón **"Recomendado"** — ¿qué hace? ¿Autosugerencia del juego?
5. **"Personalización de pistas de disco"** (botón en el header del inventario) — ¿para qué es?
6. El bloque "Efecto de conjunto" siempre muestra el texto del bonus 2pc y 4pc; **¿se resalta de color distinto si el set está activo en el agente actual?** Podría usarse para detección de "set roto" vs "set completo".
