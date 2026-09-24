# Handoff Claude Design — Prioridad de buildeo (2026-09-24)

Respuesta a [`BRIEF_prioridad_de_buildeo.md`](../../claude_design_upload/BRIEF_prioridad_de_buildeo.md).
Proyecto de Claude Design `e093a36c-4b42-433d-9387-d415712105bd` (lienzo `DaniBOD ZZZ Analytics.html`),
archivos: `prio-screen.jsx` (pantalla y selector), `prio-doc.jsx` (las razones), y las piezas que
tocó en `roster-screen.jsx` (`PRIO_C`, `Tri`, `PrioTab`, `PjCell` con `prio`, `PrioChips`,
`Legend` con `prio`) y `pj-modal.jsx` (dónde va el selector). Leídos con `DesignSync.get_file`.

Esto es el resumen de lo que hay que implementar, con los valores exactos del diseño.

## Colores (nuevos, ninguno reusa ámbar / naranja / violeta)

| | valor | uso |
|---|---|---|
| `PRIO_C.alta` | `#C4F03A` (lima) | barra, pestaña, chips, botón "Listo", "GUARDADO", modo edición |
| `PRIO_C.baja` | `#8C95A8` (pizarra) | borde de la pestaña de baja, chip |
| pestaña baja fondo | `#454B58` | |
| triángulo sobre lima | `#1A2206` | también el texto sobre lima |
| triángulo baja | `#D5DAE4` | |
| texto "BAJA" | `#C3C9D6` | |
| segmento baja activo | `#5A6070` | |
| chip normal | `#BFB8C9` | |

## La marca en la celda (120×88 en el diseño; 122×96 en la app)

- **Normal: nada.** Criterio del nivel 60.
- **Alta:** barra superior de lado a lado, 3 px, lima con halo (`0 0 8px` lima `aa`), **+** pestaña.
- **Baja:** sólo la pestaña. Sin barra, sin brillo: "apartado", no alerta.
- **Pestaña:** `left: 3, top: 0`, 17×14, sin borde superior; alta = fondo lima + ▲ `#1A2206` +
  halo; baja = fondo `#454B58`, borde 1 px pizarra, ▼ `#D5DAE4`. Triángulo de lado `h·0,3`.
- La esquina superior izquierda estaba libre; **el mindscape se corre**: `top 3, left 23` con
  pestaña (sin pestaña `top 6, left 7`).
- Sólo en PJs poseídos.
- Escala: a 62 % la pestaña queda en 10×9 y el triángulo se pierde, pero barra lima y bloque
  pizarra se distinguen por FORMA.

## Filtro

En la **fila de ELEMENTO / RANGO**, empujado a la derecha (la banda sigue en 104 px): label
`PRIORIDAD` + chips `▲ Alta n` · `Normal n` · `▼ Baja n`. Conteos sobre el roster completo.
**Estado vacío** (nadie declarado): en vez de los chips, un chip punteado lima
`Sin declarar · Marcar ▸` (entra al modo edición).

## Leyenda

Dos entradas nuevas, sólo si hay alguna prioridad: "prioridad alta" (mini celda con borde superior
lima + pestaña) y "prioridad baja" (mini celda + pestaña baja). La nota derecha de la leyenda cambia:
- vacío: `EL MOTOR DE DISCOS NO SABE A QUIÉN QUERÉS MEJORAR — HOY LOS 52 ESTÁN EN NORMAL`
- edición: `MODO EDICIÓN · EL CLICK NO ABRE LA FICHA · SALÍS CON LISTO O ESC`

## Header

- Botón nuevo `Editar prioridades` (ícono ▲▼) a la izquierda de los existentes; con la etiqueta
  lima `NUEVO` mientras no haya ninguna prioridad declarada.
- **En modo edición el header se reemplaza**: fondo lima 7 % y borde inferior lima; título
  `Editando prioridades` (lima); subtítulo `CADA CELDA: ▲ ALTA · – NORMAL · ▼ BAJA — SE GUARDA AL
  MOMENTO · EL CLICK NO ABRE LA FICHA`; conteos alta / normal / baja; a la derecha
  `● SUGERENCIAS DE DISCOS RECALCULADAS · HACE N S` y botón lima `Listo  ESC`.

## Modo edición (la decisión de diseño)

**Botonera de 3 segmentos en cada celda** (▲ · – · ▼), que **reemplaza la fila de abajo** (pips de
discos + nivel) mientras dura el modo. Un click, destino explícito, se guarda al momento.
Descartados, con su razón: el ciclo normal→alta→baja (para llegar a baja pasa por alta: recalcula
dos veces y muestra un estado no querido) y la selección múltiple (15 selecciones + 2 asignaciones
contra 15 clicks directos).

- Segmentos de 15 px de alto, gap 2. Activo: alta = lima, normal = blanco 20 %, baja = `#5A6070`.
  Hover: borde lima, fondo lima 13 %.
- Celda en hover o recién cambiada: anillo lima. Recién cambiada: etiqueta `GUARDADO` (lima, 8 px
  caps) sobre la botonera.
- La grilla lleva un tinte lima 2 % y un borde interior lima 27 %. Los no poseídos, atenuados.
- **El click en la celda NO abre la ficha.** Se sale con `Listo` o `Esc`.

## Modal de PJ

Selector sobre el hero, **a la izquierda del botón de cierre** (`right 54, top 14`), 262 px:
título `PRIORIDAD DE BUILDEO`, 3 segmentos de 26 px (`▲ Alta` · `Normal` · `▼ Baja`) y una nota:

| valor | nota |
|---|---|
| alta | Recibe discos primero · nadie de menor prioridad se los saca |
| normal | Por defecto · se mueve sólo si quien lo tiene no pierde |
| baja | Cede discos a PJs de prioridad mayor |
| recién cambiado | `● Sugerencias de discos recalculadas · …` en lima |

Sin toast en ningún caso (es un ajuste del usuario, no algo que pasó en el juego).

## Lo que NO se porta del lienzo

El modal del lienzo trae "BUILD COMPLETION" y los 4 botones de acción: la app ya los descartó
(scoring sin calibrar); el selector va sobre el modal REAL (`app/ui/pj_modal/modal.py`). Los
datos de ejemplo del lienzo (Nekomata, Miyabi… en alta) son relleno: sólo Claret y Piper vienen de
Daniel.
