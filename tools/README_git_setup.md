# Setup inicial del repo git

> El sandbox del asistente no puede borrar archivos del filesystem montado, así que el `git init` lo ejecutás vos desde Windows con permisos plenos. Hay un script PowerShell preparado.

## TL;DR

```powershell
cd D:\Proyectos\Zenless_analitycs
powershell -ExecutionPolicy Bypass -File tools\init_repo.ps1
```

Eso:
1. Limpia el `.git/` parcial heredado del sandbox (si quedó alguno).
2. Inicializa repo nuevo en branch `main`.
3. Configura `user.email` y `user.name`.
4. Agrega el remote `https://github.com/DaniBOD/Zenless_analitycs.git`.
5. Detecta si el repo remoto está vacío:
   - **Si está vacío:** stage all + commit inicial + `git push -u origin main`.
   - **Si tiene commits:** se detiene y muestra pasos manuales (no automatiza para evitar perder data).

## Antes de correr el script

1. Asegurate de tener git instalado: `git --version` debería devolver algo.
2. Tener configurado el credential helper para autenticar con GitHub. Si nunca pusheaste a este repo:
   ```powershell
   git config --global credential.helper manager-core
   ```
   La primera vez que `git push` lo necesite, se abre Windows Hello / browser para autorizar.
3. Verificá que el remoto exista (basta abrir `https://github.com/DaniBOD/Zenless_analitycs` en el navegador). Si todavía no creaste el repo en GitHub, hacelo primero — vacío, sin README, sin .gitignore (los maneja el script).

## Qué se va a commitear (resumen)

`.gitignore` excluye:
- Artifacts de Python (`__pycache__/`, `.venv/`, `dist/`, etc.)
- IDE / OS basura (`.vscode/`, `.idea/`, `.qodo/`, `Thumbs.db`)
- DB runtime backups (`db/danibod_zzz_v2.backup_*.db`, `*.db-journal`, `*.db-wal`)
- **`Inventario/`** completo (~200 MB de capturas full-res del juego — regenerable cuando esté la app activa)
- Configuración personal del usuario (`app/config/user_config.toml`, `.env`)
- Logs y reportes runtime

Se commitean (entre otros):
- `db/danibod_zzz_v2.db` (~620 KB) — fuente de verdad estructural.
- `db/migrations/` — SQL aplicadas.
- `audit/danibod_zzz_v2.backup_*.db` (~180 KB) — snapshots intencionales pre-merge.
- `audit/*.md` — reportes de auditoría.
- Toda `Documentacion/` (~37 MB con mockups, splash arts, logos).
- `Pj_stats/` (~6 MB — 45 jpegs HoYoLAB).
- `tools/` — scripts auxiliares.
- `.gitignore` y este README.

Total estimado del primer commit: **~50 MB**. Si en algún momento esto crece (ej. al meter el golden set OCR de 50 capturas full-res), conviene migrar a Git LFS. No es necesario por ahora.

## Caso B: el repo remoto YA tiene commits

Si el script detecta que `git ls-remote` devuelve algo, se detiene y te muestra los pasos manuales:

```powershell
git fetch origin
git checkout -b main origin/main
git status                            # ver qué archivos locales sobran/faltan
git add .
git commit -m "chore: integrar Fase 1 + roadmap Fase 2"
git push origin main
```

Si hay conflictos (ej. el remoto tiene un `.gitignore` distinto), resolvélos a mano antes del commit.

## Después del primer push — workflow recomendado

A partir de ahí seguir el patrón Git Flow simplificado documentado en el roadmap §11:

1. Para cada hito: `git checkout -b feature/<nombre-hito>` desde `main`.
2. Antes de cualquier write a DB: backup `db/danibod_zzz_v2.backup_premig_<ts>.db` (no se commitea, queda local — pero `audit/` sí se commitean los snapshots intencionales).
3. Al cerrar un hito: `git tag phase-2.X-<nombre>` + push del tag.
4. Tras patch de ZZZ: ejecutar `Documentacion/QA/QA-07_Regresion_Patches.md`.

## Limpieza del `.git/` corrupto del sandbox (si lo encontrás)

Si al ejecutar `git status` ves errores raros del tipo `bad config line`, es porque quedó el `.git/` corrupto del sandbox. El script lo limpia automáticamente, pero si querés hacerlo a mano:

```powershell
Remove-Item -Path .git -Recurse -Force
```

Después podés correr `init_repo.ps1` desde cero.
