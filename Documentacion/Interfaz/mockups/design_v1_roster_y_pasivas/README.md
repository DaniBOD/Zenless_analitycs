# Diseño v1 — Roster, editor de roster y confirmaciones pasivas

> **Importado de Claude Design el 2026-08-17.** El documento fuente es un *canvas de artboards*,
> no una app: son especificaciones dibujadas. La fuente de verdad sigue viviendo en el proyecto de
> Claude Design y se relee cuando haga falta — acá está lo que hace falta para **implementar**.
>
> **Proyecto:** `e093a36c-4b42-433d-9387-d415712105bd` · archivo `DaniBOD ZZZ Analytics.html`
> Se lee con la herramienta `DesignSync` (`list_files` / `get_file`).
>
> Responde al brief
> [`BRIEF_roster_y_confirmaciones_pasivas.md`](../../claude_design_upload/BRIEF_roster_y_confirmaciones_pasivas.md).

---

## 0. ⚠️ Lo primero: qué manda

El documento junta el diseño **viejo** de toasts/panel con los rediseños de las Partes A, B y C, y
trae una sección de precedencia explícita. **Donde se pisan, manda lo nuevo.**

| | versión anterior — NO implementar | **manda esto (Partes A·B·C)** |
|---|---|---|
| Frame del toast | 380 × 116 | **460 × 156** |
| Piso tipográfico | 7 – 9 px | **9,5 px** |
| Confirmación de swap | `✓ SINCRONIZADO` en verde | **`OBSERVADO` en violeta** |

Las secciones de **toasts de recomendación** y **panel** conservan la escala vieja a propósito: su
rediseño no estaba en el brief y quedan como referencia del estado actual del código.

**Esto zanja las dos divergencias que el brief levantó:**

1. El badge pasa a `OBSERVADO` violeta. Gana la implementación: el toast afirma lo que **se vio en
   pantalla**, no lo que la DB guardó, y sale igual en read-only.
2. **`EQUIPADO` verde sigue vigente — es otro evento** (decisión D2). No se fusiona con `AHORA EN`:
   uno confirma que se aplicó una sugerencia, el otro que se equipó un disco que estaba libre.

---

## 1. Parte C — Editor de roster ✅ IMPLEMENTADO

`app/ui/roster_declaration_dialog.py`. Ver §3 para qué se portó y qué no.

### El predicado de confirmación, textual del diseño

```js
const evidencia = p => p.tiene && (p.d > 0 || p.n > 1);
```

**Discos > 0 O nivel > 1.** No es "stats cargados" genérico: el diseño eligió `nivel` porque es lo
que salva a Aria (0 discos, Nv 40) y lo que deja a Remielle Dan (0 discos, Nv 1) sin evidencia —
que es justo el falso positivo que motivó el tercer estado.

### Los tres estados

| estado | color | check | ¿se puede destildar? |
|---|---|---|---|
| `confirmado` | `#B06FF0` violeta | tildado **macizo** + candado | **no** |
| `declarado` | `#F0AA3C` ámbar | tildado translúcido | sí |
| `no obtenido` | `#6B6376` gris | vacío, borde **punteado** | — |

Orden de la grilla: confirmado → declarado → no obtenido, y dentro alfabético.

### La celda — 122 × 90, grilla de 10 columnas, gap 6

```
┌──────────────────────────┐
│ [✓]              (avatar)│   check 19×19 · avatar 32 px circular
│                          │   avatar en gris si no lo tenés
│ Nombre del PJ            │   display 11,5 px · 2 líneas máx
│                          │
│ CONFIRMADO               │   caps 8 px, color del estado
│ 6 discos · Nv 60         │   motivo, 8,5 px muted
└──────────────────────────┘
```

- Candado 13×13 pegado abajo-derecha del check cuando está bloqueado.
- `ATUENDO` en violeta para las 2 variantes.
- `grafía en conflicto` en ámbar para `Lichter`/`Lighter`.
- Esquina triangular naranja de 13 px para los desajustes.

### El tooltip del bloqueo — es contenido, no adorno

> **NO SE PUEDE DESTILDAR**
> **Yanagi** tiene **6 discos equipados** y **nivel 60**. Eso es prueba de posesión: destildarlo
> declararía algo que la evidencia contradice, y borraría la build.
> — *Para quitarlo hay que borrar su build primero, en la pestaña Discos.*

Esa última línea es la que convierte un control deshabilitado en una instrucción.

### Header, filtros y leyenda

- Título **Editar roster** (23 px) + kicker `CENSO DECLARADO`.
- Bajada: *"Tildá los personajes que tenés. Esto le da al sistema el **denominador** que la
  observación no puede deducir. No inventa datos: los que falten arrancan el onboarding."*
- Botones: `Cancelar` · `Guardar censo`.
- Chips: Todos · Confirmados por evidencia · Declarados · No obtenidos · **Desajustes**.
- Contador a la derecha: `{conf+dec} DECLARADOS · {filas} FILAS EN AGENTS`.
- Leyenda al pie con los 3 puntos de color y la regla:
  `LA DECLARACIÓN ES LA TERCERA FUENTE DE CONFIRMACIÓN — NO REEMPLAZA A LA EVIDENCIA`.

### §C.4 — los dos desajustes, cada uno con su salida

| desajuste | qué ofrece la pantalla |
|---|---|
| **declarado sin fila en `agents`** | ámbar + botón `INICIAR ONBOARDING · 8 PASOS`. **No inventa el personaje**: declararlo no crea stats. |
| **en `agents` y no declarado** | naranja + dos salidas, ninguna automática: *"Sí lo tengo — declararlo y conservar la fila"* / *"No lo tengo — revisar la fila en Discos"*. |

---

## 2. PENDIENTE de implementar

### Parte B — pantalla Roster 1320×820

Define la **plantilla de "pestaña de catálogo"** que después heredan Discos, Armas y Catálogos.
Cinco bandas de altura fija; **el cuerpo nunca scrollea**:

| banda | alto | contenido |
|---|--:|---|
| Pestañas | 42 | 9 fijas, la activa con barra violeta |
| Header | 56 | título + los conteos + acciones |
| Filtros | 104 | 3 filas: ejes · rol + agrupar · estado de build |
| Cuerpo | resto | la grilla, entera |
| Leyenda | 32 | traduce cada marca visual — **obligatoria** |

Reglas que se heredan:

- **Si el catálogo no cabe, se comprime la celda; no se agrega scroll.**
- Los filtros son **del dominio**, no genéricos (acá elemento/rango/rol/facción; en Discos serán
  set/slot/main). Lo que se hereda es la **banda de estado ámbar** — *"a qué le faltan datos"*.
- La leyenda es obligatoria: sin ella, la esquina rayada y el borde punteado son adorno.

Marcas de la celda del roster:

- **Esquina rayada ámbar** = onboarding a medias (Velina, Pyrois, Remielle Dan, Aria). Es el dato
  que hoy ninguna superficie muestra.
- **El nivel se tiñe solo cuando no es 60** — 42 de 51 están en 60; pintar el caso normal es ruido.
- Discos por encima de 6 (Manato 8, Velina 7) van como `+n`: la grilla de 6 casilleros no se estira
  por una excepción.
- **`∞` no es una S con adorno**: S y A son círculos huecos, `∞` es una **cápsula maciza con halo
  naranja**. Ordena primero — con 1 PJ, alfabético se perdería entre 37 S.

**Decisión B7 · las 2 variantes de atuendo:** celda **propia**, ni anidada ni oculta. Tienen rango,
rol, mindscape y build propios (Billy Estelar es S/Disruptivos mientras Billy es A/Ataque), y son
builds reales que compiten por discos — esconderlas haría que un disco "desaparezca" del inventario
visible. Lo que evita leerlas como 2 personajes más son **tres marcas simultáneas**: borde punteado
violeta, badge `ATUENDO · Billy`, y el conteo del header separado.

**El conteo del header son cuatro números, no uno** — *"un solo número obligaría a elegir cuál
mentira contar"*: `51 filas` `−2 atuendo` `49 distintos` `+6 no obtenidos` `= 55 conocidos`, más
`4 sin thresholds` en ámbar, que es el que pide acción.

### Parte A — confirmaciones pasivas

Frame **460 × 156**, piso tipográfico **9,5 px**, badge `OBSERVADO` violeta. El detalle vive en
`partea-doc.jsx` y `toasts-passive.jsx` del proyecto de diseño.

---

## 3. Qué se portó y qué no

El diseño es web (React + CSS con `clip-path`, glows compuestos, tooltips flotantes). Qt no
reproduce todo, y forzarlo daría un resultado peor. Del editor se portó lo que **significa** algo:

| se portó | se dejó |
|---|---|
| los 3 estados con sus colores exactos | los chamfers por `clip-path` |
| el predicado `d > 0 or n > 1` | los glows por `box-shadow` compuesto |
| candado + el motivo del bloqueo | el tooltip flotante con flecha (va como tooltip nativo) |
| grilla de 10 columnas, orden por estado | las animaciones de hover |
| chips de filtro con sus conteos | — |
| la leyenda al pie | — |
| badges `ATUENDO` y `grafía en conflicto` | — |

Los assets `assets/pj/*.webp` del proyecto de diseño son los mismos `splash_arts/*-ico.webp` del
repo: la app los resuelve con `asset_resolver.agent_avatar_path(nombre, variant="ico")`.
