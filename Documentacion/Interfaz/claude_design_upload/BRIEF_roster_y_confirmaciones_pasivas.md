# Brief Claude Design — Pantalla ROSTER + la familia de confirmaciones pasivas

> **Dos pedidos, y son de naturaleza distinta.**
>
> - **Parte A — rediseñar la familia violeta de toasts** (`REEMPLAZADO`, `AHORA EN`, `DESMONTADOS`,
>   `W-ENGINE VISTO`). Existen y funcionan en vivo, pero se pintaron a mano en Qt. Dos de ellas
>   **sí** pasaron por diseño en su momento y la implementación **divergió a propósito** — esa
>   divergencia es lo primero que este brief necesita que se resuelva (§A.1).
> - **Parte B — diseñar la pantalla ROSTER desde cero.** No existe ni en código ni en mockup. Sería
>   **la primera pestaña del panel principal** que se construye (hoy solo existe la consola de
>   captura en vivo).
> - **Parte C — el editor de roster dentro de esa pantalla**: el usuario declara qué PJs tiene.
>   Trae una regla dura de borrado y un hallazgo que la complica (§C.3).
>
> Sistema visual, tokens y componentes: `BRIEF_COMPLETO.md` (§1) y
> `mockups/design_handoff_toast_variants/source/`. Implementación real: `app/ui/toast.py`,
> `app/ui/tokens.py`, `app/ui/live_panel.py`.
>
> Briefs previos vigentes que este NO reemplaza:
> [`BRIEF_toast_desmontado_y_legibilidad.md`](./BRIEF_toast_desmontado_y_legibilidad.md) (la escala
> tipográfica sigue pendiente y aplica a todo lo de acá) y
> [`BRIEF_card_reemplazado.md`](./BRIEF_card_reemplazado.md).

---

# PARTE A — La familia violeta (confirmaciones pasivas)

## A.0 Qué son y por qué son una familia

Las 4 variantes de recomendación (`EQUIPAR`, `MEJORAR`, `RESERVA`, `DESCARTAR`) **aconsejan**:
traen score grande, countdown y barra de urgencia pulsante. Las de esta familia **reportan**: el
sistema vio algo en pantalla y lo cuenta. Sin score, sin countdown, sin urgencia. El violeta
`--purple #9D4EDD` es lo que las separa de un vistazo.

| variante | label en pantalla | qué reporta | body | footer actual |
|---|---|---|---|---|
| `reemplazado` | **REEMPLAZADO** | un disco pasó de un PJ a otro | PJ origen → disco → PJ destino | `REEMPLAZO OBSERVADO` / `S23 → badge ✓` |
| `equipado` | **AHORA EN** | un disco **libre** se equipó a un PJ | disco → PJ destino (sin origen) | `EQUIPAMIENTO OBSERVADO` / `badge + botón ✓` |
| `desmontado` | **DESMONTADOS** | una tanda de desmontaje cerrada | conteo del lote + cobertura | `DESMONTAJE OBSERVADO` / `contador N/300 ✓` |
| `arma_vista` | **W-ENGINE VISTO** | un W-Engine que el usuario abrió | nombre, rareza, nivel, ★refinamiento, atributo | `SOLO LECTURA` |

`W-ENGINE VISTO` (RF-15) **nunca pasó por diseño** — es la que está más cruda.

## A.1 ⚠️ Lo primero: el diseño y la implementación se contradicen

El handoff `design_handoff_toast_variants` especificó dos de estas variantes. La app terminó
haciendo otra cosa, y **no por descuido**: hubo un rediseño deliberado el 2026-07-20 que cambió la
semántica. El diseño nuevo tiene que zanjar cuál gana.

### Divergencia 1 — el micro-badge afirma cosas distintas

| | diseño entregado | app en producción |
|---|---|---|
| badge top-right | `✓ SINCRONIZADO` (verde) | `✓ OBSERVADO` |
| footer derecho | `inventory_discs ✓` | `S23 → badge ✓`, `badge + botón ✓`, `SOLO LECTURA` |

**La implementación es la que tiene razón, y por un motivo que no es cosmético.** Estos toasts
salen **igual en modo read-only**, donde la DB no se toca. Un badge que dice "sincronizado" cuando
puede no haberse escrito nada le enseña al usuario a confiar en una garantía que el sistema no da.
El toast afirma **lo que se vio en pantalla**, nunca lo que la DB guardó.

→ **Pedido:** conservar esa distinción, pero resolverla visualmente mejor que hoy. "OBSERVADO" en
7 px caps es la solución mínima, no una buena. La familia entera necesita una forma clara de decir
*"esto lo vi, no lo garantizo"*.

### Divergencia 2 — `equipado` cambió de significado Y de color

| | diseño entregado | app en producción |
|---|---|---|
| label | `EQUIPADO` | **`AHORA EN`** |
| color | verde `--positive` (misma acción que EQUIPAR, otra fase) | **violeta `--purple`** |
| significado | *"tu sugerencia EQUIPAR fue aplicada"* | *"un disco **libre** se equipó a un PJ"* |

Son **dos eventos distintos**. El de la app no presupone que hubo sugerencia previa: el usuario
equipó un disco que no era de nadie, y el sistema lo vio. Por eso es violeta (hecho observado) y no
verde (sugerencia cumplida).

El label perdió el nombre del PJ por una razón medida: con `AHORA EN <PJ>` en el header, un nombre
largo —`ORFIA Y MAGAS`— se comía los ~87 px de holgura y chocaba con el micro-badge. Se lee
**"AHORA EN" + el avatar/nombre que ya pinta el body**.

→ **Pedido:** validar o reemplazar esa solución. Si el header vuelve a llevar el nombre, el diseño
tiene que demostrar que aguanta `ORFIA Y MAGAS` y `N.º 0: ANBY`.

### Divergencia 3 — el ícono del header no existe

Ya está en el brief de legibilidad y sigue abierto: `tokens.py` define un ícono por variante
(`swap`, `check`, `trash`, `stack`), pero `_paint_header` dibuja **solo texto con un subrayado de
color**. El chip con esquina chaflanada de los mockups JSX **se perdió en el port a Qt**.

Ojo con las colisiones si el chip vuelve:
- `trash` es el ícono de `DESCARTAR` (recomendación) **y** de `DESMONTADOS` (hecho).
- `check` es el de `EQUIPAR` **y** el de `AHORA EN`.
- `stack` es el de `RESERVA` **y** el de `W-ENGINE VISTO`.

O la familia violeta recibe íconos propios, o se declara que el color carga con toda la
diferenciación y el chip se descarta.

## A.2 Medidas reales de hoy (no del mockup)

```
frame           380 × 140     (era 116; creció por un PARCHE de layout, no por diseño)
label header    Segoe UI 10 px bold      ID  8 px      micro-badge  7 px caps
thumb del disco 48 px         logo del set ~37 px efectivos
badge rareza    círculo 14 px, letra 7 px          ← lo peor de toda la card
body / footer   8-9 px
```

**El frame puede crecer.** Permiso explícito de Daniel. Rango sugerido a confirmar por diseño:
**420-460 px de ancho**, altura la que pida la grilla. El límite es que siga siendo un toast de
esquina: no debe tapar HUD de combate ni pedir que el usuario despegue la vista del juego.

## A.3 Lo específico de `W-ENGINE VISTO` (la que no tiene diseño)

Body actual, todo alineado a la izquierda en una columna:

```
Caldero de claridad            ← display 15 px
S · Nv 60 · equipada           ← 9 px muted   (rareza · nivel · TENENCIA)
★★★★☆                          ← refinamiento, 10 px, en violeta
ATK +12.5%                     ← atributo avanzado, mono 9 px
```

Dos decisiones tomadas que conviene respetar:

1. **El refinamiento va en estrellas, no como "P4".** "P4" es la notación del juego, pero en esta
   pantalla el usuario ve literalmente cinco estrellas con algunas llenas. Si no se pudo leer, **no
   se dibuja ninguna** — cinco vacías se leerían como refinamiento 0, que no existe (el mínimo es 1).
2. **`SOLO LECTURA` en el footer** es literal: este hito no escribe la DB.

La **tenencia** (`libre` / `equipada` / `de otro PJ`) es el dato más caro de conseguir de toda la
pantalla y hoy va perdido en una línea gris de 9 px junto a la rareza. Merece jerarquía propia.

---

# PARTE B — Pantalla ROSTER (nueva, desde cero)

## B.0 Contexto: es la primera pestaña real del panel

El panel principal está especificado como **1320×820, 9 pestañas** (Captura en vivo, Histórico,
Roster, Discos, Equipos, Lategame, Armas, Catálogos, Configuración). **En código hoy solo existe la
consola de captura en vivo** (`app/ui/live_panel.py`, 404 líneas). Hay mockups de la pestaña Discos
y del modal de PJ individual (`24-modal-pj-yanagi.png` … `28-modal-pj-caesar.png`) — pero **de la
grilla del roster no hay nada**.

Así que este diseño define, de hecho, **la plantilla de "pestaña de catálogo"** que después van a
heredar Discos, Armas y Catálogos. Vale diseñarlo pensando en eso.

## B.1 Los datos reales (medidos en la DB hoy)

**51 filas en `agents`**, que **no son 51 personajes**:

```
51 filas
 −2 variantes de ATUENDO  (Billy Estelar = Billy · N.º 0: Anby = Anby)
 = 49 personajes distintos que Daniel posee
 +6 que no posee  (Norma, Promeia, Banyue, Yidhari, Hugo, Lichter)
 = 55 personajes conocidos
```

⚠️ **Las 2 variantes de atuendo no pueden verse como 2 personajes más.** Es un límite conocido del
modelo de datos y ya causa problemas en otras partes del sistema. El diseño tiene que decidir cómo
se muestran: ¿anidadas bajo el PJ base? ¿un badge de "atuendo"? ¿ocultas por defecto?

**Distribuciones** (para que la grilla se pruebe con la forma real, no con datos inventados):

| eje | valores |
|---|---|
| rango | S **37** · A **13** · **∞ 1** |
| elemento | Físico 14 · Eléctrico 12 · Éter 9 · Fuego 9 · Hielo 5 · **Viento 1** · **Lumen 1** |
| rol | Ataque 15 · Anomalía 11 · Aturdimiento 9 · Soporte 8 · Defensa 5 · Disruptivos 3 |
| facción | 16 distintas |

⚠️ **El rango `∞`** (un solo PJ: Pyrois) es un rango **por encima de S**, nuevo del juego. No es una
S con adorno; necesita su propio tratamiento visual. Igual los elementos **Viento** y **Lumen**, con
un PJ cada uno — son los más nuevos y los que menos arte de referencia tienen.

⚠️ **Lumen no tiene bono de daño elemental.** Es el único elemento del juego sin ese stat, y está
fijado como contrato en el sistema. Si el diseño muestra "bono de daño de elemento" por PJ, ese
casillero tiene que poder estar legítimamente vacío sin parecer un dato faltante.

**Estado de las builds:**

```
47 PJs con los 6 discos equipados
 2 con 5 discos            (Jane, Nekomata)
 2 con 0 discos            (Remielle Dan, Aria)  ← los dos onboardings más recientes
46 con W-Engine asignado
42 en nivel 60
 4 sin thresholds cargados (Velina, Pyrois, Remielle Dan, Aria) ← onboarding a medias
```

**Ese último renglón es una necesidad real del proyecto, no un adorno.** Cada parche trae 1-2 PJs
nuevos, y el onboarding tiene 8 pasos que se completan en tandas. Hoy no hay ninguna superficie que
muestre *"a este PJ le falta la mitad de los datos"* — se descubre cuando algo falla. **La pantalla
Roster es el lugar natural para exponerlo.**

## B.2 Campos disponibles por PJ

```
identidad   nombre · rango (S/A/∞) · elemento · rol · facción
progreso    nivel (1-60) · mindscape (M0-M6) · despertar/silueta potencial
stats       pv · ataque · defensa · impacto · prob_critico · dano_critico
            tasa_anomalia · maestria_anomalia · tasa_perforacion · perforacion
            rec_energia · bono_dano_elemento  (NULL legítimo en varios)
build       weapon_id + nivel + refinamiento · set_4p · set_2p · disco6_main
meta        notas · protected_build (hoy 0 en todos)
```

## B.3 Assets disponibles

- **`splash_arts/`** — 114 archivos, `<PJ>-ico.webp` (avatar, 32-64 px) y `<PJ>-extend.webp` (arte
  extendido para fondos de modal). Cubre ~57 personajes, incluidos varios de los **no obtenidos**.
- **`Facciones_Logos/`** — logos de las 16 facciones. Cada uno tiene identidad visual propia del
  juego: **no rediseñar ni uniformar**.
- **Badges de PJ en 3 superficies** (`row` / `grid` / `detail`) — son recortes cosechados de la
  pantalla del juego que el sistema usa para *reconocer* PJs. **No son assets de presentación**; no
  usarlos en la UI.

## B.4 Lo que la pantalla tiene que resolver

1. **Ver 49-55 PJs de un vistazo** sin scroll infinito, en 1320×820.
2. **Filtrar/agrupar** por elemento, rol, rango, facción — y por **estado de build**, que es el uso
   real (*"¿a quién le falta el disco 6?"*, *"¿quién quedó en nivel 50?"*).
3. **Distinguir tres cosas que hoy se confunden**: PJ obtenido con build completa · PJ obtenido con
   datos a medias · PJ que existe y no se posee.
4. **Entrada al modal de PJ**, que ya está diseñado (`24-modal-pj-*.png`) — la grilla es su índice.
5. **El botón de editar roster** (Parte C).

---

# PARTE C — El editor de roster (censo declarado)

## C.0 Por qué existe: el sistema no puede enumerar solos los PJs

El sistema tiene un censo **por observación**: el usuario recorre el menú de personajes y el OCR va
marcando a quién vio. Funciona —49/51 en 18 minutos, cero errores— **pero solo para los que
posee**. Con los no obtenidos falla de dos maneras medidas el 2026-08-17:

- De **6** personajes no obtenidos por los que el usuario pasó, **solo 1** dejó registro.
- **4 de 6** se parecen tanto a un PJ propio que el reconocedor los confunde por encima del umbral:
  `Norma→Nekomata 0.615 · Promeia→Pyrois 0.615 · Banyue→Anby 0.600 · Lichter→Alice 0.667`.

O sea: mirar un personaje que no tenés le dice al sistema que estás mirando otro. **La observación
no alcanza, y encima ensucia.** El usuario, en cambio, sabe perfectamente cuáles tiene.

Esto **no** contradice la doctrina del proyecto ("no inventar datos"). La doctrina es *no inventar*,
no *no preguntar*. Declarar 55 casillas que el usuario sabe de memoria no es lo mismo que
transcribir a mano 367 discos con sus substats.

Y da algo que la observación **nunca** puede dar: el **denominador**. Por más que el sistema
recorra, no sabe cuántos personajes existen en total. El usuario sí.

## C.1 Qué es la pantalla

Selección múltiple sobre el **catálogo de personajes conocidos** (~55-58 nombres, la unión del arte
disponible). El usuario tilda los que tiene. Se abre desde un botón en la pantalla Roster.

Daniel la pidió **temporal y aparte, para pulir después** — pero conviene diseñarla bien de una,
porque es también el flujo de **"me salió un PJ nuevo en el banner"**, que ocurre cada ~6 semanas.

## C.2 La regla dura: un PJ confirmado no se puede borrar

> *"no se pueden borrar PJ que se confirmaron en el roster, es decir que ya tienen discos y stats
> alterados por encima del default. Es una obviedad que lo tiene el usuario y no puede eliminarlo."*

Un PJ con 6 discos equipados y nivel 60 **es prueba de posesión**. Destildarlo sería declarar algo
que la evidencia contradice, y borraría la build. El check tiene que verse **deshabilitado y
explicado**, no simplemente no responder al click.

## C.3 ⚠️ Hallazgo: la regla, tal cual, deja un falso positivo

Aplicando el predicado literal (*tiene discos* **o** *stats por encima del default*) sobre la DB de
hoy, quedan **exactamente estos 4** fuera de "confirmado":

| PJ | discos | nivel | W-Engine | ¿realmente lo tiene? |
|---|---|---|---|---|
| Aria | 0 | 40 | — | **sí** (salió en el banner hoy) — la salva el nivel 40 |
| Remielle Dan | 0 | **1** | — | **sí** — y el predicado **no la salva** |
| Jane | 5 | 60 | sí | sí, confirmada |
| Nekomata | 5 | 60 | sí | sí, confirmada |

**Remielle Dan quedaría borrable**, y es un PJ que Daniel obtuvo en el parche 3.1. La causa es que
un onboarding recién hecho todavía no tiene ninguna de las dos evidencias: se ingresó el personaje
pero no se le cargó nada.

→ **Hace falta una tercera fuente de confirmación: la declaración previa del propio usuario.** Una
vez que declaró que lo tiene, eso ya es evidencia. El diseño necesita entonces **tres estados**, no
dos:

| estado | de dónde sale | ¿se puede destildar? |
|---|---|---|
| **confirmado por evidencia** | tiene discos y/o stats sobre el default | **no** — check bloqueado, con motivo visible |
| **declarado** | el usuario lo tildó, todavía sin datos | sí (fue una declaración, puede corregirla) |
| **no obtenido** | ni declarado ni con evidencia | — |

## C.4 Los dos desajustes que la pantalla va a exponer

Son inevitables y ninguno se resuelve borrando datos solo:

- **Declarado pero sin fila en `agents`** → no se inventa el personaje: **dispara el onboarding**
  (8 pasos, incluye cosechar sus badges). El diseño debería sugerir esa acción, no rellenar campos.
- **En `agents` pero no declarado** → es la señal más fuerte que el sistema puede dar de una fila
  espuria. **Igual no se borra sola.** Se marca y el usuario arbitra.

## C.5 Detalle suelto de datos

Hay dos grafías del mismo personaje en los archivos de arte: `Lichter.png` / `Lichter-ico.webp`
contra `Lighter-extend.webp`. **No se resuelve por mayoría ni de memoria** — manda lo que muestre
la pantalla del juego. Si el catálogo del editor se arma de los archivos, va a aparecer duplicado
hasta que eso se cierre.

---

# Entregables

**Parte A**
1. Las **4 variantes violetas** en 3 estados (idle / hover / fade-out), con el frame nuevo.
2. Una **decisión escrita** sobre: el micro-badge de "observado vs sincronizado", el label
   `AHORA EN` vs `EQUIPADO`, y el chip con ícono (vuelve o se descarta).
3. La **tabla de escala tipográfica** pendiente del brief anterior, aplicada a las 8 variantes.
4. Sobre fondo de escritorio, como `Toast-en-escritorio-contexto-real*.png`.

**Parte B**
5. **Pantalla Roster 1320×820**, poblada con los 49 PJs reales y sus distribuciones (§B.1) — no con
   una grilla uniforme de ejemplo. Tiene que verse cómo cae `∞`, cómo caen Viento y Lumen con un PJ
   cada uno, y cómo se ven los 4 con onboarding a medias.
6. Estados de filtro/agrupación, incluido el filtro por **estado de build**.
7. La decisión sobre las **2 variantes de atuendo**.

**Parte C**
8. **Editor de roster** con los 3 estados de §C.3, mostrando explícitamente el check bloqueado con
   su motivo, y el caso Remielle Dan (declarado, sin datos, destildable).
9. Los dos desajustes de §C.4 resueltos visualmente.

Reusar tokens y componentes existentes. Tema oscuro absoluto, sin variante clara.
