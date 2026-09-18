use crate::{RELEASES_URL, UPDATE_SIGNING_PUBLIC_KEY_B64};
use anyhow::{anyhow, Context, Result};
use base64::{engine::general_purpose, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use std::{cmp::Ordering, collections::BTreeMap, fs, path::Path};

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct UpdatePlatform {
    pub(super) asset: String,
    pub(super) url: String,
    pub(super) sha256: String,
    pub(super) package: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct UpdateSignature {
    pub(super) algorithm: String,
    pub(super) value: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct UpdateManifest {
    pub(super) schema_version: u64,
    pub(super) version: String,
    pub(super) release_url: String,
    pub(super) notes: String,
    pub(super) signature: Option<UpdateSignature>,
    pub(super) standard_signature: Option<UpdateSignature>,
    pub(super) platforms: BTreeMap<String, UpdatePlatform>,
    pub(super) standard_platforms: BTreeMap<String, UpdatePlatform>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum UpdateAvailability {
    UpToDate,
    UpdateAvailable,
    UnknownCurrentVersion,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum UpdatePackageKind {
    Portable,
    Standard,
    Source,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct UpdateCheck {
    pub(super) current_version: String,
    pub(super) latest_version: String,
    pub(super) release_url: String,
    pub(super) download_url: Option<String>,
    pub(super) download_sha256: Option<String>,
    pub(super) package: Option<String>,
    pub(super) availability: UpdateAvailability,
}

pub(super) fn parse_update_manifest_payload(payload: &str) -> Result<UpdateManifest> {
    let value: serde_json::Value =
        serde_json::from_str(payload).context("failed to parse update manifest")?;
    let schema_version = value
        .get("schema_version")
        .and_then(|field| field.as_u64())
        .unwrap_or(1);
    if schema_version != 1 {
        return Err(anyhow!(
            "unsupported update manifest schema_version {schema_version}"
        ));
    }
    let version = value
        .get("version")
        .and_then(|field| field.as_str())
        .map(str::trim)
        .filter(|field| !field.is_empty())
        .ok_or_else(|| anyhow!("update manifest did not include version"))?
        .to_string();
    let release_url = value
        .get("release_url")
        .and_then(|field| field.as_str())
        .map(str::trim)
        .filter(|field| !field.is_empty())
        .unwrap_or(RELEASES_URL)
        .to_string();
    let notes = value
        .get("notes")
        .and_then(|field| field.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let signature = parse_update_signature(value.get("signature"));
    let standard_signature = parse_update_signature(value.get("standard_signature"));
    let platforms = parse_update_platforms(value.get("platforms"), "platforms")?;
    let standard_platforms =
        parse_optional_update_platforms(value.get("standard_platforms"), "standard_platforms")?;
    if platforms.is_empty() {
        return Err(anyhow!(
            "update manifest did not include any usable platform entries"
        ));
    }

    Ok(UpdateManifest {
        schema_version,
        version,
        release_url,
        notes,
        signature,
        standard_signature,
        platforms,
        standard_platforms,
    })
}

pub(super) fn parse_update_signature(value: Option<&serde_json::Value>) -> Option<UpdateSignature> {
    let object = value?.as_object()?;
    let algorithm = object
        .get("algorithm")
        .and_then(|field| field.as_str())
        .map(str::trim)
        .filter(|field| !field.is_empty())?;
    let value = object
        .get("value")
        .and_then(|field| field.as_str())
        .map(str::trim)
        .filter(|field| !field.is_empty())?;
    Some(UpdateSignature {
        algorithm: algorithm.to_string(),
        value: value.to_string(),
    })
}

pub(super) fn parse_optional_update_platforms(
    value: Option<&serde_json::Value>,
    field_name: &str,
) -> Result<BTreeMap<String, UpdatePlatform>> {
    match value {
        Some(_) => parse_update_platforms(value, field_name),
        None => Ok(BTreeMap::new()),
    }
}

pub(super) fn parse_update_platforms(
    value: Option<&serde_json::Value>,
    field_name: &str,
) -> Result<BTreeMap<String, UpdatePlatform>> {
    let mut platforms = BTreeMap::new();
    let platform_values = value
        .and_then(|field| field.as_object())
        .ok_or_else(|| anyhow!("update manifest did not include {field_name}"))?;
    for (key, platform) in platform_values {
        let Some(url) = platform
            .get("url")
            .and_then(|field| field.as_str())
            .map(str::trim)
            .filter(|field| !field.is_empty())
        else {
            continue;
        };
        let Some(sha256) = platform
            .get("sha256")
            .and_then(|field| field.as_str())
            .map(str::trim)
            .filter(|field| is_sha256_hex(field))
        else {
            continue;
        };
        let asset = platform
            .get("asset")
            .and_then(|field| field.as_str())
            .map(str::trim)
            .filter(|field| !field.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| {
                url.rsplit('/')
                    .next()
                    .filter(|name| !name.is_empty())
                    .unwrap_or("update.zip")
                    .to_string()
            });
        let package = platform
            .get("package")
            .and_then(|field| field.as_str())
            .map(str::trim)
            .filter(|field| !field.is_empty())
            .unwrap_or("portable-zip")
            .to_string();
        platforms.insert(
            key.to_string(),
            UpdatePlatform {
                asset,
                url: url.to_string(),
                sha256: sha256.to_ascii_lowercase(),
                package,
            },
        );
    }
    Ok(platforms)
}

pub(super) fn is_sha256_hex(value: &str) -> bool {
    value.len() == 64 && value.chars().all(|ch| ch.is_ascii_hexdigit())
}

pub(super) fn update_check_from_manifest(
    current_version: &str,
    manifest: &UpdateManifest,
    package_kind: UpdatePackageKind,
) -> UpdateCheck {
    let latest_version = version_label_from_raw(&manifest.version);
    let availability = match compare_version_labels(current_version, &latest_version) {
        Some(Ordering::Less) => UpdateAvailability::UpdateAvailable,
        Some(Ordering::Equal | Ordering::Greater) => UpdateAvailability::UpToDate,
        None => UpdateAvailability::UnknownCurrentVersion,
    };
    let platform_map = match package_kind {
        UpdatePackageKind::Portable => &manifest.platforms,
        UpdatePackageKind::Standard => &manifest.standard_platforms,
        UpdatePackageKind::Source => &manifest.platforms,
    };
    let platform = platform_map.get(current_update_platform_key());
    UpdateCheck {
        current_version: current_version.to_string(),
        latest_version,
        release_url: manifest.release_url.clone(),
        download_url: platform.map(|entry| entry.url.clone()),
        download_sha256: platform.map(|entry| entry.sha256.clone()),
        package: platform.map(|entry| entry.package.clone()),
        availability,
    }
}

pub fn verify_update_manifest_file(path: &Path) -> Result<()> {
    let payload = fs::read_to_string(path)
        .with_context(|| format!("failed to read update manifest {}", path.display()))?;
    let manifest = parse_update_manifest_payload(&payload)?;
    verify_update_manifest_signature(&manifest)
}

pub(super) fn verify_update_manifest_signature(manifest: &UpdateManifest) -> Result<()> {
    verify_update_manifest_signature_with_key(manifest, UPDATE_SIGNING_PUBLIC_KEY_B64)
}

pub(super) fn verify_update_manifest_signature_with_key(
    manifest: &UpdateManifest,
    public_key_b64: &str,
) -> Result<()> {
    verify_signature_with_key(
        manifest
            .signature
            .as_ref()
            .ok_or_else(|| anyhow!("update manifest is missing signature"))?,
        update_manifest_signing_payload(manifest).as_bytes(),
        public_key_b64,
    )?;
    if !manifest.standard_platforms.is_empty() {
        verify_signature_with_key(
            manifest
                .standard_signature
                .as_ref()
                .ok_or_else(|| anyhow!("update manifest is missing standard_signature"))?,
            standard_update_manifest_signing_payload(manifest).as_bytes(),
            public_key_b64,
        )?;
    }
    Ok(())
}

pub(super) fn verify_signature_with_key(
    signature: &UpdateSignature,
    payload: &[u8],
    public_key_b64: &str,
) -> Result<()> {
    if !signature.algorithm.eq_ignore_ascii_case("ed25519") {
        return Err(anyhow!(
            "unsupported update manifest signature algorithm {}",
            signature.algorithm
        ));
    }
    let public_bytes = general_purpose::STANDARD
        .decode(public_key_b64.trim())
        .context("failed to decode update signing public key")?;
    let public_key_bytes: [u8; 32] = public_bytes
        .as_slice()
        .try_into()
        .map_err(|_| anyhow!("update signing public key must be 32 bytes"))?;
    let verifying_key = VerifyingKey::from_bytes(&public_key_bytes)
        .context("failed to load update signing public key")?;
    let signature_bytes = general_purpose::STANDARD
        .decode(signature.value.trim())
        .context("failed to decode update manifest signature")?;
    let signature_bytes: [u8; 64] = signature_bytes
        .as_slice()
        .try_into()
        .map_err(|_| anyhow!("update manifest signature must be 64 bytes"))?;
    let signature = Signature::from_bytes(&signature_bytes);
    verifying_key
        .verify(payload, &signature)
        .context("update manifest signature verification failed")
}

pub(super) fn update_manifest_signing_payload(manifest: &UpdateManifest) -> String {
    let mut lines = vec!["ilab-gpt-conjure-update-manifest-v1".to_string()];
    push_signing_field(
        &mut lines,
        "schema_version",
        &manifest.schema_version.to_string(),
    );
    push_signing_field(&mut lines, "version", &manifest.version);
    push_signing_field(&mut lines, "release_url", &manifest.release_url);
    for (platform_key, platform) in &manifest.platforms {
        push_signing_field(&mut lines, "platform", platform_key);
        push_signing_field(&mut lines, "asset", &platform.asset);
        push_signing_field(&mut lines, "url", &platform.url);
        push_signing_field(&mut lines, "sha256", &platform.sha256);
        push_signing_field(&mut lines, "package", &platform.package);
    }
    let mut payload = lines.join("\n");
    payload.push('\n');
    payload
}

pub(super) fn standard_update_manifest_signing_payload(manifest: &UpdateManifest) -> String {
    let mut lines = vec!["ilab-gpt-conjure-standard-update-manifest-v1".to_string()];
    push_signing_field(
        &mut lines,
        "schema_version",
        &manifest.schema_version.to_string(),
    );
    push_signing_field(&mut lines, "version", &manifest.version);
    push_signing_field(&mut lines, "release_url", &manifest.release_url);
    for (platform_key, platform) in &manifest.standard_platforms {
        push_signing_field(&mut lines, "standard_platform", platform_key);
        push_signing_field(&mut lines, "asset", &platform.asset);
        push_signing_field(&mut lines, "url", &platform.url);
        push_signing_field(&mut lines, "sha256", &platform.sha256);
        push_signing_field(&mut lines, "package", &platform.package);
    }
    let mut payload = lines.join("\n");
    payload.push('\n');
    payload
}

pub(super) fn push_signing_field(lines: &mut Vec<String>, name: &str, value: &str) {
    lines.push(format!("{name}:{}:{value}", value.len()));
}

pub(super) fn compare_version_labels(current: &str, latest: &str) -> Option<Ordering> {
    Some(parse_semver_label(current)?.cmp(&parse_semver_label(latest)?))
}

pub(super) fn parse_semver_label(value: &str) -> Option<(u64, u64, u64)> {
    let clean = value
        .trim()
        .trim_start_matches('v')
        .trim_start_matches('V')
        .split(['-', '+'])
        .next()?;
    let mut parts = clean.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next()?.parse().ok()?;
    Some((major, minor, patch))
}

pub(super) fn version_label_from_raw(value: &str) -> String {
    let clean = value.trim().trim_start_matches('v').trim_start_matches('V');
    if is_semver_like(clean) {
        format!("v{clean}")
    } else if value.trim().is_empty() {
        version_label_from_raw(env!("CARGO_PKG_VERSION"))
    } else {
        value.trim().to_string()
    }
}

pub(super) fn is_semver_like(value: &str) -> bool {
    let mut parts = value.split('.');
    let Some(major) = parts.next() else {
        return false;
    };
    let Some(minor) = parts.next() else {
        return false;
    };
    let Some(patch) = parts.next() else {
        return false;
    };
    [major, minor, patch]
        .iter()
        .all(|part| !part.is_empty() && part.chars().all(|ch| ch.is_ascii_digit()))
}

pub(super) fn current_update_platform_key() -> &'static str {
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        "darwin-aarch64"
    }
    #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
    {
        "darwin-x86_64"
    }
    #[cfg(all(target_os = "windows", target_arch = "x86_64"))]
    {
        "windows-x86_64"
    }
    #[cfg(not(any(
        all(target_os = "macos", target_arch = "aarch64"),
        all(target_os = "macos", target_arch = "x86_64"),
        all(target_os = "windows", target_arch = "x86_64")
    )))]
    {
        "unsupported-platform"
    }
}
