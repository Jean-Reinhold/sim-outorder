# OpenCode Project Configuration

This directory follows OpenCode's per-project configuration layout.

```text
.opencode/agents/experiment-analyst.md      Subagent that runs/interprets sim-outorder experiments
.opencode/commands/analyze-experiments.md   Slash command that invokes the subagent
```

Use the command from OpenCode:

```text
/analyze-experiments
```

The command intentionally delegates to a subagent so the primary conversation is not filled with the full experiment-analysis context. The subagent may run the existing experiment scripts, inspect generated JSON/CSV/logs, and update only `reports/conclusions.md` with measured conclusions.
