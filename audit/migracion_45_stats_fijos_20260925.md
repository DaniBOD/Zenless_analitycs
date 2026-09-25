# Migración 45 · Stats fijos por PJ (2026-09-25)

Tabla `pj_stats_fijos` (INVESTIGACION): el valor de un stat que el kit de un PJ necesita para que
una pasiva rinda completa. Caso 14 (Gatillo, Prob. Crítica) y el pedido de Daniel ("algunos PJ
requieren un stat fijo… Astra Yao y Zhao"). Kits leídos en Prydwen el 2026-09-25 con la pasiva
núcleo en Lv. 7 (el deslizador de la guía); las cuentas, propias, en la columna `cuenta`.

| PJ | stat | objetivo | cuenta (resumen) |
|---|---|---|---|
| Gatillo | Prob. Crítica | 90 % | +1,5 % aturdimiento de réplicas por 1 % sobre 40 %, hasta +75 % |
| Evelyn | Prob. Crítica | 55 % pantalla | ≥ 80 % en combate; su núcleo da 25 % |
| Dialyn | Prob. Crítica | 100 % | +2 Impacto por 1 % sobre 50 %, hasta +100 |
| Miyabi | Prob. Crítica | 80 % | acumulación +100 % de su Prob. Crítica, hasta 80 % |
| Rina | Tasa de Perforación | 72 % | 25 % de la suya + 12 %, hasta 30 %; 8 ATK por 1 %, hasta 576 |
| Astra Yao | ATK | 3.429 | 35 % del ATK inicial, hasta 1.200 |
| Zhao | PV | 27.000 | +1 % de daño por 400 PV sobre 15.000, hasta 40 % |
| Seth | ATK | 3.750 | escudo 80 % del ATK, hasta 3.000 |
| Soukaku | ATK | 2.500 | +20 % hasta 500 (40 % hasta 1.000 con Vórtice) |
| Sunna | ATK | 1.750 | texto del kit: con 1.750 el buff es máximo |
| Remielle Dan | ATK | 4.000 | 40 % del ATK (3 anómalos), hasta 1.600 |
| Yuzuha | ATK / Maestría | 3.000 / 200 | "con 3.000 da el bono completo" / +0,2 % por punto sobre 100, hasta 20 % |
| Ju Fufu | ATK | 3.400 | ≥ 2.800: +5 % Daño Crítico por 100, hasta +30 % |
| Qingyi | Impacto | 220 | +6 ATK por punto sobre 120, hasta 600 |
| Velina | Recarga de Energía | 2,88 | sobre 1,2: +0,21 % daño y +0,5 Maestría por 0,01, hasta 35 % / 84 |
| 8 PJs con Monarca del Pináculo en la guía | Prob. Crítica | 50 % | 4pc: +15 % extra de Daño Crítico al equipo con ≥ 50 % (sólo si es su 4pc objetivo) |

Fuera, a propósito: umbrales sin tope (Alice AM > 140, Nangong AM > 110), conversiones sin umbral
(PV → Fuerza bruta), Cissia (RE 4,4, inalcanzable), Burnice (texto con un "6" delante: puede ser su
M6, a verificar), Lucy (depende del nivel de su Especial), Harumasa "75 %, no más" (es un techo).

**Supuesto a confirmar con Daniel:** pasivas núcleo al Lv. 7. Astra con núcleo menor necesita más
ATK (Lv. 1: 22 % → 5.455, inalcanzable). Los valores de la pantalla son los de la última pasada de
S18: Dialyn, Anby, Ju Fufu y Astra Yao cambiaron de discos después (mig 44).

Aplicada con la app cerrada: backup `premig_20260925_122826`; 16 filas de kit + 8 de Monarca;
integrity ok. sha `3030cbc67be3` → `ba7d6a89e126`. Tests: `test_stats_fijos.py` (10), 9 sabotajes
en rojo (dos salieron verdes primero y destaparon tests que no discriminaban).
