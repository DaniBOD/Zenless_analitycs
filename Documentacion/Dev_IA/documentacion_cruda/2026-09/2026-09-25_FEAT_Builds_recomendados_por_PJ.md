# FEAT · Builds recomendados por PJ y build objetivo (2026-09-25) — EN CURSO

> Fase A, etapa 1. Decisiones de Daniel en el SPEC (`2026-09-22_SPEC_Criterio_…`, casos 12-13,
> R18-R20). Brief de diseño: `Interfaz/claude_design_upload/BRIEF_build_objetivo.md`.

## El hallazgo

Revisando las 28 sugerencias firmes con los datos completos de los discos, a Daniel le alcanzaron
las dos primeras:

- **#152 → Ye Shunguang**: "no le sirve Armonía umbría en general porque el PJ no genera réplicas".
- **#163 → Nangong Yu**: "no le sirve Balada porque las 2pc son para daño crítico, ella es una
  stunner/anómala, un PJ que tiene una build peculiar".

Y la dirección: "la idea es mejorar en base a los sets que ya tiene el jugador (que sean
razonables, obvio, si no sugiere otro set acorde al PJ); si necesitás esta base de conocimiento
podés ver en wikis qué sets le sirven a cada PJ y así lo cargás en la DB".

**Medido** (desglose de `evaluar_cambio`): los dos deltas salen enteros de los substats (+6,30 y
+6,12; delta de sets 0,00). Los dos discos **rompen un 2pc** que el PJ lleva (Tecno tetraodóntido,
Jazz Caótico) y no cuesta nada, porque el 2pc sólo vale si su bono es un substat: **19 de 30 sets**
tienen un 2pc "sin modelar". `agents.set_4p_id/set_2p_id` están en NULL en los 52 (build observada;
nadie la reconstruye desde el rebuild del 2026-08-17): el set sólo entraba por rol
(`disc_set_archetype`). Y Nangong es STUN, cuyo perfil tiene la Prob. Crítica como peso mayor (1,13).

**Hallazgo aparte:** en 3 slots dos firmes se pisan (Piper s3, Nangong Yu s6, Dialyn s2):
`resolver_conflictos` no reserva el slot del ORIGEN que ocupa el disco que repone. Pendiente, con
test propio.

## La base de conocimiento (captura de Prydwen)

- Prydwen responde **403** a un cliente HTTP (WebFetch); la guía se leyó con el navegador
  integrado. La pestaña "Build" se activa por click; el extractor espera la pestaña, la clickea y
  espera "BEST DISK DRIVES STATS". Una línea por guía, **sin la prosa de las notas** (líneas > 90
  caracteres fuera): `audit/prydwen/2026-09-25_captura_prydwen.jsonl`.
- Los **52** PJs tienen guía. Sporos = Seed (alias ya existente en `asset_resolver`).
- Formas raras que el parser cubre con test: dos 4pc con el mismo puesto (Nangong, Yanagi); dos
  builds de stats sin rótulo (César); builds con rótulo (Sunna, Astra, Yuzuha, Pulchra); 4pc sin
  2pc (Evelyn — la guía no los da); sin substats (Ju Fufu, Zhao).
- Resultado (sobre copia): 119 opciones de 4pc, 461 de 2pc, 549 filas de stats; 0 rótulos sin
  reconocer, 0 sets sin cruce.

**Confirma los dos casos:** la guía de Ye Shunguang no nombra Shadow Harmony; la de Nangong Yu no
tiene un solo crítico (substats: Anomaly Proficiency > ATK% > PEN > ATK).

**Builds equipados contra la guía** (R19): 35 razonables; 4pc fuera de la guía: Gatillo y Grace
(alta), Rina, Billy, Corin, Evelyn; 2pc fuera: Burnice, Nicole; sin 2pc: Anby, N.º 11; sin 4pc
completo: Antón, Ben, Manato, Nekomata, Piper, Seth, Soukaku.

## Hecho

| paso | qué |
|---|---|
| mig 43 | `pj_sets_4pc`, `pj_sets_2pc`, `pj_stats_recomendados` (INVESTIGACION), `ajustes_usuario_build` (DECLARADO). 7 tests, 6 sabotajes en rojo |
| cargador | `app/scripts/cargar_builds_prydwen.py`: parser de la captura + carga RNF-01 que reemplaza lo de fuente 'prydwen'. 34 tests, 8 sabotajes en rojo |
| carga real | 52 PJs, 119 / 461 / 549 filas; `audit/carga_builds_prydwen_20260925.md` |
| editor | `BuildObjetivoRepo` + `app/core/build_objetivo.EditorBuildObjetivo` (RNF-01, un backup por sesión, el mismo camino que usará la ficha). 6 tests, 6 sabotajes en rojo |
| declarados | **Gatillo** 4pc Armonía umbría + 2pc Tecno Pícido; **Grace** 4pc Blues Libre + 2pc Jazz Caótico. Daniel: "son builds mías que veo óptimas, dejalo como builds creadas por el usuario". `audit/builds_declarados_20260925.md` |

## El motor (R18-R20), en tres cambios

Daniel aceptó la escala de pesos ("esos pesos también deben ser ajustables por el usuario") y pidió
un **asesor**: si el usuario pone algo que no le sirve al PJ (ej. DEF% como prioridad en Ellen), se
respeta, pero el sistema avisa "esto no te beneficia, te recomiendo Daño y Prob. Crítica". Grace y
Gatillo, con sus builds propias, tienen que salir coherentes (Blues Libre/Jazz Caótico dan
Competencia de Anomalía, el n.º 1 de Grace; Tecno Pícido da Prob. Crítica, el n.º 1 de Gatillo).

| cambio | commit | efecto medido (copia, contra 20260925_000654) |
|---|---|---|
| (a) pesos de la guía por PJ; el rol no penaliza lo que la guía valora | `ca480cf` | 168 → 154; **#163 → Nangong Yu desaparece** |
| (b) principales 4-6 de la guía, con los ajustes de Daniel al rol encima (lo agregado se suma, lo quitado se resta) | `326e3ff` | 154 → 155, 16 cambian de destino |
| (c) build objetivo: R19 en `AgentRepo`, R20 en `scoring.set_valido`, no desarmar un set objetivo activo | `7f0fedf` + fix | 155 → 88; **#152 → Ye Shunguang desaparece**; mover 96 → 16, equipar 58 → 32, reserva 0 → 22, descartar 4 → 16 |

Origen del objetivo: 39 equipado, 2 declarado, 4 guía (4pc fuera de la guía), 7 guía (sin 4pc).
R20 decide a quién se le SUGIERE; guardar/descartar sigue por rol (un disco excelente de un set que
nadie usa hoy se guarda).

**Conflicto a resolver con Daniel:** el caso 11 (#369, Floración Hielo slot 5, Nv 0: "no está bien el
descarte") volvió a **descartar**: Floración no está en el build objetivo de Lycaon ni de Soukaku.

## Lo que encontraron las verificaciones

- **Un test se rompió con un commit de DATOS.** `test_sugerir_movimientos` elegía "el primer PJ de
  Ataque" de la copia de la DB (N.º 11) y esperaba que el libre bueno fuera a él; con las
  prioridades de Daniel (commit `25934f1`, pusheado sin suite por ser "sólo datos") se lo lleva un
  PJ de alta. Un commit que cambia la DB de dominio cambia lo que ven los tests que la copian:
  **la suite corre también antes de pushear datos.** Arreglo: el fixture borra las prioridades en
  su copia (la prioridad tiene sus tests propios).

- **37 rojos de la suite tras (c)**, dos causas: `AgentRepo` leía `disc_archetypes.mains_*` sin
  guarda (las DB mínimas de los tests no las traen), y el optimizador de builds filtraba con
  `set_valido` y, sin discos del set objetivo para un slot, armaba builds de 5. Guarda con
  `_tiene_columnas`; R20 queda sólo en el recomendador (el optimizador ya prioriza el objetivo por el
  bono de set).
- Un sabotaje salió **verde** (el slot vacío del origen): el test sacaba un disco con valor, y
  dejar el slot vacío ya perdía por sí solo. Test nuevo con un disco que RESTA.

## Abierto

- El asesor de coherencia (sets y pesos declarados contra la guía) y el editor de pesos en la ficha.
- Caso 11 contra R20.
- UI: selector del build objetivo (brief entregado).
