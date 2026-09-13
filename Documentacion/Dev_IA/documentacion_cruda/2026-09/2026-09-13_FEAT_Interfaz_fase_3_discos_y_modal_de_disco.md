# Interfaz fase 3: la pantalla Discos y el modal de disco

**2026-09-13** · commits `1322c01` → `31e4beb` en main. **Probada en vivo por Daniel: "se ve bien".** Viene de la
[fase 2](2026-09-13_FEAT_Interfaz_fase_2_roster_y_modal_de_PJ.md). Mockups:
`mockup-exports/22-tab-discos-inventario-completo.png` y `23-modal-disco-detalle.png`.

## 1 · Qué quedó

| pieza | dónde |
|---|---|
| datos del inventario, puros | `app/ui/discos/datos.py` |
| cómo se escribe un stat (una sola regla) | `app/ui/formato.py` — la usan la vista en vivo, la tabla y el modal |
| pantalla Discos: tabla, filtros, lateral, leyenda | `app/ui/discos/{tabla,filtros,lateral,view}.py` |
| modal de disco | `app/ui/disco_modal/{datos,modal}.py` |
| fixture "esquema real, filas propias" | `conftest.db_esquema_real` (también la usa el modal de PJ) |

**La tabla vieja mostraba 200 de 385 discos sin decirlo** (`LIMIT 200`) y tenía una columna Score
siempre vacía. La nueva los trae todos en una consulta (5 ms) y la vista se arma y pinta en ~210 ms
con la DB real.

Suite completa sobre main: **2900 passed, 0 failed, 0 skipped** (antes 2871). sha256 de la DB
de dominio idéntico antes y después.

### Decisiones de Daniel

| tema | decisión |
|---|---|
| 385 filas | **tabla con scroll**, sin paginado: la regla "sin scroll" del Roster no aplica a un inventario |
| columna lateral | **distribución por set** (click filtra) **+ libres por slot** |
| modal, columnas 2 y 3 | **el dueño con su build** (este slot destacado) y **otros discos del mismo set y slot** |

Y el criterio de las fases anteriores: **sólo informa**. Fuera de los mockups: columna y filtro de
score, re-puntuar, acciones rápidas, insight de IA, PJs compatibles ordenados, arquetipo, score
proyectado, recomendación final, historial RF-13 y los 5 botones del pie del modal.

## 2 · Lo medido antes de diseñar

- 385 discos activos: 305 equipados, **80 libres** (13/16/18/4/21/8 por slot), 28 sets.
- `score_evaluacion` y `agentes_compatibles` **0/385**; `inventory_disc_evaluations` vacía.
- **No hay columna de rareza**: el badge "S" del mockup no tiene de dónde salir y no se dibuja.
- 12 discos tienen 3 substats; el modal muestra 3 filas, no una cuarta vacía.
- `disc_sets` tiene los efectos de 2 y 4 piezas para los 30 sets.
- Los nombres de stat están mezclados en la DB (`ATK%` junto a `Prob. Crítica`) y los textos de
  4 piezas tienen fragmentos en inglés. Se muestran tal cual: embellecerlos es trabajo de
  `stats_vocab` o del catálogo, no de la pantalla.

## 3 · Criterios que no son cosméticos

- **Dueño a la vista = equipado.** Un disco con `agente_asignado` y `equipado = 0` no se pinta como
  de alguien.
- **Las alternativas no se ordenan por calidad**: libres primero, después nivel. Ordenar por
  "mejor" sería una recomendación, y el scoring no está calibrado.
- **El filtro vive en `datos.filtrar`**, no en el modelo de Qt: la misma función que prueban los
  tests puros es la que decide qué filas se ven.
- **Click en fila después de ordenar y filtrar**: el test rompe el caso en que el índice de fila se
  lee contra la lista original (saboteado: da rojo).

## 4 · Lo que vieron las capturas y no los tests

Otra vez, render offscreen con la DB real y las fuentes de Windows antes de commitear:

1. **La tabla arrancaba ordenada por #ID descendente.** Activar el orden en un `QTableView` hace que
   Qt ordene en el acto por la columna 0 y pisaba el orden por set. Test nuevo.
2. **La vista medía 1106 px de alto**: el lateral listaba los 28 sets en filas fijas. La lista va
   ahora en su propio scroll y el test mira alto además de ancho.
3. **En el modal, un hueco de ~90 px** entre el logo del set y la caja del main: las etiquetas con
   word-wrap de los efectos descuadraban el reparto de alto. Fila de identidad de alto fijo.

## 5 · Errores míos

- Una nota al pie del modal decía "sin score". El test que prohíbe la palabra en pantalla la cazó:
  **explicar la ausencia del scoring también es mostrarlo**.
- El test de "sin botones de acción" filtraba por texto en mayúsculas y confundía con acciones a los
  botones de alternativas (`#00012 ATK% 30% · LIBRE`). Ahora se distinguen por nombre de objeto.
- En `conftest` la ruta de la DB tenía un `.parent` de más. Se vio antes de usarla, verificando que
  el archivo existía.

## Queda abierto

1. ~~QA en vivo de Daniel~~ — hecho el 2026-09-13, aprobada.
2. La columna SUBS queda angosta en la ventana mínima (tiene tooltip con los 4). Maximizada entra.
3. El título en mayúsculas pequeñas pierde las tildes en algunas fuentes ("DUENO", "DISTRIBUCION").
4. Las alternativas muestran hasta 12; si hay más, se sugiere filtrar la tabla.
5. Pendientes heredados: nombres de stat mezclados y textos de 4 piezas en inglés en el catálogo.
6. **Visto al levantar la app para el QA, no es de esta fase**: con ZZZ abierto el monitor arranca
   solo y la ventana queda *Not Responding* entre "ZZZ detectado" y "OCR backend listo" — 19 s esta
   vez; el log muestra 6 a 41 s en sesiones anteriores. La app quedó en ~580 MB con el monitor
   activo (no es RAM en reposo; no se midió con el juego cerrado). El arranque del OCR parece correr
   en el thread de la UI: a diagnosticar aparte, midiendo antes de tocar (A1).
