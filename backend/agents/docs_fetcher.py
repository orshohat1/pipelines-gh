"""Smart runtime fetcher for official GitHub Actions best practices.

Analyzes the source pipeline to detect which topics are relevant, then
fetches only the matching documentation sections and action versions.
Results are cached in memory with a configurable TTL.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

_CACHE_TTL = 6 * 3600  # 6 hours
_REQUEST_TIMEOUT = 5  # seconds per request (fallbacks available)

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

# Starter workflow templates — mapped to topics for selective fetch
_STARTER_WORKFLOWS: dict[str, tuple[str, str]] = {
    # topic_key → (display_name, path)
    "node": ("Node.js CI", "ci/node.js.yml"),
    "python": ("Python application", "ci/python-app.yml"),
    "docker": ("Docker image", "ci/docker-image.yml"),
    "dotnet": (".NET", "ci/dotnet.yml"),
    "java": ("Java with Maven", "ci/maven.yml"),
    "go": ("Go", "ci/go.yml"),
}

_STARTER_BASE = "https://raw.githubusercontent.com/actions/starter-workflows/main"


# ── Topic detection ──────────────────────────────────────────────────────────

# Each topic maps to (detection_patterns, relevant_actions, docs_section_key)
_TOPICS: dict[str, dict[str, Any]] = {
    "node": {
        "patterns": [r"node|npm|yarn|pnpm|package\.json|NodeTool|setup-node"],
        "actions": ["actions/setup-node"],
        "starter": "node",
    },
    "python": {
        "patterns": [r"python|(?<!\w)pip(?!\w)|poetry|conda|requirements\.txt|UsePythonVersion|setup-python"],
        "actions": ["actions/setup-python"],
        "starter": "python",
    },
    "dotnet": {
        "patterns": [r"dotnet|nuget|csproj|UseDotNet|setup-dotnet|msbuild|\.sln"],
        "actions": ["actions/setup-dotnet"],
        "starter": "dotnet",
    },
    "java": {
        "patterns": [r"java|maven|gradle|pom\.xml|setup-java|jdk"],
        "actions": ["actions/setup-java"],
        "starter": "java",
    },
    "go": {
        "patterns": [r"\bgo\b|golang|go\.mod|setup-go"],
        "actions": ["actions/setup-go"],
        "starter": "go",
    },
    "docker": {
        "patterns": [r"docker|container|Dockerfile|registry|acr|ecr|gcr|build-push"],
        "actions": ["docker/build-push-action", "docker/login-action", "docker/setup-buildx-action"],
    },
    "azure": {
        "patterns": [r"azure|AzureWebApp|AzureCLI|az\s|service.?connection|AzureRm"],
        "actions": ["azure/login", "azure/webapps-deploy"],
    },
    "aws": {
        "patterns": [r"aws|amazon|s3|ec2|lambda|ecs|configure-aws"],
        "actions": ["aws-actions/configure-aws-credentials"],
    },
    "gcp": {
        "patterns": [r"gcp|google|gcloud|cloud.?run|gke"],
        "actions": ["google-github-actions/auth"],
    },
    "artifacts": {
        "patterns": [r"artifact|upload|download|archiveArtifact|publish"],
        "actions": ["actions/upload-artifact", "actions/download-artifact"],
    },
    "cache": {
        "patterns": [r"cache|restore.?key|hashFiles"],
        "actions": ["actions/cache"],
    },
    "security": {
        "patterns": [r"security|codeql|dependabot|dependency.?review|trivy|scanning|sbom"],
        "actions": ["actions/dependency-review-action", "github/codeql-action"],
    },
    "deploy": {
        "patterns": [r"deploy|environment|production|staging|approval|protection|slot"],
        "actions": [],
    },
    "matrix": {
        "patterns": [r"matrix|(?<!\w)strategy(?=:?\s*\{?\s*matrix)|parallel.+os|fail.?fast|max.?parallel"],
        "actions": [],
    },
    "reusable": {
        "patterns": [r"template|reusable|workflow_call|include:|extends:|shared.?lib"],
        "actions": [],
    },
}


def detect_topics(pipeline_content: str) -> set[str]:
    """Analyze pipeline content to determine which topics are relevant.

    Returns a set of topic keys (e.g. {"node", "docker", "deploy", "azure"}).
    Always includes "core" topics (triggers, permissions, concurrency, secrets).
    """
    content_lower = pipeline_content.lower()
    detected: set[str] = set()

    for topic_key, topic_info in _TOPICS.items():
        for pattern in topic_info["patterns"]:
            if re.search(pattern, content_lower):
                detected.add(topic_key)
                break

    return detected


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

# Topic-keyed documentation sections — only the relevant ones get included
_DOCS_SECTIONS: dict[str, str] = {
    "triggers": """\
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
```""",

    "permissions": """\
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
```""",

    "concurrency": """\
## Concurrency Control
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true   # true for PR builds, false for deployments
```""",

    "secrets_vars": """\
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
```""",

    "expressions": """\
## Expressions & Contexts
```yaml
# Conditionals
if: ${{ github.ref == 'refs/heads/main' }}
if: ${{ github.event_name == 'pull_request' }}
if: ${{ needs.build.result == 'success' }}
if: ${{ always() }}   # run regardless of prior step status
if: ${{ failure() }}   # run only if a prior step failed

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
```""",

    "matrix": """\
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
```""",

    "cache": """\
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
```""",

    "artifacts": """\
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
```""",

    "deploy": """\
## Environment Protection
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
      url: ${{ steps.deploy.outputs.url }}
```""",

    "azure": """\
## OIDC Authentication — Azure
```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: azure/login@v2
    with:
      client-id: ${{ secrets.AZURE_CLIENT_ID }}
      tenant-id: ${{ secrets.AZURE_TENANT_ID }}
      subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
```""",

    "aws": """\
## OIDC Authentication — AWS
```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
      aws-region: us-east-1
```""",

    "gcp": """\
## OIDC Authentication — GCP
```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY }}
      service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
```""",

    "reusable": """\
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
```""",

    "docker": """\
## Docker Build & Push
```yaml
- uses: docker/setup-buildx-action@v3
- uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
- uses: docker/build-push-action@v6
  with:
    push: true
    tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
```""",
}

# Core topics always included (small & universally relevant)
_CORE_TOPICS = {"triggers", "permissions", "concurrency", "secrets_vars", "expressions"}


async def fetch_best_practices(pipeline_content: str = "") -> str:
    """Fetch a targeted GitHub Actions best-practices reference.

    Analyzes the pipeline content to detect relevant topics, then builds a
    focused reference with only the sections that matter. Always includes
    core topics (triggers, permissions, concurrency, secrets/vars, expressions).

    Args:
        pipeline_content: Source pipeline YAML to analyze for topic detection.
                          If empty, returns only core topics + action versions.
    """
    # Detect which topics matter for this pipeline
    detected = detect_topics(pipeline_content) if pipeline_content else set()
    all_topics = _CORE_TOPICS | detected

    # Determine which actions to look up (core + detected)
    actions_to_fetch: dict[str, str] = {
        "actions/checkout": TRACKED_ACTIONS["actions/checkout"],
    }
    for topic_key in detected:
        topic_info = _TOPICS.get(topic_key, {})
        for action in topic_info.get("actions", []):
            if action in TRACKED_ACTIONS:
                actions_to_fetch[action] = TRACKED_ACTIONS[action]

    # Build cache key from the topic set
    cache_key = "bp:" + ",".join(sorted(all_topics))
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Fetch live action versions (only for relevant actions)
    versions = dict(actions_to_fetch)
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"Accept": "application/vnd.github+json"},
        ) as client:
            results = await asyncio.gather(
                *(
                    _fetch_latest_version(client, action, fallback)
                    for action, fallback in actions_to_fetch.items()
                ),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, tuple):
                    action, version = result
                    versions[action] = version
    except Exception as e:
        logger.warning("Failed to fetch action versions: %s", e)

    # Fetch one relevant starter workflow example (if topic matches)
    starter_content = ""
    for topic_key in detected:
        topic_info = _TOPICS.get(topic_key, {})
        starter_key = topic_info.get("starter")
        if starter_key and starter_key in _STARTER_WORKFLOWS:
            name, path = _STARTER_WORKFLOWS[starter_key]
            try:
                async with httpx.AsyncClient(
                    timeout=_REQUEST_TIMEOUT, follow_redirects=True
                ) as client:
                    resp = await client.get(f"{_STARTER_BASE}/{path}")
                    if resp.status_code == 200:
                        starter_content = f"\n## Official Starter Workflow: {name}\n```yaml\n{resp.text.strip()}\n```\n"
                        break
            except Exception:
                pass

    # Build the reference document
    parts: list[str] = []
    parts.append("# GitHub Actions Reference (auto-fetched, topic-aware)\n")

    # Action versions table
    parts.append("## Action Versions (use these exact versions)\n")
    parts.append("| Action | Version |")
    parts.append("|--------|---------|")
    for action, version in sorted(versions.items()):
        parts.append(f"| `{action}` | `@{version}` |")
    parts.append("")

    # Topic-specific docs sections
    for topic_key in sorted(all_topics):
        section = _DOCS_SECTIONS.get(topic_key)
        if section:
            parts.append(section)
            parts.append("")

    if starter_content:
        parts.append(starter_content)

    topics_str = ", ".join(sorted(detected)) if detected else "none"
    parts.append(f"\n<!-- detected topics: {topics_str} -->")

    result = "\n".join(parts)
    _set_cached(cache_key, result)
    logger.info("Built best-practices reference: %d chars, topics: %s", len(result), topics_str)
    return result


# ── Planner-specific condensed reference ─────────────────────────────────────

# One-line summaries per topic — no YAML code blocks, just enough for planning
_PLANNER_SUMMARIES: dict[str, str] = {
    "triggers": "Triggers: push/PR/schedule/workflow_dispatch with branch and path filters",
    "permissions": "Permissions: default `contents: read` at workflow level; override per-job as needed; `id-token: write` for OIDC",
    "concurrency": "Concurrency: use `concurrency.group` with `cancel-in-progress: true` for PRs, `false` for deploys",
    "secrets_vars": "Secrets vs Vars: `secrets.*` for credentials only; `vars.*` for app names, regions, resource groups",
    "expressions": "Expressions: `if:` conditionals, `$GITHUB_OUTPUT` for step outputs, `needs.<job>.outputs` for cross-job data",
    "matrix": "Matrix: `strategy.matrix` for multi-OS/version testing with `fail-fast` and `exclude/include`",
    "cache": "Caching: built-in via setup-node/setup-python `cache:` param; manual via `actions/cache` with `hashFiles()` keys",
    "artifacts": "Artifacts: `upload-artifact`/`download-artifact` with `retention-days` for cross-job file sharing",
    "deploy": "Deployment: use `environment:` with protection rules and required reviewers for production gates",
    "azure": "Azure: OIDC via `azure/login` with workload identity federation (client-id, tenant-id, subscription-id)",
    "aws": "AWS: OIDC via `aws-actions/configure-aws-credentials` with `role-to-assume`",
    "gcp": "GCP: OIDC via `google-github-actions/auth` with workload identity provider",
    "reusable": "Reusable Workflows: `on: workflow_call` with typed inputs/secrets; caller uses `uses: ./.github/workflows/file.yml`",
    "docker": "Docker: `setup-buildx-action` → `login-action` → `build-push-action` for multi-platform builds",
    "security": "Security: CodeQL for SAST, `dependency-review-action` on PRs, container scanning with Trivy",
}


async def fetch_planner_summary(pipeline_content: str = "") -> str:
    """Fetch a condensed GitHub Actions reference for the planner agent.

    Returns action versions table + one-line topic bullets (~2KB) instead of
    the full YAML-heavy reference (~15KB) used by the coder. The planner
    outputs JSON plans, not YAML — it only needs to know *what* actions and
    capabilities exist, not their exact YAML syntax.
    """
    detected = detect_topics(pipeline_content) if pipeline_content else set()
    all_topics = _CORE_TOPICS | detected

    # Build cache key (separate from coder's "bp:" namespace)
    cache_key = "bp-plan:" + ",".join(sorted(all_topics))
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Reuse the coder's version cache if available, otherwise use fallbacks
    versions_cache = _get_cached("action_versions")
    if versions_cache:
        versions = versions_cache
    else:
        versions = dict(TRACKED_ACTIONS)

    # Filter to only relevant actions
    relevant_actions: dict[str, str] = {
        "actions/checkout": versions.get("actions/checkout", TRACKED_ACTIONS["actions/checkout"]),
    }
    for topic_key in detected:
        topic_info = _TOPICS.get(topic_key, {})
        for action in topic_info.get("actions", []):
            if action in versions:
                relevant_actions[action] = versions[action]
            elif action in TRACKED_ACTIONS:
                relevant_actions[action] = TRACKED_ACTIONS[action]

    # Build condensed reference
    parts: list[str] = [
        "# GitHub Actions Reference (planning summary)\n",
        "## Action Versions\n",
        "| Action | Version |",
        "|--------|---------|"]
    for action, version in sorted(relevant_actions.items()):
        parts.append(f"| `{action}` | `@{version}` |")
    parts.append("")

    parts.append("## Capabilities\n")
    for topic_key in sorted(all_topics):
        summary = _PLANNER_SUMMARIES.get(topic_key)
        if summary:
            parts.append(f"- {summary}")
    parts.append("")

    topics_str = ", ".join(sorted(detected)) if detected else "none"
    parts.append(f"<!-- planner topics: {topics_str} -->")

    result = "\n".join(parts)
    _set_cached(cache_key, result)
    logger.info("Built planner summary: %d chars, topics: %s", len(result), topics_str)
    return result
