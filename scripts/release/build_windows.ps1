param(
    [string]$Version = "0.0.0-dev",
    [string]$PythonExe = "python",
    [string]$DistDir = "dist",
    [string]$BundleName = "HOH-Game",
    [string]$InnoScriptPath = ""
)

$ErrorActionPreference = "Stop"

Write-Host "Installing release build dependencies..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install pyinstaller build

Write-Host "Installing application runtime dependencies..."
& $PythonExe -m pip install .

Write-Host "Building wheel + sdist..."
& $PythonExe -m build

Write-Host "Building PyInstaller bundle..."
& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $BundleName `
    --collect-submodules bleak.backends `
    --add-data "assets;assets" `
    --add-data "config;config" `
    app/__main__.py

$sourceDirRel = Join-Path $DistDir $BundleName
if (-not (Test-Path $sourceDirRel)) {
    throw "Expected PyInstaller output missing at '$sourceDirRel'."
}
$sourceDir = (Resolve-Path -LiteralPath $sourceDirRel).Path

$portableZip = Join-Path $DistDir "hoh-game-$Version-portable-win64.zip"
if (Test-Path $portableZip) {
    Remove-Item $portableZip -Force
}
Compress-Archive -Path "$sourceDir\*" -DestinationPath $portableZip -Force
Write-Host "Portable artifact: $portableZip"

if (-not (Get-Command iscc -ErrorAction SilentlyContinue)) {
    Write-Warning "Inno Setup compiler (iscc) not found; skipping Setup.exe generation."
    Write-Host "Install Inno Setup from https://jrsoftware.org/isinfo.php to build GUI installer."
    exit 0
}

$hasInnoScript = -not [string]::IsNullOrWhiteSpace($InnoScriptPath)
if (-not $hasInnoScript -or -not (Test-Path -LiteralPath $InnoScriptPath)) {
    Write-Warning "No Inno Setup script configured/found; skipping Setup.exe generation."
    exit 0
}

$installerOutputRel = Join-Path $DistDir "installer"
if (-not (Test-Path $installerOutputRel)) {
    New-Item -ItemType Directory -Path $installerOutputRel | Out-Null
}
$installerOutput = (Resolve-Path -LiteralPath $installerOutputRel).Path
$innoScript = (Resolve-Path -LiteralPath $InnoScriptPath).Path

Write-Host "Building Inno Setup installer..."
& iscc "/DMyAppVersion=$Version" "/DSourceDir=$sourceDir" "/DOutputDir=$installerOutput" $innoScript
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}
Write-Host "Installer artifacts written to: $installerOutput"
