# SPEC — Compactar Dev_IA por período

**2026-09-08.** Qué se hace con 76 documentos de desarrollo, y qué se va a hacer con los 300 que
vienen. Diseño acordado con Daniel; el piloto de julio decide si se aplica al resto.

## El problema, medido

| | |
|---|---|
| documentos | **76** · 14.397 líneas · 5 meses |
| ritmo | **27/mes** en el pico (julio y agosto) |
| referencias cruzadas entre ellos | **3** |
| documentos que nadie referencia | **37 de 75** |
| índice | no existe |

El costo no es guardar: es **consultar lo añejo**. Con la mitad del corpus inalcanzable salvo
listando el directorio, no hay forma barata de saber si vale la pena abrir un documento de 300
líneas — hay que abrirlo para averiguarlo.

**Anatomía de julio** (4.679 líneas): **2.654 son prosa** (57%), 409 filas de tabla, 89 líneas de
código, 341 encabezados. Lo valioso ya está estructuralmente separado de lo prescindible.

## La restricción que manda

Daniel, textual: *aligerar la lectura **sin que Claude pierda efectividad**.* Comprimir mal deja
peor que no comprimir — un resumen seguro y equivocado propaga el error con la autoridad del
original. Esta misma sesión dio dos ejemplos (*"7 huecos de catálogo"* cuando eran 6; *"el corte
separa Modelo II de Modelo III"* cuando lo separa el match exacto).

## Qué se conserva y qué se tira

| se conserva | por qué |
|---|---|
| **las mediciones** (`60/60`, `8/10`, `0.977`, `hue S=22 varianza cero`) | un número medido no se reconstruye leyendo código. Es lo único que impide re-derivar o adivinar |
| **las hipótesis refutadas** | evita repetir un camino muerto. Es lo más caro de regenerar y lo primero que tira un resumen genérico |
| **dónde vive la autoridad** (archivo, función, commit) | convierte el compacto en índice ejecutable en vez de anécdota |
| **lo que quedó abierto**, y si se cerró después | |

| se tira | por qué |
|---|---|
| la narrativa del proceso | 57% del volumen; no cambia ninguna decisión futura |
| los bloques de código | están en git, con más precisión y sin envejecer |
| el paso a paso de implementación | el código es la autoridad; el doc sólo miente con el tiempo |

### Criterio de aceptación

**Si se borraran los crudos, ¿se podría decidir igual?** Es verificable: se elige una pregunta que
hoy sólo responde un crudo y se ve si el compacto la contesta. No es "que sea corto".

### Refinamiento que trajo el piloto: medición ≠ constante

De 9 preguntas de prueba contra el compacto de julio, **7 se responden**. Las 2 que no son las dos
mismas cosa: **constantes que ya viven en el código** (el criterio de píxel de las estrellas, en
`parser_weapon_s26.py:119`; la geometría de los tiles de S2, en `parser_s2.py`).

Eso afina la regla, y en la dirección de comprimir más:

> Una medición que **se convirtió en una constante del código** no va al compacto: el código es su
> autoridad, y duplicarla crea la divergencia que este diseño evita. Lo que sí va es **la evidencia
> que justifica la constante** y **las alternativas que fallaron** — eso no está en ningún lado más.

Ejemplo del propio compacto: `_DISC_STRIP_MIN = 3` está en el código, así que lo que se conserva no
es el `3` sino *por qué* 3 (farmeo real da 3 en todas las capturas, pantallas sin discos ≤2).

## Estructura

```
Documentacion/Dev_IA/
├── 00_Practicas_Aprendidas.md      ← NO se mueve: CLAUDE.md §0 apunta a esta ruta
├── 00_Indice.md                    ← la puerta única
├── compactos/
│   └── YYYY-MM_compacto.md
└── documentacion_cruda/
    └── YYYY-MM/
```

**Ningún archivo se mueve nunca.** Los documentos nuevos nacen ya en `documentacion_cruda/YYYY-MM/`.
Mover rompe enlaces, y este proyecto vive de punteros a rutas: un archivo que se muda dos meses
después convierte cada referencia vieja en un 404 silencioso. Hay **una sola mudanza histórica**
(los 76 de hoy) y después ninguna.

## El corte entre vivo y añejo

**No es una fecha: es la existencia del compacto.**

- el mes **tiene** compacto ⇒ está cerrado, se lee el compacto;
- el mes **no tiene** compacto ⇒ está vivo, se leen los crudos.

Sin umbral que calibrar ni aritmética de fechas que pueda estar mal. El compacto de un mes se
escribe cuando arranca el siguiente.

**Mensual, no quincenal.** Los nombres ya empiezan con `YYYY-MM-DD`, así que el mes es una frontera
gratuita y sin ambigüedad; quincenal obliga a inventar el corte y a discutirlo cada vez. Si un mes
supera ~30 documentos, ahí se parte.

## Una sola autoridad por pregunta (B1)

La agregación de lecciones **ya existe** y es lectura obligatoria. El compacto no la duplica:

| documento | responde | cuándo se carga |
|---|---|---|
| `00_Practicas_Aprendidas.md` | *cómo trabajar* — lecciones transferibles | siempre (CLAUDE.md §0) |
| `compactos/YYYY-MM_compacto.md` | *qué pasó y qué se midió* — hechos, caminos descartados, números | a demanda |
| `00_Indice.md` | *qué hay y si sigue siendo cierto* | siempre; es barato |

⚠️ **El compacto NO lleva lecciones transferibles.** Esas van a `00_Practicas`. El compacto lleva
justo lo que `00_Practicas` descarta a propósito: qué se construyó, qué se probó y se abandonó, con
qué evidencia.

## El índice, y la propiedad que lo hace sostenible

Dos niveles: **una línea por mes cerrado** (apuntando a su compacto) y **una línea por documento del
mes vivo**. Eso lo deja acotado — hoy ~10 líneas; dentro de un año, 17 más las del mes en curso.

**No crece con el corpus, crece con el calendario.** Es la única forma de que el índice no reproduzca
el problema que este diseño arregla.

El mapa documento-por-documento de los meses viejos vive **dentro de cada compacto**, que abre con la
lista de crudos que cubre: se conserva entero, y se paga sólo al abrir ese mes.

## Por qué un compacto de período cerrado es seguro

El riesgo de todo resumen es divergir de la fuente. **Un compacto de un período cerrado no puede
divergir, porque la fuente está congelada**: julio ya pasó y esos 27 documentos no se van a editar.
Resumir trabajo *activo* sería peligroso; resumir historia no lo es.

De ahí la regla: **sólo se compacta lo cerrado, y una vez compactado el período es inmutable.**

## Los 16 nombres fuera de convención

Los de mayo a julio usan `Hito_2.8_` o directamente nada, en vez de `YYYY-MM-DD_TIPO_Nombre`. Se
normalizan **en la misma mudanza**, con `git mv` para que la historia siga al archivo, y el mapeo
viejo→nuevo queda escrito en el compacto de su mes — para que una referencia vieja siga siendo
resoluble.

## Plan

1. ~~Piloto: compacto de julio~~ **HECHO.** 4.679 líneas → **173**, ratio **27:1** (3,7 % del
   original). Las 15 mediciones del compacto verificadas una por una contra el crudo; el criterio
   de aceptación da 7/9, y los 2 que faltan son constantes que viven en el código (ver arriba).
2. ~~Decidir si se sigue~~ **sí.**
3. ~~Mudanza histórica~~ **HECHO** (`c0c93d7`). 76 archivos con `git mv`, 154 enlaces re-enlazados
   por resolución, **0 rotos por la mudanza** (baseline 52 → 51, verificado uno por uno con
   `tools/check_doc_links.py`). **Los nombres NO se normalizaron**, contra lo que decía este
   paso: 13 de los 17 "fuera de convención" dicen `Hito_2.8_`, que es información real, y la
   estructura misma vuelve innecesario el renombre — a los crudos se llega por el compacto, no
   por nombre de archivo.
4. Compactos de mayo, junio y agosto — **pendiente**. Mientras falten, esos meses cuentan como
   vivos y el índice lista sus documentos uno por uno.
5. ~~`00_Indice.md`~~ **HECHO.**
6. ~~Actualizar CLAUDE.md §0~~ **HECHO**: el índice entra a la lectura obligatoria, y queda escrita
   la regla de dónde nace un documento nuevo.

**Septiembre NO se compacta**: está vivo.

## Fuera de alcance

- **Compactar `audit/`.** Otro corpus, otro criterio (son evidencia, no narrativa).
- **Tocar `project-context-IA.md` o el roadmap.** Tienen su propia autoridad.
- **Borrar crudos.** Nunca. El compacto es una vía rápida, no un reemplazo.
