# Expense approval showcase

This example is a committed replay bundle for a reimbursement decision. It covers all three Jev
answer types—Choice, Score, and Noul—and requires no API keys or network access.

From the repository root, run:

```bash
uv run jevcompiler showcase
```

The command validates the task and program, executes the recorded answers, checks the expected
`approve` decision, freezes an immutable artifact, and verifies its file hashes. Generated output
stays under the ignored `.jevcompiler/` workspace unless `--output` selects another destination.

The five replay inputs are:

- `task.yaml`: decision policy, actions, objectives, and safe teacher policy
- `program.yaml`: restricted executable decision graph
- `state.json`: representative expense claim
- `answers.json`: recorded typed Jev response
- `showcase.json`: expected decision and replay metadata
