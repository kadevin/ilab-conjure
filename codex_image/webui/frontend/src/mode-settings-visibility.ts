import { isGptImageModel } from "./gpt-image-models";
export interface ModeSettingsVisibilityInput {
  catalogAvailable: boolean;
  modelId: string | null;
  protocolProfile: string | null;
  legacyDirectApi: boolean;
}

export interface ModeSettingsVisibility {
  showMainModel: boolean;
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
      showPromptFidelity: true,
    };
  }

  if (!isGptImageModel(modelId)) {
    return {
      showMainModel: false,
      showPromptFidelity: false,
    };
  }

  if (!protocolProfile) {
    return {
      showMainModel: false,
      showPromptFidelity: true,
    };
  }

  const usesResponses = protocolProfile.endsWith("_responses");
  return {
    showMainModel: usesResponses,
    showPromptFidelity: true,
  };
}
