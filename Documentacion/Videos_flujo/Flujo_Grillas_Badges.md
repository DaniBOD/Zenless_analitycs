# Fixture de test — Flujo_Grillas_Badges.mp4

**Video:** `Flujo_Grillas_Badges.mp4` (LOCAL, gitignoreado — pesa ~271 MB)
**Capturado:** 2026-06-12 · 2560×1440 · 60 fps · ~230 s · 13801 frames
**Flujo:** Nangong Yu → Stats → Equipamiento → Slot 1 → recorrido de los **20 discos**
de la grilla, posando **~10 s en cada uno** (mucha variación de frame por disco).

Es el **primer fixture de regresión** del pipeline de identificación de dueño en grilla
S17 (Fase 5R). Un video + su tabla de verdad de tierra = test end-to-end de
localización + recorte + match + voto.

---

## 1. Verdad de tierra — posición → PJ dueño (Nangong Yu · slot 1)

Confirmada por el usuario. Cambio vs la versión previa (Ejemplo1 de
`16_discos_pj_grilla`): **pos 5 ahora = Ben** (antes estaba LIBRE).

| Pos | Dueño        | Pos | Dueño     |
|-----|--------------|-----|-----------|
| 1   | Nangong Yu   | 11  | Jane      |
| 2   | Yuzuha       | 12  | Grace     |
| 3   | **LIBRE**    | 13  | Burnice   |
| 4   | Yanagi       | 14  | Vivian    |
| 5   | **Ben**      | 15  | César     |
| 6   | Piper        | 16  | Gatillo   |
| 7   | Seth         | 17  | Soukaku   |
| 8   | **LIBRE**    | 18  | Nicole    |
| 9   | Dialyn       | 19  | Sunna     |
| 10  | Rina         | 20  | Lucía     |

- **Look-alikes de la watch-list presentes:** Ben (pos 5), Soukaku (pos 17).
- **LIBRE (sin dueño — nunca debe dar un PJ; sería wrong RNF-02):** pos **3** y **8**.

---

## 2. Test aplicado

Diagnóstico del gap "dueño incierto" en vivo (QA previo: ~31-47% identificados,
0 wrong, resto incierto/no-localizado, **no determinista entre pasadas**).

### Hallazgo raíz
El descriptor NO es el problema (clava con conf 0.9+ cuando el recorte sale limpio,
0 wrong). El cuello es el **recorte del GRID-badge** (avatar chico en la esquina del
tile), con dos fallas:
- **NOLOC (~27% de frames):** capturado mid-transición, sin anillo de selección estable.
- **Confound de arte amarillo:** la detección del anillo (HSV amarillo/lima) se confunde
  con el arte de los discos "llama" (mismo hue) → bbox corrido → crop degenerado → incierto.

### Fuente alternativa evaluada: DETALLE-badge
El avatar del dueño al lado de "Nivel 15/15" en el panel de detalle. Posición fija-en-X
(cx≈0.495), fondo oscuro (sin arte), siempre presente → esquiva ambas fallas. Localizador
por blob saturado, robusto al corrimiento en Y (nombre 1 vs 2 líneas).

### Resultados (medidos sobre este video)

| Métrica | GRID-badge (actual) | DETALLE-badge (nuevo) |
|---------|---------------------|------------------------|
| **Localización** (345 frames) | 252/345 = **73%** | 345/345 = **100%** |
| Calidad de crop | variable (degenerados) | limpia, centrada |
| Matchea librería del grid | sí | no (framing distinto → librería propia) |
| **Discriminación** (leave-one-out) | 90.6% / 0.9% wrong (offline 47/47) | _(en medición — ver §4)_ |

**Conclusión:** el detalle-badge resuelve la localización (100% vs 73%) pero requiere su
PROPIA cosecha de refs. Plan: `crop_detail_badge` + librería de detalle + usarlo como
señal primaria en S17, con el grid-badge de respaldo.

---

## 3. Cómo re-correr los tests sobre este video

```bash
# Tasa de localización grid vs detalle + discriminación del detalle (bootstrap de
# etiquetas desde los reads confiados del grid, que son 0-wrong):
.venv/Scripts/python.exe tools/validate_detail_badge.py \
    "Documentacion/Videos_flujo/Flujo_Grillas_Badges.mp4" --gate 0.85 --step 12

# Volcado de diagnóstico en vivo (recortes + verdicto por disco):
#   tools/qa_launch.ps1 -ReadOnly -GridDiag "audit\grid_diag"
#   luego: python tools/inspect_grid_diag.py
```

---

## 4. Discriminación del detalle-badge (leave-one-out, etiquetas bootstrap del grid)

`validate_detail_badge.py --gate 0.85 --step 12`:

```
Owners etiquetados (grid conf>=0.85): 3 | detalle-crops: 11
TOP-1: 11/11 = 100%  |  ABST: 0%  |  WRONG: 0%
Owners: Dialyn(3), Nicole(2), Rina(6)
```

**100% top-1, 0 wrong — pero muestra fina (3 owners).** El bootstrap sólo etiqueta los
PJs que el grid leyó con conf≥0.85 en un frame que además tenía detalle-crop limpio →
intersección chica. Los detalle-crops son limpios y consistentes por owner (Rina 6/6
casi idénticos: `audit/grid_diag/_det_rina.png`).

**Limitación:** no cubre los 47. El número completo requiere una **cosecha de detalle**
real (flujo-ancla → librería de detalle etiquetada por latch certero) y su leave-one-out.
Señal suficiente para implementar: el mismo descriptor da 90.6% sobre los crops MÁS
ruidosos del grid; el detalle (más limpio + 100% loc) debería igualar o superar.

### Próximo (C.4)
`crop_detail_badge` en el detector + modo detail-harvest (env-gated) → cosecha → medición
definitiva + uso como señal primaria en S17 con grid de respaldo.
