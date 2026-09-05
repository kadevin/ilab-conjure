export type ProviderCredentialSaveDecision =
  | { kind: "allow" }
  | { kind: "key_required" }
  | {
      kind: "confirm_origin_change";
      providerId: string;
      previousOrigin: string;
      nextOrigin: string;
    };

export type ProviderOriginChangeConfirmation = {
  providerId: string;
  previousOrigin: string;
  nextOrigin: string;
};

export function providerUrlOrigin(value: unknown): string {
  try {
    return new URL(String(value || "").trim()).origin;
  } catch {
    return "";
  }
}

export function evaluateProviderCredentialSave(
  draft: any,
  savedProviders: any[],
): ProviderCredentialSaveDecision {
  if (String(draft?.api_key || "").trim()) return { kind: "allow" };

  const providers = Array.isArray(savedProviders) ? savedProviders : [];
  const nextOrigin = providerUrlOrigin(draft?.base_url);
  const existing = providers.find((provider) => provider?.id === draft?.id);
  if (existing && Boolean(existing.api_key_set || existing.api_key)) {
    const previousOrigin = providerUrlOrigin(existing.base_url);
    if (previousOrigin && previousOrigin === nextOrigin) return { kind: "allow" };
    return {
      kind: "confirm_origin_change",
      providerId: String(draft.id || ""),
      previousOrigin,
      nextOrigin,
    };
  }

  const sourceId = String(draft?.api_key_source_provider_id || "").trim();
  const source = providers.find((provider) => provider?.id === sourceId);
  if (
    source
    && Boolean(source.api_key_set || source.api_key)
    && providerUrlOrigin(source.base_url) === nextOrigin
  ) {
    return { kind: "allow" };
  }

  return { kind: "key_required" };
}

export function isConfirmedProviderOriginChange(
  decision: ProviderCredentialSaveDecision,
  confirmation: ProviderOriginChangeConfirmation | null | undefined,
): boolean {
  return decision.kind === "confirm_origin_change"
    && Boolean(confirmation)
    && decision.providerId === confirmation?.providerId
    && decision.previousOrigin === confirmation?.previousOrigin
    && decision.nextOrigin === confirmation?.nextOrigin;
}

export function clearProviderApiKeyInputs(settings: any): any {
  return {
    ...settings,
    providers: Array.isArray(settings?.providers)
      ? settings.providers.map((provider: any) => ({
          ...provider,
          api_key: "",
          api_key_source_provider_id: "",
        }))
      : [],
  };
}
