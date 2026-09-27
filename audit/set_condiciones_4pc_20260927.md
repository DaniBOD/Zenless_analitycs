# Condiciones del 4pc de los sets · verificación 2026-09-27

Para la mig 46 (`set_condiciones_4pc`). Candidatas leídas de `disc_sets.bonus_4p_desc` (texto
propio, resumido) y **verificadas** contra la wiki de Fandom en inglés, leída con el navegador
integrado (API `action=parse`), el 2026-09-27. Se carga lo que dice Fandom, no el resumen.

| set | 4pc según Fandom (lo relevante) | condición cargada | alcance |
|---|---|---|---|
| Monarca del Pináculo (King of the Summit) | "When the equipper is a Stun character and uses an EX Special Attack or Chain Attack, increases CRIT DMG of all squad members by 15 %, and when the equipper's CRIT Rate is more than or equal to 50 %, further increases CRIT DMG by 15 %" | rol Aturdimiento · Prob. Crítica ≥ 50 | todo · parte |
| Balada de la rama y la espada (Branch & Blade Song) | "When Anomaly Mastery exceeds or equals 115 points, the equipper's CRIT DMG increases by 30 %. When any squad member applies Freeze or triggers the Shatter effect…" | Tasa de Anomalía ≥ 115 | parte |
| Rosa espinosa (Thorned Rose) | "The equipper's DMG increases by 15 %. When the equipper's initial DEF is at least 1,000/1,800, CRIT Rate increases by 8/16 %." | DEF ≥ 1.800 (el escalón completo) | parte |
| Conejo en el país de las maravillas (Bunny in Wonderland) | "When the equipper is a Defense character: …" | rol Defensa | todo |
| Nana a la luz cenicienta (Moonlight Lullaby) | "When the equipper is a Support character and uses an EX Special Attack or Ultimate…" | rol Soporte | todo |
| Floración del alba (Dawn's Bloom) | "Increases Basic Attack DMG by 20 %. When equipped by an Attack character, using an EX Special Attack or Ultimate will further increase…" | rol Ataque | parte |
| Balada de aguas blancas (White Water Ballad) | "When the equipper is within any Ether Veil, their CRIT Rate increases by 10 %… If the equipper is an Attack character, … an additional 10 % CRIT Rate and 10 % ATK" | rol Ataque | parte |
| Firmamento llameante (The Sky Ablaze) | "When the equipper is an Ether attribute Agent, their CRIT DMG increases by 30 %. When the equipper uses an EX Special Attack or Ultimate, their ATK increases by 10 %" | elemento Éter | parte |
| Hado emplumado (Feathered Fate) | "…Anomaly Proficiency increases by 50. If the equipper is a Lumiflux character, Attribute Anomaly DMG increases by 15 %" | elemento Lumen | parte |

## Vocabulario

Tabla "Other Languages" de Fandom: **Anomaly Mastery = "Tasa de Anomalía"** (columna
`agents.tasa_anomalia`) y **Anomaly Proficiency = "Maestría de Anomalía"** (`maestria_anomalia`).
La condición de Balada es `tasa_anomalia ≥ 115`.

## Diferencias con el resumen de `disc_sets`

- **Firmamento llameante:** el resumen decía "Si el portador es un agente Éter: Daño Crítico +30 %"
  sin aclarar que el ATK +10 % vale para cualquiera → alcance `parte`, no `todo`.
- Ninguna otra contradicción.

## De paso: Yuzuha (mig 45)

Su kit: "If Yuzuha's Anomaly Mastery exceeds 100, every point over increases … When Yuzuha's Anomaly
Mastery is at 200, she grants the full buff effect" (Fandom, `Ukinami_Yuzuha`). El fijo ya era
`tasa_anomalia` 200 (correcto); la cuenta decía "Maestría de Anomalía". Se corrige el texto en la
mig 46.
