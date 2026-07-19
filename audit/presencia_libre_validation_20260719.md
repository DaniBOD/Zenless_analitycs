# Validación offline 5R.L.8 — presencia estructural + LIBRE invertido (2026-07-19)

**Contexto:** fix del falso LIBRE del QA 2026-07-18 (disco de Jane equipado, visto desde
la grilla de Velina, reportado "LIBRE (disponible)"). Causa: la presencia del detalle se
contaba por confianza del matcher (`conf≥0.86 o margen≥0.10`) → un avatar real NO
nombrable (gap de refs) contaba como ausente → la regla "LIBRE gana a incierto"
(2026-06-21) declaraba LIBRE en falso.

**Cambio (decisión del usuario 2026-07-19 — "presencia gana a LIBRE"):**
1. Presencia ESTRUCTURAL: `AgentIdentifier.s17_detail_is_face` clasifica el crop del
   detalle como CARA vs TEXTO '(N)' comparando distancia mínima a anclas de cara
   (refs cosechadas del detalle ∪ semilla `-ico` del roster, disponibles día-1) contra
   anclas de texto (`app/resources/avatar_reject_det/`, 3 crops reales: "(5)"×1 de la
   cosecha Cissia, "(1)"×2 de los libres reales). Independiente del naming.
2. `_s17_is_libre` invertido: `LIBRE ⇔ sin votos ∧ firma vigente ∧ detail_present == 0`.
   Un solo frame con cara bloquea LIBRE; un libre real sigue saliendo en 1 frame.
3. Rama nueva en `_assign_s17_pj`: presencia sin naming → "equipado · dueño incierto"
   (`equip_detectado=True`, `equip_libre=False`) — nunca limbo ni falso LIBRE.

## Resultados (librería runtime: det 250 refs / 49 PJs · 3 anclas de texto)

| Gold set | N | Resultado |
|---|---|---|
| EQUIPADOS (`audit/harvest/*__S17__*`, 1 sample = peor caso) | 180 | **1 falso-LIBRE** (`rina__S17__3`, residual PRE-EXISTENTE, ver abajo) · 179 resueltos por voto · presencia detalle en 169 |
| LIBRES reales (carpeta 17, incluye los 2 con crop de texto "(1)") | 11 | **11/11 LIBRE** con 1 sample |
| CARAS (crops det del gold set `audit/harvest_badges`) | 163 | **163/163 → presencia** (0 falso-texto = 0 vía nueva de falso-LIBRE) |
| TEXTO (anclas reject) | 3 | 3/3 → no-cara |

**Margen del clasificador cara-vs-texto:** min 0.030 · p5 0.046 · p50 0.173 (lado cara).
Texto de ESTILO NO VISTO puede clasificar como cara (leave-one-out de `texto_1_a` falla
contra los otros 2 estilos) → costo: "incierto" en vez de LIBRE = dirección segura
(RNF-02). Se mitiga sumando estilos reales al reject a medida que aparezcan.

## Residual conocido (pre-existente, NO regresión)

`rina__S17__3`: el avatar de Rina en el detalle es de BAJA SATURACIÓN (mismo caso
Lycaon) → falla la etapa-1 (blob saturado) de `crop_detail_badge` → sin crop → sin
presencia; y en ese frame la grilla tampoco votó → LIBRE falso. La regla VIEJA daba
exactamente lo mismo (sin votos + present=0 → libre). En los otros 3 frames de Rina la
grilla vota y la salva. Se descartó "presencia por blob de etapa-1" como cura: el blob
dispara en los 11 libres (arte/título saturado de la franja) → mataría la detección de
LIBRE. Camino real: refs de grilla para Rina (re-cosecha limpia, ver herramienta de
salud de librerías) o revisar el gate de saturación con datos de avatares pálidos.

## Descartes medidos (para el archivo)

- **Umbral absoluto de distancia al reject de texto** (para librería vacía): NO separa —
  caras grises (Nangong Yu 0.349 por ruta de luminancia) quedan más cerca del texto que
  un texto de estilo no visto (0.528).
- **Mezclar el reject de texto en el reject-set de NAMING del `_detbadge`**: causaba
  rechazos de caras grises legítimas → naming y presencia quedan como señales separadas.
- `texto_5_b` (crop `cissia__det__2`) era idéntico px a px a `texto_5_a` → eliminado.

**Tests:** `test_s17_avatar_assignment.py` 96 passed (incluye regresión Jane
`test_monitor_avatar_real_no_nombrable_nunca_libre`, clasificador
`test_detail_is_face_distingue_cara_de_texto`, libres reales 11/11) + `test_s17_owner_vote.py`
+ `test_grid_badge_presence.py` → 111 passed.
