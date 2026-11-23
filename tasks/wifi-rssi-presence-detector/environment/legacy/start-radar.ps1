param([string]$ProjectRoot = "<project>")
$ErrorActionPreference = "Stop"
$server = Join-Path $ProjectRoot "server\ruview.exe"
$injector = Join-Path $ProjectRoot "rssi_to_ruview.py"
Start-Process -FilePath $server -WorkingDirectory (Join-Path $ProjectRoot "server")
Start-Process -FilePath "python" -ArgumentList @($injector) -WorkingDirectory $ProjectRoot
Start-Process (Join-Path $ProjectRoot "ui\index.html")
