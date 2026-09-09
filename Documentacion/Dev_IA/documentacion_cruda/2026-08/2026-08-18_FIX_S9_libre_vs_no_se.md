# S9: "está libre" y "no pude leer" dejan de ser la misma respuesta

> **2026-08-18** · `app/core/detector.py`, `app/core/monitor.py`
> Desbloquea la persistencia de los **72 discos sin dueño** (20 % del inventario), que era el
> bloqueante real del censo de discos.

---

## 1. El dato no faltaba: se tiraba

`crop_s9_selected_badge` devolvía `None` en dos situaciones que no se parecen en nada:

- **no se localizó el tile** seleccionado — no se pudo leer;
- **se leyó y no hay avatar** — el disco está libre.

La función distinguía los dos casos internamente y los colapsaba al devolver. Sin esa distinción no
se puede persistir un disco suelto: registrar como libre algo que no se pudo leer equivale a
declarar suelto un disco que alguien tiene equipado.

`equip_libre` ya existía en `DiscParsed` y lo llenaba el camino de S17 (con su árbitro por el panel
de detalle, validado en junio). **S9 nunca lo tocaba.**

## 2. Por qué el gate que ya estaba no servía

`_grid_badge_present` exige blob saturado + anillo de Hough. Medido sobre los fixtures de
`09_Inventario_discos_general`, da **`True` en los 4 discos libres**: la esquina de un tile libre
tiene la barra amarilla de nivel y el arte gris del disco, con saturación y circularidad de sobra.

No es una sorpresa — es la tercera vez que aparece el mismo hallazgo:

| dónde | qué se midió | conclusión |
|---|---|---|
| S17, junio 2026 | blob 719-1249 en libres vs 245-333 en avatares de baja saturación | *"no existe umbral que la separe"* |
| RF-15 armas, julio | área saturada libre 0-8002 vs dueño 103-7157 | **se solapa**; nitidez separa 11× |
| **S9, esta nota** | blob libre 861-1890 dentro del rango equipado 375-2527 | **se solapa** |

**Brillo y saturación miden el resplandor del arte. La nitidez mide detalle — y una cara tiene
detalle, un degradé no tiene ninguno.**

## 3. La calibración

|Laplaciano| medio del disco interior (55 % del lado), sobre los 11 tiles etiquetados a ojo:

```
equipado   55.89 – 81.44      (n=7)
libre      12.51 – 15.70      (n=4)      gap 3.56×
```

Y sobre los **504 tiles** de la grilla completa de los 14 fixtures, la distribución es bimodal:

```
  0- 10  ###########################  79
 10- 15  ##############               43
 15- 20                                1
 20- 25                                0     ← franja vacía
 25- 30                                0
 30- 35                                0
 35- 40                                1
 40- 45  #                             3
 45- 50  #                             5
 50- 60  ########                     25
 60- 70  ################################ 146
 70- 80  #####################        104
 80- 90  ##############               67
```

**En 20–35 no cae ninguna muestra.** El umbral de 30 no está afinado al borde de una clase: está en
el medio de un hueco. Sólo 4 de 504 (0,8 %) caen en la zona 20–45.

## 4. Lo que cambia en el código

`read_s9_selected_badge` devuelve tres estados —`con_dueno` / `libre` / `no_localizado`— con la
nitidez como evidencia. `crop_s9_selected_badge` sobrevive con el mismo contrato (recorte o `None`)
y pasa a ser su vista de un campo, así que ningún llamador se entera salvo que quiera preguntar
**por qué**.

En el monitor, `_assign_s9_owner` marca `equip_libre=True` cuando el lector lo afirma, y el warmup
del dueño **corta ahí**: reintentar el badge de un disco que ya se sabe libre es esperar algo que no
va a aparecer. Antes esos discos agotaban el techo de ciclos porque "no tiene dueño" no se
distinguía de "todavía no lo veo".

El recorte NO se devuelve para un disco libre, a propósito: dárselo al matcher es invitarlo a
nombrar el arte del disco — el falso "Cissia" de los libres (5R.L.7.2).

## 5. ⭐ Hallazgo aparte: **el inventario SÍ tiene contador**

El header de S9 dice **`Pistas de disco [339/3000]`**.

El plan del censo (2026-07-22) y el módulo de censo del roster se construyeron sobre lo contrario:
*"el menú de personajes no tiene contador `N/M`"*, y de ahí salió toda la asimetría
PENDIENTE ≠ HUÉRFANO y el cierre explícito por F8. **Para discos eso no aplica**: hay un
denominador escrito en pantalla, igual que el `N/300` del desmontaje, que la memoria del proyecto
ya registra como *"única autoridad del conteo"*.

Consecuencia concreta: el censo de discos **puede saber cuándo terminó** —cuando registró 339
discos distintos— en vez de depender de que el usuario declare el cierre. Es un cambio de diseño
para la fase siguiente, no de esta nota.

(Y de paso: 339 en pantalla contra 367 en la DB vieja. La diferencia es exactamente el tipo de
divergencia que motivó reconstruir la DB.)

## 6. La lección

El bug no era un dato que faltaba: era **una distinción que el código conocía y descartaba al
devolver**. Vale releer la firma de una función cuando dos casos distintos comparten valor de
retorno — `None` es cómodo y borra el porqué.

---

## 7. El camino de persistencia (misma tanda)

Con la afirmación disponible, `persist_s17_disc` deja de cortar en seco:

```python
if agente_id is None:
    if parsed.equip_libre:            # evidencia positiva
        return self._persist_disco_libre(...)
    return None                       # no se pudo leer → sigue sin escribir
```

**Se persiste lo que se AFIRMA, no lo que no se pudo leer.** Ausencia de dato no es dato.

Sin dueño no existe la clave natural `(PJ, slot)`, así que la deduplicación sale por identidad
completa — y por eso ese arreglo tenía que ir primero.

### El borde que puede corromper

Un disco visto libre cuya identidad coincide con uno **equipado** admite dos lecturas y ninguna
verificable: o es ese mismo disco recién desequipado, o es su gemelo (22 pares indistinguibles en
el inventario real).

| acción | consecuencia |
|---|---|
| actualizar la fila equipada | la marca libre — **falso LIBRE**, que es lo que habilita un reemplazo erróneo |
| insertar | duplica |
| **abstenerse y avisar** | ✅ el conteo puede quedar corto, y queda dicho |

Es la misma decisión que en los gemelos del upsert: cuando las dos salidas escriben algo falso, la
tercera es no escribir.
