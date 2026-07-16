param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$DistDir = Join-Path $RepoRoot "dist\windows"
$ManifestPath = Join-Path $DistDir "manifest.txt"
$WorkPath = Join-Path $RepoRoot "build\windows"
$SpecPath = Join-Path $RepoRoot "build\windows-spec"

Set-Location $RepoRoot

if (-not $SkipTests) {
    py -3.12 -m pytest
    py -3.12 -m ruff format --check src tests
    py -3.12 -m ruff check src tests
    py -3.12 tools/check_chinese_project_text.py
}

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw "Missing PyInstaller. Install pyinstaller in the build environment first."
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

pyinstaller `
    --noconfirm `
    --clean `
    --name bagholder `
    --distpath $DistDir `
    --workpath $WorkPath `
    --specpath $SpecPath `
    -m stock_agent.bootstrap.entrypoints

Get-ChildItem -Recurse -File $DistDir |
    ForEach-Object { $_.FullName.Substring($RepoRoot.Path.Length + 1) } |
    Set-Content -Encoding UTF8 $ManifestPath

py -3.12 tools/packaging_guard.py $ManifestPath
Write-Host "Windows package build completed: $DistDir"
