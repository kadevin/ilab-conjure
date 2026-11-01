param(
  [string]$Version = "",
  [string]$OutputDir = ".dist",
  [string]$PythonVersion = "3.14.10",
  [string]$PythonSha256 = ""
)

$ErrorActionPreference = "Stop"

$ProjectName = "ilab-conjure"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

if ([System.IO.Path]::IsPathRooted($OutputDir)) {
  $BuildRoot = $OutputDir
} else {
  $BuildRoot = Join-Path $RepoRoot $OutputDir
}

if (-not $Version) {
  try {
    $Version = (git -C $RepoRoot describe --tags --always --dirty).Trim()
  } catch {
    $Version = Get-Date -Format "yyyyMMdd-HHmmss"
  }
}

$SafeVersion = ($Version -replace "[^A-Za-z0-9_.-]", "-").Trim("-")
if (-not $SafeVersion) {
  $SafeVersion = "dev"
}

$BundleName = "iLab-GPT-CONJURE-windows-x64"
$BundleRoot = Join-Path $BuildRoot $BundleName
$ResourcesDir = Join-Path $BundleRoot "resources"
$AppDir = Join-Path $ResourcesDir "app"
$PythonDir = Join-Path $ResourcesDir "python"
$CacheDir = Join-Path $BuildRoot "_cache"
$ZipPath = Join-Path $BuildRoot "${BundleName}_${SafeVersion}.zip"
$HashPath = "${ZipPath}.sha256.txt"
$ManifestPath = Join-Path $BuildRoot "windows-app-build.json"

$PythonEmbedZip = "python-${PythonVersion}-embed-amd64.zip"
$PythonEmbedUrl = "https://www.python.org/ftp/python/${PythonVersion}/${PythonEmbedZip}"
$PipWheelUrl = "https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl"
$PipWheelSha256 = "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
if (-not $PythonSha256 -and $PythonVersion -eq "3.14.10") {
  $PythonSha256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
}
if ($PythonSha256 -notmatch '^[0-9a-fA-F]{64}$') {
  throw "A verified -PythonSha256 is required for this Python version."
}

$AppItems = @(
  "codex_image",
  "launcher",
  "assets",
  "requirements-webui.txt",
  "package.json",
  "package-lock.json",
  "tsconfig.webui.json",
  "scripts/build-webui-css.mjs",
  "pyproject.toml",
  "README.md",
  "README.zh-CN.md",
  "LICENSE",
  "SECURITY.md",
  "CONTRIBUTING.md"
)

function Copy-AppItem {
  param(
    [string]$RelativePath
  )

  $Source = Join-Path $RepoRoot $RelativePath
  if (-not (Test-Path $Source)) {
    return
  }
  $Target = Join-Path $AppDir $RelativePath
  $TargetParent = Split-Path -Parent $Target
  New-Item -ItemType Directory -Force -Path $TargetParent | Out-Null
  Copy-Item -Path $Source -Destination $Target -Recurse -Force
}

function Remove-LocalArtifacts {
  param(
    [string]$Root
  )

  $Names = @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store", "target")
  foreach ($Name in $Names) {
    Get-ChildItem -Path $Root -Recurse -Force -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -eq $Name } |
      Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  }
  Get-ChildItem -Path $Root -Recurse -Force -Include "*.pyc", "*.pyo" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path $BuildRoot, $CacheDir | Out-Null
if (Test-Path $BundleRoot) {
  Remove-Item -Recurse -Force $BundleRoot
}
if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
if (Test-Path $HashPath) {
  Remove-Item -Force $HashPath
}

New-Item -ItemType Directory -Force -Path $AppDir, $PythonDir | Out-Null

foreach ($Item in $AppItems) {
  Copy-AppItem -RelativePath $Item
}

Copy-Item -Path (Join-Path $ScriptDir "standard_webui_app.py") -Destination (Join-Path $AppDir "standard_webui_app.py") -Force
Copy-Item -Path (Join-Path $ScriptDir "README-app.md") -Destination (Join-Path $BundleRoot "README-app.md") -Force
Copy-Item -Path (Join-Path $ScriptDir "THIRD_PARTY_NOTICES.md") -Destination (Join-Path $ResourcesDir "THIRD_PARTY_NOTICES.md") -Force
if (Test-Path (Join-Path $AppDir "LICENSE")) {
  Copy-Item -Path (Join-Path $AppDir "LICENSE") -Destination (Join-Path $BundleRoot "LICENSE") -Force
}
Set-Content -Path (Join-Path $ResourcesDir "app-version.txt") -Value $Version -Encoding ASCII
Remove-LocalArtifacts -Root $AppDir

$EmbedZipPath = Join-Path $CacheDir $PythonEmbedZip
if (-not (Test-Path $EmbedZipPath)) {
  Write-Host "Downloading $PythonEmbedUrl"
  Invoke-WebRequest -Uri $PythonEmbedUrl -OutFile $EmbedZipPath
}

if ((Get-FileHash -Path $EmbedZipPath -Algorithm SHA256).Hash -ne $PythonSha256) {
  throw "Python runtime SHA256 mismatch."
}
Expand-Archive -Path $EmbedZipPath -DestinationPath $PythonDir -Force

$PythonPathFile = Get-ChildItem -Path $PythonDir -Filter "python*._pth" | Select-Object -First 1
if ($null -eq $PythonPathFile) {
  throw "Could not find python*._pth in embedded Python runtime."
}

$PathLines = Get-Content $PythonPathFile.FullName
$NextPathLines = New-Object System.Collections.Generic.List[string]
$HasAppPath = $false
$HasImportSite = $false
foreach ($Line in $PathLines) {
  if ($Line.Trim() -eq "..\app") {
    $HasAppPath = $true
  }
  if ($Line.Trim() -eq "import site" -or $Line.Trim() -eq "#import site") {
    if (-not $HasAppPath) {
      $NextPathLines.Add("..\app")
      $HasAppPath = $true
    }
    $NextPathLines.Add("import site")
    $HasImportSite = $true
    continue
  }
  $NextPathLines.Add($Line)
}
if (-not $HasAppPath) {
  $NextPathLines.Add("..\app")
}
if (-not $HasImportSite) {
  $NextPathLines.Add("import site")
}
Set-Content -Path $PythonPathFile.FullName -Value $NextPathLines -Encoding ASCII

$PythonExe = Join-Path $PythonDir "python.exe"
& $PythonExe (Join-Path $AppDir "codex_image\runtime_security.py")
if ($LASTEXITCODE -ne 0) { throw "Python security baseline check failed." }
$PipWheelPath = Join-Path $CacheDir "pip-26.2.2-py3-none-any.whl"
if (-not (Test-Path $PipWheelPath)) {
  Invoke-WebRequest -Uri $PipWheelUrl -OutFile $PipWheelPath
}
if ((Get-FileHash -Path $PipWheelPath -Algorithm SHA256).Hash -ne $PipWheelSha256) {
  throw "pip wheel SHA256 mismatch."
}
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_NO_CACHE_DIR = "1"
& $PythonExe -m zipfile -e $PipWheelPath (Join-Path $PythonDir "Lib\site-packages")
if ($LASTEXITCODE -ne 0) { throw "Could not bootstrap the verified pip wheel." }
& $PythonExe -m pip --version
if ($LASTEXITCODE -ne 0) { throw "Could not run pip." }
& $PythonExe -m pip install --require-hashes --no-warn-script-location -r (Join-Path $AppDir "requirements-webui.txt")
if ($LASTEXITCODE -ne 0) { throw "Runtime dependency installation failed." }
$CertifiCaBundle = Join-Path $PythonDir "Lib\site-packages\certifi\cacert.pem"
if (-not (Test-Path $CertifiCaBundle)) {
  throw "certifi CA bundle was not installed at $CertifiCaBundle"
}
& $PythonExe -m pip freeze | Set-Content -Path (Join-Path $ResourcesDir "python-requirements.lock.txt") -Encoding UTF8
if ($LASTEXITCODE -ne 0) { throw "Runtime dependency inventory failed." }
$env:APP_LAUNCHER_MODE = "standard"
$env:ILAB_CONJURE_APP_DIR = $AppDir
$env:ILAB_CONJURE_DATA_DIR = Join-Path $BuildRoot "_standard-data-probe"
& $PythonExe -c "import fastapi, uvicorn, multipart, httpx, PIL; import standard_webui_app; print('standard import ok')"
if ($LASTEXITCODE -ne 0) { throw "Packaged application import check failed." }
Remove-Item -Recurse -Force $env:ILAB_CONJURE_DATA_DIR -ErrorAction SilentlyContinue
Remove-Item Env:APP_LAUNCHER_MODE -ErrorAction SilentlyContinue
Remove-Item Env:ILAB_CONJURE_APP_DIR -ErrorAction SilentlyContinue
Remove-Item Env:ILAB_CONJURE_DATA_DIR -ErrorAction SilentlyContinue
& $PythonExe (Join-Path $ScriptDir "..\cleanup-runtime.py") `
  --app-dir $AppDir `
  --runtime-dir $PythonDir `
  --platform windows
if ($LASTEXITCODE -ne 0) { throw "Packaged runtime cleanup failed." }
& $PythonExe (Join-Path $AppDir "codex_image\runtime_security.py") --runtime
if ($LASTEXITCODE -ne 0) { throw "Packaged runtime security check failed." }
& $PythonExe -m codex_image.dependency_check --requirements (Join-Path $AppDir "requirements-webui.txt")
if ($LASTEXITCODE -ne 0) { throw "Trimmed runtime dependency check failed." }

if ($null -eq (Get-Command cargo -ErrorAction SilentlyContinue)) {
  throw "cargo was not found. Install Rust toolchain before building the standard app launcher."
}
& cargo build --manifest-path (Join-Path $RepoRoot "launcher\Cargo.toml") --release --locked
if ($LASTEXITCODE -ne 0) {
  throw "Rust tray launcher build failed."
}
$LauncherExe = Join-Path $RepoRoot "launcher\target\release\ilab-conjure-launcher.exe"
if (-not (Test-Path $LauncherExe)) {
  throw "Rust tray launcher binary was not found at $LauncherExe"
}
Copy-Item -Path $LauncherExe -Destination (Join-Path $BundleRoot "iLab GPT CONJURE.exe") -Force

Compress-Archive -Path (Join-Path $BundleRoot "*") -DestinationPath $ZipPath -CompressionLevel Optimal
$Hash = Get-FileHash -Path $ZipPath -Algorithm SHA256
[System.IO.File]::WriteAllText(
  $HashPath,
  "$($Hash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $ZipPath)`n",
  [System.Text.Encoding]::ASCII
)

$Manifest = [ordered]@{
  project = $ProjectName
  version = $Version
  bundle = $BundleName
  zip = (Resolve-Path $ZipPath).Path
  sha256 = $Hash.Hash.ToLowerInvariant()
  python_version = $PythonVersion
  data_dir = "%APPDATA%\iLab GPT CONJURE"
}
$Manifest | ConvertTo-Json | Set-Content -Path $ManifestPath -Encoding UTF8

Write-Host "Built $ZipPath"
Write-Host "SHA256 $($Hash.Hash.ToLowerInvariant())"
