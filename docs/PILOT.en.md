# Pilot: Pitwall in one week

Thank you for joining. This week Pitwall is **invite-only**. Afterwards it goes public for everyone, with your
improvements in it. Please do not share the link until then.

Effort: **30 minutes setup**, then **10–15 minutes a day**, and three short check-ins.

## What you get

- A cockpit for a few important applications: pipeline, target date, research order, interview cockpit.
- A structure for your own notes after every interview.
- The weekly-budget idea: fewer applications, done more thoroughly.

## Setup (Mac, Windows, Linux)

1. Install Python 3.9 or newer: <https://www.python.org/downloads/> (Mac: often already there, `python3 --version`).
2. Accept the GitHub invitation (email or <https://github.com/notifications>).
3. Get the repository: green **Code → Download ZIP** button, unzip. Or with Git:
   `git clone https://github.com/yslop/pitwall.git`
4. Start in the folder: Mac/Linux `./pitwall`, Windows double-click `pitwall.cmd`.
5. The setup dialog opens in your browser. Pick Deutsch or English at the top right, keep "demo data" ticked.
6. Connect your AI if you have a Claude, ChatGPT or Gemini subscription. It also works without AI.

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

Every evening of the pilot week the feedback is reviewed and sorted. Anything that blocks setup is fixed right away.
After day 7 there is a summary in the pilot issue (anonymised), then version 0.2.0 and the public release. Contributors
are named in the CHANGELOG if you wish.

## Your data

Everything stays on your computer. Nobody sees your data, not even us. Never send screenshots with real names, companies
or notes; the demo data is enough for every bug report.
