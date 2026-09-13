# Logos de W-Engines (Armas) — 31/38 mapeados

Logos oficiales de W-Engines. Cobertura **31/38 archivos** mapeados al `weapons.nombre` de la DB (los 7 restantes requieren tu confirmación, ver §Sin match).

## Archivos renombrados (31 W-Engines)

Cada archivo tiene dos versiones: original `W-Engine_<Name>.webp` (backup) + slug en español.

| Slug ES | Nombre ES (DB) | Original EN |
|---------|----------------|-------------|
| `aguijon_afilado.webp` | Aguijón afilado | Sharpened Stinger |
| `almohadillas_ferreas.webp` | Almohadillas férreas | Steel Cushion |
| `amo_de_llaves.webp` | Amo de llaves | The Brimstone |
| `anhelo_marcato.webp` | Anhelo marcato | Marcato Desire |
| `caldero_de_la_claridad.webp` | Caldero de la claridad | Cauldron of Clarity |
| `camara_acorazada.webp` | Cámara acorazada | Bashful Demon |
| `canon_bombastico.webp` | Cañón bombástico | Kaboom the Cannon |
| `coctelera_incandescente.webp` | Coctelera incandescente | Flamemaker Shaker |
| `compilador_quimerico.webp` | Compilador quimérico | Fusion Compiler |
| `cuter.webp` | Cúter | Box Cutter |
| `esplendor_surcanimbos.webp` | Esplendor surcanimbos | Cloudcleave Radiance |
| `estrella_callejera.webp` | Estrella callejera | Street Superstar |
| `florescencia_aurifera.webp` | Florescencia aurífera | Gilded Blossom |
| `fosil_preciado.webp` | Fósil preciado ("la roca") | Precious Fossilized Core |
| `gastronomo_selvatico.webp` | Gastrónomo selvático | Rainforest Gourmet |
| `hellfire_gears.webp` | Hellfire Gears | Hellfire Gears |
| `lapso_de_tiempo.webp` | Lapso de tiempo | Slice of Time |
| `llanto_mielgo.webp` | Llanto mielgo | Weeping Gemini |
| `motor_estelar.webp` | Motor estelar | Starlight Engine |
| `pacificador_especializado.webp` | Pacificador especializado | Peacekeeper - Specialized |
| `primavera_termal.webp` | Primavera termal | Spring Embrace |
| `proyector_de_celuloide.webp` | Proyector de celuloide | Reel Projector |
| `replica_motor_estelar.webp` | Réplica motor estelar | Starlight Engine Replica |
| `rompecabeza_ilusorio.webp` | Rompecabeza ilusorio | Puzzle Sphere |
| `rotor_de_canon.webp` | Rotor de cañón | Cannon Rotor |
| `taladradora_giratoria_eje.webp` | Taladradora giratoria - Eje | Drill Rig - Red Axis |
| `templo_a_la_granizada.webp` | Templo a la granizada | Hailstorm Shrine |
| `transmorfer_original.webp` | Transmorfer original | Original Transmorpher |
| `transito_herciano.webp` | Tránsito herciano | Radiowave Journey |
| `viaje_estruendoso.webp` | Viaje estruendoso | Roaring Ride |
| `visitante_de_altamar.webp` | Visitante de altamar | Deep Sea Visitor |

## Sin match seguro (7 archivos — REVISAR MANUALMENTE)

Los siguientes 7 archivos no tienen un match claro con `weapons.nombre` de la DB. Posibles razones: nombre EN del archivo difiere del que cargaste manualmente en la DB, o el arma no está en tu inventario.

| Archivo | Posible nombre ES | Acción sugerida |
|---------|-------------------|-----------------|
| `W-Engine_Big_Cylinder.webp` | ¿Cilindro neumático (id=42)? | Verificar EN canónico |
| `W-Engine_Bunny_Band.webp` | ¿No está en DB? | Verificar si la tenés equipada |
| `W-Engine_Demara_Battery_Mark_II.webp` | ¿Variante de Bashful Demon? | Verificar identidad |
| `W-Engine_Housekeeper.webp` | ¿Arma de Lycaon/Ellen? Faltaría en DB | Buscar en HoYoLAB |
| `W-Engine_Steam_Oven.webp` | ¿No en DB? | Verificar si la tenés |
| `W-Engine_The_Simmering_Pot.webp` | ¿Caldero ardiente (id=13)? | Verificar EN canónico |
| `W-Engine_The_Vault.webp` | ¿No en DB? | Verificar |

**Cómo resolver:** consultá Hakush.in o Prydwen.gg con el nombre EN del archivo. Si confirmás el nombre ES correcto, podés:
1. Renombrar manualmente el archivo a `<slug>.webp`
2. Actualizar el README con el match
3. (Opcional) Corregir `weapons.nombre_en` en la DB con `UPDATE weapons SET nombre_en='<canonico>' WHERE nombre='<es>';`

## Helper para resolver desde código

```python
def get_weapon_logo(weapon_nombre_es: str) -> Path:
    slug = (weapon_nombre_es.lower()
                            .replace('á','a').replace('é','e').replace('í','i')
                            .replace('ó','o').replace('ú','u').replace('ñ','n')
                            .replace(' - ', '_').replace(' ', '_').replace('/', '_'))
    return Path("Documentacion/Interfaz/Engines_Animation") / f"{slug}.webp"
```

## Uso recomendado en la UI

| Contexto | Tamaño |
|----------|--------|
| Toast (badge del arma del PJ destinatario) | 16×16 px |
| Tabla de armas en pestaña "Armas" RF-14 | 32×32 px |
| Card de PJ en Roster (mostrando arma equipada) | 48×48 px |
| Pestaña Catálogo de armas | 96×96 px |
