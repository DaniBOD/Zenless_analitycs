# Brief Claude Design — Toast "DESMONTADOS" + legibilidad de todas las variantes

> **Dos pedidos en un brief, y el segundo es el importante.**
>
> 1. Diseñar la variante **DESMONTADOS** (tanda de desmontaje cerrada). Existe y funciona en vivo
>    desde el 2026-07-26, pero está pintada a mano en Qt sin pasar por diseño.
> 2. **Agrandar íconos y tipografía en TODAS las variantes.** Pedido explícito de Daniel tras el
>    QA: *"los toasts (íconos) que sean más grandes y legibles porque son algo chicos; si es
>    necesario agrandar los toasts, que así sea"*. **El frame 380×140 deja de ser intocable.**
>
> Sistema existente: componentes `BlockBox`, `DiscThumb`, `Rarity`, `Icon`, `ZButton`, `Countdown`,
> `UrgencyBar` y los tokens de `tokens.css`. Código de referencia:
> `mockups/Codigos-claude-desing/toasts.jsx`. Implementación real: `app/ui/toast.py`.

---

## Parte A — El problema de legibilidad (medido, no impresión)

Estos son los tamaños **reales del código en producción**, no del mockup. Todo en px lógicos, sobre
una pantalla de 2560×1440.

| Elemento | Dónde | Tamaño actual |
|---|---|---|
| Frame del toast | `WIDTH × HEIGHT` | **380 × 140** (+28 px de chrome exterior) |
| Label del header ("DESMONTADOS") | `_paint_header` | Segoe UI **10 px** bold |
| `#ID` del evento | `_paint_header` | **8 px** |
| Micro-badge "✓ OBSERVADO" | `_paint_header` | **7 px** caps |
| Thumb del disco | `DiscThumb` | **48 px** (56 en una variante) |
| **Logo del set dentro del thumb** | `DiscThumb`, escala 0.78 | **~37 px efectivos** |
| **Badge de rareza (círculo S/A/B)** | `DiscThumb` | **círculo de 14 px, letra de 7 px** |
| Substats / meta del cuerpo | `_paint_body` | **8-9 px** |
| Labels del footer | `_paint_footer` | **8 px** caps |

**Los tres peores, por orden:**

1. **El badge de rareza: 14 px de círculo con una letra de 7 px.** Es el dato que dice si el disco
   es S o A — el más importante del thumb después del set— y es lo más chico de toda la card.
2. **El logo del set a ~37 px.** Es el identificador visual principal del disco. Los logos de set
   de ZZZ tienen bastante detalle interno; a 37 px se vuelven manchas difíciles de distinguir
   entre sí (comparar "Salón huracanado" vs "Firmamento llameante" a ese tamaño).
3. **La franja de 7-8 px** (ID, micro-badge, footer). Está en el límite de lo legible de reojo, y
   un toast se lee **de reojo, mientras el usuario juega** — nunca fijando la vista.

### Un hallazgo que hay que resolver en el diseño

**El ícono del header nunca se implementó.** `tokens.py` define un ícono por variante
(`check`, `up`, `stack`, `trash`, `swap`, `feed`), pero `_paint_header` en Qt dibuja **solo el
label de texto con un subrayado de color**. El chip con esquina chaflanada + ícono que estaba en
los mockups JSX se perdió en el port a Qt.

Así que cuando Daniel dice "los íconos son chicos", en parte se refiere a íconos **que no existen**
en la app. El diseño tiene que decidir explícitamente: o vuelve el chip con ícono (y con qué
tamaño), o se declara que el label de texto es la identidad de la variante y se lo agranda.

### Restricción real que el diseño debe respetar

El frame ya creció una vez **por un bug de layout, no por diseño**: `HEIGHT` pasó de 116 a 140 con
el comentario *"para que header (label) no se solape con thumb"*. Es un parche. El rediseño es la
oportunidad de fijar una grilla vertical que aguante las 7 variantes sin parches.

**Libertad explícita concedida por el usuario:** el toast puede crecer. Sugerencia de rango, a
confirmar por diseño: **420-460 px de ancho** y la altura que pida la grilla. El límite real es que
siga siendo un toast de esquina y no una ventana: no debe tapar HUD de combate ni pedir que el
usuario despegue la vista del juego.

### Entregable de la parte A

Una **tabla de escala tipográfica y de íconos** para las 7 variantes: qué tamaño toma cada rol
(label de variante, ID, micro-badge, nombre de set, substats, footer, badge de rareza, logo de set,
avatar de PJ), con el frame final propuesto. Más un antes/después de **una** card de recomendación
(p.ej. EQUIPAR) mostrando la ganancia de legibilidad.

---

## Parte B — La variante DESMONTADOS

### Qué es y cuándo sale

Cuando el usuario desmonta discos en la pantalla de Desmontaje del juego, el sistema sigue su
selección y, al confirmarse la destrucción (modal "Obtenido"), emite **un solo toast por tanda**.

**Uno por tanda, no uno por disco.** Es un pedido explícito: en una limpieza de 50 discos, 50
toasts serían inusables.

Es una **confirmación pasiva**: reporta algo que ya pasó y que el sistema observó en pantalla. No
aconseja nada, no tiene call-to-action, no afirma que se haya escrito la DB (la bitácora va a un
archivo en `audit/`, y el toast sale igual en modo read-only).

**Ojo con la distinción, que es fina y significativa:** ya existe una variante `DESCARTAR`, que es
la **recomendación** ("te conviene tirarlo"). Ésta es el **hecho** ("ya los tiraste"). Deben ser
inconfundibles de un vistazo: `DESCARTAR` es naranja/warning y trae score y countdown; `DESMONTADOS`
es violeta, sin score ni countdown.

### Datos reales de la primera tanda en vivo (2026-07-26)

```
declarado: 3     capturados: 3     faltantes: 0
confirmacion_grado_s: true
avisos: ["scroll durante la tanda", "contador del header ilegible"]
```

### El contenido, y por qué

El dato autoritativo es **el conteo**, no los discos. El conteo sale del contador `N/300` del juego
y es la única fuente confiable; los discos individuales pueden faltar si el usuario clickeó más
rápido de lo que el OCR alcanza a leer.

- **Número grande y centrado** (hoy 26 px): la cantidad desmontada. Es lo autoritativo.
- **"DISCOS DESMONTADOS"** (singular si es 1).
- **Cobertura**: `"3 con datos"` en verde si se leyeron todos, o `"5 con datos · 2 sin leer"`
  atenuado si faltan. **Esto tiene que verse**, no esconderse: si el usuario no nota que faltan
  stats, va a suponer que la bitácora quedó completa cuando no lo está.
- **Footer**: `DESMONTAJE OBSERVADO` + `contador N/300 ✓`.
- **Micro-badge top-right**: `✓ OBSERVADO` (no "SINCRONIZADO": el toast afirma lo que se vio en
  pantalla, no lo que la DB guardó).

### Lo que el diseño tiene que resolver y hoy no está

1. **El caso de cobertura parcial.** Hoy es una línea de texto atenuado. Con tandas grandes
   (50 discos, 30 sin datos) merece jerarquía propia — quizá una barra de cobertura. Es la
   información que le dice al usuario que su ritmo de clicks le está costando datos.
2. **`confirmacion_grado_s`.** La tanda incluía un disco de grado S y el usuario lo confirmó a
   mano. ¿Merece una marca? Destruir un S es irreversible y poco común.
3. **Los avisos.** Hoy van solo al log. `"scroll durante la tanda"` y `"contador del header
   ilegible"` explican por qué podrían faltar datos. ¿Un indicador discreto?
4. **El ícono `trash`**, que como se dijo arriba hoy no se dibuja. Ojo: `trash` es el mismo ícono
   que usa `DESCARTAR`. Si vuelve el chip con ícono, estas dos variantes necesitan íconos
   distintos — o el violeta tiene que cargar solo con toda la diferenciación.

### Data model

```js
{
  variant: "desmontado",
  teardown_total: 3,        // contador del juego: autoritativo
  teardown_known: 3,        // discos con stats leídos
  confirmacion_grado_s: true,
  avisos: ["scroll durante la tanda", "contador del header ilegible"],
}
```

---

## Entregable conjunto

1. La card **DESMONTADOS** en 3 estados (idle / hover / fade-out), en dos escenarios: **cobertura
   completa** (3 de 3) y **cobertura parcial** (18 de 50, que es donde el diseño se pone a prueba).
2. La **tabla de escala** de la parte A, aplicable a las 7 variantes.
3. Un antes/después de una card de recomendación con la escala nueva.
4. Todo sobre fondo de escritorio para contexto, como los mockups
   `Toast-en-escritorio-contexto-real*.png`.

Reusar tokens y componentes existentes. El violeta `--purple (#9D4EDD)` ya está tomado por las tres
variantes de confirmación pasiva (`REEMPLAZADO`, `AHORA EN`, `DESMONTADOS`).
