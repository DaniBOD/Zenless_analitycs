# SPEC · El editor de la ficha del PJ: sets y stats que se vuelven pesos (2026-09-27)

**Estado:** diseño aprobado por partes con Daniel el 2026-09-27; falta su revisión de este documento.
Sigue a [FEAT Builds recomendados por PJ](2026-09-25_FEAT_Builds_recomendados_por_PJ.md) (R18-R22) y
retoma dos pendientes: el asesor de coherencia y el editor de pesos en la ficha.

## Qué pidió Daniel

> "Vamos con el editor de pesos y stats. Ojo: el usuario no es que toque el motor, sino que al
> seleccionar un set y los stats deseados influyen en los pesos de forma interna."

> "Primero quiero que se tome como prioridad el set que se elige."

Y, de antes (2026-09-25): *"si el usuario ajusta una substat de Ellen a DEF% como prioritario lo
puede hacer, pero que el sistema le diga 'Oye, esto no te beneficia en nada, te recomiendo Daño y
Probabilidad crítica'"*; y que sus builds propias de Grace y Gatillo "tengan sentido".

## Decisiones (sus respuestas)

| pregunta | decisión |
|---|---|
| qué elige el usuario | **sets (4pc + 2pc), principales de los slots 4-6, prioridad de substats y stats fijos** |
| cómo expresa los substats | **niveles**: Imprescindible / Muy bueno / Bueno / Sirve / No sirve; varios comparten nivel, como en la guía |
| qué hace el set con los pesos | **bonos + condiciones**: el 2pc vale como su stat (como hoy) y las condiciones de stat del 4pc se vuelven stats fijos. Los niveles los elige el usuario; si no encajan con el set, el sistema avisa |
| cómo se guarda | **niveles, no números** (enfoque A): el peso numérico no existe en ningún lado que el usuario toque |
| la pantalla | **motor ya, pantalla con brief**: datos, motor, avisos y editor probados por código; un brief único a Claude Design; la pantalla cuando vuelva el mockup |
| prioridad del set | **el set primero**. Además: mientras el PJ está por DEBAJO de un fijo, ese stat **sube a Imprescindible** hasta cumplirlo |
| esa subida, ¿sólo para el set? | **set y kit**: vale para todos los stats fijos (condiciones del 4pc y pasivas) |
| ¿un fijo por encima del set? | **"No, al menos que si lo pones por encima del set predefinido que al menos sea un set secundario (set de 2pc)"** → R24: un fijo puede romper el 2pc, **nunca el 4pc** |
| ¿cuándo se rompe el 2pc? | **sólo si el cambio lo ALCANZA** (y supera la mejora mínima); acercarse no alcanza |
| ¿y qué queda en su lugar? | **"si cumple el set 2pc obvio debe cumplir la stat fijada y el set 2pc que esté en segunda recomendación de la lista"** → se **arma el 2pc alternativo** de la guía, con una sugerencia de **a dos discos** |
| ¿sólo el segundo de la lista? | **el siguiente disponible**: el renglón 2; si ningún par cumple, el 3, y así. Nunca un 2pc fuera de la lista |

## El orden en que decide el motor (de más fuerte a más débil)

| # | qué | cómo actúa |
|---|---|---|
| 1 | **4pc del set elegido** | filtro: nunca se rompe un 4pc activo del objetivo; un disco de otro set no se le sugiere (R20) |
| 2 | **stats fijos** (condiciones del 4pc + kit + usuario) | veto: ningún cambio lo deja por debajo (R21). **Nuevo (R23):** mientras esté por debajo, sus líneas pesan como Imprescindible. **Nuevo (R24):** para ALCANZARLO se puede romper el 2pc |
| 3 | **2pc del set elegido** | filtro como el 4pc (R20), salvo R24: se puede cambiar por el siguiente 2pc de la guía, de a dos discos |
| 4 | principal válido del slot | filtro (R9) |
| 5 | niveles de substats → pesos | puntaje entre los discos que pasaron los filtros |
| 6 | bono del set en el puntaje | el 2pc como su stat; el 4pc completo, una fracción del mejor disco posible |
| 7 | prioridad del PJ | quién recibe primero |

Consecuencias: una condición del set que choca con los niveles del usuario **gana el set** (el fijo
se aplica igual, con aviso); un disco "mejor" en substats pero de otro set nunca le gana a uno del set
elegido, salvo que sea la única forma de cumplir un fijo y sólo a costa del 2pc.

**Hoy (medido en el código, 2026-09-27) el caso NO está cubierto:** `set_valido` deja afuera todo
disco de un set que no sea el 4pc o el 2pc objetivo, y `rompe_objetivo` descarta cualquier cambio que
baje el 4pc **o el 2pc** de su cuenta. Un fijo nunca puede ganarle al 2pc.

## Parte 1 · Los datos (migración 46)

Principio de la migración 40: **la guía es el default y no se toca; el ajuste del usuario gana; si se
borra el ajuste, vuelve la guía.**

| tabla | qué | reglas |
|---|---|---|
| `ajustes_usuario_substats` | agente · substat · nivel | nivel 0-4 (0 = no sirve); una fila por substat, el usuario puede tocar uno solo |
| `ajustes_usuario_principales` | agente · slot · lista de principales | slot 4-6; reemplaza a la guía **para ese slot** |
| `ajustes_usuario_fijos` | agente · stat · objetivo | objetivo `NULL` = desactivé el fijo de la guía; stat en el vocabulario de `agents` (el CHECK de `pj_stats_fijos`) |
| `set_condiciones_4pc` | set · tipo (`stat` / `rol` / `elemento`) · stat + umbral, o rol, o elemento · texto · fuente · url | una fila por condición, verificada contra Prydwen/Fandom antes de cargarla (RNF-02) |
| `ajustes_usuario_build` | (ya existe, mig 43) | sin cambios |

- `ajustes_usuario_pesos` (mig 40) está **vacía** (0 filas, medido 2026-09-27): se retira en la misma
  migración; el repositorio deja de leerla.
- **Una sola autoridad (B1):** la condición de Monarca del Pináculo hoy está COPIADA en `pj_stats_fijos`
  (8 filas con `requiere_set_4p_id = 34`). Pasa a `set_condiciones_4pc` una vez, y las 8 filas se
  borran en la misma transacción.
- Candidatas leídas de `disc_sets.bonus_4p_desc` (a verificar, no a copiar):
  - de stat: Monarca del Pináculo (Prob. Crítica ≥ 50 %), Balada de la rama y la espada ("Anomaly
    Mastery ≥ 115" → hay que confirmar si es Tasa o Maestría en el vocabulario de la DB), Rosa espinosa
    (DEF inicial ≥ 1.000 / 1.800: dos escalones → el fijo es el que da el efecto completo);
  - de rol/elemento: Monarca (Aturdimiento), Nana a la luz cenicienta (Soporte), Conejo en el país de
    las maravillas (Defensa), Floración del alba (Ataque, para su segunda parte), Firmamento llameante
    (Éter), Balada de aguas blancas (Ataque, para una parte), Hado emplumado (Lumen, para una parte).
  - Una condición de rol/elemento que sólo afecta **una parte** del 4pc se carga igual, con el texto
    diciendo qué parte: el aviso tiene que ser honesto sobre cuánto se pierde.

## Parte 2 · Cómo lo combina el repositorio

Todo en `AgentRepo._load`; el motor lee el resultado y no sabe de dónde vino cada dato.

- **Pesos:** por substat, el nivel del usuario; si no hay, el de la guía (primera variante, como hoy);
  si la guía no lo nombra, 0. Nivel → peso con `PESO_POR_NIVEL` (1,0 / 0,8 / 0,6 / 0,4) y 0 para "no
  sirve". Sigue la regla vigente: el castigo del rol cae sólo sobre lo que vale 0.
- **Principales:** por slot, los del usuario si los eligió; si no, `mezclar_principales` como hoy.
- **Fijos:** el kit (`pj_stats_fijos`) ∪ las condiciones de stat del 4pc OBJETIVO (sólo si el PJ cumple
  el rol/elemento que pide el set) → encima, los ajustes del usuario (cambiar, agregar, desactivar). El
  mismo stat desde dos fuentes: el objetivo mayor.
- **R23 · un fijo sin cumplir se busca.** Si el stat actual del PJ (S18) está por debajo del objetivo,
  las líneas que suben ese stat pesan como mínimo 1,0. Qué líneas: el mapa de R21
  (`app/core/stats_fijos.DIRECTOS` y la parte % de `DE_BASE`) — una sola autoridad. Las líneas
  PLANAS de un stat de base (ATK, PV, DEF planos) quedan en su nivel: una mejora de ATK plano rinde
  bastante menos que una de ATK%, y subirla a 1,0 la igualaría. Sin el stat leído (S18 vacío) no se
  sube nada (B2: no se juzga sin dato). Al alcanzar el objetivo, vuelve el nivel elegido.
- **R24 · un fijo vital puede cambiar el 2pc por el siguiente de la guía, nunca el 4pc.** Es una
  sugerencia de **a dos discos** que ARMA el 2pc alternativo:
  1. sólo si el 4pc objetivo está ACTIVO (4 piezas) y hay un fijo con stat leído por debajo;
  2. los dos slots que no ocupa el 4pc son los que se reemplazan;
  3. se prueban los 2pc que la guía combina con ese 4pc (`pj_sets_2pc.grupo`) en orden, sin el 2pc
     actual: el primer renglón con algún par válido gana; dentro del renglón (puede traer dos sets
     equivalentes), el par de mayor mejora;
  4. el par sale de discos **LIBRES** del mismo set, uno por slot, con principal válido (R9). Mover
     discos de otros PJs de a pares queda fuera de alcance;
  5. el par vale si deja al PJ **cumpliendo** el fijo que le faltaba, no le baja ningún otro por
     debajo del suyo (R21) y la mejora del par supera `MEJORA_MINIMA`.

  La sugerencia lo dice: *"cambia tu 2pc de X por Y para llegar a Z"*. "Cumpliendo" se prueba con la
  cota prudente de R21, que **no cuenta** las ganancias % de un stat de base. En la práctica R24 aplica
  a los stats que suman directo (Prob. Crítica, Tasa de Perforación, Maestría de Anomalía) y a lo
  plano: para ATK% / PV% no se puede probar que se llega sin conocer la base, y no se supone (B2).
  A medir al implementarlo: cuántas sugerencias nuevas aparecen (se listan para Daniel).
- **Build objetivo:** R19, sin cambios.
- Cada guardado llama `agentes_cambiaron()`: el cambio llega al motor sin reiniciar.

## Parte 3 · El asesor de coherencia (`app/core/coherencia.py`)

Función pura: `(PJ, guía, elección del usuario) → list[Aviso]`. **Nunca bloquea**: el motor usa lo
elegido igual.

**⚠️ No te beneficia**
- substat con nivel > 0 que la guía no nombra ("DEF% no le suma nada a Ellen; la guía prioriza Daño
  Crítico y Prob. Crítica");
- substat que la guía pone en el nivel 1 y el usuario marcó "no sirve";
- principal fuera de la guía para ese slot;
- 4pc cuya condición de rol/elemento el PJ no cumple ("el 4pc de Nana sólo se activa en Soporte").

**ℹ️ Informativo**
- set fuera de la guía (los builds de Grace y Gatillo);
- condición de stat del 4pc que quedó como fijo ("Balada pide … ≥ 115: queda como fijo");
- un fijo por debajo del objetivo y que por eso se busca (R23), con cuánto falta.

**Criterio de éxito:** los builds declarados de Grace y Gatillo dan sólo informativos; Ellen con DEF%
Imprescindible da el ⚠️.

## Parte 4 · El editor, la pantalla y las pruebas

- **`app/core/ficha_pj.py`** (sin Qt), el patrón de `EditorPrioridades` / `EditorBuildObjetivo`:
  conexión propia, un backup por sesión, transacción, `foreign_key_check` + `integrity_check`,
  `agentes_cambiaron()`. Operaciones: nivel de un substat; principales de un slot; fijo (cambiar,
  agregar, desactivar); 4pc/2pc (reusa `EditorBuildObjetivo`); "volver a la guía" por dato. Y una
  **foto para pintar**: guía, elección, lo que usa el motor y los avisos. La vista sólo pinta.
- **La pantalla:** un brief único a Claude Design para la sección del modal del PJ, que reemplaza a
  `BRIEF_build_objetivo.md`. Estados con datos reales: Ellen con el ⚠️ de DEF%; Gatillo y Grace fuera
  de la guía; un PJ con Monarca y el fijo derivado del set; Anby buscando su Prob. Crítica (48,2 / 50);
  el vacío de un PJ nuevo sin guía.
- **Pruebas:** cada regla con su test y su sabotaje (nivel → peso; el ajuste pisa a la guía; borrar
  vuelve a la guía; cada aviso; R23 sube por debajo y vuelve al cumplir; sin stat leído no sube; R24 rompe el 2pc sólo si alcanza, nunca el 4pc, y no con una ganancia % no probada).
  **Invariante de la migración:** con cero ajustes, pesos, principales y fijos de los 52 PJs
  **idénticos** a antes de la mig 46 (medido antes/después), y el reporte de sugerencias igual
  **salvo lo que cambian R23 y R24**, que se mide y se reporta aparte.

## Orden de entrega (un commit por paso; suite completa antes de cada push)

1. Este SPEC.
2. Mig 46 + condiciones de set verificadas (con su registro en `audit/`).
3. La mezcla en el repositorio (niveles, principales, fijos) — invariante sin ajustes.
4. R23 — medido sobre el reporte, antes/después.
5. R24 — medido igual; cada par sugerido, listado para Daniel.
6. El asesor de coherencia.
7. El editor (`ficha_pj.py`).
8. El brief de la pantalla.

## Fuera de alcance

- Elegir la **variante** de la guía (5 PJs tienen más de una: "CRIT Build" / "Anomaly Build"): se sigue
  usando la primera. Si hace falta, es otro paso.
- Recordar avisos descartados ("no me lo muestres más").
- Rangos (`ajustes_usuario_rangos`): quedan como están.
