# Builds objetivo declarados por Daniel (2026-09-25)

Gatillo y Grace (prioridad alta) llevan un 4pc que su guía de Prydwen no lista. Daniel: "son builds
mías que veo óptimas, dejalo como builds creadas por el usuario". Escritos con
`app.core.build_objetivo.EditorBuildObjetivo` (el mismo camino que usará la ficha del PJ), con la
app cerrada (verificada por CommandLine):

```
sha antes 9904064e4da7
[build] Gatillo → 4pc 41 + 2pc 48      (Armonía umbría + Tecno Pícido)
[build] Grace → 4pc 31 + 2pc 27        (Blues Libre + Jazz Caótico)
backup db\danibod_zzz_v2.backup_prebuild_20260925_092253.db   (uno para la sesión)
declarados: {32: (41, 48), 41: (31, 27)}
integrity ok fk []
sha despues 8316bf936237
```

El motor todavía no lee `ajustes_usuario_build`: ninguna sugerencia cambia hasta el paso del motor.
