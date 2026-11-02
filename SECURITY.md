# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for a
vulnerability.

- Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  on this repository (the **Security** tab → **Report a vulnerability**), or
- Contact the maintainer directly through their GitHub profile.

Please include a description, reproduction steps, and the potential impact. We aim to
acknowledge reports promptly and will coordinate a fix and disclosure timeline with you.

## Scope and expectations

Agent Studio is **self-hosted** software that runs AI agents against a project folder
on your own machine or server. Keep the following in mind when deploying it:

- **It is designed for a trusted, single-operator environment.** The API does not ship
  with authentication; do not expose it directly to an untrusted network or the public
  internet without adding your own access controls in front of it.
- **Agents execute code.** The default sandbox is an unprivileged container with egress
  limited to the npm registry, GitHub, and the preview host. Local mode (no Docker /
  `FORCE_LOCAL=1`) runs commands directly in the project folder — use it only on your
  own development machine.
- **Secrets stay local.** Provider API keys are stored encrypted at rest, GitHub tokens
  are stored by reference with mode `0600`, and neither is sent to the browser or the
  model. Never commit real keys; `api/.env` and `PROJECTS_DIR/.secrets` are gitignored.

## Handling exposed credentials

If a credential is ever committed or otherwise exposed, **revoke and rotate it
immediately**, then remove it from history before publishing. Treat any key that has
reached a log, transcript, or commit as compromised.
