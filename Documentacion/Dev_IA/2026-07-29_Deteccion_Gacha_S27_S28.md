# Detección de la pantalla de gacha — S27 (banner) y S28 (resultados)

**Fecha:** 2026-07-29
**Estado:** spec aprobado, sin implementar
**Alcance:** Fase 1 — **detección pura, sin extracción**
**RNF aplicables:** RNF-03 (solo píxeles), RNF-02 (nada inventado), RNF-06 (cadencia)

---

## 1. Por qué esta fase es distinta

Daniel tiene una cantidad limitada de tiradas. Al contrario del ritmo habitual del
proyecto —iterar contra el juego hasta que el parser salga bien— acá **no se pueden
hacer QAs sucesivos** sobre la pantalla de resultados: cada tirada gastada sin
cosechar es un fixture que no se recupera.

De ahí la regla que ordena todo el trabajo:

> **Lo primero que tiene que funcionar es el volcado de frames crudos, no la
> detección fina.** El parser se desarrolla después, offline, contra esos frames.

Hay un x10 disponible y pendiente. Se dispara **después** de que esta fase esté
verificada, no antes.

---

## 2. Alcance

### Entra

1. Dos estados nuevos en `detector.py`: `S27` (banner) y `S28` (resultados de
   sintonización), registrados en los 7 puntos.
2. Templates anclados al cromo invariante de cada pantalla.
3. Verificaciones `_verify_s27` / `_verify_s28`.
4. Cierre del roce medido entre los banners y el template de `S2`.
5. Volcado crudo de frames **armado por detección**, sin intervención manual.
6. Test de regresión que crece solo con los fixtures que Daniel vaya agregando.

### No entra (spec siguiente)

- OCR de la pity, del canal, de las monedas y de los días restantes.
- Lectura de la rareza por badge en la grilla.
- Matcher de íconos de W-Engine contra `Documentacion/Interfaz/Engines_icons/`.
- Identificación del PJ del tile contra `Documentacion/Interfaz/splash_arts/`.
- Cualquier escritura a DB. Esta fase es **display-only**.
- La animación de recolección (la pila de televisores). No se modela ni se
  detecta: es salteable y no contiene ningún dato. Sí queda grabada, porque el
  volcado graba todo.

---

## 3. Hallazgos verificados

Todo lo de esta sección se midió sobre los fixtures reales, no se dedujo.

### 3.1 Los fixtures no disparan ningún estado actual

Los 15 archivos de `Documentacion/Screenshots_Triggers/Gacha_Sintonizacion/`
(2559×1439) clasifican **S12** con el detector real. Terreno virgen, sin
falsos positivos preexistentes.

### 3.2 `S26` ya está ocupado

`S26` es *"Equipamiento PJ — vista detalle W-Engine"*, registrado en los 7 puntos
(comparte template con `S17`, se separa por `_verify_s26`). `STATE_DESCRIPTIONS`
llega hasta `S25` pero el resto del registro incluye `S26`. Los estados nuevos
son **`S27`** y **`S28`**.

### 3.3 El cromo invariante del banner

Mapa de desvío píxel a píxel sobre los 6 banners de 3.1 (Aria, Remielle,
W_engine_Aria, W_engine_Remielle, Bangbus, Permanente):

| Región | Comportamiento |
|--------|----------------|
| Botones `1 sintonización` / `10 sintonizaciones` (inferior derecha) | **estable** |
| Riel de canales (columna izquierda, ~0–12 % del ancho) | **estable** (las pastillas; los íconos cambian) |
| Barras superior e inferior | **estable** |
| Arte central (personaje, título, promoción) | **cambia entero** |

⚠️ El template **debe** anclarse en la franja inferior de botones. Anclarlo en el
arte lo rompe en el patch siguiente. Este es el motivo por el que se pidieron
banners de más de un tipo antes de diseñar.

### 3.4 Riesgo latente: los banners rozan el umbral de `S2`

| Banner | Mejor match actual | Confianza | Umbral de ese estado |
|--------|--------------------|-----------|----------------------|
| `Aria.png` | `s2_resultado_desafio.png` | **0.773** | `S2` = 0.80 |
| `Bangbus.png` | `s2_resultado_desafio.png` | 0.726 | 0.80 |
| `W_engine_Aria.png` | `s2_resultado_desafio_evento.png` | 0.602 | 0.80 |

Margen real de `Aria.png`: **0.027**. El template de `S2` es una banda superior
dominada por fondo oscuro y ya se sabe que sobre-matchea bandas oscuras (la nota
del propio `THRESHOLD_BY_STATE` documenta el eclipse de `S13` a ~0.90). Un banner
a 0.773 está demasiado cerca de un estado que **captura discos**.

No es un problema hipotético que aparezca al agregar `S27`: existe hoy. Entra al
alcance porque estos fixtures son la primera evidencia de que existe.

### 3.5 La grilla de resultados es estática

Las 7 capturas de resultados muestran botón *Confirmar* y el texto *"Pulsa un
espacio en blanco para cerrar"*: la pantalla **espera input**, no se va sola. Lo
mismo el splash del agente (botón *Saltar*).

Consecuencia de diseño: **no hay carrera contra el reloj** en los frames que
importan. La única parte veloz es la animación, que no tiene datos. El volcado
crudo se justifica como red de seguridad ante un parser inmaduro, no como
defensa contra una ventana de milisegundos.

---

## 4. Diseño

### 4.0 Cómo se fija cada umbral

Los `0.85` de las tablas que siguen son **punto de partida, no valor final**. El
umbral se fija con la convención que ya usa el resto de `THRESHOLD_BY_STATE`:
medir el match de los fixtures objetivo, medir el de los negativos (los otros
fixtures de la carpeta más el QA negativo existente), y clavar el umbral **en el
medio del hueco** entre ambos. Si no hay hueco, el template está mal elegido y se
vuelve al paso del ancla — no se fuerza el número.

El valor definitivo y su medición se documentan como comentario en el propio
`THRESHOLD_BY_STATE`, igual que los estados existentes.

### 4.1 `S27` — Canal de sintonización (banner)

**Rol:** ANTELACIÓN A CAPTURA, igual que `S13` (nodo de farmeo → drops) y `S21`
(slider de baterías → `S22`). No extrae nada en esta fase.

| Punto de registro | Valor |
|---|---|
| `STATE_DESCRIPTIONS` | `"Canal de sintonización (banner) — ANTELACIÓN A CAPTURA"` |
| `THRESHOLD_BY_STATE` | a calibrar; punto de partida 0.85 (arma un flujo) |
| `_VALID_TRANSITIONS` | desde `S1`/`S12`; hacia `S28`, `S12`, `S1` |
| `_STATE_TEMPLATES` | `s27_banner_sintonizacion.png` = franja de botones ×1/×10 |
| `_VERIFICATION_REGISTRY` | `_verify_s27` |
| `NON_CAPTURE_STATES` | sí — no hay discos en esta pantalla |
| `polling_cadence_ms` | agresiva (~400 ms): es la antesala del evento |

**Responsabilidad extra:** al entrar en `S27` se **arma el volcado crudo**. Esto
reemplaza al disparo por hotkey que se descartó — el usuario entra al banner y el
sistema ya está grabando, sin acordarse de nada.

### 4.2 `S28` — Resultados de sintonización

| Punto de registro | Valor |
|---|---|
| `STATE_DESCRIPTIONS` | `"Resultados de sintonización (grilla 5×2)"` |
| `THRESHOLD_BY_STATE` | a calibrar; punto de partida 0.85 |
| `_VALID_TRANSITIONS` | desde `S27`, `S12`; hacia `S27`, `S12`, `S1` |
| `_STATE_TEMPLATES` | `s28_resultados_sintonizacion.png` = título + franja *Confirmar* |
| `_VERIFICATION_REGISTRY` | `_verify_s28` |
| `NON_CAPTURE_STATES` | sí en esta fase (no extrae) |
| `polling_cadence_ms` | ~1000 ms: la pantalla es estática y espera input |

**Orden en `_STATE_TEMPLATES`:** dos estados pueden compartir template y gana el
primero cuya verificación pasa. `S28` va **antes** que `S2` en la lista, por lo
medido en §3.4.

### 4.3 Volcado crudo de frames

Herramienta aparte, fuera del código de producción, modelada sobre
`tools/grab_desmontaje_frames.py`.

Solo lee píxeles: `mss` para capturar y `win32gui` para localizar la ventana. No
envía inputs, no lee memoria del proceso, no automatiza nada del juego (RNF-03).
Al haberse descartado el disparo por hotkey, esta fase ni siquiera **escucha** el
teclado.

Diferencias respecto de ese antecedente, y el porqué de cada una:

1. **Sin dedupe.** El dedupe decide *tirar* frames; en un evento irrepetible eso
   es exactamente lo que no queremos.
2. **Sin `classify()` en el camino crítico.** El loop de captura solo captura.
   La clasificación aparece en dos lugares, ninguno de ellos dentro del loop:

   - **Para armar/desarmar**, en un hilo aparte que muestrea (p. ej. 1 de cada
     10 frames de la cola). Es la única clasificación en vivo y no puede frenar
     la captura ni aunque tarde.
   - **Para etiquetar**, después y offline, con una herramienta que renombra los
     PNG ya volcados con el estado que dice el detector real.

   Consecuencia asumida: desarmar puede demorar unos frames de más. Se prefiere
   grabar de más antes que cortar antes de tiempo.
3. **Escritura desacoplada.** Medido sobre un frame real de 2559×1439:

   | operación | costo |
   |---|---|
   | `mss.grab` + BGRA→BGR (1080p) | ~28 ms |
   | `cv2.imwrite` PNG nivel 3 (default) | **252 ms** |
   | PNG nivel 1 | 203 ms · 2,5 MB |
   | PNG nivel 0 | 158 ms · 11 MB |

   Encodear en línea es **más lento que el intervalo** del cosechador actual. El
   loop mete el frame crudo en una cola y sigue; 2–3 threads escritores la drenan
   en paralelo (`imencode` suelta el GIL, así que escalan de verdad).
4. **Armado por detección, no por tecla.** Arranca al entrar en `S27`, corta al
   salir de `S28`.

**Presupuesto:** ~10 fps × 2,5 MB ≈ **1,5 GB por pasada de un minuto**. Aceptable
para un evento único.

**Destino:** `audit/frames_gacha/`, **gitignoreado en el mismo commit que lo
introduce** (lección del 2026-07-28: 150 MB de capturas de engines obligaron a
reescribir el historial).

### 4.4 Los fixtures también van al `.gitignore`

`Documentacion/Screenshots_Triggers/Gacha_Sintonizacion/` pesa ~38 MB y va a
crecer con cada patch. Mismo criterio y mismo precedente que
`16_discos_pj_grilla/` y `Engines_Triggers/`: queda **local**, se ignora en el
mismo commit, y el test que lo consume es *skip-if-absent*.

### 4.5 Regresión que crece sola

Un test recorre **todos** los archivos de `Banners/` y de
`Resultados_sintonizacion/` y exige:

- todo archivo de `Banners/` → `S27`;
- todo archivo de `Resultados_sintonizacion/` que sea grilla → `S28`;
- **ningún** archivo dispara un estado ajeno, en particular `S2`, `S13`, `S17`,
  `S22`, `S24` (los que capturan o escriben).

Descubre los archivos por glob. Cuando Daniel agregue los banners de 3.2 o 3.3, la
cobertura se extiende sin tocar el test — que es el modo de trabajo continuo que
pidió explícitamente.

Los `Resultados_sintonizacion/` no son todos grilla: `Ejemplo_3` es el splash del
agente contratado y `Ejemplo_6` es la animación de televisores. El test los trata
como **no-`S28`** y no exige estado para ellos en esta fase.

---

## 5. Riesgos

| # | Riesgo | Mitigación |
|---|--------|------------|
| R1 | El template del banner se ancla sin querer en arte que cambia | El ancla sale del mapa de desvío de §3.3, no de la intuición. La regresión sobre los 6 banners lo detecta. |
| R2 | `S27`/`S28` empujan el roce con `S2` a un FP real | Orden explícito en `_STATE_TEMPLATES` + `_verify_*` + la regresión de §4.5 exige que ningún fixture dispare `S2`. |
| R3 | El x10 se dispara antes de que el volcado esté verificado | El ensayo en seco (§6) es un criterio de aceptación bloqueante. |
| R4 | El volcado llena el disco si queda armado | Tope duro de frames y de segundos por pasada; corte al salir de `S28`. |
| R5 | La grilla y el splash comparten cromo y se confunden | `Ejemplo_3` y `Ejemplo_6` entran a la regresión justamente como negativos de `S28`. |

---

## 6. Criterios de aceptación

1. Los 6 banners → `S27`. Los 7 fixtures de grilla → `S28`.
2. `Ejemplo_3` (splash) y `Ejemplo_6` (animación) **no** dan `S28`.
3. Ningún fixture de la carpeta dispara `S2`, `S13`, `S17`, `S22` ni `S24`.
4. El QA negativo existente sigue verde: los estados nuevos no rompen nada.
5. La suite completa pasa.
6. **Ensayo en seco, costo cero:** Daniel abre el banner y navega entre canales sin
   tirar. Se verifica en vivo que `S27` engancha, que el volcado arranca solo, que
   sostiene el ritmo y que corta bien. **Bloqueante: sin esto no se tira el x10.**
7. Recién con 1–6 verdes, se tira el x10 y se cosechan los frames.

---

## 7. Después de esta fase

Con los frames del x10 en mano, y ya offline sin gastar nada:

- OCR del banner: pity A, pity S, canal seleccionado, monedas, días restantes. Es
  texto plano y es el dato de mejor relación valor/esfuerzo de la pantalla. La
  pity es **por canal**, así que el canal seleccionado es obligatorio para que el
  número signifique algo.
- Rareza por badge en la grilla (barato y confiable).
- Matcher de íconos de W-Engine sobre `avatar_descriptor.py`, cuyo docstring ya
  anticipa el reuso *"para íconos de W-engines y discos cambiando solo la librería
  de referencia"*. Se hereda el reject-set y el gate de abstención: ante duda,
  "incierto", nunca un nombre inventado (RNF-02).
- El tile del PJ es un **retrato rectangular**, encuadre distinto de los `-ico`
  circulares que usa hoy el `AvatarMatcher`. Es la mitad más incierta de las dos.

**Hueco de catálogo a resolver:** los 15 íconos `W-Engine_29_*` (Alpha, Bravo,
Charlie, Base, Arrow, Cobalt, Mark_I/II/III, Noviluna, Pleniluna, Revolver…) —
que son las esferas rango B de las grillas — **no están mapeados a ningún
`weapons.nombre`**. El README de `Engines_icons` mapea 31 de los otros, y la DB
tiene 6 armas rango B. El matcher va a poder decir *"esto es `W-Engine_29_Base`"*
sin saber a qué fila corresponde. Se resuelve offline; lo no verificable queda
NULL (RNF-02).

**Fuente gratuita de verdad de tierra:** el historial de sintonización lista en
texto los nombres de lo ya tirado. Cruzado con las grillas cosechadas da un set
etiquetado **sin gastar una sola tirada**, o sea que permite *medir* la tasa de
acierto del descriptor en vez de estimarla.
