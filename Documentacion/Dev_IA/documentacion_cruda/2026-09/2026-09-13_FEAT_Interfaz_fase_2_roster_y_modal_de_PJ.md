# Interfaz fase 2: la pantalla Roster y el modal de PJ

**2026-09-13** · commits `d60e73e` → `21efffe` en main. Plan aprobado en la sesión; decisiones de
Daniel abajo. Viene de la [fase 1](2026-09-13_FEAT_Interfaz_fase_1_y_lo_que_la_suite_escondia.md).

La fase porta dos diseños de Claude Design que no estaban en Qt: la **Parte B** del diseño v1
(pantalla Roster, especificación escrita en
[`design_v1_roster_y_pasivas/README.md`](../../../Interfaz/mockups/design_v1_roster_y_pasivas/README.md) §2,
sin imagen exportada) y el **modal de PJ** (`mockup-exports/24-modal-pj-yanagi.png`). Antes se cerraron
dos deudas del catálogo de armas que la fase 1 había dejado anotadas.

## 1 · Qué quedó

| pieza | dónde | estado |
|---|---|---|
| mig `_33`: `nombre_en` de Última cena, Caldero ardiente, Tetera esmeraldina | `db/migrations/` | ✅ íconos de armas 34 → 36 de 40 |
| mig `_34`: Severed Innocence estaba **dos veces** en `weapons` (filas 22 y 62) | `db/migrations/` | ✅ unificada en la 22 con el nombre de pantalla; 61 → 60 filas; íconos 37/40 |
| una sola paleta de elementos | `tokens.ELEMENTO_COLOR` | ✅ la tabla vieja del roster no coincidía con el mockup (B1) |
| logo de facción | `asset_resolver.faction_logo_path` | ✅ tabla explícita; Covenant of Dayat sin logo, declarado |
| datos del roster | `app/ui/roster/datos.py` | ✅ puro, sin Qt |
| pantalla Roster | `app/ui/roster/{celda,filtros,view}.py` | ✅ header, filtros, grilla entera sin scroll, leyenda |
| modal de PJ | `app/ui/pj_modal/{datos,modal}.py` | ✅ se abre desde una celda |

Suite completa sobre main: **2871 passed, 0 failed, 0 skipped** (24 min; antes 2832). El sha256 de
la DB de dominio es idéntico antes y después de la corrida: la suite no escribió.

### Decisiones de Daniel

| tema | decisión |
|---|---|
| stats de combate vacías (0/51 desde la reconstrucción del 17/08) | el modal dice **"sin leer"**; se llenan solas al abrir los atributos en el juego sin `-ReadOnly` |
| color de acento de cada PJ | **del elemento**: 7 colores, un PJ nuevo tiene color el día 1 |
| alcance del Roster | **la Parte B completa** — es la plantilla de Discos y Armas |
| "build completion %" y los 4 botones del modal | **afuera**, como en la vista en vivo |
| región derecha de la vista en vivo | irá el scoring del mockup cuando se implemente el scoring |

## 2 · Lo que se midió antes de diseñar

- **"Onboarding a medias" tiene una fuente exacta**: no tener filas en `agent_thresholds`. Da Aria,
  Pyrois, Remielle Dan y Velina — los mismos cuatro que la especificación nombra a mano.
- El diseño dice "+6 no obtenidos"; la DB tiene **7**, porque `Lichter`/`Lighter` son una grafía en
  conflicto que el editor tampoco dedupea. El header **calcula**, no copia el número del diseño.
- El diseño supone "42 de 51 en nivel 60"; hoy el nivel está **vacío para los 51**. La marca "nivel
  teñido si ≠ 60" se implementó igual, y el caso vacío dice "sin leer".
- Hay 16 facciones y 23 archivos de logo sin convención de nombres (mitad en español, mitad
  `Faction_…_Icon`, dos duplicados). Por eso el resolvedor es una tabla, con un test que falla
  **nombrando** la facción nueva sin logo (verificado sacando Faetón de la tabla).

## 3 · Lo que los tests no veían y las capturas sí

Se renderizó cada pantalla offscreen **con la DB real y las fuentes de Windows** antes de commitear.
Tres defectos con todos los tests en verde:

1. **Una fila de chips estiraba la vista a 2549 px.** La ventana mínima deja 1100 px para las vistas;
   la mitad de la grilla quedaba fuera. Los filtros se repartieron en otras filas y la leyenda dejó de
   imponer ancho. Test nuevo contra la DB real.
2. **Los casilleros de discos medían 0 px.** Un widget pintado a mano sin tamaño declarado; los tests
   miraban textos. Test nuevo sobre el tamaño.
3. **Maximizada, la grilla dejaba media pantalla vacía.** Varias cantidades de columnas empataban en
   la escala tope y ganaba la primera (7). Desempate hacia la de más columnas, y grilla centrada.

Y una trampa del propio instrumento: **sin fuentes, el offscreen dibuja cada letra como un cuadrado
más ancho que el glifo real**. El test de ancho dio 1407 px con la vista ya arreglada; con las fuentes
registradas, 1076. Un test de medidas de texto tiene que cargar las fuentes reales o se miente.

## 4 · Errores míos

- **Conté mal las armas sin ícono en la fase 1** ("6, a todas les falta `nombre_en`"): eran 4 sin
  nombre y 2 sin archivo. Lo destapó hacer la migración, no releer el doc.
- **La mig `_33` casi escribe un `nombre_en` duplicado**: el chequeo de unicidad del ensayo lo cazó
  (`expected_0 = 1`). Así apareció el duplicado del catálogo.
- **Un test del modal tenía la premisa equivocada**: esperaba que 2+2+1 discos no dieran sets, pero
  dos pares SON dos bonos de 2 piezas. El código estaba bien.
- **No vi fallar los tests de datos del roster antes de escribir el módulo** (lo escribí en el mismo
  paso). Se compensó saboteando: descartados, orden de `∞`, "sin leer", el id del click y el formato
  de stats — todos dieron rojo.

## Queda abierto

1. **QA en vivo de Daniel**: la grilla maximizada y en 1320×820, filtros, y el modal de Yanagi (4+2),
   Nekomata (5 discos, sin arma), Remielle Dan (sin umbrales, sin logo de facción) y Billy Estelar
   (atuendo).
2. **Viento tiene color provisional** (`#6EE7B7`): no hay captura de Velina para muestrearlo.
3. **Logo de Covenant of Dayat** (Remielle Dan) no existe en el repo.
4. **Faltan 3 archivos de ícono** de armas (Sol Exuvia, Boisterous Echoes, Ice-Jade Teapot), y las
   filas 5 y 13 de `weapons` tienen stat secundario y pasiva que no coinciden con las fuentes.
5. **Maximizada queda aire abajo**: la escala de la celda tiene tope 1.3. Se ajusta con lo que Daniel
   vea en vivo.
6. **El "agrupar" de la fila de filtros** del diseño no se portó: la especificación no dice por qué
   se agrupa.
