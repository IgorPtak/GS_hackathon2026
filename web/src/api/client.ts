import createClient from "openapi-fetch";

import type { paths } from "./schema.gen";

/** Typed client for the api service. Paths are relative: the Vite proxy or nginx routes them. */
export const apiClient = createClient<paths>({ baseUrl: "" });
