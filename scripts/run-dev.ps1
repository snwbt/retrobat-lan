param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (!(Test-Path $VenvPython)) {
  py -3.11 -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPython -m pip install -e "$ProjectRoot[dev,process]"
Set-Location $ProjectRoot
& $VenvPython -m uvicorn app.main:app --host $HostName --port $Port

