# Armas reales de DaniBOD — datos para Claude Design

> Volcado directo de `db/danibod_zzz_v2.db` por `tools/stage_design_engines.py`. Es el dato
> con el que la pantalla de W-Engines tiene que probarse: distribuciones reales, huecos reales.

## Resumen

- **56 armas** en el inventario (40 modelos distintos): **46 equipadas**, **10 libres**. Hay copias repetidas del mismo modelo (se guardan para refinar).
- Rareza: A **44** · S **12**
- Especialidad: Ataque **16** · Anomalía **13** · Soporte **8** · sin dato **7** · Defensa **6** · Aturdimiento **3** · Ruptura **3**  ← *sin dato* = el catálogo no la tiene
- Nivel: Nv 60 **50** · Nv 0 **3** · Nv 20 **1** · Nv 30 **1** · Nv 50 **1**
- Refinamiento (el juego lo llama **P1–P5**): P5 **39** · P1 **13** · P2 **3** · P3 **1**
- Ícono: 37 de 40 modelos. **Sin ícono**: Ecos bulliciosos, Sol exuvia, Tetera esmeraldina

## Lo que la pantalla NO puede mostrar todavía

La app sigue la regla **"sólo informa"** (decisión de Daniel en las pantallas anteriores): nada
que salga de un scoring sin calibrar.

- `weapon_evaluations`: **0 filas** → no hay score de arma ni "mejor arma para X".
- `prydwen_weapon_recommendations_snapshots`: **0 filas** → no hay recomendaciones de la comunidad cargadas.
- `pj_weapon_synergy`: 294 filas (matriz de bonus por rol del RF-14). Es insumo del scoring, no un dato para mostrar crudo.
- **Nivel del PJ y sus stats están vacíos** para los 51 (se re-censan): no diseñar nada que
  dependa de "ATK del PJ con esta arma".

## Las armas del inventario

| # | arma | rareza | especialidad | ATK base | stat secundario | Nv | P | dueño | ícono |
|--:|---|:-:|---|--:|---|--:|:-:|---|---|
| 1 | Aguijón agudo | S | Anomalía | 713 | ATK% 25% | 60 | P1 | Jane | `engines/aguijon_agudo.webp` |
| 2 | Almohadillas férreas | S | Ataque | 684 | CRIT Rate 24% | 60 | P1 | LIBRE | `engines/almohadillas_ferreas.webp` |
| 3 | Coctelera incandescente | S | Anomalía | 713 | ATK% 30% | 60 | P1 | Burnice | `engines/coctelera_incandescente.webp` |
| 4 | Compilador quimérico | S | Anomalía | 684 | PEN Ratio 24% | 60 | P1 | Grace | `engines/compilador_quimerico.webp` |
| 5 | Engranaje infernal | S | Aturdimiento | 684 | CRIT Rate 24% | 60 | P2 | Dialyn | `engines/engranaje_infernal.webp` |
| 6 | Esplendor surcanimbos | S | Ataque | 743 | CRIT DMG 48% | 60 | P1 | Ye Shunguang | `engines/esplendor_surcanimbos.webp` |
| 7 | Inocencia sacrificada | S | Ataque | 713 | CRIT DMG 48% | 60 | P1 | N.º 0: Anby | `engines/inocencia_sacrificada.webp` |
| 8 | Petrazufre | S | Ataque | 684 | Energy Regen 60% | 60 | P1 | Sporos | `engines/petrazufre.webp` |
| 9 | Sol exuvia | S | Ataque | 713 | ATK% 30% | 60 | P1 | Pyrois | **falta** |
| 10 | Templo a la granizada estelífera | S | Anomalía | 743 | CRIT Rate 24% | 60 | P1 | Miyabi | `engines/templo_a_la_granizada_estelifera.webp` |
| 11 | Tetera esmeraldina | S | — | — | Impact | 50 | P1 | Qingyi | **falta** |
| 12 | Visitante de altamar | S | Ataque | 713 | CRIT Rate 24% | 60 | P1 | Ellen | `engines/visitante_de_altamar.webp` |
| 13 | Amo de llaves | A | Ataque | 624 | ATK% 25% | 60 | P5 | Corin | `engines/amo_de_llaves.webp` |
| 14 | Anhelo marcato | A | Ataque | 594 | CRIT Rate 20% | 60 | P5 | Orfia y Magas | `engines/anhelo_marcato.webp` |
| 15 | Caldero ardiente | A | — | 594 | ATK% 30% | 60 | P5 | Ju Fufu | `engines/caldero_ardiente.webp` |
| 16 | Caldero de la claridad | A | Ruptura | — | HP% 30% | 60 | P5 | Yixuan | `engines/caldero_de_la_claridad.webp` |
| 17 | Cañón bombástico | A | Soporte | 624 | Energy Regen 50% | 60 | P5 | Lucía | `engines/canon_bombastico.webp` |
| 18 | Cañón bombástico | A | Soporte | 624 | Energy Regen 50% | 60 | P5 | Yuzuha | `engines/canon_bombastico.webp` |
| 19 | Cañón bombástico | A | Soporte | 624 | Energy Regen 50% | 60 | P3 | Sunna | `engines/canon_bombastico.webp` |
| 20 | Cilindro neumático de Bigger | A | Defensa | 500 | DEF% | 20 | P5 | Ben | `engines/cilindro_neumatico_de_bigger.webp` |
| 21 | Cámara acorazada | A | Soporte | 594 | ATK% 25% | 60 | P5 | Nicole | `engines/camara_acorazada.webp` |
| 22 | Cámara acorazada | A | Soporte | 594 | ATK% 25% | 0 | P5 | LIBRE | `engines/camara_acorazada.webp` |
| 23 | Cámara acorazada | A | Soporte | 594 | ATK% 25% | 0 | P1 | LIBRE | `engines/camara_acorazada.webp` |
| 24 | Cúter | A | Aturdimiento | 624 | Impact 15% | 60 | P5 | Pulchra | `engines/cuter.webp` |
| 25 | Demonio cohibido | A | Soporte | — | ATK% 20% | 60 | P5 | Astra Yao | `engines/demonio_cohibido.webp` |
| 26 | Ecos bulliciosos | A | Anomalía | 594 | Anomaly Mastery 75 | 60 | P5 | Velina | **falta** |
| 27 | Estrella callejera | A | Ataque | 594 | ATK 25% | 60 | P5 | LIBRE | `engines/estrella_callejera.webp` |
| 28 | Florescencia aurífera | A | Ataque | 594 | ATK% 25% | 60 | P5 | Antón | `engines/florescencia_aurifera.webp` |
| 29 | Fósil preciado | A | Aturdimiento | 594 | Impact 15% | 60 | P5 | Nangong Yu | `engines/fosil_preciado.webp` |
| 30 | Gastrónomo selvático | A | Anomalía | 594 | Anomaly Mastery 75 | 60 | P5 | Piper | `engines/gastronomo_selvatico.webp` |
| 31 | Lapso de tiempo | A | Soporte | 594 | PEN Ratio 20% | 60 | P5 | Rina | `engines/lapso_de_tiempo.webp` |
| 32 | Llanto mielgo | A | Anomalía | 594 | ATK% 25% | 60 | P5 | Aria | `engines/llanto_mielgo.webp` |
| 33 | Llanto mielgo | A | Anomalía | 594 | ATK% 25% | 60 | P5 | Alice | `engines/llanto_mielgo.webp` |
| 34 | Llanto mielgo | A | Anomalía | 594 | ATK% 25% | 60 | P5 | Yanagi | `engines/llanto_mielgo.webp` |
| 35 | Llanto mielgo | A | Anomalía | 594 | ATK% 25% | 60 | P5 | Vivian | `engines/llanto_mielgo.webp` |
| 36 | Llanto mielgo | A | Anomalía | 594 | ATK% 25% | 60 | P5 | Remielle Dan | `engines/llanto_mielgo.webp` |
| 37 | Motor estelar | A | Ataque | 594 | ATK% 30% | 60 | P5 | N.º 11 | `engines/motor_estelar.webp` |
| 38 | Pacificador especializado | A | Defensa | 624 | ATK% 25% | 60 | P5 | Seth | `engines/pacificador_especializado.webp` |
| 39 | Primavera termal | A | Defensa | 594 | HP% 25% | 60 | P2 | Pan Yinhu | `engines/primavera_termal.webp` |
| 40 | Proyector de celuloide | A | Defensa | 594 | Impact 15% | 60 | P5 | César | `engines/proyector_de_celuloide.webp` |
| 41 | Rompecabeza ilusorio | A | Ruptura | 713 | HP% 30% | 60 | P5 | Manato | `engines/rompecabeza_ilusorio.webp` |
| 42 | Rotor de cañón | A | Ataque | 594 | ATK% 30% | 60 | P5 | Evelyn | `engines/rotor_de_canon.webp` |
| 43 | Rotor de cañón | A | Ataque | 594 | ATK% 30% | 60 | P2 | Zhu Yuan | `engines/rotor_de_canon.webp` |
| 44 | Rotor de cañón | A | Ataque | 594 | ATK% 30% | 60 | P5 | LIBRE | `engines/rotor_de_canon.webp` |
| 45 | Réplica motor estelar | A | Ataque | 624 | ATK% 25% | 60 | P5 | Billy | `engines/replica_motor_estelar.webp` |
| 46 | Taladradora giratoria - Eje rojo | A | Ataque | 624 | Energy Regen 50% | 60 | P5 | Cissia | `engines/taladradora_giratoria_eje_rojo.webp` |
| 47 | Transmorfer original | A | Defensa | 594 | HP% 25% | 0 | P1 | LIBRE | `engines/transmorfer_original.webp` |
| 48 | Transmorfer original | A | Defensa | 594 | HP% 25% | 60 | P5 | Zhao | `engines/transmorfer_original.webp` |
| 49 | Tránsito herciano | A | Ruptura | 594 | HP 25% | 60 | P5 | Billy Estelar | `engines/transito_herciano.webp` |
| 50 | Viaje estruendoso | A | Anomalía | 624 | ATK% 25% | 60 | P5 | LIBRE | `engines/viaje_estruendoso.webp` |
| 51 | Viaje estruendoso | A | Anomalía | 624 | ATK% 25% | 30 | P5 | LIBRE | `engines/viaje_estruendoso.webp` |
| 52 | Última cena | A | — | 594 | Impact 18% | 60 | P5 | Gatillo | `engines/ultima_cena.webp` |
| 53 | Última cena | A | — | 594 | Impact 18% | 60 | P5 | Koleda | `engines/ultima_cena.webp` |
| 54 | Última cena | A | — | 594 | Impact 18% | 60 | P5 | Lycaon | `engines/ultima_cena.webp` |
| 55 | Última cena | A | — | 594 | Impact 18% | 60 | P5 | LIBRE | `engines/ultima_cena.webp` |
| 56 | Última cena | A | — | 594 | Impact 18% | 60 | P5 | LIBRE | `engines/ultima_cena.webp` |

## El catálogo (`weapons`) y sus huecos

60 filas. Campos con datos:

| campo | cargado |
|---|--:|
| `nombre_en` | 56/60 |
| `rareza` | 59/60 |
| `tipo_especialidad` | 56/60 |
| `atk_base` | 50/60 |
| `stat_secundario` | 59/60 |
| `stat_secundario_valor` | 51/60 |
| `pasiva_descripcion` | 51/60 |

- Las **pasivas** están escritas a mano, mezclando español e inglés, y **no son el texto del
  juego**: sirven para leer, no para citar en pantalla como si fueran oficiales.
- **Dos filas tienen stat secundario y pasiva que no coinciden con las fuentes** (Última cena y
  Caldero ardiente): corrección pendiente. No usarlas como ejemplo de card.

### Ejemplo de pasiva (tal como está en la DB)

> **Llanto mielgo** — Cuando un miembro aplica Anomaly: AP +46 stack x4. Timer separado por stack.
