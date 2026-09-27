# SPEC · Las sugerencias del motor en la pantalla Discos (2026-09-27)

**Estado:** **hecho** el 2026-09-27 (ver "Implementación"). Diseño aprobado por Daniel ese día
("si me cierra, escribilo y arrancá").

## Qué pidió Daniel

> "Eso de las sugerencias lo debemos implementar en la pantalla de discos." (2026-09-25)
> "Vamos con el asesor en la pantalla de discos" → el asesor = **las sugerencias por disco**.

Hasta hoy las sugerencias sólo salían en un reporte de `audit/sugerencias/`. La pantalla Discos
sólo informa: el 2026-09-13 se le sacó toda recomendación porque el puntaje no estaba calibrado.
Con el motor de la Fase A (R9-R24) esa decisión se revisa, en los lugares que el mockup original
(`22-tab-discos-inventario-completo.png`, `23-modal-disco-detalle.png`) ya tenía para eso.

## Decisiones

| pregunta | decisión |
|---|---|
| qué es "el asesor" en Discos | **las sugerencias por disco** (equipar, mover, cambiar 2pc, mejorar, reserva, guardar, descartar) con la mejora y el porqué |
| diseño | **los lugares del mockup original**, con los estilos actuales, sin esperar a Claude Design |
| acciones | **ninguna**: la app no actúa sobre el juego; los cambios los hace Daniel en el juego |

## Medido antes de diseñar

`generar()` sobre los 380 discos: **0,79 / 0,74 / 0,73 s** (2026-09-27). Pasa los 500 ms de una
respuesta de la interfaz (RNF-06) → se calcula en un hilo aparte y la tabla se completa al terminar.

## Parte 1 · El motor para la pantalla

- **`app/core/sugerencias.py`**: `Sugerencia`, `resolver_conflictos` y `generar(db_path)` salen de
  `app/scripts/sugerir_movimientos.py`, que queda como envoltorio del reporte (una sola autoridad;
  re-exporta los nombres para no romper a quien los importa).
- **`por_disco(reporte) → {disc_id: SugerenciaDisco}`**: la sugerencia PROPIA de cada disco, y
  además las que lo NOMBRAN: el que repone en un "mover" y el segundo disco de un par (R24). La propia
  manda en la columna; el modal muestra todas.
- **En segundo plano**: `app/ui/discos/servicio_sugerencias.py`, un `QObject` que calcula en un hilo
  con su propia conexión de sólo lectura y emite el resultado. Cada pedido lleva un número; un
  resultado viejo que llega tarde se descarta.
- **Cuándo**: cada vez que la vista se refresca (al abrir la pestaña y al volver a ella, que ya relee
  el inventario). Cubre los dos disparadores —un cambio del motor (prioridad, build, niveles, stats)
  y un cambio del inventario— sin suscribirse a nada nuevo (YAGNI): son 0,75 s en segundo plano.

## Parte 2 · La pantalla

- **Tabla, columna SUGERENCIA** (donde el mockup tenía SCORE): el tipo con su color y el destino
  (`EQUIPAR → Anby +0,57`). En conflicto: apagada, y el tooltip dice con qué choca. Un disco que sólo
  aparece en la sugerencia de otro dice cuál (`repone #213`, `par con #102`). Sin sugerencia: vacía.
  Mientras calcula, "…".
- **Filtro SUGERENCIA** (donde estaba el de score): chips por tipo, con su conteo.
- **Lateral, recuadro SUGERENCIAS** (donde estaba el insight): conteo por tipo; click = filtra.
- **Modal, columna 3** (donde estaba "Recomendación final"): una caja con la sugerencia arriba y los
  "otros discos" abajo. Detalle por tipo: equipar → contra el disco que lleva hoy el PJ en ese slot;
  mover → de quién sale, quién repone, a quién va; cambiar 2pc → los dos discos y el fijo que alcanza;
  reserva / guardar / descartar → el porqué.
- **Leyenda**: los colores de los tipos.
- Colores en un solo lugar (`tokens.SUGERENCIA`): los de los toasts para equipar (verde), mejorar
  (celeste), reserva (amarillo), descartar (naranja); nuevos para mover (rosa), cambiar 2pc
  (violeta) y guardar (amarillo oscuro).

## Orden de entrega (un commit por paso, suite completa antes de cada push)

1. Este SPEC.
2. `app/core/sugerencias.py` + `por_disco` (el script queda envoltorio; reporte idéntico).
3. `servicio_sugerencias.py` (hilo, pedidos numerados).
4. Tabla + filtro + lateral + leyenda.
5. Modal.
6. Verificación visual: la vista y el modal renderizados fuera de pantalla (`QWidget.grab`) con los
   datos reales, mirados uno por uno.

## Implementación (2026-09-27)

| paso | commit | qué |
|---|---|---|
| SPEC | `e7e6dfb` | este documento |
| motor | `0f0b193` | `app/core/sugerencias.py` + `por_disco`; el script queda envoltorio (reporte idéntico, JSON comparado) |
| hilo | `35eee70` | `ServicioSugerencias` |
| tabla | `a7350d2` | columna, filtro, lateral, leyenda, `tokens.SUGERENCIA` |
| modal | `4a3d344` | recuadro "Sugerencia del motor" en la columna 3 |

### Lo que encontraron las verificaciones

- **Una señal `dict` de Qt perdía los ids.** `Signal(dict)` pasa por un QVariantMap, que sólo acepta
  claves de texto: el resultado llegaba `{}` en silencio y la columna habría quedado vacía para siempre.
  Lo encontró el test del hilo (el resultado llegando de verdad, no a mano). La señal es `object`.
- **Un sabotaje salió verde**: el aviso de repintado del modelo (`dataChanged`) era código muerto,
  porque la vista recarga las filas cuando llega el resultado (el filtro de sugerencia también cambia).
  Se sacó; el camino real (recargar) tiene su test y su sabotaje.
- `capitalize()` pasaba a minúscula el resto de la nota del par ("disco sacudestrellas").
- **Verificación visual** (vista y modales renderizados fuera de pantalla con la DB real): el lateral
  cuenta mover 9 · equipar 32 · mejorar 2 · reserva 24 · guardar 9 · descartar 5, igual que el
  reporte; #211 (mover a Seth, repone #213) y #76 (equipar a Anby en conflicto) se leen completos.

## Fuera de alcance

- Botones de acción (bloquear, confirmar, reasignar).
- Sugerencias en vivo en el toast (paso 8).
- Los avisos de coherencia de la ficha del PJ.
