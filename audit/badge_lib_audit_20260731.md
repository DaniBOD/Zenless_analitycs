# Auditoría de librerías de badges — 2026-07-31

Read-only (`tools/audit_badge_lib.py`). Cobertura + contaminación por
vecino-extranjero en espacio de descriptores. Correr antes y después de una
re-cosecha (`qa_launch -BadgeHarvest`).

## Superficie `row`

- Refs totales: **0** en **0** PJs (roster: 50).
- ⚠️ **Sin refs (50):** Alice, Anby, Antón, Astra Yao, Ben, Billy, Billy Estelar, Burnice, Cissia, Corin, César, Dialyn, Ellen, Evelyn, Gatillo, Grace, Harumasa, Jane, Ju Fufu, Koleda, Lucy, Lucía, Lycaon, Manato, Miyabi, N.º 0: Anby, N.º 11, Nangong Yu, Nekomata, Nicole, Orfia y Magas, Pan Yinhu, Piper, Pulchra, Pyrois, Qingyi, Remielle Dan, Rina, Seth, Soukaku, Sporos, Sunna, Velina, Vivian, Yanagi, Ye Shunguang, Yixuan, Yuzuha, Zhao, Zhu Yuan
- ✅ Sin sospechas de contaminación (cada ref es más cercana a su propio PJ).

## Superficie `grid`

- Refs totales: **112** en **56** PJs (roster: 50).
- ⚠️ **Cobertura flaca (<3):** Alice (2), Anby (2), Antón (2), Astra Yao (2), Ben (2), Billy (2), Billy Estelar (2), Burnice (2), Cissia (2), Corin (2), César (2), Dialyn (2), Ellen (2), Evelyn (2), Gatillo (2), Grace (2), Harumasa (2), Jane (2), Ju Fufu (2), Koleda (2), Lucy (2), Lucía (2), Lycaon (2), Manato (2), Miyabi (2), N.º 0: Anby (2), N.º 11 (2), Nangong Yu (2), Nekomata (2), Nicole (2), Orfia y Magas (2), Pan Yinhu (2), Piper (2), Pulchra (2), Pyrois (2), Qingyi (2), Remielle Dan (2), Rina (2), Seth (2), Soukaku (2), Sporos (2), Sunna (2), Velina (2), Vivian (2), Yanagi (2), Ye Shunguang (2), Yixuan (2), Yuzuha (2), Zhao (2), Zhu Yuan (2)
- ℹ️ Sembrados de -ico no poseídos (protegidos, esperado): Aria, Banyue, Hugo, Lichter, Promeia, Yidhari
- ✅ Sin sospechas de contaminación (cada ref es más cercana a su propio PJ).

## Superficie `detail`

- Refs totales: **155** en **39** PJs (roster: 50).
- ⚠️ **Sin refs (11):** Antón, Ben, Billy Estelar, Cissia, Harumasa, Lycaon, N.º 0: Anby, Pyrois, Remielle Dan, Rina, Velina
- ✅ Sin sospechas de contaminación (cada ref es más cercana a su propio PJ).
