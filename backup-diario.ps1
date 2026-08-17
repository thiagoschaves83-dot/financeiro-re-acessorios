<#
    BACKUP-DIARIO.PS1 - App Financeiro da Re Acessorios
    Roda sozinho todo dia (Agendador de Tarefas do Windows), nao precisa do
    app estar aberto. So copia o dados.db pra pasta de backups, com data/hora
    no nome. Nao apaga backup antigo nenhum.
#>

$root = $PSScriptRoot
$dbPath = Join-Path $root "dados.db"

if (-not (Test-Path $dbPath)) {
    Write-Host "dados.db nao encontrado - nada pra fazer backup ainda."
    exit 0
}

$backupDir = Join-Path $root "backups"
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }

$carimbo = Get-Date -Format "yyyyMMdd_HHmm"
Copy-Item $dbPath (Join-Path $backupDir "dados_$carimbo.db") -Force
Write-Host "Backup diario criado: dados_$carimbo.db"
