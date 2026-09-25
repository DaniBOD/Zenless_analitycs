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

## Lo que encontraron las verificaciones

- **Un test se rompió con un commit de DATOS.** `test_sugerir_movimientos` elegía "el primer PJ de
  Ataque" de la copia de la DB (N.º 11) y esperaba que el libre bueno fuera a él; con las
  prioridades de Daniel (commit `25934f1`, pusheado sin suite por ser "sólo datos") se lo lleva un
  PJ de alta. Un commit que cambia la DB de dominio cambia lo que ven los tests que la copian:
  **la suite corre también antes de pushear datos.** Arreglo: el fixture borra las prioridades en
  su copia (la prioridad tiene sus tests propios).

## Abierto

- Pasar de niveles a pesos (propuesta: 1,0 / 0,8 / 0,6 / 0,4; lo no nombrado = 0) — decide Daniel.
- Motor: R18-R20 + principales por PJ.
- UI: selector del build objetivo (brief entregado).
