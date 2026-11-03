# Pitwall · fewer applications, better conversations

[Deutsch](README.md) · Part of [yslop](https://github.com/yslop): *why slop?* Tools for people who would rather do it well than do a lot.

**[Try the live demo](https://yslop.github.io/pitwall/)**, no installation, made-up data.

![Pitwall in 25 seconds: cockpit, job-ad analysis with fit score, briefing, interview cockpit with panic card](docs/media/star_en.gif)

**Pitwall is a local, AI-assisted job-search cockpit.** It helps you focus on a few roles that really fit and prepare every
conversation thoroughly: pipeline, staged research, briefing and an interview cockpit with a conversation guide, a bio
for exactly this role, a panic card and the best questions for the panel.

> The job market keeps getting faster. Keeping up does not take more applications; it takes a clear view of which ones
> are worth it and preparation that takes every conversation seriously. Pitwall is built for that.

**Less admin, more impact.** Instead of tracking countless application processes in a spreadsheet, you focus on what
decides: how you perform in the conversation and the next good step in your working life, including after a layoff or in
a time of change. Pitwall keeps pipeline, deadlines and research together for you.

## What makes Pitwall different

- **Focus over volume.** A weekly budget for new applications, a fit check before any effort, a nudge when you start to
  scatter. Pitwall is explicitly not a mass-application tool.
- **Evidence or marked as assumption.** Every statement in a briefing is either sourced (FACT) or marked (INFERENCE).
- **Your data stays with you.** Everything is files in this folder. No account, no server, no telemetry.
- **Your AI, your choice.** Claude, ChatGPT or Gemini subscription, your own API key, an EU provider or a local model
  (Ollama). Without AI, everything deterministic still works.
- **Decide against your yardstick.** After every conversation a traffic-light matrix in the interview cockpit: budget,
  scope of the role, chemistry, pay, work model (or your own criteria). One red is a stop signal; the recommendation
  Go / Check / Stop then shows next to the process in the cockpit.
- **Your goal, your band.** Goal ("contract signed") with a date, salary floor and target are set in the setup dialogue
  and stay local.
- **German and English.** Switch the interface bottom left.

## Up and running in five minutes

**Easiest: download an installer.** [Releases](https://github.com/yslop/pitwall/releases/latest) has
`Pitwall-…-mac-arm64.dmg` (Apple Silicon), `…-mac-intel.dmg`, `…-windows-setup.exe` and `…-linux-x64.tar.gz`. They bring
their own Python; nothing to install first. The installers are not signed (yet): macOS asks the first time (right-click →
Open), Windows shows "Windows protected your PC" (→ More info → Run anyway).

**Or with Git and Python 3.9+.** On first start `./pitwall` creates a local `.venv` in the folder and installs three
packages (Jinja2, requests, Beautiful Soup); after that everything runs offline.

```bash
git clone https://github.com/yslop/pitwall.git
cd pitwall
./pitwall                     # Windows: pitwall.cmd
```

The **setup dialogue** opens in your browser on first start (local only, 127.0.0.1). Then open `01_cockpit.html`.
"Start with sample data" loads the fictional person **Alex Muster** with 40 processes and a few memory logs.

## Privacy: governance by design

Everything personal is excluded by `.gitignore`; keys live only in `.env`; "local only" blocks remote AI providers in
code; a leak guard checks every pull request. Details: [PRIVACY.md](PRIVACY.md).

## Contribute and pilot

[CONTRIBUTING.en.md](CONTRIBUTING.en.md) · pilot: [docs/PILOT.en.md](docs/PILOT.en.md) · ideas: GitHub Discussions.

## Licence

Code: [MIT](LICENSE). Pitwall is a project by **XLRTE** (Prasanna Easwarananthan), born out of his own job search.
