# Prompt Rewrite Task

Attached: `all_prompts_inventory.json` — every LLM prompt in the workbench
codebase, with file path, line range, variable name, role, and full text.

Rewrite each prompt. Output this exact format for every entry:

```
=== PROMPT ID: <id> ===
FILE: <file_path> (lines <line_numbers>)
REWRITTEN:
<text>
=== END ===
```

## Rules

1. Remove "You are an expert X" openings. State the task directly.
2. Be concise. The model is capable.
3. Where JSON output is expected, embed the schema in the prompt.
4. Where analysis is requested, add "Think step by step before answering."
5. For judgment tasks, ask the model to express confidence and flag uncertainty.
6. Preserve template variables (e.g. `{body.topic}`) unchanged.
7. For citizen/ German legal prompts: add explicit "do not give legal advice,
   do not invent citations, say when you don't know" instructions.
8. Do not change the role (system/user).
