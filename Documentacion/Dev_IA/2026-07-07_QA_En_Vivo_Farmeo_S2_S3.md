# QA en vivo del flujo de farmeo (S2/S3) — fixes durables · 2026-07-07

**Estado:** CERRADO (código) · commits `56516ab`…`83e52b7` en `main`. QA del flujo **pausado por
el usuario** ("más tarde seguimos con más QA de este flujo").
**Contexto:** continuación directa de la [fase de confiabilidad anti-FP](./2026-07-07_Confiabilidad_Detector_Anti_FP.md)
(commit `96b4e13`), que dejó el "QA en vivo" como pendiente. Sesión larga de farmeo real
end-to-end (S13→S14→S2→S3) con `-IdDiag`. Sigue siendo **display-only** (no persiste; el scoring/
descarte se ignora hasta el hito de análisis).

## Síntomas encontrados en vivo

1. El **evento de doble recompensa** bajaba el match del template S2 → el resultado de farmeo no
   se reconocía.
2. Parpadeo **S13↔S12**: el template S2 matchea la pantalla S13 (previa) a ~0.90 → entraba y salía.
3. S2 reportaba **"sin disco visible"** aun con discos S dorados en columnas izquierdas.
4. En vivo el disco **no se reconocía** al abrir el modal S3 (S3→S12 constante).
5. **Crash al capturar S3**: `SQLite objects created in a thread can only be used in that same
   thread`.
6. El log/card no mostraban los stats del disco capturado.

## Fixes (en orden de commit)

**1. S2 template propio del evento + umbral 0.80** (`56516ab`→`37f7d8f`).
El intento inicial fue bajar el umbral S2 de 0.80→0.70 para pescar el evento doble-recompensa,
pero eso **reabría FP** (guías/banners con iconos de disco matcheaban a ~0.72). Solución final:
**template dedicado** `s2_resultado_desafio_evento.png` + **restaurar umbral a 0.80**. Cada
variante matchea su propio template alto en vez de un umbral laxo compartido. Ver
[fase confiabilidad](./2026-07-07_Confiabilidad_Detector_Anti_FP.md) (el 0.80 es el mismo que
protege del QA negativo de 33 FP).

**2. Verify-fallback en `classify`** (`d34b6f3`).
Antes, si el candidato top de template pasaba el umbral pero **fallaba su verificación**
secundaria, se caía directo a S12. El template S2 matchea S13 a ~0.90 → verificaba, fallaba, S12,
y al ciclo siguiente re-matcheaba → **parpadeo**. Fix: `_template_candidates` junta todos los
candidatos ≥ umbral y `classify` **cae al siguiente que pase su verificación** en vez de a S12.
Corta el parpadeo S13↔S12.

**3. Conteo S2 en el grid COMPLETO** (`9fcbc36`).
`parse_s2_resultado` contaba discos S por **franjas doradas** solo en la región angosta (columnas
derechas) → perdía los discos S de columnas izquierdas → falso "sin disco visible". Ahora cuenta
en región WIDE (`_GRID_X_WIDE=0.685-0.997`, `_GRID_Y_WIDE=0.40-0.62`, `count_gold_disc_strips`).
**Importante:** la **verificación anti-FP** (`count_reward_rarity_strips`, `_verify_s2`) **sigue en
la región NARROW calibrada** (`_grid_region(wide=False)`) — no se tocó, para no reabrir FP. Son dos
usos distintos de la misma geometría: WIDE para *contar*, NARROW para *verificar*.

**4. `_verify_s3` reescrito** (`198e296`).
Estaba ROTO: promediaba el HUE de un ROI mal ubicado (debajo del ícono) → fallaba en **9/10**
modales S3 reales → el disco no se reconocía (S3→S12). Reescrito a **fracción de color de rareza**
(gold/purple/blue) en ROI corregido `x 0.53-0.68, y 0.19-0.44`, umbral `0.015` (los reales dan
0.029-0.066). **Gap de test cerrado:** los tests de parser saltaban `classify()` → se agregó test
de `classify()` sobre los 10 S3 reales.

**5. SQLite cross-thread** (`6af899d`).
Al capturar S3, el monitor (thread daemon) tocaba `self._con` (repos de lectura, creada en el main
thread) → crash. Fix: `get_connection(check_same_thread=False)` para la conexión de **solo lectura
compartida**. Las **escrituras siguen yendo por `DiscSyncer` con su propia conexión** → **RNF-01
intacto** (la relajación de thread-check es solo para la conexión read-only).

**6. UI stats en vivo** (`d759fc1`).
El log y la card `LastDiscCard` (pestaña Captura en vivo) ahora muestran **stat principal +
secundarios** (nombre+valor+rolls, payload `subs_detail`). El **toast NO** (pedido explícito del
usuario). El scoring/descarte se ignora hasta el hito de análisis.

**7. Gate de captura por foco de ventana** (`83e52b7`).
Cherry-pick de otra sesión → main. Documentado aparte en
[`2026-07-07_Gate_Captura_Por_Foco_Anti_FP.md`](./2026-07-07_Gate_Captura_Por_Foco_Anti_FP.md).
Solo captura con ZZZ al frente (`is_zzz_focused`, `capture_only_focused=True` default,
`[monitor].solo_capturar_si_enfocado`).

## Resultado

- Flujo real S13→S14→S2→S3 corre sin crash ni parpadeo; el disco se reconoce y sus stats se ven
  en log + card.
- 52 tests afectados en verde tras resolver los conflictos de cherry-pick del gate de foco (ambos
  kwargs del constructor de `Monitor` conviven: `farm_session=` + `capture_only_focused=`).

## Pendiente cuando se retome el QA de este flujo

1. **Reforzar S13** + **pre-asociar los 2 sets por el título del nodo** (el usuario ofreció mapear
   título→2 sets).
2. Preview opcional de slots en S2 (el slot definitivo ya sale en S3).
3. Abrir el **2º disco (slot 6)** para confirmar la deduplicación por firma (`_s3_disc_signature`).
4. **Relanzar la app**: la instancia que quedó corriendo en el QA es previa al gate de foco
   (`d759fc1`) → no lo tiene activo hasta relanzar (`qa_launch.ps1 -FromSource -IdDiag -ReadOnly`).

## Referencias

- Commits (main): `56516ab`, `71c6b30`, `d34b6f3`, `37f7d8f`, `9fcbc36`, `198e296`, `6af899d`,
  `d759fc1`, `83e52b7`.
- Archivos: `app/core/detector.py`, `app/core/parser_s2.py`, `app/core/parser_disc_s3.py`,
  `app/core/monitor.py`, `app/core/capturer.py`, `app/ui/controller.py`,
  `app/config/defaults.toml`.
- Memoria: `project_farmeo_captura.md` (sección "QA EN VIVO DEL FLUJO 2026-07-07").
- Docs hermanos de hoy: [Confiabilidad anti-FP](./2026-07-07_Confiabilidad_Detector_Anti_FP.md),
  [Gate por foco](./2026-07-07_Gate_Captura_Por_Foco_Anti_FP.md).
