# Censo de cuenta — Fase 0 (cobertura) + Fase 1 (roster) · 2026-08-16

> Ejecuta las fases 0 y 1 del [PLAN del 2026-07-22](./2026-07-22_PLAN_Censo_Inicial_Cuenta.md).
> Módulos nuevos: `app/core/census.py` (puro) y `app/core/census_store.py` (persistencia).
> Habilita: que el invariante equipado/asignado deje de estar bloqueado por "la DB divergió".

---

## 1. Qué problema resuelve, y la restricción que lo define

La DB es **transcripción manual nunca verificada contra el juego**, y ya divergió (QA 2026-07-20:
la DB decía Jane donde el juego decía Velina). El censo invierte la relación: la cuenta es la
verdad, la DB su reflejo.

**RNF-03 define la arquitectura.** El sistema no puede navegar el juego, así que el censo no es un
ETL: es un recorrido que el usuario hace y el sistema observa. De ahí el corolario que ordena todo
el módulo:

> Un censo que no sabe qué **no** vio es peor que no tener censo, porque produce una foto parcial
> con cara de completa.

### Decisiones de Daniel

| | |
|---|---|
| Alcance | Fase 0 + roster. Discos y armas después |
| Persistencia | Multi-sesión |
| Frecuencia | Recurrente — historial, para re-censar tras cada patch |
| Huérfanos | Marcar con nota + fecha. **No** borrar |
| Cierre | Hotkey explícita (F8) |
| Feedback | Solo log durante el recorrido |

---

## 2. Las dos asimetrías que sostienen la fase 0

### PENDIENTE ≠ HUÉRFANO, y la diferencia es una declaración humana

Verificado sobre las capturas: **el menú de personajes no tiene contador `N/M`**. Es la diferencia
con el desmontaje, donde el `N/300` del header es la única autoridad del conteo. Sin contador, el
sistema no puede saber si el recorrido llegó al final — y no debe fingir que sí.

Entonces `huerfano` es una transición **del cierre**, nunca de la observación. Dos corolarios que
se asumen de frente en vez de esquivarse:

- una corrida que nunca se cierra **no produce huérfanos jamás**;
- una **abandonada** (vencida a las 72 h, o contra otra DB) tampoco. Vencerse no es terminar.

### Reportar un PJ nuevo pide más evidencia que reconocer uno conocido

Un falso positivo acá dispara el onboarding de un personaje que no existe. Tres capas:

1. Un texto que no matchea pero **se parece** a alguien conocido (`Astre Yoo` → Astra Yao) se
   trata como lectura sucia de ese candidato, no como alta.
2. Un desconocido genuino exige **dos lecturas concordantes**.
3. El reporte nombra **las dos lecturas posibles** en vez de afirmar un alta.

---

## 3. El quinto estado que hizo falta: `no_poseido`

Daniel lo levantó antes del paso 2: **el menú lista en GRIS a los que no poseés**, mezclados con
los tuyos. El recorrido los lee sí o sí, y sin distinguirlos cada uno se reporta como PJ nuevo —
un onboarding falso por cada personaje que te falta, en **cada** pasada. `_OBS_MIN_NUEVO=2` no lo
tapa: scrollear pasa por los grises tantas veces como quieras.

La defensa no necesitó código de visión, porque el sistema ya tenía **dos listas que significan
cosas distintas y que nadie había cruzado**:

| lista | qué es | cuántos |
|---|---|---|
| `agents` | los que **poseés** | 51 |
| `avatar_refs/` | los que **existen** | 56 |

La diferencia —Banyue, Hugo, Lichter, Promeia, Yidhari— es lo que el menú pinta en gris.

**La resta la hace el censo, no el llamador.** Se le pasa el catálogo entero; si la diferencia
viniera ya hecha, un error de wiring mandaría un PJ propio a `no_poseido`.

### Un gris puede disfrazarse de PJ propio

Medido antes de escribir el parser:

```
Lichter  → 0.667 contra Alice   ← ¡por encima del umbral de identificación (0.55)!
Hugo     → 0.500 contra Zhao
```

El match difuso interceptaba a Lichter antes de que llegara al chequeo del catálogo, y le cargaba
ruido a un PJ que sí se tiene. Se arregló por **precedencia**: un match EXACTO contra la lista de
los que existen le gana a un parecido de 0.667.

### El hueco que queda, declarado

⚠️ **La guarda del catálogo es parcial y el hueco no es residual.** En `Ejemplo_10.png` se cuentan
**~9 grises en una sola pantalla** contra **5** de diferencia. La mayoría de los no obtenidos no
tienen arte todavía.

La señal definitiva es el **CANDADO**: un tile no obtenido reemplaza el badge de rango por un
candado y pone "Nivel 1" en gris. Es estructural, no una heurística de saturación — y eso importa
porque `is_gray` ya nos mintió una vez (separaba paletas, no obtenido/no-obtenido). Leerlo pide
localizar el tile seleccionado en la grilla inclinada de S15: **queda para una tanda aparte**.

---

## 4. Dónde vive el estado: `census.db`, no el dominio

Molde de `metrics.db` (commit `b526aba`), y acá pesa más:

1. Una escritura por cambio de selección no encaja con la ceremonia de RNF-01, que es por
   migración. Meterlo adentro obligaría a inventar una excepción a RNF-01 **dentro de la feature
   cuyo objetivo es restaurar la confianza en esa DB**.
2. **El censo es el flujo que más conviene ejercitar en readonly** — mirar el menú no arriesga
   nada. Con el estado adentro habría que elegir entre no poder correrlo así o perder la prueba
   del sha256.
3. Vuelve **estructural** lo que si no queda en disciplina: sin handle de escritura al dominio, la
   observación no puede contaminarlo por accidente.

Efecto colateral bienvenido: **no hizo falta migración**. La 19 sigue siendo la última.

El test que lo justifica corre una pasada entera y compara el sha256 del dominio antes y después.

### La única escritura al dominio

`marcar_huerfanos_en_dominio` — solo en el cierre, solo anota `no_visto_en_censo_<fecha>` en
`agents.notas`, con backup + transacción + los dos PRAGMA + gate de readonly, e idempotente.
`agents.notas` ya existía, así que **no hizo falta migración tampoco para esto**.

---

## 5. Lo que el parser tiraba

`identify_menu_agent` devolvía 3 campos y descartaba dos cosas que el censo necesita:

- **la confianza del OCR** (`text, _conf = ocr.text(...)`, con `_conf` sin usar);
- **el porqué de una abstención**: cinco caminos distintos devolvían el mismo `(None,None,None)`
  — ROI que falla, ROI chico, OCR que revienta, OCR vacío, y *ningún match en el roster*. El
  último es la señal de un PJ que falta cargar.

`read_menu_agent` devuelve `MenuAgentRead` con `conf`, `motivo`, `candidato` y `score`.
`identify_menu_agent` queda como su vista de 3 campos.

**`conf` y `score` miden cosas distintas y hacen falta las dos**: `conf` es qué tan seguro está el
OCR de los CARACTERES, `score` qué tan seguro está el sistema de la IDENTIDAD. Un OCR nítido de un
nombre deformado tiene conf alta y score bajo — y ese caso tiene que caer en DUDOSO.

### Umbrales medidos, no elegidos

Sobre las 9 capturas reales, **9/9 correctas**:

| | mínimo correcto | umbral | margen |
|---|---|---|---|
| `sim` | 0.925 (`Remielle &`) | 0.75 | 0.175 |
| `conf` | 0.878 (`N.°0:Anby 0`) | 0.80 | 0.078 |

Hay un test parametrizado que afirma que ninguna lectura buena cae por debajo.

---

## 6. Un bug que la captura de Daniel destapó

`Ejemplo_10.png` hizo caer `test_menu_personajes_sigue_s15`. **No era un artefacto del test.**

El detector separaba el menú de la tienda de música **por color** (S4 ≤0.014 vs S15 ≥0.184), y una
zona de la lista dominada por grises tiene colorido **0.048** — por debajo del umbral de 0.10. El
menú se clasificaba como tienda de música.

No es un caso de laboratorio: **una pasada de censo recorre toda la lista**, así que cae ahí
seguro — y con el estado equivocado el censo deja de contar. Estaba latente desde julio.

Bajar el umbral habría sido un parche (con la lista entera en gris el colorido se va al piso
igual). Se agregó una segunda señal **independiente del color**:

| | S4 (tienda) | S15 (menú) |
|---|---|---|
| contraste (std) | 19.2 – 22.1 | **51.6** – 85.7 |

Separa por **estructura**: la grilla tiene decenas de tiles con bordes duros y texto, los pinte
como los pinte; el gramófono es liso y oscuro. Se piden **las dos** señales, lo que solo vuelve
más estricta la clasificación como S4 — la dirección segura, porque un falso S4 manda el frame a
handlers ajenos mientras que fallar la detección lo deja en S15, su default.

Tiene test propio además del parametrizado: aquel no dice *por qué* esa captura importa, y si
alguien la borra del folder la cobertura se iría en silencio.

---

## 7. Un fallo propio, y el test que lo cazó

`cerrar_censo` usaba `datetime` sin importarlo (en `monitor.py` solo se importa dentro de otras
funciones). Tiraba `NameError` **y el `except` que envuelve la marca se lo comía**: los huérfanos
no se marcaban, en silencio. El patrón del return mudo.

El primer test no lo vio porque corría en readonly y solo miraba el reporte. El que quedó
**verifica la fila del dominio**, y se confirmó que atrapa el bug rompiéndolo a propósito. Es la
diferencia entre "se intentó" y "se marcó", y solo se ve mirando el efecto real.

---

## 8. Cómo se usa

```powershell
tools\qa_launch.ps1 -FromSource -ReadOnly -Censo
```

Recorrer el menú PJ por PJ. Una línea por PJ nuevo: `[censo] Aria — visto conf 0.97 · 12/51`.
**F8 cierra** la pasada → reporte en `audit/censos/` + marca de huérfanos.

`-ReadOnly` deja acumular igual (el estado vive en `census.db`) pero **no** marca huérfanos: es lo
que corresponde para una primera corrida, porque cortar a la mitad y cerrar no deja 40 PJs
marcados.

---

## 9. Riesgo abierto

**Si el gate de firma se traga un cambio de selección**, ese PJ queda pendiente en silencio y al
cerrar se vuelve un **huérfano falso**. Es *el* riesgo de esta fase y no se puede bajar el umbral
sin pagar un OCR por frame de animación. Mitigación por diseño: el cierre lo declara el usuario, y
re-seleccionar al PJ lo recupera. Falta que el cierre imprima los pendientes antes de confirmar
(hoy solo van al reporte).

---

## 10. Lecciones

1. **Dos listas que nadie había cruzado valían más que código de visión nuevo.** El sistema ya
   sabía qué personajes existen y cuáles se poseen; la diferencia era exactamente la respuesta.
2. **El orden de las guardas es parte del diseño.** Poner el match difuso antes del catálogo
   dejaba a un personaje ajeno disfrazarse de propio, con un número (0.667) que parecía suficiente.
3. **Un test verde con el parche muerto es peor que uno rojo.** Al mover la costura a
   `_match_agent_scored`, cinco tests seguían pasando usando el matcher real: parecían aislados
   sin estarlo.
4. **Verificar el efecto, no la intención.** El test que miraba el reporte pasaba mientras los
   huérfanos no se marcaban.
5. **Una captura nueva es un test nuevo.** El screenshot de Daniel destapó un bug de detección de
   julio que ninguna de las 8 capturas previas podía mostrar.
