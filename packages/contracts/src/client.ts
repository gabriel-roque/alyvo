import createClient from "openapi-fetch";
import type { paths } from "./schema";

export function createAlyvoClient(baseUrl: string, accessToken?: () => string | null) {
  return createClient<paths>({
    baseUrl,
    fetch: async (input: Request) => {
      const headers = new Headers(input.headers);
      const token = accessToken?.();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return fetch(new Request(input, { headers }));
    },
  });
}
