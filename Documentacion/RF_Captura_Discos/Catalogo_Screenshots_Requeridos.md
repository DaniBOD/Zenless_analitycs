# Catálogo de Screenshots Requeridos — RF-04 / RF-05

**Propósito:** Lista exhaustiva de capturas necesarias para calibrar ROI de OCR, validar la lógica de detección de cambios/upgrades de discos, y cerrar las dudas sobre iconos de interfaz.

**Estructura:** Cada sección corresponde a una subcarpeta en `Screenshots_Triggers/Discos_Triggers/`. Guarda cada archivo con el prefijo de la subcarpeta + descripción corta (ej. `01_farmeo_shiyu_3drops.png`).

**Formato preferido:** PNG sin compresión, resolución nativa del juego. Nombre del archivo en minúsculas con guiones bajos. Si es una comparación PRE/POST, prefijo `pre_` y `post_` con timestamp.

---

## 01 — Pantalla Resultado de Desafío (captura antelación)

**Carpeta:** `01_Pantalla_Resultado_Desafio/`

**Nombre en juego (ES):** "Patrulla de Área" (fuente principal de farmeo de discos).

**Qué se ve en la lista de drops (confirmado con el usuario):**
- Emblema del set (icono miniatura).
- Rareza (color del borde: S / A / B).
- Número de disco (slot I a VI).

**Qué NO se ve y requiere abrir detalle:**
- Main stat y su valor (slots I-III tienen main fijo, slots IV-VI son aleatorios).
- Substats y rolls.

**Implicación para el flujo:** Desde la lista ya podemos pre-registrar (set + slot + rarity) como "pendiente de completar". Si el usuario abre el detalle, completamos el registro con main + subs. Si no, queda marcado como pendiente hasta que aparezca en el inventario más tarde.

**Convención de main stats por slot (para el optimizador):**
| Slot | Main stat |
|------|-----------|
| I    | HP (PV) fijo |
| II   | ATK fijo |
| III  | DEF fijo |
| IV   | Aleatorio (CritRate, CritDmg, ATK%, HP%, DEF%, AnomProf) |
| V    | Aleatorio (PEN%, Ice DMG%, Fire DMG%, Elec DMG%, Ether DMG%, Physical DMG%, HP%, ATK%, DEF%) |
| VI   | Aleatorio (ATK%, HP%, DEF%, Impact%, AnomMast, EnergyRegen%) |

**Objetivo:** Capturar la pantalla que sale al terminar una Patrulla de Área, para inferir el set/slot/rarity de cada drop sin tener que abrir el inventario.

**Necesito:**

- `01a_resultados_0_drops.png` — una corrida que no soltó discos (para entrenar el clasificador negativo).
- `01b_resultados_1_drop.png` — un solo disco dropeado.
- `01c_resultados_varios_drops.png` — 3+ discos en la misma corrida (caso típico de farmeo eficiente).
- `01d_resultados_mixto.png` — drops de varios tipos en la misma pantalla (disco + crédito + materiales) para ver cómo se diferencian los iconos.
- `01e_resultados_patrulla_area.png` — Patrulla de Área (fuente principal, prioridad máxima).
- `01f_resultados_otra_actividad.png` — otra actividad que drope discos si existe (ej. eventos).

**Qué ROI voy a extraer:**

- Posición y tamaño del panel de drops (izquierda según tu descripción).
- Icono del set (emblema miniatura) — clave para identificar el set sin texto.
- Color del borde del disco (rareza: S dorado, A morado, B azul — confirmar).
- Texto del slot (si aparece) o icono de slot (I, II, III, IV, V, VI).

**Preguntas abiertas:**

1. ¿La lista de drops muestra el nombre del set textualmente, o solo el emblema?
2. ¿El slot del disco se ve desde la lista o solo al abrir el detalle?
3. ¿Hay algún indicador visual de si el drop es "nuevo set" o ya lo tenías?
4. ¿Aparece el nivel del drop (siempre 0)?
5. ¿El orden de la lista es cronológico, por rareza, o aleatorio?

---

## 02 — Detalle de Disco desde Resultado

**Carpeta:** `02_Detalle_Disco_Desde_Resultado/`

**Objetivo:** Pantalla que aparece cuando haces clic sobre un drop específico en la pantalla de resultados, con los 4 substats visibles.

**Necesito:**

- `02a_detalle_S_3subs.png` — disco S con 3 substats (nivel 0, sub4 bloqueado). Importantísimo: es el estado base de cualquier drop nuevo.
- `02b_detalle_S_4subs.png` — disco S con 4 substats visibles (sub4 desbloqueado ya al dropear, si aplica).
- `02c_detalle_A.png` — disco A para ver diferencia de color/layout.
- `02d_detalle_B.png` — disco B idem.
- `02e_detalle_slot_par.png` — disco de slot II, IV o VI (tienen main stat variable).
- `02f_detalle_slot_impar.png` — disco de slot I, III o V (tienen main stat fijo o semi-fijo).

**Qué ROI voy a extraer:**

- Main stat + valor (zona superior, tipografía grande).
- 4 substats + valores + rolls (badges/estrellas/círculos al lado de cada sub).
- Set name + icono (header).
- Nivel del disco (normalmente 0 si recién dropeó).

**Preguntas abiertas:**

6. ¿En la pantalla de detalle desde resultados, ya aparecen los rolls (badges) de cada sub o solo el valor?
7. ¿Los rolls se muestran como número (x3) o como iconos (●●●○○)?
8. ¿Hay un botón de "equipar directamente desde aquí" o solo se puede desde el inventario?

---

## 03 — Pantalla de Agente con Discos Equipados

**Carpeta:** `03_Pantalla_Agente_Discos_Equipados/`

**Objetivo:** Esta es la pantalla más crítica para RF-04 (detección de cambio de disco). Necesito mapear exactamente dónde está cada uno de los 6 slots, el nombre del agente, y cómo se ve un slot vacío.

**Necesito:**

- `03a_agente_6slots_llenos.png` — un agente con los 6 slots equipados (el caso normal).
- `03b_agente_0slots.png` — un agente sin discos equipados (todos los slots vacíos).
- `03c_agente_parcial.png` — un agente con algunos slots llenos y otros vacíos.
- `03d_mismo_agente_con_swap.png` — PAREJA DE CAPTURAS: el mismo agente antes y después de cambiar un disco en un slot específico (nombrar: `03d_pre.png` + `03d_post.png`).
- `03e_set_completo_2pc.png` — agente con un set con bonus 2pc activo (para ver cómo se indica visualmente).
- `03f_set_completo_4pc.png` — agente con bonus 4pc activo.

**Qué ROI voy a extraer:**

- Nombre del agente (header).
- Posición de cada uno de los 6 slots en la pantalla.
- En cada slot: emblema del set, nivel del disco, main stat resumido.
- Bonus de set (2pc, 4pc) — ¿hay icono dedicado?

**Preguntas abiertas:**

9. ¿Cuántos discos se muestran en la vista del agente por defecto? ¿Hay que hacer scroll o están los 6 visibles?
10. ¿Al hover o click sobre un slot, se despliega detalle? ¿O requiere ir a inventario?
11. ¿El indicador de set activo (2pc/4pc) es un ícono, un texto, o ambos?
12. ¿Los slots vacíos se muestran como placeholder gris o simplemente no aparecen?

---

## 04 — Vista Individual de Disco (desde inventario)

**Carpeta:** `04_Inventario_Disco_Vista_Individual/`

**Objetivo:** Pantalla que aparece al clickear un disco desde el inventario general de discos (no desde un agente). Es la vista más completa y la que usaremos como "fuente de verdad" para poblar `inventory_discs`.

**Necesito:**

- `04a_nivel_0_S_3subs.png` — disco S nivel 0 recién obtenido.
- `04b_nivel_3_S_4subs.png` — disco S nivel 3 (desbloqueó sub4).
- `04c_nivel_9_S.png` — disco S nivel 9 (3 rolls aplicados).
- `04d_nivel_15_S.png` — disco S maxeado (5 rolls aplicados).
- `04e_nivel_15_A.png` — disco A maxeado (para comparar substats max entre rarezas).
- `04f_disco_equipado.png` — disco equipado: muestra **avatar miniatura** del agente (confirmado con el usuario). Por favor incluir zoom al avatar.
- `04g_disco_bloqueado.png` — disco con **candado** activo (confirmado: esa feature existe).
- `04h_disco_con_papelera.png` — disco marcado con **papelera de basura** para descarte (confirmado: existe).

**Qué ROI voy a extraer (definitivo):**

- Set name + icono.
- Slot (número romano o arábigo).
- Nivel actual.
- Main stat + valor.
- Hasta 4 substats + valor + cantidad de rolls.
- Indicador "equipado por [agente]" si aplica.
- Indicador de lock si aplica.

**Preguntas abiertas:**

13. ¿Los rolls se visualizan como badges/estrellas al lado del valor? ¿Son 0-5 por sub?
14. ¿Hay un icono de "lock" para evitar que el auto-descarte elimine el disco?
15. ¿El juego tiene una feature de "autodescarte" de discos malos?
16. ¿Cuando un disco está equipado, aparece el nombre del agente o solo un avatar miniatura?
17. ¿Hay alguna marca de "disco nuevo / no visto" en el inventario?

---

## 05 — Upgrade PRE (nivel 0)

**Carpeta:** `05_Upgrade_PRE_nivel0/`

**Objetivo:** Pantalla de upgrade inmediatamente antes de gastar EXP. Este es el "snapshot PRE" del RF-05.

**Necesito:**

- `05a_pre_nivel0_disc_S.png` — la pantalla con el disco seleccionado en nivel 0, 3 subs visibles, sub4 bloqueado, EXP a agregar.
- `05b_pre_nivel0_slider_max.png` — mismo caso pero con el slider de EXP en el máximo (listo para subir a nivel 3).
- `05c_pre_confirmar_visible.png` — la pantalla con el botón "confirmar" visible y habilitado.

**Qué ROI voy a extraer:**

- Posición del botón confirmar.
- Posición de la preview del nivel destino.
- Dónde aparece la sub4 "bloqueada" (suele ser un placeholder con icono de candado).

**Preguntas abiertas:**

18. ¿El slider permite saltar de 0 a 15 directo o solo de 3 en 3?
19. ¿La preview de "nivel post-upgrade" se ve antes de confirmar, o solo después?
20. Si confirmas un upgrade grande (0→15), ¿se muestran las 5 rolls en una sola pantalla o hay animaciones separadas por cada hito (3, 6, 9, 12, 15)?

---

## 06 — Upgrade PRE (niveles intermedios 3, 6, 9, 12)

**Carpeta:** `06_Upgrade_PRE_nivel3_6_9_12/`

**Objetivo:** Cubrir cada uno de los hitos donde se aplica un roll nuevo.

**Necesito:**

- `06a_pre_nivel3_antes_subir.png` — disco en nivel 3, a punto de pasar a nivel 6.
- `06b_pre_nivel6_antes_subir.png` — disco en nivel 6, a punto de pasar a nivel 9.
- `06c_pre_nivel9_antes_subir.png` — ídem 9→12.
- `06d_pre_nivel12_antes_subir.png` — ídem 12→15.

**Qué ROI voy a extraer:**

- Los 4 substats ya visibles con sus valores y rolls actuales (para el diff posterior).

---

## 07 — Upgrade POST (animación + confirmación)

**Carpeta:** `07_Upgrade_POST_animacion_confirmacion/`

**Objetivo:** Capturar el momento inmediatamente después de confirmar, cuando aparece la animación que resalta qué sub subió.

**Necesito:**

- `07a_post_animacion_roll_resaltado.png` — si el juego muestra un efecto visual cuando un sub recibe un roll nuevo.
- `07b_post_sub4_desbloqueada.png` — momento en que sub4 pasa de "bloqueada" a mostrar un valor.
- `07c_post_pantalla_final.png` — pantalla estable post-upgrade (equivalente a reabrir la vista del disco).
- `07d_post_multi_rolls_mismo_sub.png` — caso especial: si por azar el mismo sub recibió varios rolls en un upgrade múltiple.

**Preguntas abiertas:**

21. ¿Hay algún efecto visual/sonoro distintivo cuando sale un roll particularmente alto (golden glow)?
22. ¿Se puede hacer upgrade sin confirmación (one-click) o siempre requiere paso de confirmación?

---

## 08 — Menús y transiciones

**Carpeta:** `08_Pantallas_Menu_Transicion/`

**Objetivo:** Entrenar el clasificador de pantalla para que distinga entre "estás en algo relevante" vs "estás en menú/combate/diálogo".

**Necesito:**

- `08a_menu_principal.png` — menú principal del juego.
- `08b_inventario_tab_discos.png` — vista general del inventario filtrada por discos.
- `08c_inventario_tab_armas.png` — inventario armas (para contraste).
- `08d_combate_en_curso.png` — pantalla de combate.
- `08e_dialogo.png` — cutscene o diálogo.
- `08f_mapa.png` — overworld / mapa.
- `08g_inter_knot.png` — Inter-Knot (home base).
- `08h_tienda_silueta_potencial.png` — tienda de awakenings (para RF futuros).

---

## 09 — Iconos UI por aclarar

**Carpeta:** `09_Iconos_UI_por_aclarar/`

**Objetivo:** Capturas puntuales (crops pequeños si se puede) de iconos que vi en la vida real pero cuyo significado exacto no tengo documentado.

**Pedidos específicos, guarda con nombre descriptivo:**

- `09_icono_set_[nombre_set].png` — el emblema miniatura de cada set. Idealmente los 27 sets existentes, pero prioridad:
  - Polar Metal / Metal Polar
  - Woodpecker Electro
  - Swing Jazz
  - Caesar
  - Branch/Puffer Electro
  - Chaotic Metal
  - Freedom Blues
  - Inferno Metal
  - Fanged Metal
  - Shockstar Disco
  - Chaos Jazz
  - Thunder Metal
  - Proto Punk
  - Astral Voice
  - Hormone Punk
- `09_icono_rareza_S.png` / `09_icono_rareza_A.png` / `09_icono_rareza_B.png` — el indicador de rareza aislado.
- `09_icono_main_stat_*.png` — iconos de cada main stat (ataque, HP, defensa, crit, etc.).
- `09_icono_substat_*.png` — si son distintos a los de main stat.
- `09_badge_roll.png` — un zoom del badge/estrella que indica un roll (si tu resolución lo permite).

**Preguntas abiertas:**

23. ¿Los iconos de sets son todos distinguibles o hay algunos muy parecidos (ej. todos los "Metal" comparten un diseño base)?
24. ¿Hay algún símbolo de copyright/versión en la esquina que pueda confundir al OCR?

---

## 10 — Variantes de resolución

**Carpeta:** `10_Variantes_Resolucion/`

**Objetivo:** Si juegas a distintas resoluciones (fullscreen / borderless / ventana), necesito una captura de la pantalla del agente en cada modo para calibrar ROIs relativos.

**Necesito:**

- `10a_fullscreen_[resolucion].png` — ej. `10a_fullscreen_1920x1080.png`.
- `10b_borderless_[resolucion].png`.
- `10c_ventana_[resolucion].png`.
- `10d_modo_DLSS_o_escalado.png` — si usas DLSS/FSR, la imagen nativa del screenshot puede diferir del render.

Con al menos una variante me basta para detectar si el layout es proporcional o absoluto.

---

## Resumen rápido de qué necesito YA para empezar

Si solo puedes hacer un lote, prioriza estas 12 capturas (en este orden):

1. Pantalla Resultado de Desafío con varios drops → `01c`
2. Detalle de disco desde resultado, S con 3 subs, nivel 0 → `02a`
3. Agente con 6 slots llenos → `03a`
4. Agente sin discos → `03b`
5. Disco S nivel 0 desde inventario → `04a`
6. Disco S nivel 15 desde inventario → `04d`
7. Pantalla upgrade PRE nivel 0 → `05a`
8. Pantalla upgrade POST nivel 3 (sub4 desbloqueada) → `07b`
9. Inventario general de discos → `08b`
10. Combate (negativo) → `08d`
11. Zoom de iconos de sets principales → `09_icono_set_*`
12. Un PRE/POST del mismo disco (`05a` + `07a/b/c` del mismo ID)

---

## Convención de nombres

```
[numero_subcarpeta][letra][descripcion_corta_sin_espacios].png
```

Ejemplos:
- `01c_resultados_varios_drops.png`
- `03d_pre.png` / `03d_post.png`
- `09_icono_set_polar_metal.png`

Si no tienes claro cómo nombrar, guárdalo con cualquier nombre descriptivo en su carpeta correspondiente y yo me encargo del renombrado cuando lo procese.
