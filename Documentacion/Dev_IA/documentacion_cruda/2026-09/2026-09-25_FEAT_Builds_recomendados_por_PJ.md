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

## Tercera revisión: movimientos y stats fijos

Daniel ("va mucho mejor ahora"): los sets pesan más que el caso 11; aplicó en el juego #85 → Dialyn
y #188 → Ju Fufu y pidió registrarlos con trazabilidad; y rechazó #151 → Gatillo: su pasiva
convierte Prob. Crítica en aturdimiento hasta 90 %, y el disco se la bajaba 7,2 puntos. De ahí,
"stats fijos" (Astra Yao ATK, Zhao PV): relevados los kits de los 52 en Prydwen con la pasiva núcleo
en Lv. 7 (el deslizador de la guía se mueve por teclado desde el navegador), y las cuentas hechas a
mano.

| paso | commit | qué |
|---|---|---|
| señal única | `3ddcbd9` | `agentes_cambiaron()`: el editor del build objetivo no avisaba a los `AgentRepo` (el motor seguía con el build viejo hasta reiniciar) |
| mig 44 | `7e6a47f` | `movimientos_discos` + `EditorMovimientos` (tanda entera o nada, el desplazado queda libre); los dos swaps de Daniel registrados |
| mig 45 + R21 | ver git | `pj_stats_fijos` (16 de kit + 8 de Monarca del Pináculo) y `app/core/stats_fijos`: un cambio no deja a un PJ por debajo de su fijo |

**La cuenta sin la base.** S18 da el total de cada stat. Las líneas que suman directo (Prob.
Crítica, Tasa de Perforación, Competencia de Anomalía) son exactas; para las que son un % de la base
(ATK%, PV%, Impacto, Maestría, Recarga) se usa una cota SUPERIOR de la base, `(total − plano de los
discos) / (1 + % de los discos)`: los bonos invisibles (arma, pasivas, sets) sólo pueden achicarla,
así que la pérdida se sobreestima. El motor puede frenar de más, nunca dejar a un PJ abajo.

Hoy por debajo de su fijo: Astra Yao (3.419 / 3.429), Rina (66,4 / 72), Velina (2,16 / 2,88),
Gatillo (75,4 / 90), Miyabi (51,4 / 80), Dialyn (89,8 / 100), Seth, Soukaku, Remielle, Ju Fufu,
Qingyi (Impacto 193 / 220), Anby (43,4 / 50, Monarca). Los de Dialyn, Anby, Ju Fufu y Astra son de
antes de los swaps: hace falta repasarlos por S18.

## Cuarta revisión: los descartes

Daniel confirmó las pasivas en Lv. 7 y pidió que ése sea siempre el objetivo. Sobre los 16
descartes del reporte `20260925_124403_372452`:

| paso | commit | qué |
|---|---|---|
| mejora mínima | `0ebd129` | `MEJORA_MINIMA = 0,1`: #93 → Ju Fufu (+0,00) sale; ahora va a Pulchra (+3,70), que perdía contra el +0,00 por la prioridad |
| guardar sin subir | `097ba56` | recomendación `guardar`: sin terminar, sano, no le gana a nadie, lo esperable alcanza la reserva de su rol |
| R22 | `c65b5a5` | el único de su tipo (set, slot, principal) que le sirve a alguien se conserva |

Descartar 16 → 5: #406, #308 y #182 tienen un gemelo equipado; #368 (Bono Daño Físico en Floración)
y #407 (PV% en Tecno tetraodóntido) son únicos pero su set no le sirve a nadie con ese principal.

## Lo que encontraron las verificaciones

- **El repaso de S18 escribió la ficha de Anby en N.º 0: Anby.** El OCR leyó "pV" (el banner del
  rol no se cortaba y tomó la etiqueta "Ataque") y la "n" y el "0" sueltos hacían que N.º 0
  dominara a Anby; cada causa sola alcanzaba. Se detectó comparando la DB con el backup del
  arranque tabla por tabla, se restauró N.º 0 y se reprodujo sobre el frame en sólo lectura antes
  de arreglar (`37f1b66`, `6018d1e`; línea de base de 28 frames: único cambio, Anby). Registro:
  `audit/stats_s18_post_swaps_20260925.md`.
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
- "Guardar sin subir" exige un rol que tenga el disco SANO: el primer test de esa guarda salía
  **verde** con la guarda apagada (las líneas muertas ya lo dejaban bajo el umbral). Aislado como
  R13: muertas que pesan 0 y un umbral de reserva que lo esperable alcanza.
- Un sabotaje salió **verde** (el slot vacío del origen): el test sacaba un disco con valor, y
  dejar el slot vacío ya perdía por sí solo. Test nuevo con un disco que RESTA.

## Abierto

- El asesor de coherencia (sets y pesos declarados contra la guía) y el editor de pesos en la ficha.
- R22 en vivo: el toast no tiene el inventario (sin `builds` ni `libres`) y no juzga la unicidad.
  Llega con el paso 8.
- Burnice (RE 1,8 → 2,8): el texto viene con un "6" delante, puede ser su M6.
- UI: selector del build objetivo (brief entregado).
