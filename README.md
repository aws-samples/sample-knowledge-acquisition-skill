# Knowledge Acquisition Skill

Build and maintain a persistent, compounding knowledge base as interlinked markdown files — an **LLM Wiki**.

Unlike RAG (which rediscovers knowledge from scratch per query), the LLM Wiki compiles knowledge once and keeps it current. Cross-references are pre-built, contradictions are flagged, and synthesis reflects everything ingested. The wiki distills to state-of-the-art: it answers *"What is the best way to do X right now?"* rather than cataloging every historical approach.

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

## How It Works

The skill uses a three-layer architecture:

1. **Raw Sources** (`wiki/raw/`) — Immutable source material (PDFs, articles, cloned repos). Never modified after download.
2. **Wiki Pages** (`wiki/entities/`, `wiki/concepts/`, `wiki/comparisons/`, `wiki/queries/`) — Agent-owned markdown files with cross-references via `[[wikilinks]]`.
3. **Schema** (`wiki/SCHEMA.md`) — Defines structure conventions, tag taxonomy, and domain configuration.

Navigation is maintained through `index.md` (content catalog) and `log.md` (chronological action log).

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
