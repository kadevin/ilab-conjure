param(
  [switch]$AutoInstall,
  [switch]$RestartLauncher
)

$ErrorActionPreference = "Stop"

$RepoSlug = "kadevin/ilab-conjure"
$LatestUpdateManifestUrl = "https://github.com/kadevin/ilab-conjure/releases/latest/download/latest.json"
$PlatformKey = "windows-x86_64"
$AssetPattern = "^ilab-gpt-conjure_windows_portable_x64_.+\.zip$"
$BundleDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $BundleDir "data"
$VersionFile = Join-Path $BundleDir "portable-version.txt"
$UpdateNoticeFile = Join-Path $DataDir "update-notice.json"
$PostUpdateOnboardingFile = Join-Path $DataDir "post-update-onboarding.json"
$LauncherExe = Join-Path $BundleDir "Start iLab GPT CONJURE.exe"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "ilab-gpt-conjure-update-$Timestamp"
$ExtractDir = Join-Path $TempRoot "extract"
$ManifestPath = Join-Path $TempRoot "latest.json"
$BackupRoot = Join-Path $BundleDir ".backup"
$BackupDir = Join-Path $BackupRoot "update-$Timestamp"
$Headers = @{
  "Accept" = "application/json"
  "User-Agent" = "ilab-gpt-conjure-portable-updater"
}

# Do not move data. The data directory contains user settings, API keys, gallery
# assets, inputs, outputs, history, task databases, and logs.
$ReplaceItems = @(
  "app",
  "python",
  "Start iLab GPT CONJURE.exe",
  "Start WebUI Portable.bat",
  "Update WebUI Portable.bat",
  "Update WebUI Portable.ps1",
  "README-portable.md",
  "THIRD_PARTY_NOTICES.md",
  "LICENSE",
  "python-requirements.lock.txt",
  "portable-version.txt"
)

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message"
}

function Get-ManifestPlatform {
  param(
    [Parameter(Mandatory = $true)] $Manifest,
    [Parameter(Mandatory = $true)][string] $PlatformKey
  )
  if ($null -eq $Manifest.platforms) {
    throw "Update manifest does not include platforms."
  }
  $Platform = $Manifest.platforms.PSObject.Properties[$PlatformKey].Value
  if ($null -eq $Platform) {
    throw "Update manifest does not include platform entry: $PlatformKey"
  }
  return $Platform
}

function Get-CurrentPortableVersion {
  if (-not (Test-Path $VersionFile)) {
    return ""
  }
  return ((Get-Content -Path $VersionFile -TotalCount 1) -replace "\s", "")
}

function ConvertTo-VersionTuple {
  param([string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) {
    return $null
  }
  $Match = [regex]::Match($Value.Trim(), "^[vV]?(\d+)\.(\d+)\.(\d+)")
  if (-not $Match.Success) {
    return $null
  }
  return @(
    [int]$Match.Groups[1].Value,
    [int]$Match.Groups[2].Value,
    [int]$Match.Groups[3].Value
  )
}

function Test-VersionCurrentOrNewer {
  param(
    [string]$Current,
    [string]$Latest
  )
  $CurrentParts = ConvertTo-VersionTuple -Value $Current
  $LatestParts = ConvertTo-VersionTuple -Value $Latest
  if ($null -eq $CurrentParts -or $null -eq $LatestParts) {
    return $false
  }
  for ($Index = 0; $Index -lt 3; $Index++) {
    if ($CurrentParts[$Index] -gt $LatestParts[$Index]) {
      return $true
    }
    if ($CurrentParts[$Index] -lt $LatestParts[$Index]) {
      return $false
    }
  }
  return $true
}

function Clear-UpdateNotice {
  if (Test-Path $UpdateNoticeFile) {
    Remove-Item -Force $UpdateNoticeFile -ErrorAction SilentlyContinue
  }
}

function ConvertTo-VersionString {
  param([string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) {
    return ""
  }
  $Match = [regex]::Match($Value.Trim(), "^[vV]?(\d+)\.(\d+)\.(\d+)")
  if (-not $Match.Success) {
    return ""
  }
  return "$($Match.Groups[1].Value).$($Match.Groups[2].Value).$($Match.Groups[3].Value)"
}

function Write-PostUpdateOnboardingNotice {
  param(
    [string]$FromVersion,
    [string]$ToVersion
  )
  try {
    $NormalizedTo = ConvertTo-VersionString -Value $ToVersion
    if ([string]::IsNullOrWhiteSpace($NormalizedTo)) {
      return
    }
    $NormalizedFrom = ConvertTo-VersionString -Value $FromVersion
    $ReleaseUrl = "https://github.com/kadevin/ilab-conjure/releases/tag/v$NormalizedTo"
    $Payload = [ordered]@{
      kind = "portable_standard_app_transition"
      to_version = $NormalizedTo
      to_version_label = "v$NormalizedTo"
      updated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
      dismissed = $false
      release_url = $ReleaseUrl
      standard_download_url = $ReleaseUrl
    }
    if (-not [string]::IsNullOrWhiteSpace($NormalizedFrom)) {
      $Payload["from_version"] = $NormalizedFrom
      $Payload["from_version_label"] = "v$NormalizedFrom"
    }
    if (-not (Test-Path $DataDir)) {
      New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    }
    $Json = ($Payload | ConvertTo-Json -Depth 4)
    $Utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($PostUpdateOnboardingFile, "$Json`n", $Utf8NoBom)
  } catch {
    Write-Host "Could not write post-update onboarding notice: $($_.Exception.Message)"
  }
}

function Get-NormalizedPath {
  param([Parameter(Mandatory = $true)][string] $Path)
  return [System.IO.Path]::GetFullPath($Path).TrimEnd([char[]] @("\", "/"))
}

function Assert-PathInsideBundle {
  param([Parameter(Mandatory = $true)][string] $Path)
  $BundleRoot = Get-NormalizedPath -Path $BundleDir
  $FullPath = Get-NormalizedPath -Path $Path
  if ($FullPath -eq $BundleRoot) {
    return
  }
  $ExpectedPrefix = $BundleRoot + [System.IO.Path]::DirectorySeparatorChar
  $AltExpectedPrefix = $BundleRoot + [System.IO.Path]::AltDirectorySeparatorChar
  if (
    -not $FullPath.StartsWith($ExpectedPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
    -not $FullPath.StartsWith($AltExpectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)
  ) {
    throw "Refusing to modify path outside bundle: $FullPath"
  }
}

function Assert-ReplaceItemName {
  param([Parameter(Mandatory = $true)][string] $Item)
  if ([System.IO.Path]::IsPathRooted($Item) -or $Item -match '(^|[\\/])\.\.([\\/]|$)') {
    throw "Refusing unsafe replace item: $Item"
  }
}

function Restore-Backup {
  if (-not (Test-Path $BackupDir)) {
    return
  }
  Write-Host "Restoring previous files from $BackupDir"
  foreach ($Item in $ReplaceItems) {
    Assert-ReplaceItemName -Item $Item
    $BackupItem = Join-Path $BackupDir $Item
    $TargetItem = Join-Path $BundleDir $Item
    Assert-PathInsideBundle -Path $BackupItem
    Assert-PathInsideBundle -Path $TargetItem
    if (-not (Test-Path $BackupItem)) {
      continue
    }
    if (Test-Path $TargetItem) {
      Remove-Item -Recurse -Force $TargetItem
    }
    $TargetParent = Split-Path -Parent $TargetItem
    if ($TargetParent -and -not (Test-Path $TargetParent)) {
      New-Item -ItemType Directory -Force -Path $TargetParent | Out-Null
    }
    Move-Item -Force $BackupItem $TargetItem
  }
}

try {
  Write-Host "iLab CONJURE portable updater"
  Write-Host "Bundle: $BundleDir"
  Write-Host "Data:   $DataDir"

  if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
  }
  New-Item -ItemType Directory -Force -Path $TempRoot, $ExtractDir | Out-Null

  Write-Step "Checking latest release"
  Invoke-WebRequest -UseBasicParsing -Uri $LatestUpdateManifestUrl -Headers $Headers -OutFile $ManifestPath
  if (-not (Test-Path $LauncherExe)) {
    throw "Could not verify update manifest because the tray launcher was not found."
  }
  & $LauncherExe --verify-update-manifest $ManifestPath
  if ($LASTEXITCODE -ne 0) {
    throw "Update manifest signature verification failed."
  }
  $Manifest = Get-Content -Raw $ManifestPath | ConvertFrom-Json
  $Platform = Get-ManifestPlatform -Manifest $Manifest -PlatformKey $PlatformKey
  $ReleaseVersion = [string]$Manifest.version
  $ZipName = [string]$Platform.asset
  $ZipUrl = [string]$Platform.url
  $ExpectedHash = ([string]$Platform.sha256).ToLowerInvariant()
  if ($ZipName -notmatch $AssetPattern) {
    throw "Manifest asset does not match the Windows x64 portable package pattern: $ZipName"
  }
  if ([string]::IsNullOrWhiteSpace($ZipUrl)) {
    throw "Update manifest platform $PlatformKey does not include url."
  }
  if ($ExpectedHash -notmatch "^[0-9a-f]{64}$") {
    throw "Update manifest platform $PlatformKey does not include a valid sha256."
  }

  $CurrentVersion = Get-CurrentPortableVersion
  if (Test-VersionCurrentOrNewer -Current $CurrentVersion -Latest $ReleaseVersion) {
    Clear-UpdateNotice
    Write-Host ""
    Write-Host "Already up to date ($ReleaseVersion)."
    Write-Host "No app files were changed."
    exit 0
  }

  Write-Host ""
  if (-not [string]::IsNullOrWhiteSpace($CurrentVersion)) {
    Write-Host "Current version: $CurrentVersion"
  } else {
    Write-Host "Current version: unknown"
  }
  Write-Host "Latest version:  $ReleaseVersion"
  Write-Host "Release asset:   $ZipName"
  Write-Host "Manifest SHA256: $ExpectedHash"
  Write-Host "Download URL:    $ZipUrl"
  Write-Host ""
  Write-Host "Quit the system tray launcher and close any WebUI server window before updating."
  if ($AutoInstall) {
    Write-Host "Auto install requested; continuing without prompt."
  } else {
    Read-Host "Press Enter to continue"
  }

  $ZipPath = Join-Path $TempRoot $ZipName

  Write-Step "Downloading $ReleaseVersion"
  Invoke-WebRequest -UseBasicParsing -Uri $ZipUrl -OutFile $ZipPath

  Write-Step "Verifying SHA256"
  $ActualHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($ExpectedHash -ne $ActualHash) {
    throw "SHA256 mismatch. Expected $ExpectedHash but got $ActualHash."
  }

  Write-Step "Extracting update package"
  Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force
  $NewRoot = $ExtractDir
  if (-not (Test-Path (Join-Path $NewRoot "app"))) {
    $Candidates = @(Get-ChildItem -Path $ExtractDir -Directory | Where-Object { Test-Path (Join-Path $_.FullName "app") })
    if ($Candidates.Count -ne 1) {
      throw "Could not identify extracted portable bundle root."
    }
    $NewRoot = $Candidates[0].FullName
  }

  foreach ($RequiredItem in @("app", "python", "Start iLab GPT CONJURE.exe", "portable-version.txt")) {
    if (-not (Test-Path (Join-Path $NewRoot $RequiredItem))) {
      throw "Downloaded package is missing required item: $RequiredItem"
    }
  }

  New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

  if ($AutoInstall) {
    Write-Host "Waiting for the current launcher process to exit before replacing files."
    Start-Sleep -Seconds 2
  }

  Write-Step "Backing up current app files"
  foreach ($Item in $ReplaceItems) {
    Assert-ReplaceItemName -Item $Item
    $CurrentItem = Join-Path $BundleDir $Item
    if (-not (Test-Path $CurrentItem)) {
      continue
    }
    $BackupItem = Join-Path $BackupDir $Item
    Assert-PathInsideBundle -Path $CurrentItem
    Assert-PathInsideBundle -Path $BackupItem
    $BackupParent = Split-Path -Parent $BackupItem
    if ($BackupParent -and -not (Test-Path $BackupParent)) {
      New-Item -ItemType Directory -Force -Path $BackupParent | Out-Null
    }
    Move-Item -Force $CurrentItem $BackupItem
  }

  Write-Step "Installing updated app files"
  foreach ($Item in $ReplaceItems) {
    Assert-ReplaceItemName -Item $Item
    $SourceItem = Join-Path $NewRoot $Item
    if (-not (Test-Path $SourceItem)) {
      continue
    }
    $TargetItem = Join-Path $BundleDir $Item
    Assert-PathInsideBundle -Path $TargetItem
    $TargetParent = Split-Path -Parent $TargetItem
    if ($TargetParent -and -not (Test-Path $TargetParent)) {
      New-Item -ItemType Directory -Force -Path $TargetParent | Out-Null
    }
    Copy-Item -Recurse -Force $SourceItem $TargetItem
  }

  Write-Step "Update complete"
  Clear-UpdateNotice
  Write-PostUpdateOnboardingNotice -FromVersion $CurrentVersion -ToVersion $ReleaseVersion
  Write-Host "Updated to $ReleaseVersion."
  Write-Host "Data was preserved at $DataDir"
  Write-Host "Backup was saved at $BackupDir"
  if ($RestartLauncher -and (Test-Path $LauncherExe)) {
    Write-Host "Restarting Start iLab GPT CONJURE.exe."
    Start-Process -FilePath $LauncherExe -WorkingDirectory $BundleDir
  } else {
    Write-Host "Start the WebUI again with Start iLab GPT CONJURE.exe."
  }
} catch {
  Write-Host ""
  Write-Host "Update failed: $($_.Exception.Message)"
  try {
    Restore-Backup
  } catch {
    Write-Host "Rollback failed: $($_.Exception.Message)"
  }
  exit 1
} finally {
  if (Test-Path $TempRoot) {
    Remove-Item -Recurse -Force $TempRoot -ErrorAction SilentlyContinue
  }
}
