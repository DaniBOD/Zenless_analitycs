# Stats S18 después de los swaps de Dialyn y Ju Fufu · 2026-09-25

Daniel repasó en el juego la ficha de atributos (S18) de los PJs afectados por los swaps de
`movimientos_discos` (mig 44). La app corrió desde fuente con escritura, con backup previo.

## Sesión 1 (backup `danibod_zzz_v2.backup_premig_20260925_145802.db`)

| PJ | cambios |
|---|---|
| Dialyn (27) | PV 11.122 → 10.898 · ATK 1.974 → 1.993 · DEF 1.031 → 1.001 · Prob. Crítica 89,8 → 85,0 · Daño Crítico 83,6 → 98,0 · Maestría 138 → 120 |
| Ju Fufu (29) | ATK 3.286 → 3.229 · DEF 925 → 895 · Prob. Crítica 65,0 → 67,4 · Daño Crítico 74,0 → 88,4 |
| Astra Yao (36) | ATK 3.419 → 3.476 · DEF 784 → 814 · Prob. Crítica 24,2 → 21,8 · Daño Crítico 83,6 → 69,2 |
| ⚠️ N.º 0: Anby (30) | recibió la ficha de **Anby**: PV 11.385 · ATK 1.150 · DEF 1.047 · Impacto 160 · Prob. Crítica 48,2 · Daño Crítico 69,2 · Maestría 129 |

La comparación tabla por tabla contra el backup dio sólo esas 4 filas de `agents`.

**Restauración de N.º 0** (backup `…_150412.db`, transacción, `foreign_key_check` vacío,
`integrity_check` ok): los 7 campos de la fila 30 volvieron a los del backup de la sesión 1
(PV 10.558 · ATK 2.909 · DEF 869 · Impacto 93 · Prob. Crítica 53,0 · Daño Crítico 186,0 ·
Maestría 138).

**Causa** (reproducida sobre el frame de la ficha, sesión en sólo lectura): el OCR leyó "pV" y el
banner del rol no se cortaba → rol "Ataque"; y la "n" y el "0" sueltos ("A n b y", "0 Ciudad")
hacían que N.º 0: Anby dominara a Anby. Arreglos `37f1b66` y `6018d1e`.

## Sesión 2, con los arreglos (backup `…_151741.db`)

| PJ | resultado |
|---|---|
| Anby (15) | PV 11.161 → 11.385 · ATK 1.169 → 1.150 · DEF 1.018 → 1.047 · Prob. Crítica 43,4 → 48,2 · Daño Crítico 83,6 → 69,2 · Maestría 111 → 129 |
| N.º 0: Anby (30) | identificada bien; sus valores en pantalla son IGUALES a los restaurados → no escribió nada |

Diferencia contra el backup de la sesión 2: sólo la fila de Anby. `integrity_check` ok, FK vacío.
sha256 final `d15369fc5525`.
