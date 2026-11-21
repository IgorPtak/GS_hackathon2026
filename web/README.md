# web

React + Vite + TypeScript + Tailwind app. API types are generated into src/api/schema.gen.ts.

## Scripts

| Command                                                | What it does                                                                    |
| ------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `npm ci`                                               | Install from `package-lock.json`                                                |
| `npm run dev`                                          | Vite dev server on port 5173; proxies `/api/v1/ingest` → 8001 and `/api` → 8000 |
| `npm run gen:api`                                      | Regenerate `src/api/schema.gen.ts` from `../contracts/openapi.yaml`             |
| `npm run lint` · `npm run typecheck` · `npm run build` | ESLint · `tsc --noEmit` · production build to `dist/`                           |
| `npm run format`                                       | Prettier write (`format:check` for CI)                                          |

The Docker image (`Dockerfile`, `nginx.conf`) builds the SPA and serves it with nginx, using the same proxy rules.
