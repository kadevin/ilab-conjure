$ErrorActionPreference = "Stop"

$RepoSlug = "kadevin/ilab-gpt-conjure"
$LatestReleaseUrl = "https://api.github.com/repos/kadevin/ilab-gpt-conjure/releases/latest"
$AssetPattern = "^ilab-gpt-conjure_windows_portable_x64_.+\.zip$"
$BundleDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $BundleDir "data"
$VersionFile = Join-Path $BundleDir "portable-version.txt"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "ilab-gpt-conjure-update-$Timestamp"
$ExtractDir = Join-Path $TempRoot "extract"
$BackupRoot = Join-Path $BundleDir ".backup"
$BackupDir = Join-Path $BackupRoot "update-$Timestamp"
$Headers = @{
  "Accept" = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
  "User-Agent" = "ilab-gpt-conjure-portable-updater"
}

# Do not move data. The data directory contains user settings, API keys, gallery
# assets, inputs, outputs, history, task databases, and logs.
$ReplaceItems = @(
  "app",
  "python",
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

function Get-ReleaseAsset {
  param(
    [Parameter(Mandatory = $true)] $Release,
    [Parameter(Mandatory = $true)][string] $Pattern
  )
  return @($Release.assets | Where-Object { $_.name -match $Pattern } | Select-Object -First 1)[0]
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

function Restore-Backup {
  if (-not (Test-Path $BackupDir)) {
    return
  }
  Write-Host "Restoring previous files from $BackupDir"
  foreach ($Item in $ReplaceItems) {
    $BackupItem = Join-Path $BackupDir $Item
    $TargetItem = Join-Path $BundleDir $Item
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
  Write-Host "iLab GPT Conjure portable updater"
  Write-Host "Bundle: $BundleDir"
  Write-Host "Data:   $DataDir"

  if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
  }
  New-Item -ItemType Directory -Force -Path $TempRoot, $ExtractDir | Out-Null

  Write-Step "Checking latest release"
  $Release = Invoke-RestMethod -Uri $LatestReleaseUrl -Headers $Headers
  $ZipAsset = Get-ReleaseAsset -Release $Release -Pattern $AssetPattern
  if ($null -eq $ZipAsset) {
    throw "Could not find a Windows x64 portable asset in latest release $($Release.tag_name)."
  }
  $HashAsset = @($Release.assets | Where-Object { $_.name -eq "$($ZipAsset.name).sha256.txt" } | Select-Object -First 1)[0]
  if ($null -eq $HashAsset) {
    throw "Could not find SHA256 file for $($ZipAsset.name)."
  }

  $CurrentVersion = Get-CurrentPortableVersion
  if (Test-VersionCurrentOrNewer -Current $CurrentVersion -Latest $Release.tag_name) {
    Write-Host ""
    Write-Host "Already up to date ($($Release.tag_name))."
    Write-Host "No app files were changed."
    exit 0
  }

  Write-Host ""
  if (-not [string]::IsNullOrWhiteSpace($CurrentVersion)) {
    Write-Host "Current version: $CurrentVersion"
  } else {
    Write-Host "Current version: unknown"
  }
  Write-Host "Latest version:  $($Release.tag_name)"
  Write-Host ""
  Write-Host "Close the WebUI server window before updating."
  Read-Host "Press Enter to continue"

  $ZipPath = Join-Path $TempRoot $ZipAsset.name
  $HashPath = Join-Path $TempRoot $HashAsset.name

  Write-Step "Downloading $($Release.tag_name)"
  Invoke-WebRequest -UseBasicParsing -Uri $ZipAsset.browser_download_url -OutFile $ZipPath
  Invoke-WebRequest -UseBasicParsing -Uri $HashAsset.browser_download_url -OutFile $HashPath

  Write-Step "Verifying SHA256"
  $ExpectedHash = ((Get-Content -Raw $HashPath) -split "\s+")[0].ToLowerInvariant()
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

  foreach ($RequiredItem in @("app", "python", "Start WebUI Portable.bat", "portable-version.txt")) {
    if (-not (Test-Path (Join-Path $NewRoot $RequiredItem))) {
      throw "Downloaded package is missing required item: $RequiredItem"
    }
  }

  New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

  Write-Step "Backing up current app files"
  foreach ($Item in $ReplaceItems) {
    $CurrentItem = Join-Path $BundleDir $Item
    if (-not (Test-Path $CurrentItem)) {
      continue
    }
    $BackupItem = Join-Path $BackupDir $Item
    $BackupParent = Split-Path -Parent $BackupItem
    if ($BackupParent -and -not (Test-Path $BackupParent)) {
      New-Item -ItemType Directory -Force -Path $BackupParent | Out-Null
    }
    Move-Item -Force $CurrentItem $BackupItem
  }

  Write-Step "Installing updated app files"
  foreach ($Item in $ReplaceItems) {
    $SourceItem = Join-Path $NewRoot $Item
    if (-not (Test-Path $SourceItem)) {
      continue
    }
    $TargetItem = Join-Path $BundleDir $Item
    $TargetParent = Split-Path -Parent $TargetItem
    if ($TargetParent -and -not (Test-Path $TargetParent)) {
      New-Item -ItemType Directory -Force -Path $TargetParent | Out-Null
    }
    Copy-Item -Recurse -Force $SourceItem $TargetItem
  }

  Write-Step "Update complete"
  Write-Host "Updated to $($Release.tag_name)."
  Write-Host "Data was preserved at $DataDir"
  Write-Host "Backup was saved at $BackupDir"
  Write-Host "Start the WebUI again with Start WebUI Portable.bat."
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
