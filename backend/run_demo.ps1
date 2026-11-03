param([string]$DatabasePath = '', [int]$Port = 8001)
$ErrorActionPreference = 'Stop'
$backendDirectory = $PSScriptRoot
$pythonPath = Join-Path $backendDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'The existing backend virtual environment was not found.' }
if ($Port -lt 1 -or $Port -gt 65535) { throw 'Port must be between 1 and 65535.' }
if (-not $DatabasePath) {
    $workspaceDirectory = Split-Path (Split-Path $backendDirectory -Parent) -Parent
    $DatabasePath = Join-Path $workspaceDirectory 'npc-memory-browser-demo\demo.sqlite3'
}
$demoDatabasePath = [IO.Path]::GetFullPath($DatabasePath)
$originalDatabasePath = [IO.Path]::GetFullPath((Join-Path $backendDirectory 'conversation_memory.sqlite3'))
if ($demoDatabasePath -eq $originalDatabasePath) { throw 'The original conversation database cannot be used for the demo.' }
$demoDirectory = Split-Path $demoDatabasePath -Parent
New-Item -ItemType Directory -Path $demoDirectory -Force | Out-Null
$previousDatabase = $env:NPC_DATABASE_PATH
$previousSummary = $env:NPC_SUMMARY_CONTEXT
$previousDemo = $env:NPC_DEMO_ENABLED
try {
    $env:NPC_DATABASE_PATH = $demoDatabasePath
    $env:NPC_SUMMARY_CONTEXT = '1'
    $env:NPC_DEMO_ENABLED = '1'
    Write-Host "Disposable demo database: $demoDatabasePath"
    Write-Host "Open http://127.0.0.1:$Port/demo"
    Write-Host 'Press Ctrl+C to stop. No database history will be deleted.'
    Push-Location -LiteralPath $backendDirectory
    try { & $pythonPath -B -m uvicorn main:app --host 127.0.0.1 --port $Port --no-proxy-headers }
    finally { Pop-Location }
} finally {
    $env:NPC_DATABASE_PATH = $previousDatabase
    $env:NPC_SUMMARY_CONTEXT = $previousSummary
    $env:NPC_DEMO_ENABLED = $previousDemo
}
