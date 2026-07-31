# LinkDogger

Public-profile people discovery and networking intelligence tool.

LinkDogger lets you search for a company and discover **publicly discoverable
people** associated with it, enrich their profiles with publicly available
social/professional links, calculate networking-related signals, and present
the results through both a CLI and an optional local web dashboard.

> LinkDogger does **not** claim to know every employee of a company. It only
> surfaces people that can be reasonably associated with the company from
> publicly available information.

## Privacy and Data Rules

- Only publicly available information is used, through legitimate access
  methods (official APIs preferred when available).
- No authentication bypass, no CAPTCHA circumvention, no rate-limit evasion,
  no scraping of private profiles, no fabrication of follower counts or
  social accounts.
- Unverifiable information is marked unavailable (`null`), never guessed.
- Every result carries source/provenance information.

## Status

This project is built incrementally in stages, each on its own branch with a
conventional commit and pull request.

| Stage | Description | Status |
| ----- | ----------- | ------ |
| 0 | Project bootstrap | Done |
| 1 | CLI (`search`, `--json`, `--version`) | Done |
| 2 | Company discovery | Done |
| 3 | People discovery | Done |
| 4 | Social profile enrichment | Done |
| 5 | Identity matching | Done |
| 6 | Networking intelligence scoring | Done |
| 7 | Sorting and filtering | Done |
| 8 | JSON output and export | Done |
| 9 | Web GUI | Done |
| 10 | Testing and hardening | Done |
| 11 | Final documentation | Done |

## Requirements

- Python 3.12+

## Installation (development)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

## Configuration

Configuration is read from environment variables prefixed with `LINKDOGGER_`
and an optional local `.env` file. Copy `.env.example` to `.env` to get
started. Secrets are never committed.

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `LINKDOGGER_LOG_LEVEL` | `INFO` | Logging verbosity. |
| `LINKDOGGER_WEB_HOST` | `127.0.0.1` | Bind address for the web dashboard. |
| `LINKDOGGER_WEB_PORT` | `8000` | Port for the web dashboard. |
| `LINKDOGGER_DISCOVERY_BACKEND` | `mock` | `mock` (sample data) or `github` (official API). |
| `LINKDOGGER_GITHUB_TOKEN` | *(none)* | Optional GitHub token to raise API rate limits. |
| `LINKDOGGER_REQUEST_TIMEOUT_SECONDS` | `10.0` | Timeout for provider calls. |
| `LINKDOGGER_MAX_RESULTS` | `100` | Default maximum results per search. |

By default the app uses a mock backend (`mock-sample-data`) so it can be
explored without network access. Set `LINKDOGGER_DISCOVERY_BACKEND=github` to
use the GitHub API for real company and people discovery; the backend is safe
to run without a token and automatically degrades to public, unauthenticated
calls.

## Usage

### Help and version

```bash
linkdogger --help
linkdogger --version
```

### Search for a company

```bash
linkdogger search "OpenAI"
```

Shows a live searching animation while discovery runs, then displays a table
of publicly discoverable people associated with the company, ranked by
**follow-back likelihood (descending)** by default:

```text
LinkDogger v0.1.0
Company: OpenAI

Found 3 publicly discoverable people

                    Publicly discoverable people @ OpenAI
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Name         ┃ Position            ┃ Location        ┃ Platforms ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ Alex Sample  │ Software Engineer   │ San Francisco…  │ github, … │
│ …            │ …                   │ …               │ …         │
└──────────────┴─────────────────────┴─────────────────┴───────────┘

Use --json for machine-readable output.
```

### Inspecting what is happening

```bash
linkdogger search "OpenAI" --log
```

Replaces the animation with detailed progress logs (backend in use, API
requests, enrichment status) printed to stderr.

### Machine-readable output

```bash
linkdogger search "OpenAI" --json
```

Emits a versioned JSON document (`schema_version`) with `query`,
`generated_at`, `count`, and `results`.

### Sorting, filtering and limits

```bash
# Sort by networking score (asc or desc), then take the top 5
linkdogger search "OpenAI" --sort networking-score-desc --limit 5

# Filter by role and location
linkdogger search "OpenAI" --role engineer --location "San Francisco"
```

`--sort` accepts `followers`, `networking-score`, `followback`, `influence`
or `name`, each optionally suffixed with `-asc`/`-desc` (default `desc`).
Without `--sort`, results are ranked by follow-back likelihood, descending —
the best profiles to engage with appear first.

### Exporting results

```bash
linkdogger search "OpenAI" --export results.json
linkdogger search "OpenAI" --export results.csv
linkdogger search "OpenAI" --export results.md
```

### Web dashboard

```bash
linkdogger --web
```

Serves a local dashboard at `http://127.0.0.1:8000` (see configuration above)
with a search form, result cards, and the same sorting/filtering options as
the CLI, backed by the same `PeopleService` pipeline.

> **Note:** the mock backend returns clearly marked sample data (source
> `mock-sample-data`). Unavailable information is `null` — never guessed.

## Development

```bash
pip install -e ".[dev]"
ruff check .
ruff format .
mypy src
pytest
```

Continuous integration runs lint, format, type and test checks on every push
and pull request (`.github/workflows/ci.yml`) across Python 3.12–3.14.

## Project Structure

```text
linkdogger/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── .github/workflows/ci.yml
├── src/
│   └── linkdogger/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py                 # Typer CLI (search, --json, --web)
│       ├── errors.py              # LinkDoggerError hierarchy
│       ├── config/
│       │   └── settings.py        # LINKDOGGER_* configuration
│       ├── models/
│       │   ├── company.py
│       │   ├── person.py
│       │   ├── social.py
│       │   ├── networking.py
│       │   └── search.py          # versioned SearchResult envelope
│       ├── discovery/
│       │   ├── base.py            # CompanyDiscoverer / PeopleDiscoverer
│       │   ├── mock.py            # sample data backend
│       │   └── github.py          # official GitHub API backend
│       ├── enrichment/
│       │   ├── base.py            # Enricher protocol
│       │   ├── github.py
│       │   ├── linkedin.py
│       │   ├── website.py
│       │   └── social.py
│       ├── matching/
│       │   └── identity.py        # cross-platform identity merging
│       ├── scoring/
│       │   ├── weights.py
│       │   ├── followback.py
│       │   └── networking.py
│       ├── services/
│       │   ├── people_service.py  # shared pipeline (CLI + web)
│       │   ├── processing.py      # sort keys, result filters
│       │   └── factory.py         # backend wiring
│       ├── output/
│       │   ├── json.py
│       │   ├── table.py
│       │   └── export.py          # JSON / CSV / Markdown
│       └── web/
│           ├── app.py             # FastAPI factory
│           ├── routes.py
│           ├── templates/index.html
│           └── static/
│               ├── app.js
│               └── style.css
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

## License

MIT
