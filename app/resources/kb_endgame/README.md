# Base de conocimiento de endgame

Insumo para la futura **IA asesora de endgame**. Vive dentro de `app/` a propósito (D1): lo que la
app vaya a leer tiene que viajar con el `.exe`, y `app/build/main.spec` ya empaqueta
`app/resources/` entera.

## Qué hay y quién manda

| Pregunta | Autoridad | Dónde |
|---|---|---|
| ¿Qué enemigos hay, con qué stats y resistencias? | la DB | `enemies`, `enemy_resistances` |
| ¿Qué salas, oleadas y buffos tuvo un ciclo? | la DB | `shiyu_cycles.frentes` (JSON) |
| ¿**Por qué** un equipo rinde más que otro en una sala? | estos `.md` | `shiyu/ciclo_NNN_*.md` |

Los hechos estructurados van a la DB; el razonamiento va acá. Un `.md` **no** repite stats que
ya están en la DB salvo para argumentar; si hay contradicción, manda la DB (y la DB cede ante la
pantalla).

## Etiquetas de evidencia

Cada afirmación del análisis lleva una etiqueta, para que el asesor sepa cuánto pesarla:

| Etiqueta | Significa | Ejemplo |
|---|---|---|
| **[P]** | leído de la pantalla del juego | "la sala 2 muestra resistencia sólo a Etéreo" |
| **[D]** | dato medido (dataset, DB) con su n | "38 528 prom., n≈1 654" |
| **[F]** | afirmación textual de una fuente (Prydwen, Game8, Fandom) | "Burnice no sufre el tiempo en campo de Remielle" |
| **[I]** | inferencia propia, con confianza **alta / media / baja** | "el jefe pesa más que la oleada" |

**Los promedios de puntaje son observacionales.** Quien tiene la firma o un PJ limitado suele
tener la cuenta más invertida en general. La unidad de evidencia es la **comparación
controlada**: mismo núcleo, mismo Bangboo, cambia un solo slot. Aun así queda sesgo de
inversión; la dirección de una brecha grande con n grande es confiable, el número exacto no.

## Cómo se agrega un ciclo

1. Migración con los enemigos nuevos (sólo los que falten) + la fila de `shiyu_cycles`.
   Precedente: `db/migrations/2026-09-18_38_enemigos_y_ciclo_shiyu_quinto_frente.sql`.
2. `shiyu/ciclo_NNN_<fecha_inicio>_<frente>.md` con la misma estructura del ciclo 001.
3. Datos de uso: dataset `LvlUrArti/ShiyuDataProcessed` en Hugging Face (MIT, dar crédito a
   LvlUrArti) — `<fase>/sd/comps/5-{1,2,3}_combined.json` y `<fase>/builds.json`.
4. Verificar contra pantalla lo que se pueda (atributos recomendados, resistencia del enemigo
   poderoso). Wiki y pantalla ya discreparon una vez (ciclo 001, sala 2).
