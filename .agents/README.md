# Agent Workflows

This folder contains human-readable tasks for agents that work on this repository. These tasks are intentionally not executable scripts. The intent is to have an agent run the existing experiment scripts, inspect the generated data and logs, reason about the architecture behavior, and write conclusions that can be included in the HTML report.

Use these prompts when the repo already has a working Docker and experiment setup:

```text
.agents/experiment-analyst.md       Main task for analyzing results and writing conclusions
.agents/experiment-rationale.md     Explanation of what each assignment experiment is testing
```

The expected agent-authored output is:

```text
reports/conclusions.md
```

`scripts/generate_report.py` reads `reports/conclusions.md` when present and embeds it in the static report as the "Interpretacao Agentica" section.
