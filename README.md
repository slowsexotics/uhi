# UHI — Free, Open-Source AI for Creators

UHI is a local-first personal AI creator assistant in development. It helps you describe what you want to make, choose one practical next action, and keep track of what you tried and learned. The goal is useful personal AI that ordinary people can own and control.

**Status: macOS development preview.** The reviewed source snapshot supports local creator profiles, saved feedback and briefing history, plus an optional local Ollama adapter. It is not yet a packaged application for nontechnical users. The UHI-owned source is licensed under MIT; see [License](#license). The source is publicly available at [slowsexotics/uhi](https://github.com/slowsexotics/uhi).

## Why UHI Exists

Powerful personal AI should be accessible without forcing people into expensive subscriptions or giving up control over their data and workflows. Creators deserve tools that help them build independence. UHI aims to make personal AI practical while leaving people in charge of their work, information and choice of services.

## Who It's For

- Content creators and people starting their first creative project.
- People without technical backgrounds who want approachable AI tools.
- Independent entrepreneurs organizing their work.
- People who value privacy and local control.
- Anyone exploring personal AI systems.

The mission includes these audiences; this preview currently needs comfort with a terminal and local development tools.

## What UHI Can Do Today

The included code and isolated tests exercise:

- A dashboard served only on the local loopback interface.
- Onboarding and an editable creator profile with interests, goals, experience, time and resources.
- Local SQLite storage of preferences, briefing history, answers, obstacles and progress reported by the user.
- Structured creator briefings with one suggested action, steps, a reason, a concrete completion criterion and one plain-language question.
- Saved feedback included in the next briefing context; retry identifiers prevent duplicate successful generations.
- Validation that rejects malformed model output and records failures without claiming success.

**Experimental:** the optional Ollama adapter requires explicit configuration and an already loaded, user-owned model. Automated tests use mock responses; real model quality and hardware performance are not verified by those tests.

**Unavailable:** social account connections and collection, cloud providers, Telegram, automatic scheduling, automatic startup, model installation and service startup. Older interface panels remain visible as unfinished design references. Do not paste API keys or bot tokens into this preview. No social analytics are bundled; an empty dashboard does not establish zero activity.

## Architecture and Technology

UHI consists of a Python standard-library HTTP server, HTML/CSS/JavaScript dashboard and a namespaced SQLite data layer. There are no required pip or npm runtime dependencies. The server binds to `127.0.0.1:8080`; it uses host/origin checks, a process-local session cookie and CSRF checks for mutations. User and model text in the creator briefing interface is rendered with text nodes.

The optional adapter talks directly to a local Ollama HTTP endpoint on port `11434`. Model responses are constrained and validated against a structured output contract. No model is downloaded by the normal preview flow.

UHI is separate from OpenClaw, an external project. Earlier development involved private orchestration infrastructure; that infrastructure, its data and its integrations are excluded here. Profile editing, feedback and history in this snapshot do not require it. Disabled integrations would need separately designed, user-owned implementations before they can be offered. This repository does not include or claim ownership of OpenClaw or Ollama.

## Getting Started

### Prerequisites

Use a macOS development machine with Python **3.10 or newer** and a browser. Check `python3 --version`. The source uses only Python's standard library; SQLite and time-zone support must be available in your Python installation. Node.js with the built-in test runner is needed only to run frontend tests.

This is a development preview, not a one-click installer. Windows and Linux support have not been established. It does not require a private installation, Telegram account, cloud account or a model to save a profile and inspect history.

### Run the preview

From the repository root, use a new data directory outside the checkout:

```sh
export UHI_DATA_DIR="$(mktemp -d /tmp/uhi-preview.XXXXXX)"
python3 -B dashboard/server.py
```

Open `http://127.0.0.1:8080` directly in your browser. Complete the creator profile; AI generation can remain unconfigured. Stop the development server with Control-C. The data directory remains after exit; record its path if you want to revisit that preview. Keep it private and back it up separately. For persistent use, set `UHI_DATA_DIR` to a dedicated absolute directory you own outside the source checkout and outside any agent/runtime installation.

The program rejects the checkout, its ancestors and protected runtime locations as storage directories. It does not import existing private data. Do not use credentials, shared runtime data or a production installation as a fixture.

### Optional local briefings

Use only a separate local backend you own and have deliberately prepared. A compatible Ollama service and the exact named model must already be running and loaded. UHI does not install or start them for you. Do not use a shared production backend for evaluation.

In the same terminal before starting UHI:

```sh
export UHI_INFERENCE_APPROVED=1
export UHI_MODEL='your-installed-model:tag'
export UHI_OLLAMA_URL='http://127.0.0.1:11434'
python3 -B dashboard/server.py
```

Replace the model placeholder with the exact already loaded model name. If a saved model preference exists, it must match `ollama/` followed by that name. Cloud API keys are unsupported. Leave `UHI_ALLOW_TEMP_MODEL` unset; temporary model loading is an experimental code path and is not part of the supported preview instructions. Generated suggestions can be wrong; review them before acting. UHI records progress only when you report it.

### Verify without models or live services

From the repository root:

```sh
export UHI_DATA_DIR="$(mktemp -d /tmp/uhi-tests.XXXXXX)"
python3 -B -m unittest discover -s tests/uhi -p 'test_*.py'
node --test tests/uhi/frontend.test.cjs
```

Tests create their own temporary state, mock inference and exercise the HTTP handler without opening a listening socket. No real model quality, full browser layout or installation on another operating system is established by these checks.

### Troubleshooting

If port 8080 is already used, stop and resolve the conflict on your own development machine; do not interrupt unrelated services. For storage errors, use a fresh dedicated directory and check its permissions. Corrupt data is reported as an error; do not overwrite your only backup. For generation errors, check the explicit environment settings, matching preference, model availability and structured-output support. Saving a profile does not require inference approval.

## Free Forever

UHI's core software is intended to remain free and open-source. The MIT license permits use, modification and distribution of the released code, including commercial use.

Users should be able to choose local or supported third-party AI services as integrations mature. Optional external API subscriptions and hardware can have separate costs. The free-forever commitment describes the intended core software offering; it does not promise unlimited paid compute, API usage or hosted infrastructure at no cost.

## Roadmap

**Implemented in this snapshot:** local profile persistence, validated briefing and feedback storage, an optional local adapter, isolated test fixtures and disabled external integrations.

**Current development work:** continue security review of the published source; simplify the legacy interface; strengthen filesystem and browser security checks; document a repeatable local setup.

**Next goals:**

1. Harden security and add regression coverage around data boundaries and provider adapters.
2. Build reliable installation and recovery for a clearly supported macOS configuration.
3. Test onboarding with nontechnical creators and remove unavailable legacy panels.
4. Validate Windows and Linux before claiming support.
5. Expand practical creator workflows and user-controlled AI provider connections.
6. Improve documentation and establish a sustainable contribution process.

See the [funding roadmap](docs/FUNDING_ROADMAP.md) for proposed priorities and estimates.

## Known Limitations

- Development preview with no packaged installer or verified cross-platform distribution.
- Optional inference has been tested with mocks, not certified across models or hardware.
- Social collection, cloud inference, Telegram and scheduling are disabled; legacy panels and missing guide images need cleanup.
- Local data is not encrypted by UHI; protect your account, storage and backups. Do not expose the development server to the internet or a network proxy.
- Python's built-in HTTP server and inline legacy UI scripts are development foundations, not a hardened hosted service.
- Temporary model-loading code remains experimental and requires a separate explicit environment opt-in; avoid it on shared systems.
- Ongoing security review remains necessary. Automated checks do not prove absence of all vulnerabilities.

## Funding and Sustainability

UHI is pursuing grants and voluntary support to keep its core software free and open-source. A **proposed $6,500 development grant** would support security, installation, creator usability, testing and documentation. The budget in [FUNDING_ROADMAP.md](docs/FUNDING_ROADMAP.md) is an estimate, not awarded funding.

GitHub Sponsors and optional donations are planned. No sponsorship activation, payment collection or grant submission is included in this snapshot. No grant award, sponsor, Tether affiliation or endorsement is claimed. Future optional service costs will be described separately from the free core.

## Contributing and Security

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the development boundary and test commands. Small, focused changes that improve safety or help a creator complete a real task are welcome. Use synthetic data and mock external services.

For suspected vulnerabilities, follow [SECURITY.md](SECURITY.md). Do not put credentials, private files or exploit details in public issues.

## License

UHI-owned source in this snapshot is licensed under the [MIT License](LICENSE), copyright (c) 2026 slowsexotics. The project owner confirmed the copyright holder and authorized MIT publication of the selected UHI-owned dashboard, tests and related code.

External projects and any future dependencies retain their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). No private infrastructure or third-party installation is included in this snapshot.
