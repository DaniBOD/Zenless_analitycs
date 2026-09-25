# Movimientos registrados · Dialyn y Ju Fufu (2026-09-25)

Daniel aplicó en el juego las dos primeras sugerencias firmes de
`audit/sugerencias/20260925_100942_416192` y pidió registrarlas "para que tenga trazabilidad".
Tabla nueva `movimientos_discos` (mig 44, backup `premig_20260925_120829`), escrita con
`app.core.movimientos.EditorMovimientos`, con la app cerrada (verificada por CommandLine).
El desplazado queda LIBRE (invariante del 2026-07-22: el juego no recuerda quién lo llevaba).

```
sha antes 8316bf936237 · tras mig 44 0e61acc87a70 · después 3030cbc67be3
lote 2026-09-25T12:08:29 · backup db\danibod_zzz_v2.backup_premovimientos_20260925_120829.db
antes:   85 Anby(15) · 86 Dialyn(27) · 92 libre · 188 Astra Yao(36) · 189 Ju Fufu(29) · 192 libre
después: 85 Dialyn   · 86 libre      · 92 Anby  · 188 Ju Fufu      · 189 libre      · 192 Astra Yao
integrity ok · fk []
```

| disco | slot | de | a | motivo |
|---|---|---|---|---|
| #86 | 3 | Dialyn | — | desplazado |
| #85 | 3 | Anby | Dialyn | equipa |
| #92 | 3 | libre | Anby | equipa |
| #189 | 1 | Ju Fufu | — | desplazado |
| #188 | 1 | Astra Yao | Ju Fufu | equipa |
| #192 | 1 | libre | Astra Yao | equipa |

Deducido, no observado (A4): que #86 y #189 quedaron libres (un slot lleva un disco; Daniel no
contó haberlos equipado en otro PJ). La próxima pasada de captura lo confirma o lo corrige.

La tercera sugerencia (#151 N.º 0: Anby → Gatillo) NO se aplicó: Daniel, "tiene en la pasiva más
impacto a cuanta más probabilidad tenga" — caso 14, stats fijos.
