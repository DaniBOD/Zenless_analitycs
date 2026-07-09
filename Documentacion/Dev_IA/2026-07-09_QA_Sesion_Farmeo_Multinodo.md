# QA sesión — farmeo multinodo (2026-07-09)

**Branch:** `feature/5R-detbadge-matcher` · **Modo:** QA en vivo (`qa_launch -FromSource -IdDiag
-ReadOnly -NoFocusGate -RestoreFarm`) · **Alcance:** display-only (no persiste, no puntúa DB).

Sesión de QA recorriendo múltiples nodos de farmeo para endurecer el flujo
**S13 (predice sets) → S2 (slot + set por tile) → S3 (stats del disco)**. 9 fixes, todos con
test de regresión sobre frames reales. Nodos probados: El piloto y el meca rebelde, Cuadriga
sometedragones, Engaños y baluartes, De boca y espada, La torre y el cañón.

## Fixes (en orden)

1. **`4085de6` — S3 como estado continuo.** S3 tenía handler continuo con techo de ciclos pero
   no estaba en la lista de dispatch continuo → solo despachaba en la transición. Un disco que
   NO madura al 1er frame (p.ej. slot-OCR falla → slot=0) quedaba **estancado sin emitir**. Fix:
   S3 → estado continuo (como S17/S9/S13). Bonus: re-extraer da más chances de leer bien el slot.

2. **`1a2bf3f` — persistencia del contexto de farmeo (`-RestoreFarm`).** Al reiniciar la app para
   aplicar un fix se perdía la predicción S13 (en memoria de `FarmSession`) → S2 quedaba sin
   candidatos. Ahora `FarmSession` deja un breadcrumb JSON (`DANIBOD_FARM_STATE`, solo QA) y el
   flag `-RestoreFarm` lo recarga al arrancar con ventana fresca. Producción no persiste.

3. **`c05b234` — slot S3 con nombre de set largo.** Sets de nombre largo ('Conejo en el país de
   las maravillas') caían a slot=0: el título se envuelve a 2 líneas (el `(N)` va abajo) y la
   insignia de rareza 'S' se cuela como token tras el `(N)` → `_RE_TITULO_SLOT` (anclada al final)
   falla. Fix: buscar `(N)` sin ancla en cada línea del título + rescate que escanea todas las
   líneas.

4. **`d698941` — set por predicción cuando el OCR cambia una palabra.** 'Aria brillante' se leía
   'Aria radiante' → el lookup exacto (norm_key arregla acentos, no palabras) fallaba → set_id=0
   (sin logo/nombre, sin bonus de conjunto). El resolver fuzzy global también abstiene (r=0.80 <
   cutoff 0.86). Fix: en farmeo, elegir entre los 2 sets PREDICHOS el de nombre más parecido
   (`best_predicted_set_id`, seguro con pocos candidatos).

5. **`123da33` — FP S18 en el mapa de viaje rápido.** El tab-override promovía a S18 con conf 0.90
   ante cualquier pill amarillo en la franja inferior. Un tile de tienda amarillo del mapa lo
   disparaba. Fix: el override ahora exige corroboración de la **fila de avatares** (coexiste con
   el tab-bar en la familia detalle-agente; 12/12 reales la tienen, 3/3 viaje_rapido no).

6. **`086df22` — main de nombre largo cortado en S3.** El atributo principal 'Tasa de Perforación'
   se envuelve a 2 líneas; el parser tomaba solo 'Tasa de' → `main_stat_canon=None`. Fix: aplicar
   el coalescing de nombres envueltos (ya usado en substats) también al main.

7. **`a35775a` — FP S2 de la tienda (documentado, no arreglado).** La pantalla de tienda/promo es
   casi idéntica a 'Resultados del desafío' (S2): mismo template + 4 franjas de rareza (S2 real
   da 3). No separable sin OCR sin arriesgar la detección de farmeo real (geometría/magenta/dorado
   estricto probados, fallan). **Decisión del usuario:** aceptar como limitación conocida (`Tienda`
   con allowed S2/S12 en el QA negativo) — FP cosmético (display-only, tentativo) y pantalla
   temporal (~20 días).

8. **`854ee6b` — valor del main con nombre envuelto (6.9 flat → 6 %).** Con el main envuelto, el
   valor '6 %' se alinea con la 2ª línea, pero el rescate recortaba solo la altura de la 1ª → leía
   '6.9/' → (6.9, flat). Fix: `_coalesce_wrapped_names` extiende el `y2` del nombre mergeado a la
   2ª línea, así el crop del rescate alcanza el valor.

9. **`ee2f300` — matcher del dígito de slot S2 por template (NCC), reemplaza el OCR.** El dígito
   de slot es un glifo estilizado que PaddleOCR lee mal crónicamente ('6'→'5', '5'↔'S', '4'→'2').
   Reemplazado por template matching contra 30 recortes reales etiquetados
   (`app/resources/slot_digits/`), primario con OCR de fallback. **Descriptor clave:** el hexágono
   de fondo es idéntico y domina la correlación → se resta el TEMPLATE PROMEDIO para aislar el
   residuo del dígito (margen medio 0.12→0.5). Leave-one-out: 29/30, 0 confusiones entre dígitos.
   Detalle en [`2026-07-09_IMPL_Slot_Digit_Matcher_S2.md`](2026-07-09_IMPL_Slot_Digit_Matcher_S2.md).

## Estado del flujo de farmeo (fin de sesión)

- **S13 → predicción de sets:** ✅ dinámica entre nodos, tildes/ñ, verificada en 5+ nodos.
- **S2 → slot por tile:** ✅ template matcher (robusto donde el OCR fallaba).
- **S2 → set por badge:** ✅ + fallback por predicción cuando el OCR del nombre falla.
- **S3 → stats del disco:** ✅ set/slot/main (nombre+valor, incl. nombres envueltos)/substats/score,
  con checklist multi-disco y "ya capturado".
- **FPs:** viaje rápido resuelto; tienda documentada como limitación conocida.

## Follow-ups (anotados, no urgentes)

- **Slot digit matcher:** si aparecen framings nuevos que abstienen seguido, crecer el set de refs.
- **FP tienda:** si molesta, requeriría un chequeo negativo por OCR (precio/'Comprar'); pantalla
  temporal, baja prioridad.
- **Otros nodos:** seguir cubriendo nodos para validar predicción/matcher con más sets.
- Build `.exe` sigue viejo → QA corre desde fuente (`-FromSource`).
