# El Nivel 0 y "no lo leí" eran el mismo dato

**2026-09-17 · Fase 3 de la hoja de ruta del log en S9 · FIX**

> Antecedentes: [PERF Fase 2](2026-09-17_PERF_Latencia_del_log_en_S9_lo_que_midieron_las_pasadas_A_y_B.md)
> (fases 2B ✅, 2C pendiente) y el
> [QA del censo del 2026-08-30 §3](../2026-08/2026-08-30_QA_Censo_de_discos_cinco_hallazgos_y_una_forma_repetida.md),
> que dejó esto anotado como **deuda explícita**: *"el parser usa 0 como valor **y** como centinela
> de 'no lo leí', así que separarlos pide cambiar el tipo y eso ramifica hasta la DB"*. Esta fase es
> justamente esa ramificación.

## 1. El problema en una línea

`DiscParsed.nivel` arrancaba en **0** y el merge del aggregator preguntaba `if new.nivel:`.
Con eso, el 0 significaba **dos cosas a la vez**:

- *"leí la pantalla y el disco está en Nivel 0/15"* (un drop recién levantado), y
- *"no conseguí leer el nivel"* (OCR corto, panel animando, ROI tapada).

Las dos terminaban en la misma columna `inventory_discs.nivel = 0`, **indistinguibles después**.
Hoy la DB tiene **29 discos en Nivel 0** (23 vigentes, 6 descartados) sobre 391, y no hay manera
de saber cuáles son drops de verdad. Eso es exactamente **B2**: la ausencia se estaba guardando
como si fuera un valor.

## 2. Medir antes (A1)

Antes de tocar nada corrí el parser real sobre el corpus de capturas:

| corpus | capturas | nivel leído | Nivel 0 |
|---|---|---|---|
| S17 vista individual | 16 | 13 | 3 |
| S17 libres | 11 | 9 | 2 |
| S9 inventario | 19 | 18 | 1 |
| **total** | **46** | **40 (87 %)** | **6** |

Es decir: el nivel se lee **casi siempre**, y el "casi" es justo lo que estaba disfrazado de 0.

### La premisa que me corrigió la captura

Mi primera hipótesis fue cómoda: *"un Nivel 0 con 4 substats tiene que ser una lectura fallida,
porque un disco arranca con menos substats"*. Abrí la captura antes de escribirlo en un test:
`17_…_libres/Ejemplo_7_(reemplazar).png` dice **`Nivel 0/15` con 4 substats**. Un disco S puede
salir del drop con los 4 puestos.

O sea que **el 0 es un valor legítimo y frecuente**, y no se lo puede tratar como sospechoso:
hay que separarlo del "no sé". Corregí la afirmación en el texto, en los comentarios del código y
en el docstring del test. (A1 otra vez: el número heredado de mi propia intuición no era una medición.)

## 3. El cambio

`nivel: int | None`, y el None viaja entero de punta a punta.

| capa | antes | ahora |
|---|---|---|
| `parser_disc*.py` | `nivel = 0` de arranque; `_parse_nivel` devolvía 0 | inicia en `None`; `_parse_nivel` **se abstiene** |
| merge del aggregator | `if new.nivel:` (descarta el 0 por *falsy*) | `if new.nivel is not None:` |
| `disc_is_mature` | maduraba con el 0 puesto | **un disco sin nivel no madura** — se sigue fusionando; si nunca se lee, igual se emite al techo de ciclos, pero marcado |
| `repositories.insert` | `nivel=0` | **NULL + marca** `MARCA_NIVEL_NO_LEIDO` en `notas` |
| dedup por identidad | `nivel=?` | `nivel IS ?` — **con `=` un NULL no matchea ni consigo mismo**, y cada relectura habría insertado una fila nueva |
| `update_from_parsed` | pisaba con lo que viniera | una relectura **sin** nivel no pisa un nivel bueno; una **con** nivel adopta la fila provisional y **le saca la marca** |
| `_row_to_disc` | `nivel=r["nivel"] or 0` | `nivel=r["nivel"]` |
| `scoring.py` | bonus por nivel con el 0 | nivel desconocido: **ni premio ni castigo** |
| UI (tabla, modal, `datos.py`) | "0" | tres casos: 15, nivel bajo (ámbar) y **sin leer** (`—`, apagado), como ya hacía Armas |
| `monitor._nv()` | `%d` con None revienta la línea | `?` |

La marca **tiene salida** (B2): si más tarde se lee el nivel, se adopta *esa misma fila*. Sin eso,
el disco quedaba duplicado — la vieja con NULL de fantasma y una nueva con el nivel.

### El costo que esto tiene, dicho explícito

Hacer el nivel **requisito de madurez** no es gratis: el ~13 % de los discos cuyo nivel no se lee
deja de emitir temprano y pasa a esperar el **techo de ciclos**. En una fase cuyo tema es la
latencia, eso es una contra medible y conviene tenerla a la vista en la Pasada siguiente. Lo tomo
igual porque la alternativa es la que veníamos pagando: emitir rápido un dato **inventado**, que
después nadie puede auditar (D2 — degradar en silencio es peor que fallar fuerte). El disco no se
pierde: se emite igual, con NULL y marcado.

## 4. Lo que falló en la verificación

### 4.1 El primer sabotaje pasó en VERDE — el test no tenía dientes

Sabotaje 1 = revertir el parser a `nivel = 0`. **La suite de la fase pasó igual.** Causa: mis
tests construían `DiscParsed` **a mano**, así que nunca ejercían la línea que originó la fase.
El test probaba el mecanismo, no el arreglo.

Agregué dos que entran por `_parse_s17_from_lines` con el OCR de una captura real
(`fixtures/s17_ocr/Ejemplo_1.json`): uno verifica que lee 15, el otro saca del OCR las líneas
`Nivel N/15` y exige `None`, no 0 — y que **el resto del disco se siga leyendo** (B2: abstenerse
no cuesta el dato entero). Con eso, sabotaje 1 en rojo.

**Resultado final: 8 sabotajes, 8 rojos**, con el hash del diff idéntico antes y después
(`fe85fae8660ae100`), o sea que el script restauró todo lo que tocó.

### 4.2 La mitad del bug estaba del lado de la LECTURA

Con el parser y el insert ya arreglados, un disco sin nivel seguía apareciendo como 0 en pantalla.
`_row_to_disc` tenía `nivel=r["nivel"] or 0`: el NULL se volvía a colapsar **al leer la fila**.
Escribir bien no alcanza si la lectura deshace el trabajo.

### 4.3 `self` dentro de un `@staticmethod` (9 tests rojos)

La suite completa tiró **9 fallas en `test_monitor_desmontaje.py`**: metí `self._nv(disc.nivel)`
dentro de `_fmt_teardown_disc`, que es un `@staticmethod` y no recibe `self`. Una causa, nueve
síntomas. Corregido a `Monitor._nv(...)`, y verifiqué que los otros 6 llamados a `_nv` sí están
en métodos de instancia.

Vale anotar **por qué no lo vi antes**: durante los sabotajes corrí sólo los tests de la fase.
La suite completa era el único lugar donde ese archivo se ejecutaba. No es un test que faltaba —
es un test que **no corrí hasta el final**.

## 5. Estado

- Suite completa: **0 failed / 0 skipped**, sha256 de la DB sin cambios (la suite no escribe dominio).
- La DB sigue con 29 filas en Nivel 0 heredadas: **este cambio no las reinterpreta**, sólo impide
  que sigan apareciendo. Distinguirlas es trabajo de la Fase 4.

## 6. Lo que sigue

- **Fase 4 — censo completo de discos por S9.** Daniel declara **411**; la DB tiene **391**. El
  contador del header de S9 es la autoridad. Ahí se responde la pregunta que esta fase habilita:
  de los 23 Nivel 0 vigentes, **cuántos eran genuinos**.
- **Fase 2C** — OCR del panel (~1,6 s en vivo), y después el censo de QA de los engines.
