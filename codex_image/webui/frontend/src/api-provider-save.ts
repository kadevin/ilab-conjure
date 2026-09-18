import type { ApiProviderSettings } from "./api-provider-model";

import type { ProviderOriginChangeConfirmation } from "./api-provider-credentials";
import { translate } from "./i18n";

export function apiSettingsSavePayload(settings: ApiProviderSettings, confirmedOriginChange: ProviderOriginChangeConfirmation | null = null): any {
  const payload: any = {
    schema_version: 2,
    codex_mode: settings.codex_mode,
    active_provider_id: settings.active_provider_id,
    default_provider_by_model: settings.default_provider_by_model,
    providers: settings.providers.map((provider) => {
      const item: any = {
        id: provider.id,
        name: provider.name,
        icon_emoji: provider.icon_emoji || "",
        base_url: provider.base_url,
        concurrency: provider.concurrency,
        bindings: provider.bindings,
      };
      if (provider.api_key || !provider.api_key_set) item.api_key = provider.api_key;
      if (!provider.api_key && provider.api_key_source_provider_id) {
        item.api_key_source_provider_id = provider.api_key_source_provider_id;
      }
      if (provider.id === confirmedOriginChange?.providerId) {
        item.preserve_api_key_on_origin_change = true;
      }
      return item;
    }),
  };
  return payload;
}

export async function patchApiSettings(payload: unknown, request: typeof fetch = fetch): Promise<any> {
  const response = await request("/api/api-settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = String(data.detail || "");
    if (detail === "api_key_required") throw new Error(translate("apiSettings.apiKeyRequired"));
    if (detail === "api_key_origin_change_confirmation_required") {
      throw new Error(translate("apiSettings.originChangeConfirmationRequired"));
    }
    throw new Error(detail || translate("apiSettings.saveFailed"));
  }
  return data;
}
