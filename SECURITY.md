# Security policy

## Secrets

Do not open an issue containing API keys, tokens, recordings, signed playback URLs or complete
environment files. Revoke an exposed credential at its provider before reporting the incident.

The project accepts secrets only in ignored local environment files or deployment secret stores.
Any variable prefixed with `NEXT_PUBLIC_` is browser-visible and must never contain a secret.

## Reporting a vulnerability

Until a dedicated security address exists, open a GitHub security advisory for the repository.
Include the affected version, reproduction steps and impact, but do not attach real student audio
or personal information.

## Supported configuration

Security updates target the latest `main` branch. Public internet deployments must replace the
development signing values, enable production mode, use HTTPS, and configure strict hosts and
CORS origins.
