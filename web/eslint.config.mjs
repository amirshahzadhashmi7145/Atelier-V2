import { defineConfig, globalIgnores } from "eslint/config"
import nextVitals from "eslint-config-next/core-web-vitals"
import nextTs from "eslint-config-next/typescript"

const features = ["agents", "tools", "skills", "runs", "settings", "chat"]

function featureBoundary(feature) {
  const others = features.filter((name) => name !== feature)
  return {
    files: [`src/features/${feature}/**/*.{ts,tsx}`],
    ignores: ["**/*.test.ts", "**/*.test.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/app", "@/app/**", "@/mocks", "@/mocks/**"],
              message: "features import lib and components, not app or mocks",
            },
            ...others.map((other) => ({
              group: [`@/features/${other}`, `@/features/${other}/**`],
              message: "features never import each other",
            })),
          ],
        },
      ],
    },
  }
}

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "public/mockServiceWorker.js"]),
  {
    files: ["src/lib/**/*.{ts,tsx}", "src/components/**/*.{ts,tsx}"],
    ignores: ["**/*.test.ts", "**/*.test.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/app", "@/app/**", "@/features", "@/features/**", "@/mocks", "@/mocks/**"],
              message: "lib and components cannot import app, features, or mocks",
            },
          ],
        },
      ],
    },
  },
  ...features.map(featureBoundary),
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/lib/api/**", "src/mocks/**", "**/*.test.ts", "**/*.test.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='fetch']",
          message: "No fetch() outside src/lib/api. Use the generated client.",
        },
      ],
    },
  },
])

export default eslintConfig
