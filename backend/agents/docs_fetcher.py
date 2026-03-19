"""Runtime fetcher for official GitHub Actions best practices and latest action versions.

Fetches documentation from GitHub's official sources at runtime so agents
always work with up-to-date action versions and real workflow examples.
Results are cached in memory with a configurable TTL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

_CACHE_TTL = 6 * 3600  # 6 hours
_REQUEST_TIMEOUT = 15  # seconds per request

# In-memory cache: key → (timestamp, data)
_cache: dict[str, tuple[float, Any]] = {}

# Actions we track for latest versions (with fallback major tags)
TRACKED_ACTIONS: dict[str, str] = {
    "actions/checkout": "v5",
    "actions/cache": "v4",
    "actions/setup-node": "v4",
    "actions/setup-python": "v5",
    "actions/setup-dotnet": "v4",
    "actions/setup-java": "v4",
    "actions/setup-go": "v5",
    "actions/upload-artifact": "v4",
    "actions/download-artifact": "v4",
    "actions/dependency-review-action": "v4",
    "github/codeql-action": "v3",
    "docker/build-push-action": "v6",
    "docker/login-action": "v3",
    "docker/setup-buildx-action": "v3",
    "azure/login": "v2",
    "azure/webapps-deploy": "v3",
    "aws-actions/configure-aws-credentials": "v4",
    "google-github-actions/auth": "v2",
}

# Starter workflow templates to fetch as real-world examples
_STARTER_WORKFLOWS: dict[str, str] = {
    "Node.js CI": "ci/node.js.yml",
    "Python application": "ci/python-app.yml",
    "Docker image": "ci/docker-image.yml",
}

_STARTER_BASE = "https://raw.githubusercontent.com/actions/starter-workflows/main"


# ── Cache helpers ────────────────────────────────────────────────────────────


def _get_cached(key: str) -> Any | None:
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return data
    return None


def _set_cached(key: str, data: Any) -> None:
    _cache[key] = (time.time(), data)


# ── Fetchers ─────────────────────────────────────────────────────────────────


async def _fetch_latest_version(
    client: httpx.AsyncClient, action: str, fallback: str
) -> tuple[str, str]:
    """Fetch the latest release tag for a single GitHub Action."""
    url = f"https://api.github.com/repos/{action}/releases/latest"
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            tag = resp.json().get("tag_name", "")
            if tag:
                # Extract major version: v5.0.0 → v5
                major = tag.split(".")[0]
                return action, major
        # 403 = rate limited, 404 = no releases, etc.
        return action, fallback
    except Exception:
        return action, fallback


async def fetch_action_versions() -> dict[str, str]:
    """Fetch latest major versions for all tracked GitHub Actions.

    Returns dict mapping "owner/repo" → "vN" (major version tag).
    """
    cached = _get_cached("action_versions")
    if cached is not None:
        return cached

    versions = dict(TRACKED_ACTIONS)  # start with fallbacks

    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"Accept": "application/vnd.github+json"},
        ) as client:
            results = await asyncio.gather(
                *(
                    _fetch_latest_version(client, action, fallback)
                    for action, fallback in TRACKED_ACTIONS.items()
                ),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, tuple):
                    action, version = result
                    versions[action] = version
    except Exception as e:
        logger.warning("Failed to fetch action versions: %s", e)

    _set_cached("action_versions", versions)
    return versions


async def _fetch_starter_workflow(
    client: httpx.AsyncClient, name: str, path: str
) -> tuple[str, str]:
    """Fetch a single starter workflow template from GitHub."""
    url = f"{_STARTER_BASE}/{path}"
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            return name, resp.text
    except Exception:
        pass
    return name, ""


async def fetch_starter_workflows() -> dict[str, str]:
    """Fetch official starter workflow templates from GitHub.

    Returns dict mapping template name → YAML content.
    """
    cached = _get_cached("starter_workflows")
    if cached is not None:
        return cached

    workflows: dict[str, str] = {}

    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            results = await asyncio.gather(
                *(
                    _fetch_starter_workflow(client, name, path)
                    for name, path in _STARTER_WORKFLOWS.items()
                ),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, tuple):
                    name, content = result
                    if content:
                        workflows[name] = content
    except Exception as e:
        logger.warning("Failed to fetch starter workflows: %s", e)

    _set_cached("starter_workflows", workflows)
    return workflows


# ── Main entry point ─────────────────────────────────────────────────────────

# Best-practices syntax reference (stable content, enriched with live data)
_SYNTAX_REFERENCE = """\
## Workflow Triggers
```yaml
on:
  push:
    branches: [main, 'releases/**']
    paths: ['src/**']
    paths-ignore: ['docs/**']
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        type: choice
        options: [dev, staging, production]
  schedule:
    - cron: '30 5 * * 1-5'
  workflow_call:
    inputs:
      config-name:
        required: true
        type: string
    secrets:
      token:
        required: true
```

## Permissions (all available scopes)
```yaml
permissions:
  actions: read|write|none
  attestations: read|write|none
  checks: read|write|none
  contents: read|write|none       # DEFAULT: read
  deployments: read|write|none
  discussions: read|write|none
  id-token: read|write|none       # Required for OIDC: write
  issues: read|write|none
  models: read|write|none
  packages: read|write|none
  pages: read|write|none
  pull-requests: read|write|none
  security-events: read|write|none
  statuses: read|write|none
```

## Concurrency Control
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true   # true for PR builds, false for deployments
```

## Matrix Strategy
```yaml
strategy:
  fail-fast: false
  max-parallel: 4
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    node-version: ['18', '20', '22']
    exclude:
      - os: windows-latest
        node-version: '18'
    include:
      - os: ubuntu-latest
        node-version: '22'
        experimental: true
```

## Caching Patterns
```yaml
# Built-in caching (preferred)
- uses: actions/setup-node@v4
  with:
    node-version: '20'
    cache: 'npm'

# Manual caching
- uses: actions/cache@v4
  with:
    path: ~/.npm
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

## Artifacts
```yaml
# Upload
- uses: actions/upload-artifact@v4
  with:
    name: build-output
    path: dist/
    retention-days: 5

# Download (in dependent job)
- uses: actions/download-artifact@v4
  with:
    name: build-output
```

## OIDC Authentication
```yaml
# Azure
permissions:
  id-token: write
  contents: read
steps:
  - uses: azure/login@v2
    with:
      client-id: ${{ secrets.AZURE_CLIENT_ID }}
      tenant-id: ${{ secrets.AZURE_TENANT_ID }}
      subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

# AWS
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
      aws-region: us-east-1

# GCP
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY }}
      service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
```

## Environment Protection
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
      url: ${{ steps.deploy.outputs.url }}
```

## Reusable Workflows
```yaml
# Caller
jobs:
  call-build:
    uses: ./.github/workflows/build.yml
    with:
      config-name: release
    secrets: inherit

# Callee (build.yml)
on:
  workflow_call:
    inputs:
      config-name:
        required: true
        type: string
    secrets:
      token:
        required: false
```

## Expressions & Contexts
```yaml
# Available contexts: github, env, vars, secrets, needs, strategy, matrix, steps, runner, inputs
# Conditionals
if: ${{ github.ref == 'refs/heads/main' }}
if: ${{ github.event_name == 'pull_request' }}
if: ${{ needs.build.result == 'success' }}
if: ${{ always() }}   # run regardless of prior step status
if: ${{ failure() }}   # run only if a prior step failed
if: ${{ contains(github.event.head_commit.message, '[skip ci]') }}

# Output passing between steps
- id: my-step
  run: echo "value=hello" >> $GITHUB_OUTPUT
- run: echo ${{ steps.my-step.outputs.value }}

# Output passing between jobs
jobs:
  job1:
    outputs:
      result: ${{ steps.my-step.outputs.value }}
  job2:
    needs: job1
    steps:
      - run: echo ${{ needs.job1.outputs.result }}
```

## Secrets vs Variables
```yaml
# secrets.* — ONLY for sensitive credentials
env:
  CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
  API_TOKEN: ${{ secrets.API_TOKEN }}

# vars.* — for non-sensitive configuration
env:
  APP_NAME: ${{ vars.APP_NAME }}
  RESOURCE_GROUP: ${{ vars.RESOURCE_GROUP }}
  AZURE_REGION: ${{ vars.AZURE_REGION }}
```
"""


async def fetch_best_practices() -> str:
    """Fetch and compile an up-to-date GitHub Actions best-practices reference.

    Combines:
    1. Live action versions from GitHub API
    2. Official starter workflow examples
    3. Curated syntax reference

    Returns a formatted string ready to inject into agent system prompts.
    """
    cached = _get_cached("best_practices")
    if cached is not None:
        return cached

    # Fetch live data concurrently
    versions, starters = await asyncio.gather(
        fetch_action_versions(),
        fetch_starter_workflows(),
        return_exceptions=True,
    )

    if isinstance(versions, Exception):
        logger.warning("Action versions fetch failed: %s", versions)
        versions = dict(TRACKED_ACTIONS)
    if isinstance(starters, Exception):
        logger.warning("Starter workflows fetch failed: %s", starters)
        starters = {}

    # Build the reference document
    parts: list[str] = []

    parts.append("# Official GitHub Actions Reference (auto-fetched)\n")

    # Action versions table
    parts.append("## Latest Official Action Versions\n")
    parts.append("Always use these versions when generating workflows:\n")
    parts.append("| Action | Version |")
    parts.append("|--------|---------|")
    for action, version in sorted(versions.items()):
        parts.append(f"| `{action}` | `@{version}` |")
    parts.append("")

    # Syntax reference
    parts.append(_SYNTAX_REFERENCE)

    # Starter workflow examples
    if starters:
        parts.append("\n## Official Starter Workflow Examples\n")
        parts.append("These are real, GitHub-maintained workflow templates:\n")
        for name, content in starters.items():
            parts.append(f"### {name}")
            parts.append(f"```yaml\n{content.strip()}\n```\n")

    result = "\n".join(parts)
    _set_cached("best_practices", result)
    return result
