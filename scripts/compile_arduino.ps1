param(
    [string]$Fqbn = "arduino:avr:mega"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SketchPath = Join-Path $RepoRoot "arduino\firmware"
$CliFromEnv = $env:ARDUINO_CLI
$LocalCli = Join-Path $RepoRoot "tools\arduino-cli\arduino-cli.exe"

if ($CliFromEnv -and (Test-Path -LiteralPath $CliFromEnv)) {
    $ArduinoCli = $CliFromEnv
} elseif (Test-Path -LiteralPath $LocalCli) {
    $ArduinoCli = $LocalCli
} elseif (Get-Command arduino-cli -ErrorAction SilentlyContinue) {
    $ArduinoCli = (Get-Command arduino-cli).Source
} else {
    throw "arduino-cli was not found. Install it or set ARDUINO_CLI to arduino-cli.exe."
}

$DataDir = Join-Path $RepoRoot ".arduino-data"
$DownloadsDir = Join-Path $RepoRoot ".arduino-downloads"
$BuildPath = Join-Path $RepoRoot "build\arduino"
$ConfigFile = Join-Path $RepoRoot ".arduino-cli.yaml"

New-Item -ItemType Directory -Force -Path $DataDir, $DownloadsDir, $BuildPath | Out-Null

$Config = @"
directories:
  data: $($DataDir -replace '\\','/')
  downloads: $($DownloadsDir -replace '\\','/')
  user: $($RepoRoot -replace '\\','/')
"@
Set-Content -Path $ConfigFile -Value $Config -Encoding UTF8

Push-Location $RepoRoot
try {
    & $ArduinoCli --config-file $ConfigFile core update-index
    if ($LASTEXITCODE -ne 0) { throw "arduino-cli core update-index failed with exit code $LASTEXITCODE" }

    & $ArduinoCli --config-file $ConfigFile core install arduino:avr
    if ($LASTEXITCODE -ne 0) { throw "arduino-cli core install arduino:avr failed with exit code $LASTEXITCODE" }

    & $ArduinoCli --config-file $ConfigFile compile --fqbn $Fqbn --build-path $BuildPath $SketchPath
    if ($LASTEXITCODE -ne 0) { throw "arduino-cli compile failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
