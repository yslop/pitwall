# Pilot: Pitwall in one week

Thank you for testing. The first pilot week was invite-only; Pitwall is now open, and feedback is still the most valuable
thing you can contribute. Feel free to share the link.

Effort: **30 minutes setup**, then **10–15 minutes a day**, and three short check-ins.

## What you get

- A cockpit for a few important applications: pipeline, target date, research order, interview cockpit.
- A structure for your own notes after every interview.
- The weekly-budget idea: fewer applications, done more thoroughly.

## Setup (Mac, Windows, Linux)

1. **Easiest:** download the installer for your system from <https://github.com/yslop/pitwall/releases/latest>
   (`.dmg` for Mac, `-setup.exe` for Windows) and run it. No Python needed.
2. **Or with Python 3.9+:** green **Code → Download ZIP** button, unzip, or `git clone https://github.com/yslop/pitwall.git`.
3. Start in the folder: Mac/Linux `./pitwall`, Windows double-click `pitwall.cmd`.
4. The setup dialog opens in your browser. Pick Deutsch or English at the top right, keep "demo data" ticked.
5. Connect your AI if you have a Claude, ChatGPT or Gemini subscription. It also works without AI.

## The pilot week

| Day | What you do | Feedback |
|---|---|---|
| 1 | Set up, click around with the demo data | **Check-in 1:** `./pitwall feedback` |
| 2–3 | Remove the demo data (`python3 demo/load_demo.py --remove`), add two or three of your own processes | **Check-in 2** on day 3 |
| 4–6 | Use it daily, note anything odd as an issue right away | Bugs and ideas any time |
| 7 | Look back: what should be better before the public release? | **Check-in 3 (closing)** |

## How to give feedback

`./pitwall feedback` (Windows: `pitwall.cmd feedback`) writes a short summary of counts and settings: version, system,
language, type of AI connection, how many days you used it. **No names, companies, notes, questions or keys.** It is saved
in `feedback/` and opens the pilot form on GitHub, already filled in. You read it, change it if you like, then submit.
Nothing is sent automatically.

- **Bugs:** *Issues → Bug report*. Please reproduce with the demo data, never with your real data.
- **Ideas and questions:** *Discussions*.
- **Improve it yourself:** issues labelled `good first issue`; a pull request is enough, see [CONTRIBUTING.en.md](../CONTRIBUTING.en.md).

## What happens with your feedback

Feedback is reviewed and sorted regularly. Anything that blocks setup is fixed first. Contributors are named in the
CHANGELOG if you wish.

## Your data

Everything stays on your computer. Nobody sees your data, not even us. Never send screenshots with real names, companies
or notes; the demo data is enough for every bug report.
