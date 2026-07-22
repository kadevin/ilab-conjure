export interface ModeSettingsVisibilityInput {
  catalogAvailable: boolean;
  modelId: string | null;
  protocolProfile: string | null;
  legacyDirectApi: boolean;
}

export interface ModeSettingsVisibility {
  showMainModel: boolean;
  showApiDirectNotice: boolean;
  showPromptFidelity: boolean;
}

export function resolveModeSettingsVisibility({
  catalogAvailable,
  modelId,
  protocolProfile,
  legacyDirectApi,
}: ModeSettingsVisibilityInput): ModeSettingsVisibility {
  if (!catalogAvailable) {
    return {
      showMainModel: !legacyDirectApi,
      showApiDirectNotice: legacyDirectApi,
      showPromptFidelity: true,
    };
  }

  if (modelId !== "gpt-image-2") {
    return {
      showMainModel: false,
      showApiDirectNotice: false,
      showPromptFidelity: false,
    };
  }

  if (!protocolProfile) {
    return {
      showMainModel: false,
      showApiDirectNotice: false,
      showPromptFidelity: true,
    };
  }

  const usesResponses = protocolProfile.endsWith("_responses");
  return {
    showMainModel: usesResponses,
    showApiDirectNotice: !usesResponses,
    showPromptFidelity: true,
  };
}
