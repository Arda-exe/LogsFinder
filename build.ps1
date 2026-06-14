# Build LogsFinder.exe with PyInstaller, then package a clean release/ folder.
#
# IMPORTANT: the `python3` on PATH is a Microsoft Store stub, not a real
# interpreter. Use the full path to the real Python below.

$ErrorActionPreference = "Stop"
$py = "C:\Python314\python.exe"
$version = "1.0.0"
$root = $PSScriptRoot

Write-Host "Installing PyInstaller (if needed)..."
& $py -m pip install --upgrade pyinstaller

# Generate the app icon if it isn't there yet (stdlib-only, no extra deps).
if (-not (Test-Path (Join-Path $root "app.ico"))) {
    Write-Host "Generating app.ico..."
    & $py (Join-Path $root "tools\make_icon.py")
}

Write-Host "Building LogsFinder.exe..."
& $py -m PyInstaller --onefile --windowed --name LogsFinder `
    --icon app.ico --add-data "app.ico;." main.py

$exe = Join-Path $root "dist\LogsFinder.exe"
if (-not (Test-Path $exe)) { throw "Build failed: $exe was not produced." }

# Assemble a clean release/ folder: just the exe + README, plus a zip.
# This is the single artifact you upload to GitHub Releases / hand to friends.
Write-Host "Packaging release..."
$rel = Join-Path $root "release"
if (Test-Path $rel) { Remove-Item $rel -Recurse -Force }
New-Item -ItemType Directory -Path $rel | Out-Null
Copy-Item $exe $rel
Copy-Item (Join-Path $root "README.md") $rel
$zip = Join-Path $rel "LogsFinder-v$version.zip"
Compress-Archive -Path (Join-Path $rel "LogsFinder.exe"), (Join-Path $rel "README.md") `
    -DestinationPath $zip -Force

Write-Host ""
Write-Host "Done."
Write-Host "  Standalone exe : dist\LogsFinder.exe"
Write-Host "  Release bundle : release\LogsFinder-v$version.zip  (exe + README)"
Write-Host "First run shows a Windows SmartScreen prompt - click 'More info' then 'Run anyway'."
