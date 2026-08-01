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
  no fabrication of follower counts or social accounts.
- The optional LinkedIn provider uses **your own LinkedIn account**
  (`LINKDOGGER_LINKEDIN_EMAIL`/`LINKDOGGER_LINKEDIN_PASSWORD`, opt-in) with
  the `open-linkedin-api` library, which caches your session cookies locally
  and sleeps between requests to respect rate limits. Your credentials are
  never shared or committed. Understand and accept LinkedIn's terms before
  using it — use at your own risk.
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
| `LINKDOGGER_DISCOVERY_BACKEND` | `mock` | Web backend: `mock` (sample data) or `github` (official API). |
| `LINKDOGGER_GITHUB_TOKEN` | *(none)* | Optional GitHub token to raise API rate limits. |
| `LINKDOGGER_LINKEDIN_EMAIL` | *(none)* | LinkedIn account email for the optional LinkedIn provider. |
| `LINKDOGGER_LINKEDIN_PASSWORD` | *(none)* | LinkedIn account password (never committed). |
| `LINKDOGGER_LINKEDIN_COOKIES_DIR` | *(none)* | Directory for the library's cached session cookies (default: `~/.linkedin_api/cookies/`). |
| `LINKDOGGER_LINKEDIN_COOKIE_FILE` | *(none)* | Path to a session cookie file (`li_at` + `JSESSIONID`, created by `linkdogger linkedin-login`); takes priority over credentials. |
| `LINKDOGGER_REQUEST_TIMEOUT_SECONDS` | `10.0` | Timeout for provider calls. |
| `LINKDOGGER_MAX_RESULTS` | `100` | Default maximum results per search. |

### Providers

The CLI selects a **provider** with `--provider` (default `linkedin`):

| Provider | Discovery | Enrichment |
| -------- | --------- | ---------- |
| `linkedin` (default) | Company resolution + people search (with credentials) | LinkedIn profiles (headline, location, bio, published email) |
| `github` | GitHub organizations + public members | GitHub profiles (email, accounts) |
| `hybrid` | GitHub organizations + public members | GitHub **and** LinkedIn enrichment |
| `mock` | Clearly marked sample data | *(none)* |

> **LinkedIn setup:** the LinkedIn provider uses your own account through the
> `open-linkedin-api` library (an HTTP client for LinkedIn's Voyager API, not
> a browser). Install the optional extra and authenticate either way:
>
> ```bash
> pip install -e ".[linkedin]"
> ```
>
> **Option A — session cookies (recommended when password login hits a
> challenge):** log in once in your browser, then paste your cookies:
>
> ```bash
> # set LINKDOGGER_LINKEDIN_COOKIE_FILE=linkedin-cookies.json in .env
> linkdogger linkedin-login   # prompts for li_at + JSESSIONID
> ```
>
> **Option B — credentials:** set `LINKDOGGER_LINKEDIN_EMAIL` and
> `LINKDOGGER_LINKEDIN_PASSWORD` in `.env`; the library logs in and caches
> the session cookies for reuse.
>
> Without either, the `linkedin` provider still resolves companies via
> slug URLs but honestly reports that people discovery is unavailable.
> The library sleeps between requests to respect LinkedIn's rate limits —
> expect enrichment to take a few seconds per profile.
>
> > **Python 3.14 note:** `open-linkedin-api` pins `lxml<6.0.0`, which has no
> > Python 3.14 wheels yet. On Python 3.14 install the extra with
> > `pip install -e ".[linkedin]" --no-deps` and then
> > `pip install beautifulsoup4` (lxml 6.x already satisfies it).

By default the web dashboard uses the mock backend (`mock-sample-data`) so it
can be explored without network access. Set `LINKDOGGER_DISCOVERY_BACKEND=github`
to use the GitHub API for real company and people discovery; the backend is safe
to run without a token and automatically degrades to public, unauthenticated
calls.

## ToDo's

- [x] Add system to export all the found mail to JSON file.
- [ ] Add llm support to app
- [x] Enable IPC and MCP support of the app
- [x] Using SMTP, creating system to send email using exported json file.
- [x] Observer to overlook the response of the email and inform the user.


## Usage

### Help, version and diagnostics

```bash
linkdogger --help                  # all commands and options
linkdogger --version
linkdogger doctor                  # diagnose providers, credentials, LinkedIn session
linkdogger config                  # show effective settings (secrets redacted)
linkdogger serve                   # local web dashboard (same as linkdogger --web)
```

`linkdogger doctor` validates a configured LinkedIn session live (via the
Voyager `/me` endpoint) and reports who it belongs to — or why it could not
be validated (expired cookies, login challenge, LinkedIn blocking automated
access). The same check runs automatically during searches: a cookie-session
result is logged (`LinkedIn session validated: ...` / a warning otherwise),
once per process.

### Manage your LinkedIn session

```bash
linkdogger login                    # paste li_at + JSESSIONID, saves and validates the session
linkdogger linkedin-login           # same, longer name
```

The saved session is checked with a live API call and the outcome is
reported (`Session validated: ...` or a warning).

### Search for a company

```bash
linkdogger search "OpenAI"                    # default: LinkedIn provider
linkdogger search "OpenAI" --provider github  # GitHub API only
linkdogger search "OpenAI" --hybrid           # GitHub discovery + LinkedIn enrichment
```

Shows a live searching animation while discovery runs, then displays a table
of publicly discoverable people associated with the company, ranked by
**follow-back likelihood (descending)** by default. Each row also shows the
person's **email** (public profile address, or resolved from their public
commit history — latest commit on their most recent repo, its `.patch`
header, then commit search — when the profile has none) and their
**connected accounts**
(GitHub, website, X, LinkedIn when published) as clickable hyperlinks:

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

# Outreach lists: dump every discovered email address to a JSON file
# (auto-named from the resolved company, e.g. openai.emails.json)
linkdogger search "OpenAI" --export email
```

The `--export email` variant writes a JSON document with a flat `emails`
array (for pasting into mailing tools) plus `people` entries carrying
name/position context. Only people with a discovered email are included.

### Web dashboard

```bash
linkdogger serve        # or: linkdogger --web
```

Serves a local dashboard at `http://127.0.0.1:8000` (see configuration above)
with a search form, result cards, and the same sorting/filtering options as
the CLI, backed by the same `PeopleService` pipeline.

### IPC — talk to LinkDogger from other processes

```bash
linkdogger ipc-serve                       # start the local JSON-over-HTTP server
linkdogger ipc ping                        # quick health check
linkdogger ipc status                      # version + backend
linkdogger ipc search "OpenAI" --provider github
linkdogger ipc export_emails "OpenAI" --limit 20
```

The server binds to `127.0.0.1:8123` (`LINKDOGGER_IPC_HOST/PORT`) and accepts
`POST /rpc` with `{"method": ..., "params": {...}}`. Scripts can use the
`linkdogger.ipc.IPCClient` class directly; set `LINKDOGGER_IPC_TOKEN` to
require `Authorization: Bearer <token>`.

### MCP — drive LinkDogger from an AI assistant

```bash
linkdogger mcp
```

Runs a Model Context Protocol server over stdio (JSON-RPC 2.0, no SDK
needed). Point your MCP client at it and it can call `search_company`,
`export_emails` and `get_status` tools to discover people and build
outreach lists from inside the assistant.

### Email outreach — send from the exported contacts file

```bash
# 1. Discover people and export their email addresses
linkdogger search "OpenAI" --export email

# 2. Preview the messages (always do this first)
linkdogger send openai.emails.json --dry-run
linkdogger send openai.emails.json --dry-run --subject "Hi {name} from OpenAI" --body-file template.txt

# 3. Send for real (configure LINKDOGGER_SMTP_HOST in .env)
linkdogger send openai.emails.json --subject "..." --body-file template.txt
```

Templates support the placeholders `{name}`, `{company}`, `{position}` and
`{from_name}` (sender name). `--delay` sets the pause between sends
(default 1s) to behave politely with recipient servers. Delivery failures
are isolated per recipient — one bad address never aborts the batch.

### AI-generated outreach — `send --generate`

Let an LLM draft every subject and body for you, personalized per contact,
through NVIDIA NIM (build.nvidia.com) with DeepSeek V4 Flash:

```bash
# 1. Get a free API key from https://build.nvidia.com and set it in .env
#    LINKDOGGER_AI_API_KEY=nvapi-...

# 2. Preview what the model wrote (no emails sent)
linkdogger send openai.emails.json --generate --dry-run

# 3. Send the generated drafts for real
linkdogger send openai.emails.json --generate
```

Each contact gets its own draft generated from their name, company and
position (plus your `LINKDOGGER_SMTP_FROM_NAME`). Point the generator at
any OpenAI-compatible endpoint with `LINKDOGGER_AI_BASE_URL` /
`LINKDOGGER_AI_MODEL`. Drafts are 2-4 sentence, low-pressure outreach
messages; always review a `--dry-run` before sending.

### Watch — observe replies and inform yourself

```bash
linkdogger watch openai.emails.json --once          # single scan (scripts/CI)
linkdogger watch openai.emails.json --report replies.json
linkdogger watch openai.emails.json --interval 300  # poll every 5 minutes
```

The observer connects to your inbox (configure `LINKDOGGER_IMAP_HOST` in
.env), matches inbound messages against the contacts you wrote to, and
reports who replied, when, and a preview of what they said. `--since-days`
limits the scan window (default 7); new replies are printed as they arrive,
duplicates are filtered by IMAP UID, and `--report` writes findings as JSON.

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
(Note: the workflow is currently disabled — restore it from git history
(`git show fa4e99d:.github/workflows/ci.yml`) when CI is wanted again.)

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
│       ├── linkedin_api.py        # shared open-linkedin-api client helper
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
│       │   ├── github.py          # official GitHub API backend
│       │   └── linkedin.py        # LinkedIn provider (Voyager API client)
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
│       │   └── export.py          # JSON / CSV / Markdown / email payload
│       ├── ipc/
│       │   ├── server.py          # local JSON-over-HTTP server
│       │   └── client.py          # IPCClient for scripts
│       ├── mcp_server.py          # Model Context Protocol stdio server
│       ├── mail/
│       │   ├── contacts.py        # load contacts from exported JSON
│       │   ├── sender.py          # SMTP outbox (linkdogger send)
│       │   └── observer.py        # IMAP reply watcher (linkdogger watch)
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
