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
| 0 | Project bootstrap | In progress |
| 1 | CLI (`search`, `--json`, `--version`) | Planned |
| 2 | Company discovery | Planned |
| 3 | People discovery | Planned |
| 4 | Social profile enrichment | Planned |
| 5 | Identity matching | Planned |
| 6 | Networking intelligence scoring | Planned |
| 7 | Sorting and filtering | Planned |
| 8 | JSON output and export | Planned |
| 9 | Web GUI | Planned |
| 10 | Testing and hardening | Planned |
| 11 | Final documentation | Planned |

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

```text
LINKDOGGER_LOG_LEVEL=INFO
LINKDOGGER_WEB_HOST=127.0.0.1
LINKDOGGER_WEB_PORT=8000
```

## Development

```bash
ruff check .
ruff format .
mypy src
pytest
```

## Project Structure

```text
linkdogger/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── src/
│   └── linkdogger/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       └── config/
│           └── settings.py
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

## License

MIT
