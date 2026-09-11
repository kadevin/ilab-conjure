import { sha256 } from "@noble/hashes/sha2.js";

/** File-integrity checks also run on HTTP LAN origins without Web Crypto. */
export async function sha256Hex(
  bytes: ArrayBuffer,
  cryptoProvider: Pick<Crypto, "subtle"> | null | undefined = globalThis.crypto,
): Promise<string> {
  const digest = cryptoProvider?.subtle
    ? new Uint8Array(await cryptoProvider.subtle.digest("SHA-256", bytes))
    : sha256(new Uint8Array(bytes));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
