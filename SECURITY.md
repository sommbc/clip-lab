# Security

## Supported Versions

The public repository tracks the current `main` branch.

## Reporting A Vulnerability

Open a private security advisory if the host supports it. Otherwise, create an issue with a minimal
description and avoid posting secrets, exploit payloads, private URLs, cookies, API keys, or media
that is not yours to share.

## Secret Handling

Clip Lab must be runnable from `.env.example` without real credentials. Real keys belong only in a
local `.env` file or deployment secret manager and must never be committed.

Never commit:

- `.env` or `.env.*`
- OpenRouter keys
- Hugging Face tokens
- YouTube cookies
- raw user uploads
- generated clips
- downloaded model weights
- private prompts or local machine paths

See `docs/secrets.md` for the repo-level secret policy.
