import { applyAppearance, readAppearance } from "./appearance";

// Synchronous, before the stylesheet on both entry pages; no API dependency.
applyAppearance(readAppearance());
