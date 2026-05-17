# publicar.ps1 — Sincroniza el vault JME y publica al sitio público.
#
# Uso (PowerShell):
#   cd C:\Users\Alejandro\projects\jme-encarnacion
#   .\publicar.ps1
#   .\publicar.ps1 -Message "agregué actas de mayo 2025"
#
# Qué hace:
#   1. Copia el vault de Google Drive → content/ (excluye raw, markdown, samples, _tmp, scripts, .obsidian, log.md, index.md)
#   2. Convierte DASHBOARD.md → content/index.md (homepage del sitio público)
#   3. Valida frontmatter YAML de todas las notas (avisa si hay errores)
#   4. git add + commit + push a la rama main
#   5. GitHub Actions reconstruye el sitio en 2-3 min
#
# URL pública: https://zer0me.github.io/jme-encarnacion/

[CmdletBinding()]
param(
    [string]$Message = "",
    [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"

$VAULT = "G:\Mi unidad\JME"
$REPO  = "C:\Users\Alejandro\projects\jme-encarnacion"
$DST   = Join-Path $REPO "content"

if (-not (Test-Path $VAULT)) {
    Write-Error "No encuentro el vault en $VAULT. ¿Está conectada Google Drive?"
    exit 1
}

Set-Location $REPO

# 0. Regenerar bloques dinámicos del DASHBOARD.md desde estado actual del vault
Write-Host ""
Write-Host "[0/6] Regenerando tablas dinámicas en DASHBOARD.md..." -ForegroundColor Cyan
python (Join-Path $REPO "tools\build_dashboard.py")
if ($LASTEXITCODE -ne 0) {
    Write-Error "build_dashboard.py falló."
    exit 1
}

# 1. Sync vault → content/
Write-Host ""
Write-Host "[1/6] Sincronizando vault -> content/..." -ForegroundColor Cyan
$rcExit = 0
# /XF con ruta completa para excluir SOLO el index.md del root del vault
# (no los index.md de subcarpetas como concejales/index.md).
$rootIndex = Join-Path $VAULT "index.md"
robocopy $VAULT $DST /MIR `
    /XD raw markdown samples _tmp _tmp_compressed scripts .obsidian `
    /XF log.md $rootIndex `
    /NFL /NDL /NJH /NS /NC /NP
$rcExit = $LASTEXITCODE
# Robocopy exit codes: 0-3 son éxito, 4+ son problemas
if ($rcExit -ge 4) {
    Write-Error "Robocopy falló con exit code $rcExit"
    exit 1
}
Write-Host "      OK (robocopy exit $rcExit = éxito)" -ForegroundColor Green

# 2. DASHBOARD.md → index.md (homepage)
Write-Host "[2/6] DASHBOARD.md -> content/index.md (homepage del sitio)..." -ForegroundColor Cyan
Copy-Item (Join-Path $DST "DASHBOARD.md") (Join-Path $DST "index.md") -Force
Write-Host "      OK" -ForegroundColor Green

# 3. Validar frontmatter YAML
if (-not $SkipValidation) {
    Write-Host "[3/6] Validando frontmatter YAML de todas las notas..." -ForegroundColor Cyan
    $valOut = python (Join-Path $REPO "tools\validate_frontmatter.py")
    $valExit = $LASTEXITCODE
    Write-Host $valOut
    if ($valExit -ne 0) {
        Write-Warning "Hay notas con frontmatter inválido. El build de Quartz va a fallar para esas notas."
        $continue = Read-Host "¿Continuar igual con el push? (s/n)"
        if ($continue -ne "s") { exit 1 }
    } else {
        Write-Host "      OK — todo el frontmatter es válido" -ForegroundColor Green
    }
} else {
    Write-Host "[3/6] Validación de frontmatter SALTEADA" -ForegroundColor Yellow
}

# 4. git status + commit + push
Write-Host "[4/6] Detectando cambios git..." -ForegroundColor Cyan
$changes = git status --short
if (-not $changes) {
    Write-Host "      No hay cambios para publicar. Salgo." -ForegroundColor Yellow
    exit 0
}
Write-Host "      Cambios detectados:"
$changes | ForEach-Object { Write-Host "        $_" }

if (-not $Message) {
    $Message = "publish: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}
Write-Host "      Mensaje commit: $Message"

git add .
git commit -m $Message
if ($LASTEXITCODE -ne 0) {
    Write-Error "git commit falló."
    exit 1
}

# 5. Push
Write-Host "[5/6] Push a GitHub..." -ForegroundColor Cyan
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Error "git push falló."
    exit 1
}

Write-Host ""
Write-Host "Listo. GitHub Actions reconstruye el sitio en 2-3 min." -ForegroundColor Green
Write-Host "URL pública: https://zer0me.github.io/jme-encarnacion/" -ForegroundColor Green
Write-Host "Ver progreso del build: https://github.com/zer0me/jme-encarnacion/actions" -ForegroundColor Green
