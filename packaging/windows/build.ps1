param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$DistDir = Join-Path $RepoRoot "dist\windows"
$ManifestPath = Join-Path $DistDir "manifest.txt"
$WorkPath = Join-Path $RepoRoot "build\windows"
$SpecPath = Join-Path $RepoRoot "build\windows-spec"
$EntryScript = Join-Path $RepoRoot "src\stock_agent\bootstrap\packaging_entry.py"

function Assert-NativeCommandSucceeded {
    param(
        [string]$StepName
    )
    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE."
    }
}

Set-Location $RepoRoot

if (-not $SkipTests) {
    py -3.12 -m pytest
    Assert-NativeCommandSucceeded "pytest"
    py -3.12 -m ruff format --check src tests
    Assert-NativeCommandSucceeded "ruff format"
    py -3.12 -m ruff check src tests
    Assert-NativeCommandSucceeded "ruff check"
    py -3.12 tools/check_chinese_project_text.py
    Assert-NativeCommandSucceeded "Chinese text check"
}

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw "Missing PyInstaller. Install pyinstaller in the build environment first."
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

py -3.12 -m PyInstaller `
    --noconfirm `
    --clean `
    --name bagholder `
    --distpath $DistDir `
    --workpath $WorkPath `
    --specpath $SpecPath `
    $EntryScript
Assert-NativeCommandSucceeded "PyInstaller"

Get-ChildItem -Recurse -File $DistDir |
    ForEach-Object { $_.FullName.Substring($RepoRoot.Path.Length + 1) } |
    Set-Content -Encoding UTF8 $ManifestPath

py -3.12 tools/packaging_guard.py $ManifestPath
Assert-NativeCommandSucceeded "Packaging guard"
Write-Host "Windows package build completed: $DistDir"
