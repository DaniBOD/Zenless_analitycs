#!/usr/bin/env bash
# Arma Documentacion/Interfaz/claude_design_upload/assets/ para subir a Claude Design.
#
# Son COPIAS de assets que ya viven versionados en Documentacion/Interfaz/. La carpeta esta
# gitignoreada a proposito: duplicar ~10 MB de webp en el repo es exactamente lo que costo
# reescribir el historial la vez que entraron los iconos de engines full-res.
#
# Uso (desde la raiz del repo):   bash tools/stage_design_assets.sh
set -euo pipefail

SRC="Documentacion/Interfaz"
DST="$SRC/claude_design_upload/assets"

rm -rf "$DST"
mkdir -p "$DST"/{pj_avatares,pj_splash,facciones,iconos_ui,sets_discos,engines}

cp "$SRC"/splash_arts/*ico*.webp    "$DST/pj_avatares/"
cp "$SRC"/splash_arts/*extend*.webp "$DST/pj_splash/"
cp "$SRC"/Facciones_Logos/*.webp    "$DST/facciones/"
cp "$SRC"/UI_general/*.webp         "$DST/iconos_ui/"
cp "$SRC"/Set_Discos_Logo/*.webp    "$DST/sets_discos/"
cp "$SRC"/Engines_icons/*.webp      "$DST/engines/"

for d in "$DST"/*/; do
  printf "%-16s %3s archivos\n" "$(basename "$d")" "$(ls "$d" | wc -l)"
done
echo "TOTAL: $(du -sh "$DST" | cut -f1)"
