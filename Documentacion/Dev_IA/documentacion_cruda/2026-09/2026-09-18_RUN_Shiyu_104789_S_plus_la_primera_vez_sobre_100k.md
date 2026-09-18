# RUN — Shiyu Defense: 104 789, S+, la primera vez sobre 100k

**Fecha:** 2026-09-18 · **Ciclo:** Nodo Crítico, Quinto Frente (fase 3.2.1 según Prydwen; resetea el 2026-09-18)
**Evidencia:** captura del resumen de temporada enviada por Daniel en sesión de Claude Code.
**No se escribió nada en la DB** — ver §5.

## 1. Resultado (leído de pantalla)

| | valor |
|---|---|
| Mejor puntuación de la temporada | **104 789** |
| Puesto | **23 %** |
| Mejor rango | **S+** |
| Objetivos | 4/4 (S+ · S · A · B en todas las salas) |
| Anterior registrado | 94 809 (top 31,35 %) → **+9 980** |

El objetivo S+ en pantalla dice: *S en todas las salas y puntuación total de 100 000*. Con tope de 50 000
por sala y S en 25 000 (Game8), el S+ exige ~33 300 de promedio por sala.

## 2. Por sala (leído de pantalla)

| sala | puntuación | rango | atributos recomendados | resistencia del enemigo poderoso | equipo |
|---|---|---|---|---|---|
| 1 — Tepes | **36 518** | S | Glacial · Etéreo | — | ⚠️ por confirmar |
| 2 — Airspace Sentinel | **33 293** | S | Glacial · Aéreo | Etéreo | ⚠️ por confirmar |
| 3 — Lockspring | **34 978** | S | Eléctrico · Físico | Etéreo | ⚠️ por confirmar |

Los equipos quedan sin cargar: las miniaturas no alcanzan para identificar a los 9 PJs con certeza (RNF-02).
**La sala 2 es la más baja** y es donde está el margen: el mejor equipo accesible del roster ahí
(Remielle / Burnice / Velina) promedia 38 528 en Prydwen.

### Discrepancia pantalla vs fuentes (manda la pantalla)

Sala 2: la pantalla muestra resistencia **sólo a Etéreo**. Akademiya lista al Airspace Sentinel resistente a
**Éter y Físico**; Game8 dice Éter. Si mañana se modela `enemy_resistances` desde la wiki, este es el caso
que lo refuta.

## 3. El ciclo (fuentes externas, NO verificado contra pantalla)

**Buffs de combate** (Game8):

- **Sala 1:** daño Éter y Hielo +35 %, Daño CRÍT +25 %. Si un agente de Ataque golpea a un enemigo
  aturdido, DEF enemiga −25 % por 5 s.
- **Sala 2:** con 2/3 agentes de Anomalía, daño de Anomalía de Atributo +10 %/+60 % y el escuadrón arranca
  con 500/1 500 decibelios.
- **Sala 3:** DEF de agentes +15 %, se ignora 20 % de RES Eléctrica. Tras EX Especial: CRÍT +5 % y
  Daño CRÍT +20 % por 15 s.

**Oleadas y debilidades** (Game8):

| sala | oleadas | jefe débil a | jefe resiste |
|---|---|---|---|
| 1 | Greedy Ranger ×3 (Fuego) → Ionized Pugnus (Físico/Hielo) + Vicious Striker ×2 (Fuego) → Tepes | Hielo, Éter | — |
| 2 | Miasmic Frenzied Maniac + Miasmic Trinox (débiles a Éter, resisten Físico) → Airspace Sentinel | Hielo, Viento | Éter (+ Físico según Akademiya) |
| 3 | Lightfoot Rover MK II (Eléctrico; resiste Fuego) + Miasmic Shieldguard ×2 + Cannoneer ×2 → Lockspring | Físico, Eléctrico | Éter |

**Stats de referencia de los jefes** (Akademiya, **nivel 70** — en Nodo Crítico vienen escalados):

| jefe | HP | ATK | DEF | Daze |
|---|---|---|---|---|
| Airspace Sentinel | 2 299 064 | 1 442 | 953 | 15 008 |
| Tepes | 1 151 316 | 1 597 | 953 | 13 236 |
| Lockspring | 1 451 241 | 1 597 | 953 | 12 959 |

Tepes tiene una *Variation 1* con otras debilidades (Fuego/Eléctrico, resiste Hielo); la de este ciclo es la
base (coincide con el buff y con la pantalla: sin resistencias).

Mecánicas: Tepes pierde su reducción de daño si se le parry-ean los martillos (Impaired); el Sentinel expone
un núcleo que recibe daño extra; durante las ráfagas de Lockspring no salen los Assist Follow-Up.

## 4. Qué se usó en la comunidad (Prydwen, fase 3.2.1, 20 021 jugadores, M0 + todos los W-Engines)

| sala | equipo | uso | score prom. |
|---|---|---|---|
| 5-1 | Miyabi / Nangong Yu / Yuzuha | 21,27 % | 33 638 |
| 5-1 | Yixuan / Dialyn / Lucía | 11,80 % | 29 646 |
| 5-2 | Remielle / Promeia / Velina | 19,10 % | 38 897 |
| 5-2 | Remielle / Jane / Velina | 18,01 % | 33 447 |
| 5-2 | Remielle / Burnice / Velina | 8,26 % | 38 528 |
| 5-3 | Ye Shunguang / Sunna / Zhao | 24,53 % | 35 859 |
| 5-3 | Ye Shunguang / Dialyn / Sunna | 14,07 % | 36 642 |

La brecha Jane vs Burnice en 5-2 (~5 000 puntos) **no** la explica el jefe: la pantalla y Fandom dicen que no resiste Físico (corregido el mismo día). Es kit —Remielle le quita campo a Jane y el Luminize no activa su pasiva— más la oleada 1, que sí resiste Físico. Análisis completo: `app/resources/kb_endgame/shiyu/ciclo_001_2026-09-04_quinto_frente.md`.

## 5. Por qué no se escribió en `lategame_runs`

- **El esquema es anterior al rework V2 (3.0):** `estrellas` 0-3 y `frente_o_slot` 1-9 no modelan sala 1-3
  dentro del Quinto Frente, ni rango S/A/B, ni el tope de 50 000 por sala.
- `shiyu_cycles` está en 0 filas → `cycle_id` quedaría NULL.
- Equipos sin confirmar → `pj_principal_id` sería inventado (RNF-02).

Queda como insumo para RF-13 y para el análisis de enemigos (trabajo futuro, decisión de Daniel 2026-09-17). **Actualización:** los enemigos y el ciclo se cargaron el mismo día en la migración 38 (`enemies` 13-23, `shiyu_cycles` ciclo 1).

## Fuentes

- Prydwen — Shiyu Defense Analytics: https://www.prydwen.gg/zenless/shiyu-defense
- Game8 — Critical Node Guide: https://game8.co/games/Zenless-Zone-Zero/archives/460702
- Game8 — Shiyu Defense 15 Critical Node: https://game8.co/games/Zenless-Zone-Zero/archives/463095
- Akademiya — Airspace Sentinel / Tepes / Lockspring: https://zzz.akademiya.app/en/enemies/30048 ·
  https://zzz.akademiya.app/en/enemies/930166 · https://zzz.akademiya.app/en/enemies/30003
