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
