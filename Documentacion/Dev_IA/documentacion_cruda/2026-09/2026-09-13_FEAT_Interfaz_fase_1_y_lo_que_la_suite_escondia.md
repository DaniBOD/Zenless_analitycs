# Interfaz fase 1 en main — y lo que la suite escondía

**2026-09-12 / 13** · commits `9102575` → `2c7bfe4` en main. Diseño en
[`2026-09-12_PLAN_Interfaz_la_pantalla_en_vivo.md`](2026-09-12_PLAN_Interfaz_la_pantalla_en_vivo.md).

La interfaz es el tramo 5 de la [hoja de ruta](2026-09-05_PLAN_Hoja_de_ruta_uso_diario.md). La fase
1 era portar el **shell de la ventana** y la **pantalla en vivo** de los mockups de Claude Design, que
existían desde mayo sin portar. Quedó hecha y probada en vivo por Daniel. Por el camino aparecieron
seis problemas que **no eran de interfaz**, y varios llevaban tiempo ahí.

## 1 · Qué quedó

| pieza | estado |
|---|---|
| Shell: barra de título propia, sidebar con contadores reales, barra inferior | ✅ en main, probado en vivo |
| Frameless con el marco nativo de Windows (snap, resize y sombra de Windows) | ✅ arrastre OK; maximizado arreglado y **confirmado por Daniel** al reabrir |
| Vista en vivo: el último ítem leído (disco con dueño → hexágono; sin dueño → disco solo; arma) | ✅ en vivo: lecturas de S17 sin errores |
| Consola de reconocimiento (tope de 1000 bloques, log escapado) | ✅ |
| Las otras 8 vistas, mudadas a `app/ui/views/` sin rediseñar | ✅ |
| `main.py` 1100 → 550 líneas, una sola paleta (`tokens.py`) | ✅ |

Decisiones de Daniel que acotaron la fase: **sólo informa** (sin botones de acción), **sin scoring
ni alternativas** (no están calibrados), **sin FPS ni latencia**, y el espacio de la derecha **en
blanco** hasta decidir qué va.

Suite completa sobre el árbol integrado: **2832 passed, 0 failed, 0 skipped** (antes: 2736 y 17
skipped — ver §2.1).

## 2 · Lo que apareció y no era de interfaz

### 2.1 · La suite escondía tests y crasheaba en silencio

Cada archivo de test armaba su propia app de Qt en un fixture, y en un proceso **la primera que se
crea decide el tipo para todos**. Los del controller (van antes en orden alfabético) creaban una
`QCoreApplication` sin GUI. En la suite completa:

- **Los tests de widgets de los toasts y del diálogo del roster se salteaban** ("ya existe una
  QCoreApplication"). Eran parte de los "17 skipped" de una suite que se reportaba verde.
- **Los tests del shell nuevo no se salteaban**: creaban un widget sin `QApplication`, Qt abortaba el
  proceso y pytest moría al 90 % **sin resumen y con código 127**. Sueltos pasaban.

Se diagnosticó primero, mal, como el timeout de la tarea en segundo plano. Se ubicó contando los
tests terminados en el log contra el orden de recolección: murió en el primer test de
`test_shell_sidebar.py` que crea un widget. Reproducido con dos archivos.

Arreglo de raíz, una autoridad: `pytest_configure` crea **una** `QApplication` antes de importar
cualquier test (`94e9702`). Los toasts ahora corren, y **no había ningún rojo escondido**.

### 2.2 · El `.exe` arrancaba con el matcher de sets vacío

`asset_resolver` buscaba las imágenes en `Documentacion/Interfaz/` con un `parents[2]` que se escapa
de `app/` (D1). `main.spec` enumeraba dos de esas carpetas, pero **no** `Set-Discos_Package_Logo`,
de donde `SetBadgeMatcher` carga sus referencias: **en el `.exe` la predicción de set por badge
arrancaba con 0 referencias, en silencio**. Tercera repetición del patrón que el propio spec
documenta.

Se mudaron las 5 carpetas (377 archivos, ~11,7 MB) a `app/resources/ui_assets/`, que el spec copia
entera (`1b592d3`). El test que lo cuida se escribió **antes** de mover y falló nombrando la carpeta
solo: *o está dentro de `app/`, o el spec lo nombra*.

### 2.3 · El disco con dueño nunca llegaba a la UI

`_on_disc_from_monitor` hacía `return` temprano para S17/S9: persistía, logueaba y cortaba. El caso
central de la pantalla en vivo **nunca emitió una señal**. Se agregó `disc_observed`, observacional:
sin score, y con la tenencia en cuatro valores que no se colapsan (`equipada` / `libre` /
`incierto` / `sin_leer`) (`017f994`).

### 2.4 · Maximizada, la ventana perdía 8 px por lado

Franja blanca arriba, escritorio a los costados y la barra inferior cortada. **Se midió antes de
tocar**: Windows decía `IsZoomed = False` y cliente (8,8) 2544×1376; Qt dibujaba 2560×1392 en (0,0).
El recorte de `WM_NCCALCSIZE` se condicionaba al estado de **Qt**, y el botón □ no maximiza con
Windows: ajusta la ventana al área de trabajo. Arreglo: recortar sólo si `IsZoomed` (`d15c6b2`).
Con la condición vieja fallaban **los dos** caminos, también el maximizado nativo. Verificador
manual: `tools/verificar_ventana_maximizada.py` (no se puede testear offscreen).

### 2.5 · La verdad de tierra del contador de armas, vieja por segunda vez

Las capturas del caso Billy leen `[56/2000]` (verificado mirando el recorte) y el test esperaba
{57, 54, 75} (`9102575`). **Pasó lo mismo que el día anterior**: llegaron capturas nuevas y la suite
completa no corrió hasta la sesión siguiente.

### 2.6 · La sesión paralela del optimizador

Se lanzó para arreglar que el optimizador medía el build actual contra `agent_discs`, vacía. Hizo
eso y **bastante más**: el arreglo de los swaps con neto ≤ 0 y la **migración `_32`**, que corrige
`disc_archetypes` (ANOMALY slot 6 = Tasa de Anomalía, Viento en slot 5) y cambia el scoring (+1.0 en
9 PJs de anomalía). Todo documentado en sus propios docs del 2026-09-12 y ya en main.

Se revisó antes de integrar: el volcado de la DB de main contra la anterior difiere **sólo en
`disc_archetypes`**, `integrity_check` ok, inventario intacto (385 / 56 / 51). Dos notas:

- Su "suite verde" daba **482 skipped**: en un worktree no están las capturas del juego (son locales).
  La verificación real de sus cambios fue la suite integrada de acá, que sí las tiene.
- Refutó una afirmación mía: el optimizador **no** corre al equipar (ver §3).

## 3 · Errores míos, para no repetirlos

- **Borré `AgentDiscRepo` diciendo "nadie lo usa"**: el grep se inundó con `app/build/` (el bundle de
  PyInstaller) y el `head` cortó justo la línea del optimizador. Se restauró desde `HEAD` antes de
  commitear. Es A5 al pie de la letra.
- **Dije que el optimizador corría cada vez que se equipa**, deducido de un resultado de grep sin
  seguir quién llama a quién. Lo refutó la otra sesión, con 0 filas en `optimizer_pending_actions` y
  0 líneas en el log. El bug era real pero latente.
- **Un test del `try` alrededor de la señal era débil**: sin el `try` pasaba igual. Lo destapó
  romperlo a propósito; lo que el `try` protege es el `return` que el censo usa como identidad.
- **En la vista en vivo escribí el código antes que los tests.** Se compensó saboteando las cuatro
  garantías centrales (orden de slots, drop sin PJ del scoring, escape, tenencias): los cuatro tests
  las cazaron.
- **Llamé "timeout" a un crash** (§2.1). El código 127 y el corte en el mismo porcentaje dos veces
  eran la pista.

## 4 · Datos pendientes

**Seis armas del inventario no tienen ícono y sí tienen el archivo**: les falta `nombre_en` en
`weapons`. `Última cena`, `Inocencia sacrificada`, `Caldero ardiente`, `Ecos bulliciosos`, `Sol
exuvia`, `Tetera esmeraldina`. Cobertura hoy: 34 de 40. Completarlos es una migración chica, con
fuente verificada (RNF-02).

> **Corrección (mismo día, mig `_33`):** el diagnóstico de arriba era impreciso. Sólo a **4** les
> faltaba `nombre_en`; Sol exuvia y Ecos bulliciosos ya lo tenían y lo que falta es el **archivo**.
> La `_33` completó Última cena → Steam Oven, Caldero ardiente → The Simmering Pot y Tetera
> esmeraldina → Ice-Jade Teapot (esta última tampoco tiene archivo). **Cobertura: 36 de 40.**
> Inocencia sacrificada quedó fuera: su nombre en inglés (Severed Innocence) ya lo tiene la fila 22
> "Serenidad cortada", del catálogo inicial y sin copias — **dos filas de catálogo para la misma
> arma**, unificarlas es decisión aparte. Y apareció otro hallazgo sin corregir: las filas 5 y 13
> tienen stat secundario y pasiva que no coinciden con las fuentes.
>
> **Mig `_34` (mismo día, decisión de Daniel):** unificadas. Sobrevive la fila 22 (tenía los datos)
> con el nombre de pantalla *Inocencia sacrificada*; la 62 se borró tras re-apuntar la única copia
> (Anby). `weapons` 61 → 60. **Cobertura: 37 de 40.**

## Queda abierto

1. ~~Daniel confirma el maximizado al reabrir la app~~ — confirmado el 2026-09-13.
2. **La región derecha de la vista en vivo**: decidido por Daniel el 2026-09-13 — va el scoring como
   en los mockups, **cuando se implemente el scoring**. Hasta entonces, en blanco.
3. **El scoring**: depende del tramo 4 (sembrar thresholds). Hasta entonces la vista no lo muestra.
4. **Las otras pantallas del mockup** (discos, modal de disco, modal de PJ, toasts): fases siguientes.
5. De §4: los archivos de ícono de Sol Exuvia, Boisterous Echoes e Ice-Jade Teapot; ~~la fila
   duplicada 22/62~~ (unificada, mig `_34`); las pasivas de las filas 5 y 13. Y la familia `W-Engine_29_*` de íconos sin mapear a nombres en español.
6. De la sesión del optimizador: la tabla `agent_discs` sigue en el esquema, y "el saqueo" (222 discos
   ajenos con neto > 0 entran a las builds) quedó diferido como opción C.
7. Dos worktrees viejos de agosto (`admiring-khorana`, `focused-cartwright`) con cambios sin commitear
   cuyo trabajo **ya llegó a main** (`8a3cbdd`): se pueden limpiar.
