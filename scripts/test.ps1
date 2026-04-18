$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = (Get-Command python).Source
} elseif (Test-Path -LiteralPath $BundledPython) {
    $Python = $BundledPython
} else {
    throw "Python was not found on PATH and the Codex bundled Python was not found at $BundledPython"
}

$env:HALLOWEEN_AUDIO_DISABLED = "1"
$env:HALLOWEEN_USE_MOCK_ARDUINO = "1"
$env:HALLOWEEN_MOCK_SCENE_DELAY_SCALE = "0"

Push-Location $RepoRoot
try {
    & $Python -m unittest discover -s tests -v
} finally {
    Pop-Location
}
