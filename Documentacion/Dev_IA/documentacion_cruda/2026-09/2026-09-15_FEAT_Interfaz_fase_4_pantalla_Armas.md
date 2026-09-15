# Interfaz fase 4: la pantalla Armas (W-Engines)

**2026-09-15** · commits `44eafad` → `97e70ec` en main. Viene de la
[fase 3](2026-09-13_FEAT_Interfaz_fase_3_discos_y_modal_de_disco.md).

Primera pantalla diseñada **a partir del paquete de referencias** que arma
`tools/stage_design_engines.py` (datos reales, íconos, capturas de la app). Daniel hizo el prompt en
Claude Design y el diseño volvió como `Pestana Armas - W-Engines.html`, con `engines-screen.jsx`,
`engines-data.jsx`, `engines-compare.jsx` y `engines-doc.jsx`.

## 0 · Leer el proyecto de Claude Design: la autorización

`DesignSync` pide `/design-login`, que sólo corre en una sesión interactiva. Dos obstáculos:

- `claude` **no estaba en el PATH**.
- La ruta que la sesión veía, `AppData\Roaming\Claude\claude-code\<versión>\claude.exe`, **no existe
  para PowerShell**: la app de escritorio es un paquete de la Store y esa carpeta está virtualizada.
  La física es `AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude-code\...`.

Con eso Daniel hizo el login y el proyecto se pudo leer completo.

## 1 · El diseño se dibujó con datos viejos

`engines-data.jsx` lista **33 engines, de los cuales 5 tenían nivel, refinamiento y dueño**; el
resto va en ámbar como *tenencia sin leer*. Pero el censo de armas ya había cerrado: **las 56 armas
tienen los tres datos**. Portarlo tal cual habría dicho "sin leer" en 51 armas que sí se conocen.
Además, varias rarezas del mockup no coinciden con la DB (Llanto mielgo aparece S y es A) y la lista
de "PJs sin engine" salía del roster viejo.

**Regla aplicada: del diseño se porta el criterio, no los datos.** Lo que se tomó:

| del diseño | por qué vale |
|---|---|
| jerarquía: inventario = grilla · auditoría y progreso = banda ámbar · comparador = modo aparte | ordena 4 trabajos que competían |
| la celda con el arte primero, franja de rareza, badge, `×n` | es una tarjeta, no una fila |
| franja de tenencia abajo con el avatar del dueño | la tenencia es el dato más caro |
| refinamiento con **mínimo 1**; sin lectura, texto | cinco estrellas vacías serían un P0 que no existe |
| **"sin leer" y "por subir" en contadores separados** | un nivel no leído no es un nivel bajo |
| "PJs sin arma" cambia el cuerpo por tarjetas | es otra pregunta sobre el mismo conjunto |

### Decisiones de Daniel

| tema | decisión |
|---|---|
| celdas | **una por arma física** (56), con `×n` de copias del modelo: las copias tienen nivel, P y dueño propios |
| modo comparador | **otra fase** |
| paleta | **amarilla, como el resto de la app** — el violeta queda para lo observacional y el atuendo |
| botón Exportar | **fuera** por ahora |

## 2 · Qué quedó

| pieza | dónde |
|---|---|
| datos puros: inventario, orden, conteos, filtros, auditoría, PJs sin arma | `app/ui/armas/datos.py` |
| celda, banda de filtros, vista | `app/ui/armas/{celda,filtros,view}.py` |
| grilla sin scroll, ahora compartida con el Roster | `app/ui/grilla.py` (salió de `roster/datos.py`) |

Con la DB real: 56 armas · 40 modelos · 46 equipadas · 10 libres · 12 S / 44 A. Auditoría: 5 PJs sin
arma (Anby, Harumasa, Lucy, Nekomata, Soukaku), 10 sin usar, 3 sin ícono. Progreso: 6 con nivel < 60,
17 con P < 5, **0 sin leer** (los chips existen deshabilitados: que el contador esté es lo que dice
que se miró). La esquina ámbar marca las armas sin ícono o sin especialidad en el catálogo.

Suite completa sobre main: **2915 passed, 0 failed, 0 skipped** (antes 2900); sha256 de la DB de
dominio idéntico antes y después.

## 3 · Lo que vieron las capturas y no los tests

Con 56 celdas en la ventana mínima la escala baja a ~0.76, y la primera versión **escondía el pie con
el refinamiento y el nivel** para que entrara el resto — justo el dato central. El nombre de dos
líneas se pisaba con el ícono. Arreglo: el badge de rareza y el `×n` pasan a superponerse en las
esquinas (ya no ocupan una fila), el ícono se achica con la celda y el nombre va en una línea
recortada con tooltip. Maximizada, la franja del dueño y el `×n` no crecían: se sumaron al escalado.

## 4 · Errores míos

- Dos tests con la premisa mal: conté un arma sin ícono donde eran dos (Tetera esmeraldina tampoco
  tiene archivo), y la regla de atuendo necesita que el PJ base exista en la fixture.
- Los tests de la vista pasaron al primer intento, así que no los vi fallar antes del código: se
  compensó saboteando el refinamiento sin leer, el id del dueño, el filtro de descartadas y la mezcla
  de "sin leer" con "bajo" — todos dieron rojo.

## Queda abierto

1. **QA en vivo de Daniel.**
2. **Modo comparador** (`engines-compare.jsx`): leído, no portado. La afinidad de rol sale de
   `weapons.tipo_especialidad`, vacía en 7 armas del inventario.
3. **Exportar**, cuando haya formato y destino.
4. Click en una celda sólo la selecciona: no hay modal de arma todavía.
5. Los datos pendientes del catálogo siguen: 3 íconos, 7 especialidades, las pasivas de las filas 5 y 13.
