# finance-qa sample

Five of the 70 questions in Veris's **finance-qa** bench, packaged as
[Harbor](https://harborframework.com) tasks and free to run. The full 70-task set is available
from Veris on request; this sample shows exactly what it looks like and how it scores.

Each task gives the agent one question over scanned historical U.S. Treasury financial
statements (1790s–1990s). The 1,462 source documents sit in a company Dropbox (a sandboxed,
API-accurate replica served over MCP). The agent must find the right document, read it, and
compute an exact figure. A deterministic script grades the final answer.

| Task | Difficulty | Skill |
|---|---|---|
| 01 Appropriation-mix dissimilarity, 1820 vs 1829 | easy | a distance metric over one blurry statement, with a printed misprint to detect |
| 02 Internal revenue refund authority change, FY1985–86 | easy | a lookup in two Appendix volumes and a subtraction to the cent |
| 03 Expenditure rigidity index spread, 1820s | medium | a derived index over a decade of clear tables |
| 04 IRS vs Post Office officer accountability, 1962 | medium | very blurry ledger, multi-step arithmetic |
| 05 OLS trend of non-debt spending, FY1844–1859 | hard | regression over 16 years, multiple sources, a misprint |

Difficulty is empirical: `easy` = every valid hosted attempt passed, `hard` = every one
failed, `medium` otherwise.

## Baseline

One attempt per task, no document-parsing service, the harness as shipped with a 30-minute
budget, models on Bedrock. The grader is the one in this repo.

| Harness | Model | Passed | Tasks solved |
|---|---|---|---|
| Claude Code | Claude Opus 5.5 | 4 / 5 | 01, 03, 04, 05 |
| Codex | GPT-6.1 Sol | 3 / 5 | 01, 03, 04 |
| Claude Code | Claude Sonnet 5.5 | 1 / 5 | 01 |
| Codex | GPT-5.6 Terra | 1 / 5 | 02 |

Every task was solved by at least one harness and none by all four. The hosted bench, where
agents also get a document-parsing MCP server, scores higher; these numbers are what this
export gives an agent that reads the scans itself.

## Quick start

```bash
export ANTHROPIC_API_KEY=...    # your agent's model key (Claude Code shown below)

harbor run -y -p tasks/01-appropriation-mix-dissimilarity-1820-vs-1829 -a oracle   # → reward 1.0: the setup works
harbor run -y -p tasks/<task> -a claude-code -m anthropic/claude-opus-5-5 \
  --ak disallowed_tools=WebSearch,WebFetch      # turn the CLI's web search off
harbor run -y -p tasks -a <agent> -m <model>     # all five
```

Requirements: Harbor ≥ 0.23, Docker on a Linux/amd64 host, ~15 GB of disk for the first
build. The world image `ghcr.io/veris-ai/bench-finance-qa-sample/bundle` is public; no
registry login is needed.

**Data and build time.** The 1,462 documents (13.4 GB) are not in this repo or in the
image: the world's Dockerfile downloads them from the public Hugging Face dataset
`veris-ai/finance-qa-corpus` at build time (pinned commit, verified against a manifest).
Expect ~5–10 minutes for that first build on a host; Docker caches the result, and all
tasks share the same world image, so later trials on that host start in seconds. On
infrastructure that gives every trial a fresh host, build the world image once and push it
to your own registry (the Dockerfile is deterministic — pinned bundle digest and dataset
commit), then point the `world` service at it with `image:` instead of `build:`.

## Layout

```
tasks/<task>/
  instruction.md          the question and the date
  task.toml               Harbor config: keywords, resources, network policy, MCP server, verifier
  environment/            the agent's container and the Dropbox sidecar
  tests/                  the verifier (grade.py + answer.json)
  solution/NOTES.md       the reference answer (never shown to the agent)
MANIFEST.json             the five tasks with their ids and fingerprints
```

`keywords` in each `task.toml` describe the task (`Clear scan`, `Blurry scan`, `Large doc`,
`Multi-source`, `Misprint`, `Statistics`, `Percent`, `Arithmetic`) for filtering.

## What the agent gets

- The question, the current date, and the Dropbox MCP server (`dropbox`, 18 tools).
- An Ubuntu container with `poppler-utils` and `tesseract-ocr` preinstalled; package indexes
  (PyPI, npm, Ubuntu) are reachable so it can install more.
- No other network. Server-side web search cannot be blocked from inside a container, so the
  instruction forbids it and the quick-start flags turn it off in the CLI; the answers exist
  on the public web, so a run that searches is not measuring the task.

## Scoring

The verifier is a deterministic script, `tests/grade.py`. It reads every message the agent
wrote (its Harbor trajectory) and takes the number the reply commits to: the last line
starting `ANSWER:`, else the last stated numeric result. Currency symbols, thousands
separators, percent signs and unit words are ignored (unit words never rescale), and a
leading minus, a Unicode minus or accounting parentheses make the number negative. The
number passes if it lies inside any accepted range in `tests/answer.json`:

```json
{"expected": 15.19, "ranges": [[15.1748, 15.2052]]}
```

`reward` is 1.0 or 0.0. `verdict.json` beside it says how the number was read (`value`,
`how`, `flags`), so a 0.0 is always explainable. No model, key or network is involved, so results are exactly reproducible across
labs.

## Network policy

```toml
[agent]
network_mode = "allowlist"
allowed_hosts = ["world", "pypi.org", "files.pythonhosted.org", "registry.npmjs.org",
                 "archive.ubuntu.com", "security.ubuntu.com", "ports.ubuntu.com",
                 "api.anthropic.com"]   # replace with your model's host
```

`[environment]` is `public` so Harbor can install the agent before the task starts.
Allowlists need Docker/Podman with nftables, or a provider that supports `allowlist` for
compose tasks; where that is unavailable, run `public`.

## Resources

Agent container: 2 CPUs, 4 GB RAM, 10 GB storage. Dropbox sidecar: 2 GB RAM.

## The full bench

These five tasks are public, so their answers are too: treat them as a setup check and a
preview, not as an evaluation. The other 65 tasks are private. Contact Veris for access.

## Data and licence

Derived from Databricks' [OfficeQA Pro V2](https://huggingface.co/datasets/databricks/officeqa-pro-v2)
(CC-BY-SA 4.0); the questions and criteria are adapted from it and released under the same
licence (`LICENSE`). The documents are U.S. government works in the public domain.
