/** Public client-facing types generated from the Alyvo OpenAPI domain. */
export { createAlyvoClient } from "./client";
export type { components, paths } from "./schema";
import type { components } from "./schema";

export type Citation = components["schemas"]["Citation"];
export type ChatResponse = Omit<components["schemas"]["ChatResponse"], "intent"> & {
  intent: "knowledge" | "schedule" | "cancel_appointment" | "ticket" | "clinical_safety";
};
export type Doctor = components["schemas"]["DoctorView"];
export type Slot = components["schemas"]["AvailabilitySlot"];
export type DocumentReview = components["schemas"]["DocumentView"];

