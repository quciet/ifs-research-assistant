param([string]$Python = "py", [switch]$Agent, [switch]$Semantic)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentRoot = Join-Path $projectRoot ".venv"
if (-not (Test-Path -LiteralPath (Join-Path $environmentRoot "Scripts/python.exe"))) {
    if ($Python -eq "py") { & $Python -3.12 -m venv $environmentRoot }
    else { & $Python -m venv $environmentRoot }
    if ($LASTEXITCODE -ne 0) { throw "Could not create Python environment." }
}
$projectPython = Join-Path $environmentRoot "Scripts/python.exe"
$installTarget = if ($Semantic) { "${projectRoot}[agent,semantic]" } elseif ($Agent) { "${projectRoot}[agent]" } else { $projectRoot }
$constraints = if ($Semantic) { 'requirements-semantic.lock.txt' } elseif ($Agent) { 'requirements-agent.lock.txt' } else { 'requirements.lock.txt' }
& $projectPython -m pip install -e $installTarget -c (Join-Path $projectRoot $constraints) --cache-dir (Join-Path $projectRoot 'workspace/pip-cache')
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
Write-Output "Ready: $projectPython"

if ($Semantic) {
    & $projectPython -m ifs_agent --project $projectRoot index --semantic --download-model
    if ($LASTEXITCODE -ne 0) { throw "Local indexing did not finish. Rerun setup to resume; exact search remains available." }
}
