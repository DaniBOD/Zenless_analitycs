# Logos de Drive Discs (Sets) — 26/26 cobertura completa

Logos oficiales de los 26 sets de discos del juego ZZZ. Cobertura 100% del catálogo `disc_sets` de la DB.

## Convención de nombres

Cada archivo tiene **dos versiones**:
- **Original (EN):** `Drive_Disc_<Name>_Icon.webp` — backup del archivo descargado del wiki
- **Renombrado (ES):** `<nombre_es_slug>.webp` — usable directamente desde la app

Slugs en español derivados de `disc_sets.nombre` (lowercase, sin acentos, snake_case):

| ID DB | Nombre ES | Slug archivo |
|-------|-----------|--------------|
| 24 | Voz Astral | `voz_astral.webp` |
| 25 | Balada rama y espada | `balada_rama_y_espada.webp` |
| 26 | Conejo en el país de las maravillas | `conejo_en_el_pais_de_las_maravillas.webp` |
| 27 | Jazz Caótico | `jazz_caotico.webp` |
| 28 | Metal Caótico | `metal_caotico.webp` |
| 29 | Floración del alba | `floracion_del_alba.webp` |
| 30 | Metal Colmilludo | `metal_colmilludo.webp` |
| 31 | Blues Libre | `blues_libre.webp` |
| 32 | Punk Hormonal | `punk_hormonal.webp` |
| 33 | Metal Infernal | `metal_infernal.webp` |
| 34 | Monarca del Pináculo | `monarca_del_pinaculo.webp` |
| 35 | Nana a la luz cenicienta | `nana_a_la_luz_cenicienta.webp` |
| 36 | Notas encadenadas | `notas_encadenadas.webp` |
| 37 | Melodía de Faetón | `melodia_de_faeton.webp` |
| 38 | Polar Metal | `polar_metal.webp` |
| 39 | Punk Primitivo | `punk_primitivo.webp` |
| 40 | Puffer Electro | `puffer_electro.webp` |
| 41 | Armonía umbría | `armonia_umbria.webp` |
| 42 | Aria brillante | `aria_brillante.webp` |
| 43 | Disco Sacudestrellas | `disco_sacudestrellas.webp` |
| 44 | Soul Rock | `soul_rock.webp` |
| 45 | Jazz Oscilante | `jazz_oscilante.webp` |
| 46 | Metal Eléctrico | `metal_electrico.webp` |
| 48 | Tecno Pícido | `tecno_picido.webp` |
| 49 | Fábula Yunkui | `fabula_yunkui.webp` |
| 51 | Balada de aguas blancas | `balada_de_aguas_blancas.webp` |

## Helper para resolver desde código

```python
def get_disc_set_logo(set_nombre_es: str) -> Path:
    slug = (set_nombre_es.lower()
                         .replace('á','a').replace('é','e').replace('í','i')
                         .replace('ó','o').replace('ú','u').replace('ñ','n')
                         .replace(' - ', '_').replace(' ', '_').replace('/', '_'))
    return Path("Documentacion/Interfaz/Set_Discos_Logo") / f"{slug}.webp"
```

## Uso recomendado en la UI

| Contexto | Tamaño |
|----------|--------|
| Toast flotante (badge del set del disco capturado) | 24×24 px |
| Tabla histórico (columna "Set") | 20×20 px |
| Card de build en optimizador (4pc destacado) | 48×48 px |
| Pestaña Catálogos → sección Sets | 96×96 px |

## Nota sobre limpieza

Los archivos originales `Drive_Disc_*_Icon.webp` se mantuvieron como backup. Si querés limpiarlos para reducir clutter, podés borrarlos manualmente — la app solo necesita los slugs en español.
