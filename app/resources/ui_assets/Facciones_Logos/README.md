# Logos de facciones — 16 archivos

Logos oficiales de las facciones del juego ZZZ. **Cobertura 100%** del roster: las 13 facciones distintas que cubren los 46 PJs (incluida Cissia, patch v2.7) tienen su logo correspondiente.

> **Corrección abril 2026:** la columna `agents.faccion` fue corregida según las wikis oficiales (Fandom, Game8, TVTropes). Antes había 6 facciones con miembros mal asignados; ahora hay 13 facciones canónicas con cobertura precisa. Ver §"Cambios aplicados" al final.
>
> **Adición mayo 2026 (v2.7):** Cissia ingresa al roster bajo la facción CRIT con variante visual propia "Metropolitan Order Division" (mismo patrón que Jane Doe).

## Mapeo facción ↔ logo ↔ PJs del roster (FINAL — 13 facciones)

| Facción canónica | PJs | Logo | Tag visual |
|------------------|-----|------|------------|
| **Hollow Special Operations Section 6** | Miyabi, Soukaku, Harumasa, Yanagi (4) | `Faction_Hollow_Special_Operations_Section_6.webp` | Escudo militar verde-petróleo / dorado |
| **Sons of Calydon** | Burnice, César, Piper, Lucy, Pulchra (5) | `Hijos_Caledon.webp` | Cerdo motorizado / naranja agresivo |
| **Belobog Heavy Industries** | Koleda, Antón, Ben, Grace (4) | `Construcciones_Belobog.webp` | Industrial / construcción |
| **Criminal Investigation Special Response Team** (CRIT) | Seth, Jane, Qingyi, Zhu Yuan, **Cissia** (5) | `Faction_Criminal_Investigation_Special_Response_Team_Icon.webp` | Insignia policial · sub-facción N.E.P.S. |
| **Cunning Hares** | Billy, Nicole, Anby, Nekomata (4) | `Liebres_astutas.webp` | Conejo gamer rosa/violeta |
| **Spook Shack** | Manato, Lucía, Yuzuha, Alice (4) | `Cabaña_Terror.webp` | Sobrenatural / paranormal |
| **Victoria Housekeeping** | Lycaon, Corin, Rina, Ellen (4) | `Servicios_Domesticos_Victoria.webp` | Servicio doméstico elegante |
| **Yunkui Summit** | Pan Yinhu, Ye Shunguang, Ju Fufu, Yixuan (4) | `Pinaculo_Yunkui.webp` | Místicos / monjes |
| **Obol Squad** | N.º 11, Gatillo, Orfia y Magas, **N.º 0: Anby**, **Sporos** (5) | `Escuadron_Obolos.webp` | Soldados / militar |
| **Stars of Lyra** | Evelyn, Astra Yao (2) | `Estrellas_Lira.webp` | Música / showbiz |
| **Angels of Delusion** | Sunna, Nangong Yu (2) | `Agenles_delusion.webp` | Antagonistas / facción gris |
| **Krampus Compliance Authority** | Dialyn, Zhao (2) | `Auditoria_Krampus.webp` | Auditoría / compliance |
| **Mockingbird** | Vivian (1) | `Ruiseñor.webp` | Operaciones encubiertas |

**Total: 46 PJs / 13 facciones / 13 logos canónicos + 3 logos variante.**

## Logos variante / extras

Logos adicionales que **no son la insignia oficial de la facción paraguas**, sino variantes personales o sub-divisiones internas:

| Logo | Asociado a | Uso |
|------|------------|-----|
| `Faction_Criminal_Investigation_Special_Response_Team_Jean_Doe_ico.webp` | **Jane Doe** (CRIT) | Variante personal del logo CRIT con identidad de Jane Doe — sub-facción "Criminal Investigation Special Response Team Jean Doe Variant" |
| `Faction_Metropolitan_Order_Division_Icon.webp` | **Cissia** (CRIT) | Variante personal del logo CRIT — sub-división **Metropolitan Order Division** (División del Orden Metropolitano) dentro de N.E.P.S. — patrón análogo a Jane Doe |
| `Faction_Defense_Force_-_Silver_Squad_Icon.webp` | (sin uso actual) | Silver Squad — facción de Defense Force, no en roster v2.7. Reservado para futuro onboarding. |

> **Patrón "facción paraguas + variante personal":** algunos PJs comparten facción canónica con otros pero traen una insignia visual distintiva (sub-división, identidad de operativo, etc.). Para el modelo de datos, la columna `agents.faccion` apunta a la facción paraguas (filtrado/joins consistentes); la variante visual se registra en `agents.notas` con el nombre del logo. Si en el futuro la app necesita un campo dedicado, conviene migración con `agents.faction_logo_variant TEXT NULL`.

## Convención de nombres recomendada

Para resolver `agents.faccion → ruta del logo` con función trivial, sugiero renombrar a:

```
Hijos_Caledon.webp                                  →  sons_of_calydon.webp
Faction_Criminal_Investigation_..._Icon.webp        →  criminal_investigation_special_response_team.webp
Servicios_Domesticos_Victoria.webp                  →  victoria_housekeeping.webp
Liebres_astutas.webp                                →  cunning_hares.webp
Construcciones_Belobog.webp                         →  belobog_heavy_industries.webp
Faction_Hollow_Special_Operations_Section_6.webp    →  hollow_special_operations_section_6.webp
Pinaculo_Yunkui.webp                                →  yunkui_summit.webp
Estrellas_Lira.webp                                 →  stars_of_lyra.webp
Ruiseñor.webp                                       →  mockingbird.webp
Escuadron_Obolos.webp                               →  obol_squad.webp
Cabaña_Terror.webp                                  →  spook_shack.webp
Auditoria_Krampus.webp                              →  krampus_compliance_authority.webp
Agenles_delusion.webp                               →  angels_of_delusion.webp
Faction_Defense_Force_-_Silver_Squad_Icon.webp      →  _extra_silver_squad.webp
Faction_Criminal_Investigation_..._Jean_Doe_ico.webp →  _extra_crit_jane_doe_variant.webp
```

```python
# Helper trivial sin tabla de mapeo
def get_faction_logo(faccion: str) -> Path:
    slug = faccion.lower().replace(" ", "_").replace("-", "_")
    return Path("Documentacion/Interfaz/Facciones_Logos") / f"{slug}.webp"
```

## Uso recomendado en la UI (RF-11)

1. **Pestaña Roster** — badge esquina superior izquierda (24×24 px) en cada card de PJ.
2. **Pestaña Equipos (RF-12)** — logo grande (48×48) entre dos PJs cuando la sinergia es por facción (`tipo='additional_ability_faccion'`).
3. **Toast flotante** — mini-badge overlay (16×16) sobre el avatar del PJ destinatario.
4. **Pestaña Catálogos** — sección "Facciones" con hero (96×96) agrupando los PJs.
5. **Tier list visual (RF-13)** — filtro "Por facción" usando los logos como pickers.

PySide6 puede renderizar webp nativamente vía `QImageReader` (Qt 6.5+).

---

## Cambios aplicados (abril 2026 — corrección de facciones)

Tras revisar Fandom Wiki + Game8 + TVTropes, se corrigieron **26 PJs** con facción incorrecta + **rename** de "Victoria Hollows" → "Victoria Housekeeping" + **7 facciones nuevas** agregadas al sistema (Yunkui Summit, Stars of Lyra, Mockingbird, Obol Squad, Spook Shack, Krampus Compliance Authority, Angels of Delusion).

| PJ | Facción anterior (incorrecta) | Facción correcta | Fuente |
|----|-------------------------------|------------------|--------|
| Lycaon, Rina, Ellen | Victoria Hollows | Victoria Housekeeping | Fandom (rename) |
| Corin | Cunning Hares | Victoria Housekeeping | Fandom |
| Pulchra | CRIT | Sons of Calydon | Game8 |
| Harumasa | CRIT | HSO Section 6 | Fandom |
| N.º 0: Anby | CRIT | HSO Section 6 | Fandom (Soldier 0 lore) |
| Yixuan, Pan Yinhu, Ju Fufu, Ye Shunguang | varias | Yunkui Summit | TVTropes |
| Astra Yao, Evelyn | Sons of Calydon | Stars of Lyra | Game8 + Fandom |
| Sporos | Victoria Hollows | Obol Squad | Game8 (S-rank Eléctrica·Ataque, build 4pc Floración + 2pc Tecno Pícido) |
| Vivian | Sons of Calydon | Mockingbird | Fandom |
| N.º 11 | CRIT | Obol Squad | TVTropes |
| Gatillo (Trigger) | Victoria Hollows | Obol Squad | TVTropes |
| Orfia y Magas | Sons of Calydon | Obol Squad | Game8 |
| Manato, Lucía, Yuzuha, Alice | varias | Spook Shack | Fandom |
| Zhao, Dialyn | Victoria Hollows | Krampus Compliance Authority | Game8 |
| Nangong Yu, Sunna | Sons of Calydon | Angels of Delusion | Game8 |

**Validación post-corrección:** `PRAGMA integrity_check = ok`, **0 violations** en `foreign_key_check`, total **45/45 agentes** asignados a una de las 13 facciones canónicas (post-onboarding Cissia: **46/46**).

> **Adición v2.7 (mayo 2026):** Cissia (S-rank Eléctrica · Ataque · M0) ingresa al roster bajo `Criminal Investigation Special Response Team` con variante visual propia **Metropolitan Order Division** (logo: `Faction_Metropolitan_Order_Division_Icon.webp`). Patrón análogo a Jane Doe.
>
> **Aclaración sobre Sporos:** una nota anterior asumía tentativamente que "Sporos" era la traducción/alias en español de "Cissia". **La hipótesis era incorrecta**: tras verificar en HoYoLAB ambos PJs, son agentes distintos:
> - **Sporos**: S-rank · build crit-DPS pure (CR 66.6 / CDmg 184.4) · W-Engine "Rotor de cañón" A-rank · 4pc Floración del alba + 2pc Tecno Pícido · Bono Eléctrico 0.0% (probable rol distinto a "Ataque Eléctrico"). Permanece en **Obol Squad** como estaba originalmente.
> - **Cissia**: S-rank Eléctrica · build híbrido Crit + ER (CR 48.2 / CDmg 126.8 / ER 3.58) · W-Engine "Taladradora giratoria - Eje" A-rank R5 · 4pc Floración del alba + 2pc Nana a la luz cenicienta · Bono Eléctrico 30%. Asignada a **CRIT** con variante MOD.
>
> Ambos comparten el set 4pc "Floración del alba" pero las builds y W-Engines son distintas, descartando la hipótesis de alias.

## Fuentes

- [Factions | Fandom Wiki](https://zenless-zone-zero.fandom.com/wiki/Faction)
- [All Factions List | Game8](https://game8.co/games/Zenless-Zone-Zero/archives/460201)
- [Characters by Faction | TVTropes](https://tvtropes.org/pmwiki/pmwiki.php/Characters/ZenlessZoneZero)
- [Faction Overview | Icy Veins](https://www.icy-veins.com/zenless-zone-zero/faction-overview-guide)
- [Yunkui Summit | Fandom](https://zenless-zone-zero.fandom.com/wiki/Yunkui_Summit)
- [Stars of Lyra Faction Guide | Game8](https://game8.co/games/Zenless-Zone-Zero/archives/490864)
