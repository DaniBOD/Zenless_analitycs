# Auditoría de librerías de badges — 2026-07-19

Read-only (`tools/audit_badge_lib.py`). Cobertura + contaminación por
vecino-extranjero en espacio de descriptores. Correr antes y después de una
re-cosecha (`qa_launch -BadgeHarvest`).

## Superficie `row`

- Refs totales: **355** en **49** PJs (roster: 49).
- ✅ Cobertura completa, todos los nombres canónicos.
- ⚠️ **Sospecha de contaminación (3 refs):** ref etiquetada como X pero más cercana a otro PJ:
  - `N.º 11` → se parece más a `Ben` (1 ref(s), Δ=0.573)
  - `Yuzuha` → se parece más a `Orfia y Magas` (1 ref(s), Δ=0.099)
  - `Velina` → se parece más a `Billy Estelar` (1 ref(s), Δ=0.030)

## Superficie `grid`

- Refs totales: **1598** en **56** PJs (roster: 49).
- ℹ️ Sembrados de -ico no poseídos (protegidos, esperado): Aria, Banyue, Hugo, Lichter, Promeia, Seed, Yidhari
- ✅ Cobertura completa, todos los nombres canónicos.
- ⚠️ **Sospecha de contaminación (2 refs):** ref etiquetada como X pero más cercana a otro PJ:
  - `Piper` → se parece más a `Antón` (1 ref(s), Δ=0.070)
  - `Cissia` → se parece más a `Evelyn` (1 ref(s), Δ=0.025)

## Superficie `detail`

- Refs totales: **250** en **49** PJs (roster: 49).
- ⚠️ **Cobertura flaca (<3):** Lycaon (1)
- ⚠️ **Sospecha de contaminación (8 refs):** ref etiquetada como X pero más cercana a otro PJ:
  - `Lycaon` → se parece más a `Nangong Yu` (1 ref(s), Δ=0.541)
  - `Nangong Yu` → se parece más a `Koleda` (1 ref(s), Δ=0.244)
  - `Sporos` → se parece más a `Seth` (1 ref(s), Δ=0.142)
  - `Antón` → se parece más a `Pan Yinhu` (1 ref(s), Δ=0.141)
  - `Ben` → se parece más a `Koleda` (1 ref(s), Δ=0.129)
  - `N.º 11` → se parece más a `Soukaku` (1 ref(s), Δ=0.083)
  - `Seth` → se parece más a `N.º 0: Anby` (1 ref(s), Δ=0.062)
  - `N.º 0: Anby` → se parece más a `Seth` (1 ref(s), Δ=0.045)
