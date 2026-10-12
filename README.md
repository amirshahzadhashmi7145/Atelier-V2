# Agent Studio

Week 1 studio for defining an agent and watching a run. The contract is `openapi/agent-studio.yaml`.

```bash
pnpm --dir web install
pnpm --dir web dev
```

Mocks are on unless `NEXT_PUBLIC_USE_MOCKS=false`. Then set `NEXT_PUBLIC_API_URL` to the API.

```bash
pnpm typecheck
pnpm lint
pnpm test
pnpm test:e2e
```
