---
trigger: model_decision
description: "Apply when writing code that calls a large language model or embedding model to extract, classify, summarise or match information from documents or records."
---
 
# LLM extraction and matching rules
 
## Determinism and versioning
- Temperature 0 (or the provider's most deterministic setting). Fix and log the exact model identifier.
- Prompts live in `pipeline/prompts/<task>/<name>_v<N>.md`. Never edit a released prompt version; create v<N+1>.
- Every output row stores `model`, `prompt_version`, `run_id` and a timestamp.
## Structured output
- Define the output schema as a pydantic model. Request JSON that matches it. Validate every response.
- On validation failure: retry once with the validation error appended; if it fails again, store the raw response with status `invalid` and move on. Never repair outputs by guessing.
- Store raw model responses under `data/interim/llm_raw/<task>/<run_id>/`.
## Grounding
- Every extracted item must carry the exact supporting text span (quote) from the source document and its location (page or character offsets).
- If the supporting text is not found verbatim in the document, mark the item `unsupported`. It must not be used downstream.
- The model must be instructed to return "not stated" rather than infer. Values the document does not state are null.
## Verification status (required field)
One of: `unverified` (default), `auto_validated` (passed programmatic checks), `human_verified`, `rejected`, `unsupported`, `invalid`. Only `human_verified` items may be shown on the public site as statements about a named person.
 
## Evaluation
- Each extraction or matching task has a hand-labelled gold set in `eval/<task>/gold.*`. Report precision and recall against it in the handoff.
- Never tune prompts on the gold set's test split. Keep a dev split for iteration.
## Cost and safety
- Estimate token usage and cost on a small sample before any full run; report the estimate and wait for the user's go-ahead if it exceeds the budget in the brief.
- API keys come from `.env` only. Never log or print them.
- Do not send documents containing personal data beyond the public role (for example, asset declarations) to a model unless the brief explicitly allows it.
 
