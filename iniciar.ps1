<#
    INICIAR.PS1 - App Financeiro da Re Acessorios
    Clique com o botao direito > Executar com PowerShell (ou de dentro de um terminal PowerShell).

    Na primeira vez, prepara o ambiente sozinho (demora um pouquinho a mais).
    Depois disso, abre rapido. Fecha a janela do terminal pra desligar o sistema.
#>

$root = $PSScriptRoot
Set-Location $root

# O ambiente Python (venv) fica no disco local, nao no drive de rede (Q:\) -
# instalar pacote por pacote via rede e muito mais lento e pode ate travar.
# So o banco de dados e o codigo do app ficam na rede (o que precisa ser
# acessivel/backupeado); o venv e so software reinstalavel, fica local.
$venvPath = Join-Path $env:LOCALAPPDATA "ReAcessoriosFinanceiro\venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "Primeira vez rodando - preparando o ambiente (so demora agora)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Split-Path $venvPath) | Out-Null
    py -m venv $venvPath
    & $pythonExe -m pip install --quiet --upgrade pip
    & $pythonExe -m pip install --quiet -r (Join-Path $root "requirements.txt")
}

# Backup automatico do banco antes de abrir - protege contra erro sem precisar lembrar
$dbPath = Join-Path $root "dados.db"
if (Test-Path $dbPath) {
    $backupDir = Join-Path $root "backups"
    if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }
    $carimbo = Get-Date -Format "yyyyMMdd_HHmm"
    Copy-Item $dbPath (Join-Path $backupDir "dados_$carimbo.db") -Force
    Write-Host "Backup criado: dados_$carimbo.db" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  RE ACESSORIOS - FINANCEIRO" -ForegroundColor Magenta
Write-Host "  ------------------------------------" -ForegroundColor Magenta
Write-Host "  Abrindo em http://127.0.0.1:5000 ..." -ForegroundColor Magenta
Write-Host "  Feche esta janela para desligar o sistema." -ForegroundColor DarkGray
Write-Host ""

Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:5000"
} | Out-Null

# FLASK_DEBUG=1 so no uso local - mostra pagina de erro detalhada se algo quebrar
# durante teste. Na nuvem (PythonAnywhere) isso nao existe e o padrao fica desligado.
$env:FLASK_DEBUG = "1"
& $pythonExe (Join-Path $root "app.py")
