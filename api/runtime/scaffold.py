"""Local vite-react-ts starter used when stack scaffoldTemplate is vite-react-ts."""

from __future__ import annotations

import json
from pathlib import Path


def write_vite_react_ts(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    package = {
        "name": "app",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "test": "node -e \"process.exit(0)\"",
        },
        "dependencies": {
            "react": "^19.0.0",
            "react-dom": "^19.0.0",
        },
        "devDependencies": {
            "@types/react": "^19.0.0",
            "@types/react-dom": "^19.0.0",
            "@vitejs/plugin-react": "^4.3.0",
            "typescript": "^5.7.0",
            "vite": "^6.0.0",
        },
    }
    (folder / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    (folder / "index.html").write_text(
        '<!doctype html><html><head><meta charset="UTF-8" /><title>App</title></head>'
        '<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>\n',
        encoding="utf-8",
    )
    (folder / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "jsx": "react-jsx",
                    "strict": True,
                    "skipLibCheck": True,
                },
                "include": ["src"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "vite.config.ts").write_text(
        'import { defineConfig } from "vite"\nimport react from "@vitejs/plugin-react"\n\n'
        "export default defineConfig({ plugins: [react()] })\n",
        encoding="utf-8",
    )
    src = folder / "src"
    src.mkdir(exist_ok=True)
    (src / "main.tsx").write_text(
        'import { createRoot } from "react-dom/client"\nimport { App } from "./App"\n\n'
        'createRoot(document.getElementById("root")!).render(<App />)\n',
        encoding="utf-8",
    )
    (src / "App.tsx").write_text(
        'export function App() {\n  return <main><h1>App</h1></main>\n}\n',
        encoding="utf-8",
    )


def write_express_prisma(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    package = {
        "name": "api",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": "tsx src/index.ts",
            "build": "node -e \"process.exit(0)\"",
            "test": "node --test tests/health.test.mjs",
        },
        "dependencies": {
            "express": "^5.0.0",
            "@prisma/client": "^6.0.0",
            "zod": "^3.24.0",
        },
        "devDependencies": {
            "prisma": "^6.0.0",
            "tsx": "^4.19.0",
            "typescript": "^5.7.0",
            "@types/express": "^5.0.0",
            "@types/node": "^22.0.0",
            "vitest": "^3.0.0",
            "supertest": "^7.0.0",
        },
    }
    (folder / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    (folder / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "NodeNext",
                    "moduleResolution": "NodeNext",
                    "strict": True,
                    "skipLibCheck": True,
                    "outDir": "dist",
                    "rootDir": "src",
                },
                "include": ["src"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    src = folder / "src"
    src.mkdir(exist_ok=True)
    (src / "index.ts").write_text(
        'import http from "node:http"\n\n'
        "export function createServer() {\n"
        "  return http.createServer((req, res) => {\n"
        '    if (req.url === "/health") {\n'
        '      res.writeHead(200, { "content-type": "application/json" })\n'
        '      res.end(JSON.stringify({ ok: true }))\n'
        "      return\n"
        "    }\n"
        "    res.writeHead(404)\n"
        "    res.end()\n"
        "  })\n"
        "}\n\n"
        'if (import.meta.url === `file://${process.argv[1]}`) {\n'
        "  createServer().listen(process.env.PORT || 3001)\n"
        "}\n",
        encoding="utf-8",
    )
    tests = folder / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "health.test.mjs").write_text(
        'import assert from "node:assert/strict"\n'
        'import test from "node:test"\n'
        'import { createServer } from "../src/index.ts"\n\n'
        'test("/health", async () => {\n'
        "  const server = createServer()\n"
        "  await new Promise((resolve) => server.listen(0, resolve))\n"
        "  const { port } = server.address()\n"
        '  const res = await fetch(`http://127.0.0.1:${port}/health`)\n'
        "  assert.equal(res.status, 200)\n"
        '  assert.equal((await res.json()).ok, true)\n'
        "  server.close()\n"
        "})\n",
        encoding="utf-8",
    )
    prisma = folder / "prisma"
    prisma.mkdir(exist_ok=True)
    (prisma / "schema.prisma").write_text(
        'generator client {\n  provider = "prisma-client-js"\n}\n\n'
        'datasource db {\n  provider = "sqlite"\n  url      = "file:./dev.db"\n}\n',
        encoding="utf-8",
    )
    (folder / ".env.example").write_text("DATABASE_URL=file:./dev.db\n", encoding="utf-8")
    server = folder / "server"
    server.mkdir(exist_ok=True)
    (server / "CONTRACT.md").write_text("# API contract\n\n| Method | Path | Request | Response |\n| --- | --- | --- | --- |\n| GET | /health |  | { ok: true } |\n", encoding="utf-8")

