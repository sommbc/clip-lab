# Public Review Notes

Clip Lab is public by design as an early local-first video pipeline. It should be reviewed as a working developer system, not as a hosted consumer product.

## What A Reviewer Can Verify

- Python CLI and FastAPI API for creating local clip jobs.
- Docker Compose stack with API, renderer, and optional browser UI.
- Fixture workflow that runs without WhisperX, model keys, private media, or networked model calls.
- FFmpeg media smoke coverage for source ingest, audio extraction, clip cutting, vertical reframing, metadata, render props, and export zip.
- Remotion renderer and renderer service builds in CI.
- Public-tree hygiene and secret-pattern smoke checks in CI.
- MIT license, third-party font attribution, security policy, and documented output contract.

## Public Boundary

The repository should not contain raw private uploads, generated clips, `.env`, API keys, cookies, model weights, local logs, or private prompts. The checked sample media is a fixture only.

## Product Boundary

Clip Lab is not a SaaS, scheduler, account system, posting tool, or production-hosted app. Auth, billing, persistent job storage, social posting, and multi-user operation are intentionally out of scope until the local pipeline is stronger.

## Maintenance Boundary

Dependency automation should stay grouped and low-noise. Public pull requests that fail because of major framework churn should be closed or replaced with intentional upgrade work, not left open as stale red checks.
