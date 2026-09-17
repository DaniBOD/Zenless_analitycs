# Índice de Dev_IA

**La puerta de entrada a la documentación de desarrollo.** Qué hay, de qué mes, y si sigue siendo
cierto. Diseño en el [SPEC del 2026-09-08](documentacion_cruda/2026-09/2026-09-08_SPEC_Compactar_Dev_IA_por_periodo.md).

## Cómo se usa

- **Lecciones de cómo trabajar** → [`00_Practicas_Aprendidas.md`](00_Practicas_Aprendidas.md). Es su
  única autoridad; los compactos no las repiten.
- **Un mes con compacto** → leé el compacto: mediciones, hipótesis refutadas, dónde vive la
  autoridad y qué quedó abierto. Los crudos quedan para un detalle puntual.
- **Un mes sin compacto** → está vivo, o todavía no se compactó: abrí sólo los crudos que te sirvan.
- **Un marcador ⚠️** → la cabecera de ese documento dice algo que después dejó de ser cierto. Manda
  lo que dice acá.

**El corte entre vivo y añejo no es una fecha: es la existencia del compacto.**

## Dónde nace un documento nuevo

En `documentacion_cruda/YYYY-MM/`, **nunca en la raíz**, y con una línea en este índice. Los
archivos no se mudan después: una ruta que cambia rompe los enlaces que apuntan a ella.

---

## Meses compactados

| mes | compacto | crudos |
|---|---|---|
| 2026-07 | [`2026-07_compacto.md`](compactos/2026-07_compacto.md) · 173 líneas | 27 docs · 4.679 líneas → [`documentacion_cruda/2026-07/`](documentacion_cruda/2026-07/) |


## 2026-05 — cerrado · **sin compacto todavía** → se leen los crudos

- [2026-05-13](documentacion_cruda/2026-05/2026-05-13_Hito_2.8_Detector_Robusto_S17.md) — detector robusto + captura S17
- [2026-05-15](documentacion_cruda/2026-05/2026-05-15_Hito_2.8_Deep_S18_Multi_Trigger.md) — deep S18 multi-trigger; cierre del gap test↔runtime
- [2026-05-27](documentacion_cruda/2026-05/2026-05-27_Hito_2.8_Stats_Aggregator_F8_Robusto.md) — madurez de captura S18 + F8 global + completitud rol-aware
- [2026-05-31](documentacion_cruda/2026-05/2026-05-31_Hito_2.8_Migracion_Python_PaddleOCR.md) — migración a Python normal + PaddleOCR estable
- [2026-05-31](documentacion_cruda/2026-05/2026-05-31_Hito_2.8_QA_Real_PaddleOCR.md) — QA real en juego del `.exe` con PaddleOCR
- [2026-05](documentacion_cruda/2026-05/2026-05_Hito_2.0-2.8_Seguimiento_Desarrollo.md) — seguimiento de la Fase 2, hitos 2.0 → 2.8 · el único doc de mes, sin día

## 2026-06 — cerrado · **sin compacto todavía** → se leen los crudos

- [2026-06-02](documentacion_cruda/2026-06/2026-06-02_Hito_2.8_Capa4_Stats_ID_y_Diagnostico_Hardware.md) — Capa 4 (identidad por stats) + single-instance · ✅ en vivo; el diagnóstico de hardware quedó **sin implementar**
- [2026-06-03](documentacion_cruda/2026-06/2026-06-03_Hito_2.8_QA_Flujo_Pantallas_y_Avatar_ID.md) — QA en vivo: FP de flujo S18↔S8 + plan de estandarización de avatares
- [2026-06-06](documentacion_cruda/2026-06/2026-06-06_Hito_2.8_Regresion_Build_Env_PaddleOCR.md) — regresión del entorno de build: PaddleOCR no determinista
- [2026-06-06](documentacion_cruda/2026-06/2026-06-06_Hito_2.8_S17_Composicion_Set_y_Refinamientos.md) — composición de set por PJ + tier activo + refinamientos de S17
- [2026-06-09](documentacion_cruda/2026-06/2026-06-09_Hito_2.8_S17_QA_Fase4_Trust_Latch_y_Datos.md) — QA Fase 4: trust-latch y fixes de datos
- [2026-06-10](documentacion_cruda/2026-06/2026-06-10_Hito_2.8_Fase5R_Descriptor_Robusto.md) — Fase 5R: descriptor robusto de identidad del PJ por ícono
- [2026-06-11](documentacion_cruda/2026-06/2026-06-11_Hito_2.8_Fase5R_Grilla_Voto_Cosecha_Validacion.md) — Fase 5R: grilla S17 — voto, filtro de forma, cosecha, validación
- [2026-06-12](documentacion_cruda/2026-06/2026-06-12_BUG_fuga_memoria_RNF-06.md) — BUG de fuga de memoria · ⚠️ la cabecera dice ABIERTO: **se cerró al día siguiente** (`0f40953`, `load_merge` retenía arrays por una view)
- [2026-06-13](documentacion_cruda/2026-06/2026-06-13_Inventario_Global_Badges_Alternativa_Cosecha.md) — inventario global como vía alternativa de cosecha · **DIFERIDA**, idea de diseño
- [2026-06-13](documentacion_cruda/2026-06/2026-06-13_PLAN_Embedding_Badges_Fase5R.md) — embedding ONNX para identidad de badges · ⚠️ el doc dice APROBADO: **se DESCARTÓ tras el spike E.0** (`541cd3f`, 06-17) — el desenlace sólo está en el commit

## 2026-08 — cerrado · **sin compacto todavía** → se leen los crudos

- [2026-08-02](documentacion_cruda/2026-08/2026-08-02_FIX_Colapso_Librerias_Badges.md) — el colapso de las librerías de badges (grid + row)
- [2026-08-02](documentacion_cruda/2026-08/2026-08-02_IMPL_RF15_Desambiguacion_S29_y_S9.md) — RF-15 tramo 2(a): desambiguar las pantallas de arma de las de disco (S29, S9)
- [2026-08-04](documentacion_cruda/2026-08/2026-08-04_IMPL_RF15_S30_Inventario_Amplificadores.md) — RF-15 tramo 2(b): S30, el inventario de amplificadores
- [2026-08-07](documentacion_cruda/2026-08/2026-08-07_QA_S30_en_vivo_y_los_tres_arreglos.md) — QA en vivo de S30: tres arreglos y el dueño del arma
- [2026-08-10](documentacion_cruda/2026-08/2026-08-10_SPEC_RF15_Cosecha_Detalle_desde_S26.md) — SPEC RF-15: cosecha del detalle-badge desde S26
- [2026-08-11](documentacion_cruda/2026-08/2026-08-11_SPEC_Dedup_Cosecha_Badges.md) — SPEC: dedup por contenido en la cosecha de badges
- [2026-08-12](documentacion_cruda/2026-08/2026-08-12_DIAG_Librerias_de_Badges_tres_trampas_de_medicion.md) — las librerías de badges y tres trampas de medición
- [2026-08-15](documentacion_cruda/2026-08/2026-08-15_IMPL_Encuadre_de_Badges_y_Latch_Sostenido.md) — el encuadre de los badges y el latch sostenido
- [2026-08-15](documentacion_cruda/2026-08/2026-08-15_IMPL_Un_evento_una_linea_y_el_instrumental_de_latencia.md) — un evento, una línea — y el instrumental de latencia (QA-06)
- [2026-08-16](documentacion_cruda/2026-08/2026-08-16_IMPL_Censo_Fase0_y_Roster.md) — censo de cuenta: fase 0 (cobertura) + fase 1 (roster)
- [2026-08-17](documentacion_cruda/2026-08/2026-08-17_IMPL_Rebuild_DB_y_Roster_Declarado.md) — la DB reconstruida desde cero + el roster declarado
- [2026-08-17](documentacion_cruda/2026-08/2026-08-17_QA_Censo_Roster_y_el_problema_de_los_grises.md) — QA del censo de roster y el problema de los grises
- [2026-08-18](documentacion_cruda/2026-08/2026-08-18_FIX_Dedup_de_discos_por_identidad.md) — la firma que no distinguía discos: distinguía casilleros
- [2026-08-18](documentacion_cruda/2026-08/2026-08-18_FIX_S9_libre_vs_no_se.md) — S9: "está libre" y "no pude leer" dejan de ser la misma respuesta
- [2026-08-18](documentacion_cruda/2026-08/2026-08-18_IMPL_Censo_Discos_con_contador.md) — censo de discos con el contador del header
- [2026-08-18](documentacion_cruda/2026-08/2026-08-18_IMPL_Veto_del_latch_por_declaracion.md) — el veto del latch por declaración
- [2026-08-18](documentacion_cruda/2026-08/2026-08-18_QA_Censo_Discos_en_vivo.md) — QA en vivo del censo de discos — y las tres veces que medí mal
- [2026-08-19](documentacion_cruda/2026-08/2026-08-19_DIAG_Classify_el_costo_lo_pone_el_frame.md) — `classify` tarda 3,5 s y el costo lo pone el frame, no el template
- [2026-08-19](documentacion_cruda/2026-08/2026-08-19_FIX_Baselines_fuera_del_alcance_del_exe.md) — la red de emergencia que el `.exe` nunca tuvo (baselines fuera de `app/`)
- [2026-08-19](documentacion_cruda/2026-08/2026-08-19_FIX_Unicidad_de_nombres_en_audit.md) — el flake que era pérdida de datos: el reloj no es un discriminador
- [2026-08-20](documentacion_cruda/2026-08/2026-08-20_FIX_Unicidad_del_backup_RNF-01.md) — el backup que probaba el estado previo, y el segundo F8 que se lo llevaba
- [2026-08-20](documentacion_cruda/2026-08/2026-08-20_UNIF_Una_sola_primitiva_de_reserva.md) — dos worktrees escribieron la misma primitiva de reserva
- [2026-08-21](documentacion_cruda/2026-08/2026-08-21_FIX_Dueno_innombrable_ya_no_tira_el_disco.md) — un dueño innombrable ya no tira el disco entero
- [2026-08-29](documentacion_cruda/2026-08/2026-08-29_DIAG_La_fuga_es_del_OCR_12MB_por_inferencia.md) — la fuga de RAM es del OCR: 12,46 MB por inferencia
- [2026-08-29](documentacion_cruda/2026-08/2026-08-29_FIX_Re-arme_S9_el_gemelo_no_lo_ve_el_panel.md) — el re-arme de S9: el gemelo que el panel no puede ver
- [2026-08-29](documentacion_cruda/2026-08/2026-08-29_IMPL_OCR_en_proceso_aparte_reciclable.md) — el OCR se muda a un proceso desechable
- [2026-08-30](documentacion_cruda/2026-08/2026-08-30_QA_Censo_de_discos_cinco_hallazgos_y_una_forma_repetida.md) — el censo de discos como instrumento: cinco hallazgos, tres con la misma forma

## 2026-09 — 🟢 **vivo** — el mes en curso

- [2026-09-01](documentacion_cruda/2026-09/2026-09-01_FIX_Dos_umbrales_absolutos_donde_manda_el_margen.md) — dos umbrales absolutos donde manda el margen
- [2026-09-05](documentacion_cruda/2026-09/2026-09-05_PLAN_Hoja_de_ruta_uso_diario.md) — hoja de ruta del uso diario — los 5 tramos que pidió Daniel
- [2026-09-05](documentacion_cruda/2026-09/2026-09-05_QA_Una_marca_es_una_afirmacion_y_por_eso_se_puede_refutar.md) — una marca es una afirmación, y por eso se puede refutar
- [2026-09-06](documentacion_cruda/2026-09/2026-09-06_FEAT_Censo_de_W_Engines_el_inventario_de_armas_existe.md) — censo de W-Engines: `inventory_weapons` deja de estar vacía
- [2026-09-06](documentacion_cruda/2026-09/2026-09-06_FEAT_Los_tres_verbos_la_DB_sigue_al_juego_sola.md) — los tres verbos: la DB sigue al juego sola
- [2026-09-08](documentacion_cruda/2026-09/2026-09-08_SPEC_Compactar_Dev_IA_por_periodo.md) — SPEC de esta misma estructura: compactar Dev_IA por período
- [2026-09-12](documentacion_cruda/2026-09/2026-09-12_FIX_Una_cara_con_el_nombre_de_otro_y_el_fantasma_era_el_scroll.md) — una ref con el nombre de otro PJ, el fantasma de las copias era el scroll, y la latencia medida · **cierra el censo de armas S+A en 56**
- [2026-09-12](documentacion_cruda/2026-09/2026-09-12_PLAN_Interfaz_la_pantalla_en_vivo.md) — diseño de la interfaz, fase 1: un shell con sidebar y una vista en vivo que **sólo dice lo que vio** (sin scoring: no está calibrado)
- [2026-09-12](documentacion_cruda/2026-09/2026-09-12_FIX_El_optimizador_media_contra_una_tabla_vacia.md) — el optimizador medía la build actual contra `agent_discs` (vacía): baseline 0 en 51/51 PJs, latente (nada lo dispara en la app)
- [2026-09-12](documentacion_cruda/2026-09/2026-09-12_DIAG_Swaps_con_neto_negativo_entran_como_discos_libres.md) — DIAG: 92 discos ajenos con neto ≤ 0 entran a la mejor build rotulados "libre" (72 con neto exactamente 0: mismo arquetipo); 4 opciones, sin implementar
- [2026-09-12](documentacion_cruda/2026-09/2026-09-12_FIX_Un_disco_ajeno_solo_entra_si_gana_y_nunca_como_libre.md) — FIX B+D+A: 92 → 0 discos ajenos rotulados libre; el saqueo sigue (222 ajenos con neto > 0) — eso es la opción C, diferida
- [2026-09-12](documentacion_cruda/2026-09/2026-09-12_DIAG_El_filtro_de_mains_excluye_el_30_por_ciento_de_lo_equipado.md) — DIAG: el filtro de mains deja afuera 46/152 discos equipados (29 PJs). 9 son vocabulario viejo (ANOMALY slot 6 dice Maestría, es Tasa — pendiente de la mig 09 nunca hecho); 37 son arquetipo angosto (incluye Miyabi, cuyos thresholds de Prydwen contradicen su arquetipo)
- [2026-09-12](documentacion_cruda/2026-09/2026-09-12_FIX_Los_arquetipos_hablaban_el_vocabulario_de_antes_de_junio.md) — FIX mig `_32`: ANOMALY slot 6 = Tasa de Anomalía, Viento en slot 5, contrato arquetipos ⊆ `stats_vocab`. Excluidos 46 → 37
- [2026-09-13](documentacion_cruda/2026-09/2026-09-13_FEAT_Interfaz_fase_1_y_lo_que_la_suite_escondia.md) — interfaz fase 1 en main (shell + vista en vivo, probada por Daniel) · la suite **salteaba los tests de widgets en silencio** y crasheaba al 90 % · el `.exe` arrancaba con el matcher de sets vacío · maximizado recortaba 8 px
- [2026-09-13](documentacion_cruda/2026-09/2026-09-13_FEAT_Interfaz_fase_2_roster_y_modal_de_PJ.md) — interfaz fase 2: pantalla Roster (grilla entera sin scroll) y modal de PJ que sólo informa · migs `_33`/`_34`: Severed Innocence estaba **dos veces** en `weapons` · tres defectos con los tests en verde que sólo vieron las **capturas con fuentes reales** · beta aprobada por Daniel
- [2026-09-13](documentacion_cruda/2026-09/2026-09-13_FEAT_Interfaz_fase_3_discos_y_modal_de_disco.md) — interfaz fase 3: pantalla Discos (la tabla vieja **mostraba 200 de 385 sin decirlo**) y modal de disco que sólo informa · dueño con su build y alternativas del mismo set y slot, **sin ordenar por calidad** · aprobada por Daniel
- [2026-09-15](documentacion_cruda/2026-09/2026-09-15_FEAT_Interfaz_fase_4_pantalla_Armas.md) — interfaz fase 4: pantalla Armas desde el diseño de Claude Design · **el diseño se dibujó con 5 armas leídas de 33 y la DB tiene las 56**: se portó el criterio, no los datos · `claude.exe` virtualizado por la Store para el `/design-login` · íconos 40/40 · aprobada por Daniel
- [2026-09-15](documentacion_cruda/2026-09/2026-09-15_FIX_El_reloj_de_la_frescura_media_el_epoch_y_la_espera_la_pone_el_warmup.md) - FIX `feac3c4`: la frescura abria con `monotonic` y cerraba con `time.time()`, asi que **medía el epoch (~1,789e12 ms) y 14 muestras pasaron por latencia un mes** - una metrica ROTA se ve igual que una mala. Reloj con una sola autoridad + guarda de implausibles + la metrica que faltaba (`frescura_disco_a_log`: la frescura del CONTENIDO, que QA-06 §10 no cubria). Y la causa de los 3 s de espera de Daniel: el **warmup del dueño se cuenta en PASADAS del loop asumiendo 10 fps** y el loop corre a p50 391 ms. Fase 0 de 4; engines aparte, en el 2º censo de QA
- [2026-09-17](documentacion_cruda/2026-09/2026-09-17_PERF_Latencia_del_log_en_S9_lo_que_midieron_las_pasadas_A_y_B.md) - PERF Fase 2: click→log en S9 **3109 → 2562 ms** (−18 %). La Pasada A desmintió el diagnóstico: la **mediana de una serie bimodal** había inventado "el primer despacho no emite", y el OCR principal (`text_with_bboxes`, **8,2×** una lectura de texto, ~1,6 s en vivo) **nunca se había medido**. Libres sin warmup, **despacho rápido con confirmación de panel quieto** (el despacho lee el frame del avistaje, que puede estar animando). Caché del header **revertida: 0/72 en vivo** — el test comparaba contra `a.copy()`. La Pasada B destapó un disco en dos líneas (`Ilameante`/`llameante`): filtro por set resuelto. Pendientes: botones (2B), `nivel` (3), censo (4), OCR del panel (2C)
