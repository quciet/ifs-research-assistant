param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Run setup.ps1, then install the agent extra as described in docs/agent-guide.md.' }
& $PythonPath -m ifs_agent --project $ProjectRoot ui --port $Port
