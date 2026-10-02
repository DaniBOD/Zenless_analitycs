# Correcciones de la DB · farmeo de Claret Flint (2026-10-02)

Sesión de farmeo por baterías en modo escritura (`qa_launch -FromSource -Metrics`), noche del
2026-10-01 al 2026-10-02. Cada corrección: app cerrada (verificado por CommandLine), ensayo sobre
una copia, `apply_migration.py` con backup, transacción, `foreign_key_check` e `integrity_check`.

## 1 · Slot 6 de Claret: #417 en vez de #416 (00:14)

- **Declarado por Daniel:** "lo equipé ahora en claret ese disco pero no lo detecta" — el Tecno
  tetraodóntido slot 6 DEF% Nv 15 (PV +2, DEF +1, Prob. Crítica +1, Maestría +1) = #417.
- **Por qué la app no lo registró:** el check del cambio de dueño vio un disco que no coincidía
  con el pendiente y se abstuvo (`[equipado] ... no coincide con el disco del pendiente → se
  abstiene`, 00:12:16 y 00:12:21).
- **Cambio:** #416 → `equipado=0, agente_asignado=NULL` (el desplazado pierde los dos); #417 →
  `equipado=1, agente_asignado=52`. Los UPDATE llevan el estado previo en el WHERE.
- **Checks:** Claret con 6 equipados, uno solo en slot 6 (#417); FK y integridad ok.
- **Backup:** `db/danibod_zzz_v2.backup_premig_20261002_001444.db`.

## 2 · Dos fantasmas y el slot 1 de Sunna (00:16)

- **Confirmado por Daniel:** "dale, corregí los fantasmas y lo de Sunna".
- **#409 borrado:** Rosa espinosa slot 1 Nv 15, libre, con los mismos stats que #396 (equipado en
  Claret). Lo insertó S9 después de una mejora que terminó en el "Ver", que no confirma mejoras.
- **#411 borrado:** Hado emplumado slot 1 Nv 0, libre. El mismo disco está como #412 (Nv 3, los
  mismos 3 substats y el 4.º desbloqueado). Mismo origen: mejora desde el "Ver" y después S9.
- **#33 re-equipado en Sunna:** Nana slot 1, desplazado a las 00:00:16 cuando S9 leyó el badge de
  Sunna sobre el Rosa espinosa de Claret (#396). #396 volvió solo a Claret por S17; #33 no.
- **Antes:** ninguna fila de `inventory_disc_evaluations` ni `movimientos_discos` apuntaba a
  #409/#411. Los DELETE/UPDATE llevan el estado previo en el WHERE.
- **Checks:** #409 y #411 no existen; Sunna con un solo slot 1 equipado (#33); #396 sigue en
  Claret; #412 intacto; FK e integridad ok.
- **Backup:** `db/danibod_zzz_v2.backup_premig_20261002_001610.db`.

## 3 · Dos fantasmas más (00:25, con la app ya cerrada al final de la sesión)

- **#406 no hizo falta tocarlo:** Daniel equipó en Claret el slot 2 mejorado; S17 escribió el disco
  nuevo en la fila de Claret (#397, clave PJ+slot) y el viejo, al verse libre, coincidió con #406
  —que tenía justo sus stats por el bug de confirmación—. La DB quedó igual que el juego sola.
- **#413 borrado:** Hado emplumado slot 1 Nv 0 (Perforación, Maestría, Prob. Crítica). El disco
  real entró como #418 (Nv 15, los mismos 3 substats + ATK desbloqueado).
- **#419 borrado:** Rosa espinosa slot 4 Prob. Crítica Nv 15, libre, idéntico a #402 (equipado en
  Claret). Lo insertó un `libre_insert` 5 s después de que S17 guardara el disco nuevo en #402 —
  la guarda "libre con la identidad de un equipado" (que sí frenó con #416) acá no actuó.
- **Antes:** nada en `inventory_disc_evaluations` ni `movimientos_discos` apuntaba a #413/#419.
- **Checks:** #418 y #402 intactos; Claret con 6 equipados; FK e integridad ok.
- **Backup:** `db/danibod_zzz_v2.backup_premig_20261002_002525.db`.

## Build de Claret al cierre

4pc Rosa espinosa + 2pc Tecno tetraodóntido, 6/6: #396 (s1), #397 (s2), #398 (s3), #402 (s4,
Prob. Crítica, DEF% +2), #400 (s5, Tasa de Perforación), #417 (s6, **DEF%**, el main que faltaba).

## 4 · Cierre de la sesión de la mañana (12:00) — QA en vivo del SPEC del "Obtenido"

Segunda sesión (10:22 → 11:58) con los 5 commits del SPEC "El Obtenido guarda los discos" activos.
Daniel: "cerrá la app y hacé el cierre". Pares sospechosos buscados con `es_el_mismo_disco` sobre
todas las filas de la sesión, y cada uno contrastado con el log.

- **#404 borrado = #465.** Rosa espinosa s1 Nv 15 (Prob. Crítica +2, DEF% +2, Daño Crítico +1).
  Daniel lo equipó en Claret (11:58:23): S17 hizo `s17_swap` (insertó #465) en vez de adoptar la
  fila libre — no había aviso "libre → PJ" armado. #396 quedó desplazado, con sus stats.
- **#426 borrado = #464.** Rosa espinosa s1, mejorado a Nv 15 sin confirmar (el "Ver" se descartó
  dos veces por confianza 0,69); S9 lo insertó después como #464 (Perforación +2, DEF +2).
- **#443 y #444 borrados = #463.** Hado emplumado s3 Nv 15. #444 era el reinsertado por el roll de
  Maestría mal leído en el Obtenido (arreglado en `b177e4e`); #463 es el `s17_swap` de cuando
  Daniel lo equipó en Remielle (10:57:19), con la grilla leyéndolo "equipado · dueño incierto".
- **#422 → Nv 3** (+ PV% 3 %, DEF 73), del Obtenido 10:24:59: S10 lo leyó ya en Nv 3 y no vio subir.
- **#431 → Nv 3** (+ DEF 15, ATK 126), de la captura de Daniel y el PRE de S10 10:38:42: la captura
  se reinició a las 10:39:25 y la mejora pendiente se perdió.
- Descartados como duplicados (coincidencia de substats, otros discos): #422/#432, #426/#396,
  #457/#2; #446/#447 y #448/#449 tienen mains distintos.
- **Antes:** nada en `inventory_disc_evaluations` ni `movimientos_discos` apuntaba a las borradas.
- **Checks:** #463/#464/#465 intactos; Claret 6 equipados con #465 en s1; #463 en Remielle s3; FK e
  integridad ok. **Backup:** `db/danibod_zzz_v2.backup_premig_20261002_120051.db`.
