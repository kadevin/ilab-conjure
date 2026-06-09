import { getLegacyBridge } from "./state";
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import {
  applyAuthSourceSelection,
  authSourceDetailText,
  currentAuthSource,
  handleAuthSourceClick,
  isDirectApiMode,
  refreshHealth,
  renderAuthSource,
  setAuthSource,
  sourceLabel,
} from "./auth-source";
import {
  setModeSettingsVariant,
  setModeSpecificElementVisibility,
  updateModeSpecificSettings,
} from "./api-mode-settings";
import {
  activeApiProvider,
  addApiProvider,
  apiModeLabel,
  backendForAuthSource,
  closeApiSettingsModal,
  currentApiImageModel,
  currentApiImagesConcurrency,
  currentApiMode,
  currentApiProviderId,
  currentApiProviderLabel,
  deleteApiProvider,
  mergeApiProviderKeys,
  normalizeApiImagesConcurrency,
  normalizeApiProvider,
  normalizeApiSettings,
  openApiSettingsModal,
  persistApiSettings,
  populateApiSettingsForm,
  readApiSettingsForm,
  refreshApiSettings,
  restoreApiSettings,
  saveApiSettings,
  setApiSettingsFeedback,
  taskApiProviderId,
  taskApiProviderLabel,
  taskBackendLabel,
  taskBackendValue,
} from "./api-provider-settings";

let apiSettingsFeatureInitialized = false;

export function initApiSettingsFeature(): void {
  if (apiSettingsFeatureInitialized) return;
  apiSettingsFeatureInitialized = true;
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    const bridge = getLegacyBridge();
    renderAuthSource(bridge.state.authStatus);
    if (!bridge.els.apiSettingsModal?.classList.contains("hidden")) {
      setApiSettingsFeedback(translate("apiSettings.status"), "");
    }
  });
  Object.assign(getLegacyBridge().methods, {
    refreshHealth,
    setAuthSource,
    handleAuthSourceClick,
    renderAuthSource,
    applyAuthSourceSelection,
    authSourceDetailText,
    sourceLabel,
    currentAuthSource,
    isDirectApiMode,
    setModeSpecificElementVisibility,
    setModeSettingsVariant,
    updateModeSpecificSettings,
    normalizeApiProvider,
    normalizeApiImagesConcurrency,
    normalizeApiSettings,
    activeApiProvider,
    restoreApiSettings,
    persistApiSettings,
    mergeApiProviderKeys,
    refreshApiSettings,
    populateApiSettingsForm,
    readApiSettingsForm,
    currentApiProviderId,
    currentApiProviderLabel,
    addApiProvider,
    deleteApiProvider,
    openApiSettingsModal,
    closeApiSettingsModal,
    currentApiImageModel,
    currentApiMode,
    currentApiImagesConcurrency,
    apiModeLabel,
    backendForAuthSource,
    taskBackendValue,
    taskApiProviderId,
    taskApiProviderLabel,
    taskBackendLabel,
    setApiSettingsFeedback,
    saveApiSettings,
  });
}
