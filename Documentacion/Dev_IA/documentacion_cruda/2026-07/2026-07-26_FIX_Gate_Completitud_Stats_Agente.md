# FIX — Gate de completitud en los stats de agente (S18)

**Fecha:** 2026-07-26 · **Pedido de Daniel** · **Suite:** 1226 passed, 7 skipped

> *"Cuando veo algún evento o pantalla que determina una stat de vida o ataque salta ese log como
> FP. ¿Podés robustecer offline, para que salte el log cuando ya tenga todos los datos —nombre y
> todos los stats—? Si salen 10/11 no sería válido."*

---

## Lo que el pedido no decía, y es lo que más importa

El punto del controller que emite ese log **también persiste a `agents`**
(`AgentStatsSyncer.sync`, update parcial de los campos que cambiaron). Así que un parcial de dos
stats leído en una pantalla ajena **escribía esos dos campos en la DB**.

El pedido era de UX; el problema era de datos. Abstenerse hasta tener el dato completo es lo que
manda RNF-02, no una preferencia de presentación.

## Medido antes de implementar

La duda que justificaba medir: si AD (Acumulación de Adrenalina) fuera crónicamente ilegible
—como sugería una nota vieja—, exigir 11/11 dejaría a los **Disruptivos sin loguear nunca**.

**Los 14 fixtures reales de S18, un frame cada uno:**

| Resultado | Cuántos |
|---|---|
| nombre + 11/11 | **13** (incluye los 2 Disruptivos: Yixuan, Billy Estelar) |
| incompleto | 1 (`ejemplo_14`/Pyrois, pierde CD) |

⇒ El gate es viable y **no apaga el log de ningún rol**. En vivo será mejor todavía, porque el
aggregator fusiona entre frames.

**Los 33 negativos del corpus anti-FP:** solo dos filtran stats — `Guia_Rapida_1` (Nv) y
`Guia_Rapida_4` (**Nv + PV**, literalmente "una stat de vida"). **Ninguno llega a 11/11.**

### Lo que NO se pudo reproducir

La pantalla de evento exacta que vio Daniel **no está en el corpus**, y las dos que filtran stats
**no llegan a S18 por ningún camino** (`_deep_detect_s18` devuelve `None` en ambas). El gate las
corta por construcción, pero el camino del FP queda sin confirmar. Si reaparece, esa captura debe
sumarse a `Triggers_Generales/Falsos_positivos/`.

## Implementación

La lógica de "qué stats requiere este rol" estaba **inline en el controller**. Se movió a
`app/core/parser_agent_stats.py` como funciones puras — es lógica de dominio (lo dicta el juego,
no la UI) y el gate decide una escritura, así que tiene que probarse sin Qt:

```python
required_stat_keys(stats) -> tuple[str, ...]   # 9 comunes + 2 role-specific
missing_stat_labels(stats) -> list[str]        # etiquetas del log: ["CD", "MA"]
stats_completos(stats) -> bool                 # nombre + los 11
```

Los dos slots inferiores siguen siendo mutuamente excluyentes (Disruptivos: FB+AD · resto:
TP+ER) y sin rol identificado se asume no-disruptivo, que es el caso mayoritario.

**En el controller:**

- Sin completitud → **ni log ni sync**. Con completitud → las 3 líneas de siempre + sync.
- **No es un return mudo** (el bug histórico del proyecto): emite una línea por cada combinación
  **nueva** de faltantes. Pasar de 8/11 a 10/11 vuelve a avisar —es progreso visible—; repetir el
  mismo parcial calla.
  ```
  [parcial] stats sin registrar — falta CD, MA (9/11 leídos; el aggregator completa en los próximos ciclos)
  ```
- **El panel de la UI se actualiza igual.** Es un binding de datos, no un registro: si se
  congelara, el usuario no vería que el sistema está leyendo.

### Un detalle con test propio

`missing` compara contra `None`, **no por falsedad**. `TP = 0.0` e `IMP = 0` son valores reales y
frecuentes (casi todo el roster tiene TP en 0); tratarlos como ausentes habría dejado a esos PJs
permanentemente incompletos — un gate que se ve correcto y apaga medio roster.

## Contrato de test actualizado

`test_agent_stats_log_edge_triggered` (en `test_controller_graceful`) codificaba el contrato
viejo: usaba un parcial de 4/11 y esperaba 3 líneas de log. Su intención —edge-triggering, `conf`
inocua, reset por cambio de estado— **no cambió**; se le cambió el fixture a completo y quedó
anotado el motivo en el docstring. La conducta del parcial ahora vive en
`test_controller_stats_gate`.

## Archivos

**Nuevos:** `app/tests/unit/test_agent_stats_completitud.py` (10) ·
`app/tests/unit/test_controller_stats_gate.py` (9)

**Tocados:** `app/core/parser_agent_stats.py` (3 funciones puras + labels) ·
`app/ui/controller.py` (gate + dedup del parcial; se borró la rama `[parcial]` final, ya
inalcanzable) · `app/tests/unit/test_controller_graceful.py` (fixture del contrato).
