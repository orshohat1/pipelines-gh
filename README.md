# Pipeline Migration — GitHub Actions

Multi-agent system that converts Azure DevOps, Jenkins, and GitLab CI pipelines to GitHub Actions workflows using the GitHub Copilot SDK.


## Pipeline Flow

1. **Upload** — User uploads one or more pipeline files via the GUI
2. **Validate** — Classifier agent detects the CI/CD platform (Azure DevOps / Jenkins / GitLab CI)
3. **Plan** — Planner agent designs a migration plan; may ask HITL questions about secrets, environments, etc.
4. **Approve** — User reviews the plan and explicitly approves or rejects it
5. **Generate** — Coder agent generates GitHub Actions YAML using an Evaluator-Optimizer loop with actionlint validation
6. **Result** — Generated YAML is displayed with syntax highlighting, copy, and download

## Prerequisites

- **Python 3.11+**
- **Node.js 20+**
- **GitHub Copilot CLI** — `npm install -g @anthropic-ai/copilot-cli` (or the Copilot SDK way)
- **actionlint** (optional but recommended) — `brew install actionlint` on macOS

## Getting Started

### Backend

```bash
cd backend
pip install -e .
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and proxies API/WS requests to the backend at `:8000`.

## BYOK (Bring Your Own Key)

Expand the "BYOK Model Configuration" panel in the UI to configure your own model provider:

| Field         | Description                                |
|---------------|--------------------------------------------|
| Provider type | `openai`, `azure`, or `anthropic`          |
| Base URL      | API endpoint (e.g. `https://api.openai.com/v1`) |
| API key       | Your API key                               |
| Model name    | Default: `claude-sonnet-4.6`               |
| Wire API      | `completions` or `responses`               |

If no BYOK config is provided, the system uses the default Copilot SDK model.

## Supported Pipelines

| Platform | File Patterns |
|----------|--------------|
| Azure DevOps | `azure-pipelines.yml`, YAML with `trigger:` / `pool:` |
| Jenkins | `Jenkinsfile`, Groovy with `pipeline {` / `agent` |
| GitLab CI | `.gitlab-ci.yml`, YAML with `stages:` / `$CI_` variables |