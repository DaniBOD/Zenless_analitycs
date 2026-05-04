# Auditoría inventory_discs — 2026-05-04

**DB:** `db\danibod_zzz_v2.db`
**Total discos:** 334  
**Fecha auditoría:** 2026-05-04

## 1. Distribución de tipos en val1–val4

| Columna | NULL | REAL | INTEGER | TEXT |
|---------|-----:|-----:|--------:|-----:|
| `val1` | 0 | 185 | 0 | 149 |
| `val2` | 0 | 185 | 0 | 149 |
| `val3` | 0 | 203 | 0 | 131 |
| `val4` | 5 | 198 | 0 | 131 |

> Total TEXT (requieren conversión): **560** · Total numérico: **771**

## 2. Strings únicos en main_stat y sub1–sub4

**Canónicos** (8): `Bono Daño Eléctrico`, `Bono Daño Físico`, `Daño Crítico`, `Impacto`, `Perforación`, `Probabilidad de Crítico`, `Recuperación de Energía`, `Tasa de Perforación`

**Aliases** (6) — mapean a un canónico conocido:

| String observado | → Canónico | Ocurrencias |
|-----------------|-----------|------------|
| `Ataque` | `ATK` | 187 |
| `Defensa` | `DEF` | 136 |
| `Maestría Anomalía` | `Maestría de Anomalía` | 151 |
| `PV` | `HP` | 124 |
| `PV %` | `HP%` | 81 |
| `Prob Crítico` | `Prob. Crítica` | 239 |

**⚠️ Desconocidos** (12) — no mapean a ningún canónico ni alias conocido:

| String | Ocurrencias |
|--------|------------|
| `Ataque %` | 127 |
| `Ataque%` | 67 |
| `Bono Daño Etéreo` | 2 |
| `Bono Daño Glacial` | 4 |
| `Bono Daño Ígneo` | 9 |
| `Defensa %` | 67 |
| `Defensa%` | 26 |
| `PV%` | 42 |
| `Rec Energía` | 3 |
| `Recuperación Energía` | 5 |
| `Tasa Anomalía` | 11 |
| `Tasa Perforación` | 2 |

## 3. Valores fuera de rango

> ✅ Ningún disco con valores fuera de rango.

## 4. Foreign keys rotas

> ✅ Ninguna FK rota.

## 5. main_stat inválido por slot

⚠️ **287 disco(s) con main_stat inválido para su slot:**

| id | slot | main_stat observado | Mains esperadas |
|----|------|---------------------|----------------|
| 1 | 1 | `PV` | HP |
| 2 | 2 | `Ataque` | ATK |
| 3 | 3 | `Defensa` | DEF |
| 5 | 5 | `Bono Daño Glacial` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 6 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 7 | 1 | `PV` | HP |
| 8 | 2 | `Ataque` | ATK |
| 9 | 3 | `Defensa` | DEF |
| 10 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 11 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 12 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 13 | 1 | `PV` | HP |
| 14 | 2 | `Ataque` | ATK |
| 15 | 3 | `Defensa` | DEF |
| 16 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 17 | 5 | `Tasa Perforación` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 18 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 19 | 1 | `PV` | HP |
| 20 | 2 | `Ataque` | ATK |
| 21 | 3 | `Defensa` | DEF |
| 22 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 24 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 25 | 1 | `PV` | HP |
| 26 | 2 | `Ataque` | ATK |
| 27 | 3 | `Defensa` | DEF |
| 28 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 30 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 31 | 1 | `PV` | HP |
| 32 | 2 | `Ataque` | ATK |
| 33 | 3 | `Defensa` | DEF |
| 34 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 35 | 5 | `Tasa Perforación` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 36 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 37 | 1 | `PV` | HP |
| 38 | 2 | `Ataque` | ATK |
| 39 | 3 | `Defensa` | DEF |
| 40 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 42 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 43 | 1 | `PV` | HP |
| 44 | 2 | `Ataque` | ATK |
| 45 | 3 | `Defensa` | DEF |
| 46 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 47 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 48 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 49 | 1 | `PV` | HP |
| 50 | 2 | `Ataque` | ATK |
| 51 | 3 | `Defensa` | DEF |
| 52 | 4 | `Ataque %` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 53 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 54 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 55 | 1 | `PV` | HP |
| 56 | 2 | `Ataque` | ATK |
| 57 | 3 | `Defensa` | DEF |
| 58 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 60 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 61 | 1 | `PV` | HP |
| 62 | 2 | `Ataque` | ATK |
| 63 | 3 | `Defensa` | DEF |
| 65 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 66 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 67 | 1 | `PV` | HP |
| 68 | 2 | `Ataque` | ATK |
| 69 | 3 | `Defensa` | DEF |
| 71 | 5 | `Bono Daño Glacial` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 72 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 73 | 1 | `PV` | HP |
| 74 | 2 | `Ataque` | ATK |
| 75 | 3 | `Defensa` | DEF |
| 77 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 78 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 79 | 1 | `PV` | HP |
| 80 | 2 | `Ataque` | ATK |
| 81 | 3 | `Defensa` | DEF |
| 83 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 84 | 1 | `PV` | HP |
| 85 | 2 | `Ataque` | ATK |
| 86 | 3 | `Defensa` | DEF |
| 88 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 89 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 90 | 1 | `PV` | HP |
| 91 | 2 | `Ataque` | ATK |
| 92 | 3 | `Defensa` | DEF |
| 94 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 95 | 6 | `Rec Energía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 96 | 1 | `PV` | HP |
| 97 | 2 | `Ataque` | ATK |
| 98 | 3 | `Defensa` | DEF |
| 101 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 102 | 1 | `PV` | HP |
| 103 | 2 | `Ataque` | ATK |
| 104 | 3 | `Defensa` | DEF |
| 106 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 107 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 108 | 1 | `PV` | HP |
| 109 | 2 | `Ataque` | ATK |
| 110 | 3 | `Defensa` | DEF |
| 111 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 113 | 6 | `Rec Energía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 114 | 1 | `PV` | HP |
| 115 | 2 | `Ataque` | ATK |
| 116 | 3 | `Defensa` | DEF |
| 119 | 6 | `Rec Energía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 120 | 1 | `PV` | HP |
| 121 | 2 | `Ataque` | ATK |
| 122 | 3 | `Defensa` | DEF |
| 123 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 124 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 126 | 1 | `PV` | HP |
| 127 | 2 | `Ataque` | ATK |
| 128 | 3 | `Defensa` | DEF |
| 129 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 130 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 132 | 1 | `PV` | HP |
| 133 | 2 | `Ataque` | ATK |
| 134 | 3 | `Defensa` | DEF |
| 135 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 138 | 1 | `PV` | HP |
| 139 | 2 | `Ataque` | ATK |
| 140 | 3 | `Defensa` | DEF |
| 141 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 142 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 144 | 1 | `PV` | HP |
| 145 | 2 | `Ataque` | ATK |
| 146 | 3 | `Defensa` | DEF |
| 147 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 150 | 1 | `PV` | HP |
| 151 | 2 | `Ataque` | ATK |
| 152 | 3 | `Defensa` | DEF |
| 153 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 154 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 155 | 6 | `PV %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 156 | 1 | `PV` | HP |
| 157 | 2 | `Ataque` | ATK |
| 158 | 3 | `Defensa` | DEF |
| 160 | 5 | `Bono Daño Etéreo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 161 | 6 | `PV %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 162 | 1 | `PV` | HP |
| 163 | 2 | `Ataque` | ATK |
| 164 | 3 | `Defensa` | DEF |
| 167 | 6 | `Ataque%` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 168 | 1 | `PV` | HP |
| 169 | 2 | `Ataque` | ATK |
| 170 | 3 | `Defensa` | DEF |
| 171 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 172 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 173 | 6 | `Ataque%` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 174 | 1 | `PV` | HP |
| 175 | 2 | `Ataque` | ATK |
| 176 | 3 | `Defensa` | DEF |
| 177 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 178 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 179 | 6 | `Recuperación Energía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 180 | 1 | `PV` | HP |
| 181 | 2 | `Ataque` | ATK |
| 182 | 3 | `Defensa` | DEF |
| 183 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 184 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 185 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 186 | 1 | `PV` | HP |
| 187 | 2 | `Ataque` | ATK |
| 188 | 3 | `Defensa` | DEF |
| 191 | 6 | `Recuperación Energía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 192 | 1 | `PV` | HP |
| 193 | 2 | `Ataque` | ATK |
| 194 | 3 | `Defensa` | DEF |
| 195 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 196 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 197 | 6 | `Tasa Anomalía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 198 | 1 | `PV` | HP |
| 199 | 2 | `Ataque` | ATK |
| 200 | 3 | `Defensa` | DEF |
| 201 | 4 | `Ataque%` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 202 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 203 | 6 | `Ataque%` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 204 | 1 | `PV` | HP |
| 205 | 2 | `Ataque` | ATK |
| 206 | 3 | `Defensa` | DEF |
| 207 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 208 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 210 | 1 | `PV` | HP |
| 211 | 2 | `Ataque` | ATK |
| 212 | 3 | `Defensa` | DEF |
| 213 | 4 | `Ataque%` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 214 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 215 | 6 | `Ataque%` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 216 | 1 | `PV` | HP |
| 217 | 2 | `Ataque` | ATK |
| 218 | 3 | `Defensa` | DEF |
| 219 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 222 | 1 | `PV` | HP |
| 223 | 2 | `Ataque` | ATK |
| 224 | 3 | `Defensa` | DEF |
| 225 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 227 | 6 | `Recuperación Energía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 228 | 1 | `PV` | HP |
| 229 | 2 | `Ataque` | ATK |
| 230 | 3 | `Defensa` | DEF |
| 231 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 232 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 233 | 6 | `Ataque%` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 234 | 1 | `PV` | HP |
| 235 | 2 | `Ataque` | ATK |
| 236 | 3 | `Defensa` | DEF |
| 237 | 4 | `PV%` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 238 | 5 | `PV%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 239 | 6 | `PV%` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 240 | 1 | `PV` | HP |
| 241 | 2 | `Ataque` | ATK |
| 242 | 3 | `Defensa` | DEF |
| 243 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 244 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 245 | 6 | `Ataque%` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 246 | 1 | `PV` | HP |
| 247 | 2 | `Ataque` | ATK |
| 248 | 3 | `Defensa` | DEF |
| 249 | 4 | `PV%` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 250 | 5 | `PV%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 251 | 6 | `PV%` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 252 | 1 | `PV` | HP |
| 253 | 2 | `Ataque` | ATK |
| 254 | 3 | `Defensa` | DEF |
| 255 | 4 | `Ataque%` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 256 | 5 | `Ataque%` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 257 | 6 | `Recuperación Energía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 258 | 5 | `PV %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 259 | 3 | `Defensa` | DEF |
| 260 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 261 | 1 | `PV` | HP |
| 262 | 1 | `PV` | HP |
| 263 | 2 | `Ataque` | ATK |
| 264 | 2 | `Ataque` | ATK |
| 265 | 2 | `Ataque` | ATK |
| 266 | 2 | `Ataque` | ATK |
| 267 | 3 | `Defensa` | DEF |
| 269 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 270 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 271 | 1 | `PV` | HP |
| 272 | 1 | `PV` | HP |
| 273 | 1 | `PV` | HP |
| 274 | 2 | `Ataque` | ATK |
| 275 | 2 | `Ataque` | ATK |
| 276 | 2 | `Ataque` | ATK |
| 277 | 2 | `Ataque` | ATK |
| 278 | 3 | `Defensa` | DEF |
| 279 | 3 | `Defensa` | DEF |
| 280 | 3 | `Defensa` | DEF |
| 281 | 3 | `Defensa` | DEF |
| 284 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 287 | 1 | `PV` | HP |
| 288 | 2 | `Ataque` | ATK |
| 289 | 2 | `Ataque` | ATK |
| 290 | 2 | `Ataque` | ATK |
| 291 | 3 | `Defensa` | DEF |
| 292 | 3 | `Defensa` | DEF |
| 293 | 3 | `Defensa` | DEF |
| 294 | 5 | `PV %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 295 | 5 | `PV %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 296 | 1 | `PV` | HP |
| 297 | 4 | `Maestría Anomalía` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 298 | 3 | `Defensa` | DEF |
| 300 | 5 | `Bono Daño Glacial` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 301 | 1 | `PV` | HP |
| 302 | 1 | `PV` | HP |
| 303 | 3 | `Defensa` | DEF |
| 306 | 6 | `Ataque %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 307 | 1 | `PV` | HP |
| 308 | 1 | `PV` | HP |
| 309 | 3 | `Defensa` | DEF |
| 310 | 5 | `Bono Daño Ígneo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 312 | 6 | `Recuperación Energía` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 313 | 3 | `Defensa` | DEF |
| 314 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 315 | 4 | `Prob Crítico` | ATK%, DEF%, Daño Crítico, HP%, Maestría de Anomalía, Prob. Crítica, Probabilidad de Crítico, Tasa de Perforación |
| 316 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 318 | 6 | `PV %` | ATK%, DEF%, HP%, Impacto, Impacto (%), Maestría de Anomalía, Recarga de Energía, Recuperación de Energía |
| 319 | 2 | `Ataque` | ATK |
| 320 | 3 | `Defensa` | DEF |
| 321 | 1 | `PV` | HP |
| 322 | 3 | `Defensa` | DEF |
| 323 | 5 | `Ataque %` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 324 | 3 | `Defensa` | DEF |
| 325 | 3 | `Defensa` | DEF |
| 326 | 2 | `Ataque` | ATK |
| 327 | 1 | `PV` | HP |
| 328 | 3 | `Defensa` | DEF |
| 330 | 5 | `Bono Daño Glacial` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |
| 331 | 5 | `Bono Daño Etéreo` | ATK%, Bono Daño Eléctrico, Bono Daño Fuego, Bono Daño Físico, Bono Daño Hielo, Bono Daño Éter, DEF%, HP%, Tasa de Perforación |

## 6. Hallazgo conocido — ids 54 y 185

Discos reportados en Roadmap §2.0.1 con `main_stat='Tasa Anomalía 30%'` en slot 6 (inválido):

| id | slot | main_stat | sub1 | sub2 | sub3 | sub4 | nivel | equipado |
|----|------|-----------|------|------|------|------|-------|---------|
| 54 | 6 | `Tasa Anomalía` | Ataque % | Defensa % | Prob Crítico | Daño Crítico | 15 | 1 |
| 185 | 6 | `Tasa Anomalía` | Daño Crítico | PV | Perforación | Prob Crítico | 15 | 1 |

> **Diagnóstico probable:** confusión OCR/transcripción entre 'Tasa Anomalía' y 'Maestría de Anomalía'.
> Corrección pendiente en Hito 2.0.4 (re-estandarización).

## 7. Resumen ejecutivo

| Categoría | Hallazgos |
|-----------|----------|
| Total discos auditados | 334 |
| Valores TEXT en val1-4 (requieren conversión) | 560 |
| Stats alias (mapean a canónico) | 6 tipos distintos |
| Stats desconocidos | 12 |
| Discos con valores fuera de rango | 0 |
| Discos con FK rotas | 0 |
| Discos con main_stat inválido por slot | 287 |

**Acción requerida:** Ejecutar Hito 2.0.2 (stats_vocab.py) + Hito 2.0.3 (migración 06) + Hito 2.0.4 (re-estandarización).

---
*Generado automáticamente por `app/scripts/audit_inventory_discs.py` · Read-only, no modifica DB.*