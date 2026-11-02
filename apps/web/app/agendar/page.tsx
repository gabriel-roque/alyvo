import { permanentRedirect } from "next/navigation";

export default function LegacyScheduleRedirect() {
  permanentRedirect("/chat");
}
