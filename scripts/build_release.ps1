param(
    [string]$Version = "1.2.0"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ReleaseRoot = Join-Path $ProjectRoot "release"
$PackageRoot = Join-Path $ReleaseRoot "ForgeEmulation-$Version-windows-x64"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The project virtual environment is missing. See BUILDING.md."
}

Push-Location $ProjectRoot
try {
    & $Python "scripts\fetch_cores.py"
    if ($LASTEXITCODE -ne 0) { throw "Core verification failed." }
    & $Python -m ruff format --check src scripts tests packaging
    if ($LASTEXITCODE -ne 0) { throw "Ruff formatting failed." }
    & $Python -m ruff check src scripts tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }
    & $Python -m mypy src
    if ($LASTEXITCODE -ne 0) { throw "MyPy failed." }
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

    Remove-Item -LiteralPath build, dist, dist-runtime -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PackageRoot -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null

    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
        --name ForgeEmulation --paths src packaging\forge_emulation_gui.py
    if ($LASTEXITCODE -ne 0) { throw "Frontend packaging failed." }
    & $Python -m PyInstaller --noconfirm --clean --windowed --onefile `
        --distpath dist-runtime --name ForgeEmulationRuntime --paths src `
        packaging\forge_emulation_runtime.py
    if ($LASTEXITCODE -ne 0) { throw "Runtime packaging failed." }

    # PyInstaller can resolve Qt's Windows ICU dependency from an unrelated toolchain on PATH.
    # Qt uses the Windows system ICU for this build, so any collected copy is contamination.
    $ContaminatingIcu = Join-Path $ProjectRoot "dist\ForgeEmulation\_internal\icuuc.dll"
    if (Test-Path -LiteralPath $ContaminatingIcu) {
        Remove-Item -LiteralPath $ContaminatingIcu -Force
    }

    Copy-Item -LiteralPath "dist\ForgeEmulation" -Destination $PackageRoot -Recurse
    $InternalRoot = Join-Path $PackageRoot "_internal"
    $NoticesRoot = Join-Path $PackageRoot "Open-Source-Notices"
    New-Item -ItemType Directory -Force -Path $NoticesRoot | Out-Null
    Copy-Item -LiteralPath "dist-runtime\ForgeEmulationRuntime.exe" -Destination $InternalRoot
    Copy-Item -LiteralPath "cores" -Destination (Join-Path $InternalRoot "cores") -Recurse
    Copy-Item -LiteralPath "third_party\licenses" -Destination (Join-Path $NoticesRoot "licenses") -Recurse
    Copy-Item -LiteralPath "third_party\source" -Destination (Join-Path $NoticesRoot "corresponding-source") -Recurse
    Copy-Item -LiteralPath "third_party\build-provenance" -Destination (Join-Path $NoticesRoot "build-provenance") -Recurse
    Copy-Item -LiteralPath "third_party\core-manifest.json" -Destination $NoticesRoot
    Copy-Item -LiteralPath "THIRD_PARTY_LICENSES.md" -Destination $NoticesRoot
    Copy-Item -LiteralPath "CORE_LICENSE_MATRIX.md" -Destination $NoticesRoot
    Copy-Item -LiteralPath "packaging\README.txt" -Destination $PackageRoot
    Copy-Item -LiteralPath "LICENSE" -Destination (Join-Path $PackageRoot "LICENSE.txt")

    & $Python "scripts\verify_packaged_runtime.py" $PackageRoot
    if ($LASTEXITCODE -ne 0) { throw "Packaged runtime verification failed." }

    $ZipPath = "$PackageRoot.zip"
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $ZipPath -CompressionLevel Optimal
    & $Python "scripts\verify_release_archive.py" $ZipPath
    if ($LASTEXITCODE -ne 0) { throw "Release archive layout verification failed." }
    $ArchiveHash = Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256
    "$($ArchiveHash.Hash)  $(Split-Path $ZipPath -Leaf)" | Set-Content -LiteralPath "$ZipPath.sha256"
    $ArchiveHash | Format-List
}
finally {
    Pop-Location
}
