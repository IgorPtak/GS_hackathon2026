# LLM runbook normalization: model comparison

How well do models turn runbooks written by non-technical people (typos, Polish/English mix, steps
buried in prose, vague verbs, "ask Bob") into validated `RunbookStep` lists? Set: 12 runbooks in
`scripts/eval_runbooks/` with expected steps. Endpoint: PSNC OpenAI-compatible API, `json_schema`
output, temperature 0, client cache off. Reproduce:
`uv run python scripts/eval_runbook_llm.py --models <ids> --runs 3`.

Columns: valid = output passed Pydantic and `validate_llm_steps` (no fallback); precision/recall of
action ids; approval = correct `requires_approval` on matched actions; exact kinds = same step-kind
sequence as expected (strict: merging or splitting a prose step counts as a miss).

## All models, 1 run each (12 runbooks), 2026-11-20

| Model | Valid | Precision | Recall | Approval | Exact kinds | p50 s | p90 s |
|---|---|---|---|---|---|---|---|
| DeepSeek-V4.1-Flash | 100% | 1.00 | 1.00 | 1.00 | 0.75 | 1.5 | 1.9 |
| Qwen3.8-27B | 100% | 1.00 | 1.00 | 1.00 | 0.75 | 5.1 | 5.5 |
| Qwen3.5-397B-A17B | 100% | 1.00 | 1.00 | 1.00 | 0.42 | 3.5 | 4.1 |
| gpt-oss_120b | 100% | 1.00 | 1.00 | 1.00 | 0.00 | 4.7 | 5.7 |
| DeepSeek-V4-Flash | 100% | 1.00 | 1.00 | 0.96 | 0.25 | 1.7 | 2.4 |
| GLM-5.1 | 100% | 0.94 | 1.00 | 1.00 | 0.25 | 5.6 | 6.8 |
| GLM-5.2 | 100% | 0.92 | 1.00 | 1.00 | 0.25 | 8.5 | 11.9 |
| GLM-5.3-Flash | 92% | 0.97 | 1.00 | 1.00 | 0.64 | 14.6 | 27.0 |
| Bielik-11B-v3.0-Instruct | 100% | 0.85 | 0.92 | 0.93 | 0.00 | 4.5 | 5.4 |
| GLM-5.3 | 0% | — | — | — | — | 30.1 (timeout) | 30.1 |

## Top three, 3 runs each (36 normalizations per model)

| Model | Valid | Precision | Recall | Approval | Exact kinds | p50 s | p90 s |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B | 100% | 1.00 | 1.00 | 1.00 | 0.75 | 5.1 | 5.5 |
| DeepSeek-V4.1-Flash | 100% | 0.99 | 1.00 | 1.00 | 0.69 | 1.9 | 2.4 |
| Qwen3.5-397B-A17B | 100% | 1.00 | 0.99 | 1.00 | 0.42 | 3.3 | 4.2 |

Takeaways: Qwen3.8-27B is the most stable (identical scores over three runs). DeepSeek-V4.1-Flash is
nearly as accurate at about a third of the latency. Approvals forced by action config
(`approval: required`) are always enforced by `validate_llm_steps`, whatever the model returns.
GLM-5.3 did not answer within the 30 s client timeout.
