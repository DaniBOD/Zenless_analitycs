# =================================================================
# Inicialización del repo git para DaniBOD ZZZ Analytics
# =================================================================
# Ejecutar desde D:\Proyectos\Zenless_analitycs\ con PowerShell.
#
# Uso:
#   cd D:\Proyectos\Zenless_analitycs
#   pwsh tools\init_repo.ps1
# o
#   powershell -ExecutionPolicy Bypass -File tools\init_repo.ps1
# =================================================================

$ErrorActionPreference = "Stop"

Write-Host "=== DaniBOD ZZZ Analytics — Init repo ===" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar que estamos en la carpeta correcta
$expectedFile = "project-context-IA.md"
if (-not (Test-Path $expectedFile)) {
    Write-Error "No se encuentra '$expectedFile'. Ejecutá este script desde D:\Proyectos\Zenless_analitycs\"
    exit 1
}

# 2. Limpiar .git/ heredado del sandbox (si existe)
if (Test-Path ".git") {
    Write-Host "Borrando .git/ existente (sandbox heredado)..." -ForegroundColor Yellow
    Remove-Item -Path ".git" -Recurse -Force
}

# 3. Init
Write-Host "git init -b main..." -ForegroundColor Green
git init -b main

# 4. Config local (no toca tu config global)
Write-Host "Configurando user.email + user.name..." -ForegroundColor Green
git config user.email "daniel.pilquil.003@gmail.com"
git config user.name  "DaniBOD"
git config core.autocrlf true   # Windows: CRLF en working dir, LF en repo

# 5. Remote
$remoteUrl = "https://github.com/DaniBOD/Zenless_analitycs.git"
Write-Host "Agregando remote origin -> $remoteUrl" -ForegroundColor Green
git remote add origin $remoteUrl

# 6. Fetch para ver si el repo remoto tiene commits previos
Write-Host ""
Write-Host "Verificando si el repo remoto está vacío..." -ForegroundColor Cyan
$remoteHeads = git ls-remote --heads origin 2>$null

if ([string]::IsNullOrWhiteSpace($remoteHeads)) {
    # ─── Caso A: remoto vacío ────────────────────────────────
    Write-Host "Repo remoto vacío. Procediendo con push inicial." -ForegroundColor Green

    Write-Host ""
    Write-Host "git add . (respeta .gitignore)" -ForegroundColor Green
    git add .

    Write-Host ""
    Write-Host "Estado a commitear:" -ForegroundColor Cyan
    git status --short | Select-Object -First 30
    Write-Host "..."
    Write-Host "Total archivos staged: $((git diff --cached --name-only | Measure-Object).Count)"
    Write-Host ""

    $continue = Read-Host "¿Continuar con commit + push? (s/N)"
    if ($continue -ne "s") {
        Write-Host "Abortado por usuario. Repo inicializado pero sin commit." -ForegroundColor Yellow
        exit 0
    }

    git commit -m @"
chore: initial commit — Fase 1 cerrada + roadmap Fase 2

- DB v2 completa (31 tablas, 5 migraciones, 332 discos, 45 PJs, 6 arquetipos).
- Documentación RF-04/05/06/09/11/12/13/14 cerrada.
- Brief de diseño + mockups generados con Claude Design (sesión 1).
- Brief sesión 2 redactado (pantallas restantes).
- Roadmap Fase 2 (motor captura + scoring) redactado.

Próximo paso: ejecutar Hito 2.0.1 (audit inventory_discs).

Refs: project-context-IA.md, Documentacion/Roadmap_Implementacion/Roadmap_Motor_Captura_Scoring.md
"@

    Write-Host ""
    Write-Host "git push -u origin main" -ForegroundColor Green
    git push -u origin main

} else {
    # ─── Caso B: remoto con commits ──────────────────────────
    Write-Host "Repo remoto YA tiene commits:" -ForegroundColor Yellow
    Write-Host $remoteHeads
    Write-Host ""
    Write-Host "Pasos manuales recomendados (NO automatizo para no perder data):" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  # 1. Bajar lo que hay en el remoto:"           -ForegroundColor White
    Write-Host "  git fetch origin"                              -ForegroundColor Gray
    Write-Host ""
    Write-Host "  # 2. Crear branch desde el main remoto:"       -ForegroundColor White
    Write-Host "  git checkout -b main origin/main"              -ForegroundColor Gray
    Write-Host ""
    Write-Host "  # 3. Mergeá / rebasá tus archivos locales encima del HEAD remoto." -ForegroundColor White
    Write-Host "  #    (git status muestra qué archivos hay sin trackear o modificados)" -ForegroundColor White
    Write-Host "  git status"                                    -ForegroundColor Gray
    Write-Host ""
    Write-Host "  # 4. Cuando esté limpio, add + commit + push:" -ForegroundColor White
    Write-Host "  git add ."                                     -ForegroundColor Gray
    Write-Host "  git commit -m 'chore: integrar Fase 1 + roadmap Fase 2'" -ForegroundColor Gray
    Write-Host "  git push origin main"                          -ForegroundColor Gray
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "✅ Repo inicializado y push hecho." -ForegroundColor Green
Write-Host "Verificá en: https://github.com/DaniBOD/Zenless_analitycs"
