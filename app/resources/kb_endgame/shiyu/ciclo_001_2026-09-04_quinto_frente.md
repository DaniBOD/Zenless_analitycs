---
tipo: analisis_ciclo_shiyu
cycle_number: 1            # shiyu_cycles.cycle_number (numeración interna)
fase_prydwen: "3.2.1"
vigencia: 2026-09-04 / 2026-09-18
muestra: 20021 jugadores (Prydwen / LvlUrArti), filtro M0 en S-rank
enemigos_db: [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
resultado_daniel: {total: 104789, puesto: "23 %", rango: "S+", salas: [36518, 33293, 34978]}
fuentes:
  - https://www.prydwen.gg/zenless/shiyu-defense
  - https://huggingface.co/datasets/LvlUrArti/ShiyuDataProcessed   # 3.2.1/sd/comps + builds.json (MIT)
  - https://game8.co/games/Zenless-Zone-Zero/archives/460702
  - https://game8.co/games/Zenless-Zone-Zero/archives/463095
  - https://zenless-zone-zero.fandom.com/wiki/Tepes   # y las páginas de los otros 10 enemigos
  - https://www.prydwen.gg/zenless/characters/remielle   # Review + Teams & Synergy
  - https://www.prydwen.gg/zenless/characters/velina
  - https://www.prydwen.gg/zenless/characters/miyabi
  - https://www.prydwen.gg/zenless/characters/nangong-yu
  - https://www.prydwen.gg/zenless/characters/yixuan
  - https://www.prydwen.gg/zenless/characters/ye-shunguang
---

# Ciclo 001 — Quinto Frente (2026-09-04 → 2026-09-18)

Etiquetas: **[P]** pantalla · **[D]** dato con n · **[F]** fuente textual · **[I]** inferencia
(alta/media/baja). Ver `../README.md`. n ≈ uso % × 20 021 jugadores.

## Estructura

- [P] 3 salas. S por sala desde 25 000; tope 50 000 por sala [F Game8]. **S+ = S en las 3 y
  total ≥ 100 000.**
- [D] Peso del jefe en el HP total de su sala (nivel 70, Fandom): **53 %** (Tepes), **64 %**
  (Centinela), **66 %** (Cerrosorte). [I alta] Resolver bien al jefe decide la sala, pero la
  oleada de la sala 1 es casi la mitad del HP: ahí la oleada no se puede ignorar.

## Sala 1 — Tepes

**Condiciones**

- Buff [F Game8]: Éter y Hielo +35 %, Daño CRÍT +25 %. Si un agente de **Ataque** golpea a un
  enemigo aturdido: DEF −25 % por 5 s.
- [P] Recomienda Glacial + Etéreo. Enemigo poderoso sin resistencias.
- Tepes [F Fandom]: débil Hielo y Éter (RES −20 %). **Stun DMG Multiplier 125 %**, el más bajo
  de los tres jefes (los otros, 150 %). Reducción de daño activa hasta que sus martillos quedan
  Impaired por varias Defensive Assist.
- Oleadas: 3 Tiradores codiciosos → Pugnus ionizado + 2 Matones despiadados → Tepes. Los
  bandidos son débiles a **Fuego**; el Pugnus, a Físico y Hielo.

**Evidencia [D]**

| equipo | uso | n | prom. | M1+ |
|---|---|---|---|---|
| Miyabi / Nangong Yu / Yuzuha | 21,27 % | 4 258 | **33 638** | 37 743 |
| Yixuan / Dialyn / Lucía | 11,80 % | 2 362 | 29 646 | 36 592 |
| Yixuan / Ju Fufu / Lucía | 6,45 % | 1 291 | 28 331 | 35 216 |
| Miyabi / Vivian / Yuzuha | 3,97 % | 795 | 29 510 | 33 962 |
| Miyabi / Nangong Yu / Astra Yao | 1,15 % | 230 | 30 430 | 36 526 |
| Ye Shunguang / Dialyn / Sunna | 1,26 % | 252 | **34 897** | 41 019 |
| Ye Shunguang / Sunna / Zhao | 1,51 % | 302 | 33 569 | 40 714 |

Comparaciones controladas:

- Miyabi + Yuzuha + **Nangong** vs + Vivian: **+4 128**.
- Miyabi + Nangong + **Yuzuha** vs + Astra Yao: **+3 208**.
- Yixuan + Lucía + **Dialyn** vs + Ju Fufu: **+1 315**.

**Por qué gana Miyabi / Nangong Yu / Yuzuha**

1. [F] Miyabi vive de Desórdenes: necesita un compañero que dispare anomalías para regenerar
   Fallen Frost. Nangong Yu es aturdidora Éter con aplicación de anomalía "que rivaliza con la de
   agentes de Anomalía", además de mucho Daze, multiplicador de daño en stun y más tasa de
   acumulación para el equipo. Hace de segunda anomalía y de stunner a la vez.
2. [F] Yuzuha es "el buffer de anomalía definitivo", a la par o por encima de Astra Yao con
   Miyabi. El dato lo confirma: +3 208 sobre Astra en el mismo núcleo.
3. [I media] **Doble dip del buff.** En este equipo pegan fuerte dos atributos bonificados (Hielo
   y Éter) y los dos son debilidad de Tepes. En los equipos de Yixuan el daño bonificado sale
   casi todo de Yixuan.
4. [I baja] El stun vale menos acá (125 %). Los equipos de Yixuan concentran su daño en la
   ventana de stun (Dialyn: 3 definitivas por stun [F]), y eso podría explicar parte de su brecha.

**Hallazgo lateral** [D, n chico]: Ye Shunguang saca 34 897 en esta sala, por encima del equipo
dominante. Es de Ataque, así que activa la cláusula de DEF −25 % que ningún equipo top usa, y el
+25 % de Daño CRÍT le rinde más a un carry de crítico. Casi nadie lo lleva porque lo necesita
para la sala 3.

## Sala 2 — Centinela del espacio aéreo

**Condiciones**

- Buff [F Game8]: con **2/3 agentes de Anomalía**, daño de Anomalía de Atributo **+10 %/+60 %**
  y **500/1 500 decibelios** al entrar.
- [P] Recomienda Glacial + Aéreo. **Resistencia del enemigo poderoso: sólo Etéreo.**
- Centinela [F Fandom, coincide con [P]]: débil Hielo y Viento (−20 %), resiste Éter (+20 %),
  **Físico neutral**. **Daze 15 008**, el más alto del frente. Expone un núcleo que recibe daño
  extra y lo deja Impaired.
- Oleada 1 [F Fandom]: Bandido frenético + Trinox miasmático. **Los dos resisten Físico (+20 %)**
  y son débiles a Éter. Esquivan y atacan coordinados; si muere uno, el otro entra en Frenesí.

**Evidencia [D]** — núcleo fijo Remielle + Velina, Bangboo Ariel en todos, cambia el tercero:

| tercero | tipo | n | prom. | M1+ |
|---|---|---|---|---|
| Promeia | — | 3 824 | **38 897** | 44 387 |
| **Burnice** | Fuego, anomalía fuera de campo | 1 654 | **38 528** | **44 874** |
| Alice | Físico | 979 | 35 943 | 43 936 |
| Aria | Éter | 1 115 | 34 999 | 43 078 |
| Piper | Físico | 168 | 33 739 | 38 799 |
| **Jane** | Físico, anomalía en campo | 3 606 | **33 447** | 40 498 |
| Miyabi | Hielo | 949 | 33 351 | 39 195 |

**Burnice sobre Jane: +5 081 (+15 %).** La brecha se sostiene en M1+ (+4 376), así que no es sólo
inversión de cuenta.

El valor de Velina, en la misma lógica: Remielle + Jane + **Velina** vs + Burnice: **+6 485**.
Remielle + Alice + **Velina** vs + Jane: **+6 757**.

**Por qué Remielle / Burnice / Velina es mejor que Remielle / Jane / Velina**

1. **Tiempo en campo** [F Prydwen, Remielle]. Remielle pasa largos tramos en Phase Flow (fuera de
   campo, sin poder volver) y sus animaciones de Luminize son largas. Jane es anomalía **en
   campo**: le cuesta sostener su W-Engine con Remielle ocupando la cancha. Burnice es "de las
   pocas que no sufren el tiempo en campo de Remielle, por sus Afterburns": aplica Quemadura
   fuera de campo.
2. **La conversión rompe la pasiva de Jane** [F Prydwen, Remielle]. Remielle captura las
   anomalías de sus compañeros en *Voidflares* y las reproduce como Luminize, pero el Luminize
   no hereda el tipo de daño: un Luminize Físico no es daño de Asalto, así que **la pasiva de CRIT
   de Jane no aplica**. Con Burnice no se pierde nada equivalente.
3. **Velina potencia a Burnice** [F Prydwen, Velina]: le permite encadenar básicos potenciados
   una y otra vez (más Afterburns para Emberflow). Velina + Jane también tiene sinergia (el
   Vórtice cuenta como Asalto y puede criticar con la pasiva de Jane), pero en el trío pesa más
   la antisinergia con Remielle. Prydwen aclara que con Jane M2+ el cuadro cambia.
4. **La oleada 1 resiste Físico** [F Fandom]: Jane pega al 0,8× en la primera oleada; Burnice
   (Fuego) va neutral. [I media] Explica una parte de la brecha. **El jefe, en cambio, no
   resiste Físico** [P].
5. **Refringe multiplica la anomalía entera** [F Prydwen, Remielle], incluidos Vórtices y
   Ablooms de Velina. [I media] Un compañero que dispara muchas anomalías fuertes sin pedir campo
   (Burnice) le da a Remielle más material para Refringe y Voidflares.

**Por qué ningún equipo top deja a Velina afuera**: [F] "indispensable" para Remielle. Los equipos
de Desorden sufren con las animaciones largas de Remielle, la triple anomalía no puede usar a
Yuzuha, y Velina reduce la RES a acumulación de anomalía. Además pega Viento, que es debilidad
del jefe [F Fandom].

**Por qué Miyabi rinde mal acá** [F Prydwen, Velina]: antisinergia con Velina. El Viento tiene
mal multiplicador de Desorden y Miyabi pierde la ganancia de Fallen Frost y su reducción de RES.

## Sala 3 — Cerrosorte (Lockspring)

**Condiciones**

- Buff [F Game8]: DEF de agentes +15 %, **se ignora 20 % de RES Eléctrica**. Tras un EX: CRÍT
  +5 % y Daño CRÍT +20 % por 15 s.
- [P] Recomienda Eléctrico + Físico. Enemigo poderoso resiste Etéreo.
- Cerrosorte [F Fandom]: débil Físico y Eléctrico (−20 %), resiste Éter (+20 %). Algunos golpes
  **anulan el Assist Follow-Up** aunque el parry salga bien.
- Oleada 1: Rondador escurridizo II (débil Eléctrico, resiste Fuego) + 2 escudados + 2
  artilleros miasmáticos (débiles a Fuego y Eléctrico).

**Evidencia [D]**

| equipo | uso | n | prom. | M1+ |
|---|---|---|---|---|
| Ye Shunguang / Sunna / Zhao | 24,53 % | 4 911 | 35 859 | 42 079 |
| Ye Shunguang / Dialyn / Sunna | 14,07 % | 2 817 | **36 642** | 43 128 |
| Ye Shunguang / Dialyn / Zhao | 12,15 % | 2 433 | 31 923 | 39 019 |
| Ye Shunguang / Astra Yao / Zhao | 2,19 % | 438 | 29 880 | 36 976 |
| Cissia / Seed / Astra Yao | 3,61 % | 723 | 34 366 | 39 769 |
| Anby S0 / Orphie / Trigger | 5,39 % | 1 079 | 29 834 | 34 810 |
| Claret / Norma / Rina | 0,93 % | 186 | 37 364 | 40 262 |

Comparaciones controladas, todas sobre Ye Shunguang:

- + Dialyn + **Sunna** vs + Dialyn + Zhao: **+4 719**.
- + Zhao + **Sunna** vs + Zhao + Dialyn: **+3 936**.
- + Zhao + **Sunna** vs + Zhao + Astra Yao: **+5 979**.

**Sunna es la pieza que más mueve la sala.**

**Por qué**

1. [F Prydwen, Ye Shunguang] Ye Shunguang escala con puntos de Qingming Sword Force. Cada
   activación de **Ether Veil** le da 3, y Sunna las provee más seguido que Zhao o Dialyn (cada
   ~25 s o menos). Sunna además sube el multiplicador de stun, y como reparte sus EX mantiene
   activa la Nana a la luz cenicienta.
2. [F] Dialyn: su conversión de definitiva la mete en *Enlightened Mind*, y su +30 % de
   multiplicador de stun aplica **fuera** del stun con Ether Veil: Verdict. Zhao: activa Ether
   Veil seguido y ocupa poco campo.
3. [F Fandom] Físico es debilidad del jefe.
4. [I media] La cláusula de EX del buff premia a los soportes que spamean EX (Sunna reparte EX,
   Dialyn tiene un EX barato).
5. [I media] Los equipos Eléctricos reciben debilidad **más** el 20 % de RES ignorada, y aun así
   rinden menos (29 834 – 34 366). El kit de Ye Shunguang pesa más que la ventaja elemental.

## Reglas que el asesor debería aprender de este ciclo

| # | Regla | Confianza |
|---|---|---|
| R1 | Las cláusulas condicionales del buff definen el arquetipo de la sala ("2/3 Anomalía" ⇒ triple anomalía). | alta |
| R2 | Evidencia = comparación controlada (mismo núcleo y Bangboo) con n. Los promedios sueltos engañan. | método |
| R3 | Un carry que se va del campo por mucho tiempo (Remielle en Phase Flow) pide compañeros cuyo daño no necesite campo (Burnice). | alta |
| R4 | Las conversiones de daño rompen pasivas atadas al tipo: el Luminize no es Asalto, así que la pasiva de Jane no aplica. | alta |
| R5 | La sinergia de kit le gana a la ventaja elemental cuando chocan (sala 3: Eléctricos con RES ignorada < Ye Shunguang). | media |
| R6 | Un soporte bien elegido vale 3–6 k por sala (Sunna, Velina, Nangong, Yuzuha). | alta [D] |
| R7 | Las wikis se equivocan en resistencias: verificar contra pantalla antes de razonar sobre el jefe. | alta [P] |

## Aplicado a la cuenta de Daniel

Los equipos que usó **no están confirmados**, así que las comparaciones son condicionales. Los
gaps de build salen de `inventory_discs` / `inventory_weapons` contra `builds.json` (3.2.1):

| PJ | Lo tuyo | La comunidad | Acción |
|---|---|---|---|
| Velina | disco 4 **DEF %** | AP en 99,06 % (13 243 runs); DEF % ni figura | cambiar a Maestría de Anomalía (AP) |
| Velina | Boisterous Echoes R5 (32 744) | Weeping Gemini 33 827 · Kaboom 34 037 | tenés 4 Weeping Gemini R5 libres (Alice, Aria, Yanagi, Vivian no juegan acá) |
| Velina | ER sin medir | ER prom. **2,72** | objetivo de su pasiva |
| Burnice | disco 6 Tasa de Anomalía (26,5 %) | **Recarga de Energía 72,8 %**, ER prom. 2,43 | cambiar a ER |
| Burnice | 4p Chaos Jazz + 2p Freedom Blues (32 919) | 4p Freedom Blues + 2p Moonlight Lullaby 39 665 (n≈329) | observacional; probar |
| Miyabi | CRIT 51,4 % (abril) | CRIT prom. **73,0 %**; disco 4 dividido CD 43 % / CR 37 % | subir CRIT (disco 4 CR o substats) |
| Nangong Yu | disco 5 ATK % | Daño Éter 64 % | menor |
| Sunna | Kaboom **R3** | Kaboom 52 % (34 497) | pasarle la Kaboom R5 de Lucía, que no juega acá |
| Ye Shunguang | disco 5 Tasa de Perforación (21 %) | Daño Físico 42,6 % / ATK % 36,3 % | revisar; tu 2p Puffer Electro rinde 37 029 vs 34 247 del Branch & Blade |
| Dialyn | disco 5 Daño Físico (21,9 %) | ATK % 65,7 %; CRIT prom. 95,8 % | menor |
| Remielle | — | — | build igual a la de la comunidad; no tocar |

Tu puntaje por sala contra el promedio de su mejor equipo accesible: sala 1 **36 518** (+2 880
sobre 33 638), sala 2 **33 293** (−5 235 bajo 38 528), sala 3 **34 978** (−1 664 bajo 36 642).
**El margen está en la sala 2**, y los dos arreglos de arriba (Velina, Burnice) caen ahí.

## Correcciones respecto de lo dicho antes en la sesión del 2026-09-17/18

- La brecha Jane vs Burnice **no** es porque el jefe resista Físico: la pantalla y Fandom dicen que
  no. Es kit (puntos 1-3 de la sala 2) más la oleada 1, que sí resiste Físico.
- El disco 6 "Tasa de Anomalía" de Burnice es **Anomaly Mastery** (la tasa de acumulación), no
  Maestría/AP. Cambiarlo a ER no baja su AP. La recomendación de ER se mantiene, y ahora con
  dato: el 72,8 % lo usa.
