# Knowledge Acquisition Skill

Build and maintain a persistent, compounding knowledge base as interlinked markdown files — an **LLM Wiki**.

Unlike RAG (which rediscovers knowledge from scratch per query), the LLM Wiki compiles knowledge once and keeps it current. Cross-references are pre-built, contradictions are flagged, and synthesis reflects everything ingested. The wiki distills to state-of-the-art: it answers *"What is the best way to do X right now?"* rather than cataloging every historical approach.

The skill ships with a **Cloudscape-based web app** for visualizing wikis — browse pages, explore the knowledge graph, filter by type/tags, and navigate wikilinks in a browser. Run it locally against any wiki directory (no AWS required), or deploy it to CloudFront for team access. An **AWS serverless infrastructure** (CDK) is included for sharing wikis across multiple agents and humans: wikis are persisted in CodeCommit, indexed automatically on push, and served through a CloudFront-backed API. Multiple agents can collaborate on the same wiki via standard git operations.

## Installation

```bash
git clone git@github.com:aws-samples/sample-knowledge-acquisition-skill.git ~/.kiro/skills/knowledge-acquisition
```

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package runner)
- [gh](https://cli.github.com/) (GitHub CLI) — for GitHub search and clone scripts

## Usage

This skill activates automatically in Kiro when you ask it to research topics, build knowledge bases, or query existing wikis. Below are example prompts to get started.

### Creating a Wiki

| Prompt | What it does |
|--------|--------------|
| *"Create an LLM-Wiki about multi-agent systems"* | Bootstraps a new wiki with schema, index, and initial research on the topic |
| *"Build a knowledge base on transformer architectures"* | Searches academic sources, downloads key papers, and creates structured wiki pages |
| *"Research the latest advances in code generation and start a wiki"* | Gathers sources from arXiv, Semantic Scholar, and GitHub, then distills findings into wiki pages |

### Ingesting Sources

| Prompt | What it does |
|--------|--------------|
| *"Add this paper to the wiki: 2301.07041"* | Downloads the paper, extracts content, and creates/updates relevant wiki pages |
| *"Ingest the PDF at ./raw/papers/attention.pdf into the wiki"* | Converts the PDF to markdown and integrates findings into existing pages |
| *"Research sparse mixture of experts and add what you find to the wiki"* | Searches multiple academic sources, downloads top papers, and synthesizes into wiki pages |
| *"Clone the repo google/flaxformer and document its architecture in the wiki"* | Clones the repository and creates wiki pages about its design |

### Querying the Wiki

| Prompt | What it does |
|--------|--------------|
| *"Given the knowledge stored in the LLM-Wiki, compare LoRA vs full fine-tuning"* | Reads relevant wiki pages and synthesizes a comparison from ingested knowledge |
| *"Based on the wiki, what is the current best approach for LLM routing?"* | Queries the index, reads relevant pages, and provides a cited answer |
| *"Summarize everything the wiki knows about attention mechanisms"* | Synthesizes across multiple wiki pages into a cohesive summary |
| *"What are the tradeoffs between dense and sparse models according to the wiki?"* | Produces a structured analysis drawing from wiki content |

### Maintaining the Wiki

| Prompt | What it does |
|--------|--------------|
| *"Lint the wiki and fix any issues"* | Checks for orphan pages, broken wikilinks, stale content, and missing cross-references |
| *"Audit the wiki for outdated content"* | Identifies pages that may be superseded by newer research |
| *"Update the wiki's index"* | Rebuilds `index.md` to reflect current wiki content |

### Visualizing the Wiki

| Prompt | What it does |
|--------|--------------|
| *"Run the local webapp"* | Starts the dev-server + Vite frontend at http://localhost:5173 pointing at your wiki |
| *"Visualize this wiki"* | Same as above — launches the Cloudscape web app for browsing the wiki in a browser |
| *"Start the webapp for my-research-wiki"* | Starts the local server with `WIKI_DIRS` pointing at the specified directory |

The webapp auto-detects wiki directories and bypasses authentication on localhost — no login needed during development.

### Deploying to AWS

| Prompt | What it does |
|--------|--------------|
| *"Deploy the AWS infrastructure"* | Runs `cdk deploy WikiPlatformStack` — provisions CodeCommit, Lambda, CloudFront, Cognito, SNS |
| *"Add my wiki to the platform"* | Creates a CodeCommit repo, registers in SSM, pushes content, triggers the indexer |
| *"Deploy the webapp to AWS"* | Builds the React app with production env vars and deploys to S3/CloudFront |
| *"Create a user for the webapp"* | Creates a Cognito user with a permanent password |

These operations use the utility scripts in `scripts/` under the hood and auto-detect region and stack outputs from CloudFormation.

## How It Works

The skill uses a three-layer architecture:

1. **Raw Sources** (`$WIKI_DIR/raw/`) — Immutable source material (PDFs, articles, cloned repos). Never modified after download.
2. **Wiki Pages** (`$WIKI_DIR/entities/`, `concepts/`, `comparisons/`, `queries/`) — Agent-owned markdown files with cross-references via `[[wikilinks]]`.
3. **Schema** (`$WIKI_DIR/SCHEMA.md`) — Defines structure conventions, tag taxonomy, and domain configuration.

Navigation is maintained through `index.md` (content catalog) and `log.md` (chronological action log).

The wiki directory name is configurable via `WIKI_DIR` (default: `wiki/`). When working with multiple wikis, each gets its own name (e.g., `llm-wiki/`, `security-playbook/`).

## Infrastructure: Wiki Platform (AWS)

The skill includes a complete serverless AWS infrastructure for persisting and sharing wikis across multiple agents. Deploy once — create wikis dynamically at runtime.

### Architecture

```
CloudFront (SPA + API)
    ├── S3 (React app + /data/*.json)
    └── API Gateway (HTTP API)
            ├── wiki-reader Lambda (GET: browse wikis)
            ├── wiki-admin Lambda (POST/DELETE: manage wikis)
            └── wiki-indexer Lambda (EventBridge: builds graph/search on push)
                    │
            CodeCommit (wiki-* repos) ──▶ SNS (agent notifications)
                    │
            Agents (git clone/push via IAM)
```

**Two access paths:**
- **Humans** → React web app → Cognito auth → API → CodeCommit
- **Agents** → `git-remote-codecommit` (IAM) → CodeCommit directly

### Deploy

```bash
cd ~/.kiro/skills/knowledge-acquisition/infrastructure
pip install -r requirements.txt
cdk bootstrap   # first time only
cdk deploy WikiPlatformStack
```

### Create a Wiki (Runtime)

```bash
# Via API (human or agent):
curl -X POST https://<WebAppURL>/api/wikis \
  -H "Authorization: Bearer <token>" \
  -d '{"name": "llm-wiki", "description": "Research knowledge base", "owner": "research-agent"}'
```

### Agent Access

Agents read/write via git natively:

```bash
pip install git-remote-codecommit
git clone codecommit::<region>://wiki-llm-wiki
cd wiki-llm-wiki
git config user.name "my-agent"
git pull origin main
# ... make changes ...
git add -A && git commit -m "[my-agent] Add topic" && git push origin main
```

### Cost Estimate (Prototyping Scale)

| Service | Monthly Cost |
|---------|-------------|
| CodeCommit | $0 (free tier: 5 users, 50GB) |
| Lambda (3 functions) | $0 (free tier: 1M requests/month) |
| API Gateway (HTTP API) | $0 (free tier: 1M requests/month) |
| S3 (static assets + data) | ~$0.02 |
| CloudFront | $0 (free tier: 1TB transfer) |
| Cognito | $0 (free tier: 50K MAU) |
| SSM Parameter Store | $0 (standard tier) |
| SNS | $0 (free tier: 1M publishes) |
| EventBridge | $0 (free tier: all state-change events) |
| **Total** | **~$0/month** |

The platform costs effectively nothing at prototyping scale — all components fall within AWS free tiers.

## Web App

A React SPA built on the **Cloudscape Design System** (AWS console aesthetic) for browsing wikis:

- **Wiki list homepage** — all available wikis as clickable cards
- **Wiki overview** — page counts by type, recent activity log
- **Knowledge base views** — Cloudscape `Table` components with filtering, sorting, and pagination for entities, concepts, comparisons, and queries
- **Detail pages** — rendered markdown with frontmatter badges, resolved `[[wikilinks]]`, and backlinks
- **Knowledge graph** — interactive force-directed visualization + table view
- **Activity log** — parsed `log.md` entries with expandable details
- **Auth bypass on localhost** — no login required during local development

### URL Structure

```
/                              → Wiki list (all wikis)
/w/{wikiName}                  → Wiki overview (stats + activity)
/w/{wikiName}/concepts         → Concepts table
/w/{wikiName}/entities         → Entities table
/w/{wikiName}/comparisons      → Comparisons table
/w/{wikiName}/queries          → Queries table
/w/{wikiName}/graph            → Knowledge graph
/w/{wikiName}/log              → Activity log (parsed log.md)
/w/{wikiName}/page/{group}/{slug} → Detail page
```

### Run Locally (No AWS Required)

The web app works against local filesystem directories — no deployment needed for development:

```bash
# Terminal 1: Start local backend pointing to your wiki(s)
WIKI_DIRS=./my-wiki:./other-wiki node ~/.kiro/skills/knowledge-acquisition/webapp/dev-server.mjs

# Terminal 2: Start the React dev server
cd ~/.kiro/skills/knowledge-acquisition/webapp
npm install   # first time only
npm run dev   # opens http://localhost:5173 — auto-bypasses login
```

Each directory becomes a browsable wiki. The directory name is the wiki name.

### Deploy to AWS

Use the provided utility script (auto-detects stack outputs):

```bash
~/.kiro/skills/knowledge-acquisition/scripts/deploy-webapp.sh
```

Or manually:

```bash
cd ~/.kiro/skills/knowledge-acquisition/webapp
VITE_API_ENDPOINT=<ApiEndpoint> VITE_USER_POOL_ID=<PoolId> VITE_CLIENT_ID=<ClientId> VITE_REGION=<region> npm run build
aws s3 sync dist/ s3://<ReactUIBucketName> --delete
aws cloudfront create-invalidation --distribution-id <DistId> --paths "/*"
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Design System | Cloudscape (@cloudscape-design/components) |
| Framework | React 18 + TypeScript |
| Build | Vite 5 |
| Routing | react-router-dom v6 |
| Markdown | react-markdown + remark-gfm |
| Graph | react-force-graph-2d |
| Collections | @cloudscape-design/collection-hooks |
| Auth | Cognito (direct fetch, no Amplify) — bypassed on localhost |

## Operational Scripts

Shell scripts in `scripts/` for platform management. All auto-detect AWS region and stack outputs.

| Script | Purpose |
|--------|---------|
| `scripts/deploy-webapp.sh` | Build React app + deploy to S3 + invalidate CloudFront |
| `scripts/sync-wiki.sh WIKI_DIR` | Push local wiki changes to CodeCommit |
| `scripts/create-wiki.sh WIKI_DIR` | Register a new wiki (CodeCommit + SSM + initial push) |
| `scripts/create-user.sh USERNAME` | Create a Cognito user for webapp access |

**Region resolution** (in order): `WIKI_REGION` → `AWS_REGION` → `AWS_DEFAULT_REGION` → `aws configure get region`.

```bash
# Example: sync after making wiki edits
~/.kiro/skills/knowledge-acquisition/scripts/sync-wiki.sh ./my-wiki --message "Added new pages"

# Example: add a new wiki to the platform
~/.kiro/skills/knowledge-acquisition/scripts/create-wiki.sh ./my-new-wiki --description "Security KB" --owner alice

# Example: create a user
~/.kiro/skills/knowledge-acquisition/scripts/create-user.sh bob --email bob@example.com
```

## Data Sources

The skill can gather material from:

- **arXiv** — preprints and papers
- **Semantic Scholar** — citations, references, and related papers
- **OpenAlex** — 250M+ open-access works
- **CrossRef** — DOI-registered publications and BibTeX generation
- **Papers With Code** — GitHub implementations linked to papers
- **Wikipedia** — background summaries and context
- **DeepXiv** — semantic paper search with progressive reading
- **GitHub** — repositories, code search, and README extraction

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file for details.
