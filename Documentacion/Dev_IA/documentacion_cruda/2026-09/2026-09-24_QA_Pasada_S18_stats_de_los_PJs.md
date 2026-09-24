# QA en vivo — pasada S18 para cargar los stats de los PJs (2026-09-23/24)

**Para qué.** El motor de discos (Fase A, etapa 1, paso 6) usa los stats ACTUALES del PJ para el
balance del crítico y los rangos, pero desde el rebuild de la DB (2026-08-17) estaban vacíos: CR y
DC en **1 de 52** PJs y ATK en **0**. Daniel recorrió la pestaña *Atributos base* (S18) de cada PJ
con la app en modo escritura (`qa_launch.ps1 -FromSource`, sin `-ReadOnly`).

**Resultado:** CR+DC en **52/52**, ATK en **51/52** (Claret, Armero, no tiene ATK en su ficha).
`integrity_check` ok, sin FKs rotas. Backups de cada arranque: `backup_premig_20260923_211341`,
`…_213528`, `20260924_001803`, `…_003908`, `…_005548`.

La pasada destapó **cinco defectos** de la captura de S18, todos arreglados con un test que falla
antes del arreglo y pasa después. Tres de ellos escribían o podían escribir datos en el PJ
equivocado.

## 1. Una lectura incompleta trababa el panel (Claret)

- **Síntoma:** "[parcial] falta TP (10/11)" a las 21:16:30 y silencio por minutos. Nada se guardó.
- **Hipótesis mía, FALSA:** que el rol de Claret se hubiera clavado en "Defensa". Reproduje el
  mecanismo aislado, pero el dato de Daniel (lo que decía el panel) lo desmintió: era 10/11 con el
  rol bien. La lección: el mecanismo reproducido no prueba que sea el que pasó.
- **Causa:** el gate de firma de S18 (RNF-06) se comprometía con cualquier lectura UTILIZABLE (PV o
  ATK). Una utilizable pero incompleta lo comprometía igual → el panel quieto no se volvía a leer
  y el aggregator no tenía con qué completar. La TP de Claret falta en 1 de cada 6 frames.
  **Corrección (§8):** ese "1 de cada 6" estaba mal medido: sobre 100 frames faltó en 58.
- **Arreglo (`monitor.py`):** una lectura incompleta no compromete la firma, hasta
  `_S18_REINTENTOS_INCOMPLETO = 8` por PJ. Al llegar al tope lo AVISA con lo que falta (antes el
  "[parcial]" iba sólo al panel de la UI, no al log). Volver a entrar a S18 reintenta.
- **El test viejo fijaba el bug:** `test_monitor_dispatch_continuo_re_extrae_en_cambio` usaba una
  lectura de 4 stats sin nombre como la que "compromete". Pasó a una lectura completa.

## 2. "Hoja afilada" se leía como la afiladura del Armero (Ye Shunguang)

- **Síntoma:** "falta ATK, ER" en 8 lecturas seguidas y dos visitas.
- **Causa:** su elemento se muestra **"Hoja afilada"**. La regex de la afiladura buscaba
  `afilad\w*`, así que "afilada PV 11012" daba afiladura = 11012 → pasaba por Armero → se
  descartaban su ATK y su ER (`atk_ignorado_armero`).
- **Arreglo:** el token es `afiladur`. Test con el OCR real de su ficha.
- **De paso:** `test_la_captura_real_coincide_con_la_fila_de_la_migracion` comparaba la captura
  fija de Claret con su fila VIVA en la DB, que esta pasada cambió (PV 8360 → 8754). Ahora compara
  contra la fila de la migración 35, copiada del SQL.

## 3. Nombres en pantalla distintos al roster (Lucy, Nekomata)

- Lucy se muestra **"Luciana de Montefio"** y Nekomata **"Nekomiya Mana"**. Las identificaba la capa
  POR STATS, que desde el rebuild no tiene con qué comparar → nombre None → no se guardaban.
- **Arreglo:** `NOMBRES_EN_PANTALLA` en `parser_agent_stats`, con el nombre sacado de capturas en
  vivo (RNF-02). Un PJ cuyo nombre del roster es palabra de su nombre en pantalla ("Grace" en
  "Grace Howard") no lo necesita.

## 4. Fichas guardadas en el PJ equivocado (Grace, Billy)

- **00:21:22:** una ficha con banner **Soporte/Fuego** (la de Lucy) se guardó en **Grace**
  (Anomalía/Eléctrico). Se sobrescribió con lo correcto 2 s después sólo porque Daniel pasó por Grace.
- **00:40:18 y 00:47:58:** la ficha de **Billy Estelar** (Disruptivos, con Fuerza Bruta) se guardó
  en **Billy** (Ataque). La segunda vez ya se AUTOCONFIRMABA: la identificación por stats comparaba
  contra la fila de Billy envenenada y la "reconocía" exacta.
- **Causas y arreglos:**
  - El nombre leído "Billy Kid Estelar" contiene las palabras de Billy y de Billy Estelar. Decidía el
    bono de rol, y el banner mal recortado leyó "Ataque" (la etiqueta del stat) → Billy. Ahora un
    candidato cuyas palabras están contenidas en las de otro que también se leyó entero queda
    **dominado**: gana el más específico.
  - **El guardado es la última defensa:** no se escribe si el **elemento** de la ficha contradice
    al del PJ. Sólo el elemento, porque el rol del banner osciló entre frames de la misma ficha
    (Soporte ↔ Ataque). Tampoco se escribe si la ficha trae stats **exclusivos** de un rol que no
    es el del PJ (Fuerza Bruta/Adrenalina → Disruptivos, laceración/afiladura → Armero). En vivo
    rechazó la ficha de Billy Estelar para Billy a las 00:56:20.
  - El roster de la identificación se cargaba una vez por proceso; ahora **se refresca después de
    cada guardado**.
- **Orden de reparación que hizo falta:** primero Billy (limpia su fila), después Billy Estelar.

## 5. Riesgo conocido, SIN arreglar: un misread de un frame se persiste

- Anby se guardó con **PV 1161** (real: 11 161). Se perdió un dígito en un frame, la lectura salió
  completa, se guardó y el panel no se volvió a leer. No se pudo reproducir: en la captura posterior
  lee 11 161 en 4 de 4 frames. Se corrigió al volver a pasar. Queda sin un arreglo inventado a
  ciegas (E3); la auditoría de abajo es la red.

## 6. Discrepancias después de la pasada

- **La suite no terminó.** Se cortó en el 60 % (1951 de 3194 tests), probablemente por la pausa de
  la sesión: código de salida 4, sin resumen. Antes de cortarse marcó **un** fallo, ubicado por su
  posición en la colección (`ubicar_f.py` en el scratchpad).
- **El fallo:** `test_estado_pj.py::test_el_repo_carga_los_stats_y_avisa_cuantos_faltan`. Suponía
  que la DB viva tenía PJs sin CR/DC, para que saliera el aviso "N de 52 sin Prob./Daño Crítico".
  Con la pasada pasaron a 52/52 y el aviso desapareció. Arreglo: la copia del test deja sin
  crítico a todos menos a Ellen.
- **Es el segundo test acoplado al estado vivo de la DB en esta misma pasada** (el primero:
  `test_la_captura_real_coincide_con_la_fila_de_la_migracion`, sección 2). Patrón: un test que lee
  la DB de dominio para tener "datos reales" queda atado a los valores de ESE día, y una pasada
  legítima que cambia la cuenta lo rompe. Un test que necesita un estado lo tiene que armar en su
  copia, no heredarlo. Faltan correr los 1243 tests restantes: puede haber más.

## 7. Segunda corrida de verificación (pendiente)

Daniel va a repetir la pasada entera de una sola vez, con todos los arreglos puestos desde el
arranque. El criterio para que esté todo en orden:

- **Punto de partida:** `audit/stats_s18_20260924_final.json` (la foto de los stats de `agents` al
  cerrar esta pasada; sha256 de la DB `ce3d52dd4275…`), 52/52.
- **Lo esperado:** casi ninguna escritura. El syncer sólo escribe lo que CAMBIÓ, así que en una
  cuenta que no cambió entre pasadas, **cada campo que se escriba es una discrepancia**: o esta
  lectura o la anterior estuvo mal (como el PV 1161 de Anby). Se revisan una por una contra la
  pantalla.
- **Sin rechazos** del guardado ("no se persiste"): si aparece alguno, hay un nombre que se sigue
  resolviendo mal.
- **Sin avisos** "sigue incompleto": si aparece alguno, hay un stat que el parser no lee en ese PJ.
- Después: la suite completa, sin la app corriendo, y recién ahí el push.

## 8. Segunda corrida (2026-09-24, mañana): Claret "había que volver a entrar"

- **Síntoma (Daniel):** la primera visita a Claret no completaba; pasando por otro PJ y volviendo,
  sí. El panel decía "falta TP (10/11)".
- **Hipótesis mía, FALSA otra vez:** que un frame de transición le dejaba pegado el rol del PJ
  anterior (Anomalía) en el aggregator. La reproduje aislada, pero el panel de Daniel decía
  "falta TP", no "falta ATK, ER": el rol estaba bien. Segunda vez en esta pasada que un mecanismo
  reproducido no era el que pasó; lo que lo desmiente es el dato de la pantalla, así que se pide
  ANTES de arreglar.
- **Medición:** un script aparte (sólo pixels) leyó 100 frames de Claret mientras Daniel entraba y
  salía. TP=None en **58**, en rachas de hasta 10. Volver a entrar no tenía nada que ver: era azar.
- **Causa:** el OCR de los frames malos es siempre el mismo: `… 79 32 % Acumulación Automática Tasa
  de Perforación 1.5 de afiladura …`. La 1ª línea de la etiqueta vecina ("Acumulación Automática /
  de afiladura") queda entre el valor y su etiqueta; son 24 caracteres y el patrón del orden
  invertido admitía 20. El orden de las cajas cambia frame a frame con el fondo animado.
- **Arreglo (`4582c08`):** esa etiqueta se admite EXPLÍCITA, sin ensanchar la ventana (que podría
  cruzar a otra fila; un sabotaje con ventana 30 hace caer la guarda). Frames reales guardados:
  TP **0/62 → 62/62**.
- **Lo que destapó (`ca6bdcb`):** con la TP arreglada, 6 de esos 62 frames seguían sin **DC**:
  `Dano Critico Critico 93.2 %` (la 2ª línea de "Probabilidad de / Crítico" intercalada). El
  aggregator lo tapaba con otro frame, y le puede pasar a cualquier PJ. Con los dos: **62/62
  completos en una sola lectura**.
- El tope de 8 reintentos (§1) con un 58 % de fallos se alcanzaba en ~1 de cada 80 visitas; con
  el arreglo ya no debería dispararse en Claret.

## 9. Corrida de verificación con los arreglos (2026-09-24, 09:42–11:07): 52/52 ✅

Con todo lo anterior pusheado (hasta `6a32626`, suite 3198/3198), Daniel repitió la pasada entera.
Criterio de §7, cumplido:

- **52/52 PJs leídos y 0 diferencias** contra `audit/stats_s18_20260924_final.json`, campo por
  campo (`cruzar_con_foto.py` en el scratchpad; un sabotaje que fuerza una diferencia la detecta,
  así que el cruce no pasa en vacío).
- **0 escrituras**: el sha de la DB no cambió (`ce3d52dd4275`). Cero discrepancias con la primera
  pasada, incluido el PV de Anby (11 161).
- **0 "no se persiste", 0 "sigue incompleto", 0 errores.**
- **Todos completan al entrar:** 50 en la primera lectura, N.º 11 en 2 s. Claret, en la primera
  lectura: el arreglo de la TP se ve en vivo.
- **Ju Fufu** fue el único que no completó en la pasada: se reconoció y 3 s después Daniel ya
  estaba en el siguiente. Al volver a entrar completó en la primera lectura. No se sabe qué le
  faltaba en esos 3 s (el "[parcial]" va sólo al panel de la UI); no se repitió.
- El log rotó a mitad de la corrida y `app.log` quedó con líneas de un log viejo intercaladas: para
  auditar una corrida hay que leer `app.log.1` + `app.log` y filtrar por la fecha de la línea (las
  líneas de un traceback no la tienen: filtrarlas por prefijo deja pasar tracebacks viejos).

## Auditoría final

`auditar_pasada.py` (scratchpad) cruza cada "Stats agente" del log con la fila final:

- ningún PJ termina con la ficha de otro elemento;
- Grace, Billy y Anby tuvieron fichas distintas escritas, y su ÚLTIMA escritura es la correcta;
- no hay valores implausibles (Nv 60 con PV < 5000 o ATK < 800);
- Claret tiene **CR 109,6 %**: real, la sobrepasa con los discos. El balance del crítico la trata
  como tope (≥ 100 → la CR no suma).
