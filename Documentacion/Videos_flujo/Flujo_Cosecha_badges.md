# Fixture de test — Flujo_Cosecha_badges.mp4

**Video:** `Flujo_Cosecha_badges.mp4` (LOCAL, gitignoreado — pesa **5.29 GB**)
**Capturado:** 2026-06-12 · 2560×1440 · 60 fps · **78.4 min** · 282 048 frames
**Flujo:** la **cosecha full-roster completa** — para CADA uno de los 47 PJs el recorrido
canónico `Pj_stats → Equipamiento → Slot 1 … Slot 6`, posando **~10 s por disco**.

A diferencia de [`Flujo_Grillas_Badges.md`](./Flujo_Grillas_Badges.md) (un solo PJ, una sola
grilla, fixture liviano de 271 MB), este es el **fixture end-to-end pesado**: representa la
pasada de cosecha entera tal cual se ejecuta en vivo con `qa_launch -BadgeHarvest`. Su razón
de ser es doble:

1. **Fuente para construir la librería de detalle** (`avatar_detbadge_v2.npz`) sin re-cosechar
   en vivo: barre los 47 PJs con el panel de detalle abierto en cada disco.
2. **Smoke end-to-end** de localización + recorte + match + voto + flujo-ancla sobre el roster
   completo, reproducible offline.

---

## 1. Verdad de tierra — equip_map de la cosecha

La cosecha en vivo escribió el mapa disco→dueño en
`audit/equip_map_20260612.json` (gitignoreado): **287 discos · 47 PJs**. Ese JSON ES la
verdad de tierra de este video (cada entrada = `_disc_identity → dueño` fijado por flujo-ancla
en el latch certero).

| Discos | PJs | Quiénes |
|--------|-----|---------|
| **6/6** (esperado) | 41 | Alice, Anby, Antón, Astra Yao, Ben, Billy Estelar, Cissia, Corin, Dialyn, Ellen, Evelyn, Grace, Harumasa, Jane, Ju Fufu, Koleda, Lucy, Lucía, Manato, Miyabi, N.º 0: Anby, N.º 11, Nangong Yu, Nicole, Orfia y Magas, Pan Yinhu, Piper, Pulchra, Qingyi, Rina, Seth, Soukaku, Sporos, Sunna, Vivian, Yanagi, Ye Shunguang, Yixuan, Yuzuha, Zhao, Zhu Yuan |
| **7** | 4 | Burnice, César, Gatillo, Lycaon |
| **8** | 1 | Billy |
| **5** | 1 | Nekomata |

**Notas de la verdad de tierra:**
- **Nekomata = 5** es correcto: **no tiene disco en el slot 5** (el usuario no pasó por ahí).
  Es el caso de "slot vacío" que el flujo-ancla NO verifica (GAP conocido — ver abajo).
- **>6 discos (Billy 8, los de 7):** sobre-atribución por discos **genéricos** repetidos o por
  el flujo-ancla disparando en un disco que no era del latch. A revisar cuando se cierre la
  verdad de tierra fina; **no** son wrongs de identificación (el dueño es el latch certero), son
  discos de más colgados del PJ.
- **Billy (id 12) vs Billy Estelar (id 47):** ambos presentes y **separados** — confirma que el
  onboarding de Billy Estelar (commit 41401e2) no los colapsa. Look-alike crítico verificado.

---

## 2. Test aplicado / para qué sirve

### a) Construcción de la librería de detalle (uso primario)
El video tiene el **panel de detalle abierto** en cada disco → el avatar junto a "Nivel 15/15"
(el detalle-badge) es visible y localizable al 100% (fondo oscuro, sin arte, cx≈0.495). Barrer
los 47 PJs con `crop_detail_badge` + flujo-ancla produce `avatar_detbadge_v2.npz` etiquetada
por latch certero, **sin** la fragilidad del grid-badge (NOLOC + confound de arte amarillo).

> **Recomendación operativa:** para construir la librería de detalle preferir la **pasada en
> vivo** (`qa_launch -BadgeHarvest` con el build nuevo) por sobre el procesamiento offline de
> este .mp4 — ver §4. Este video queda como **fixture de regresión** y respaldo.

### b) Smoke end-to-end full-roster
Mide localización (grid vs detalle), tasa de abstención y wrongs sobre los 287 discos, contra
el equip_map como oráculo. Es el equivalente "pesado" del fixture de grilla.

---

## 3. ⚠️ Caveats del archivo (importante)

- **Pesa 5.29 GB.** Gitignoreado (`Documentacion/Videos_flujo/*.mp4`). No commitear.
- **cv2/ffmpeg CRASHEA decodificando secuencial** este .mp4 (segfault a nivel C, sin traceback
  Python). Se reprodujo de forma consistente. **Hay que leerlo por SEEKS** (`CAP_PROP_POS_FRAMES`),
  no con `grab()` secuencial. Los seeks cuestan ~1 s c/u pero son robustos. Las herramientas de
  validación ya usan muestreo por seek con prints de progreso.
- **Vistazo al escritorio (~1 s) a mitad del video:** confirmado inofensivo. El matcher se
  **abstiene** en frames que no son grilla S17 (sin tile/anillo válido → NOLOC, no produce dueño),
  así que ese segundo no inyecta ningún wrong ni contamina la librería. La cosecha solo aprende
  en el flujo-ancla, que requiere estar dentro de un slot del panel de equipamiento.

---

## 4. Cómo usarlo

```bash
# Localización grid vs detalle + discriminación del detalle (muestreo por SEEK, robusto al .mp4
# pesado; bootstrap de etiquetas desde reads confiados del grid):
.venv/Scripts/python.exe tools/validate_detail_badge.py \
    "Documentacion/Videos_flujo/Flujo_Cosecha_badges.mp4" --gate 0.85 --step 600

#   --step grande (p.ej. 600 = 1 muestra cada 10 s a 60 fps) para no tardar horas: el video
#   posa ~10 s por disco, así que 1 muestra cada 10 s ya cae ~1 vez por disco.

# Verdad de tierra de referencia (oráculo del smoke):
.venv/Scripts/python.exe -c "import json; d=json.load(open('audit/equip_map_20260612.json',encoding='utf-8')); print(len(d),'discos')"
```

**Construcción REAL de la librería de detalle (camino recomendado, NO offline):**
rebuild del `.exe` (para hornear `crop_detail_badge` + la cosecha del detalle) → `qa_launch
-BadgeHarvest` → mismo flujo `Pj_stats → Equipamiento → Slots 1-6`. Cosecha grid **y** detalle
en la misma pasada; se puede ir incremental reiniciando cada ~10-15 PJs por la fuga de memoria
(RNF-06). Luego leave-one-out sobre `avatar_detbadge_v2.npz` + QA en vivo.
