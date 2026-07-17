---
name: prompt-engineering-patterns
description: Governs how prompts and their surrounding context are structured for reliability - system and role composition, few-shot example selection, chain-of-thought elicitation, tool-use prompting, and structured-output enforcement. Use when designing or debugging a prompt template, selecting few-shot examples, writing a tool-calling system prompt, or enforcing a structured JSON or schema response format.
---

# Prompt Engineering Patterns

This skill governs how prompts and the context around them are structured for reliable, controllable LLM behavior, covering system and role composition, few-shot example selection, chain-of-thought elicitation, tool-use prompting, and structured-output enforcement. Adapted from the wshobson/agents llm-application-dev plugin (MIT). A prompt is a versioned artifact with measurable behavior, not a string tuned by feel — every pattern here earns its place by moving a specific, checkable failure mode, and is retired the moment the eval harness stops showing it is worth its added complexity.

## System and role structure

Put stable instructions — role, constraints, output format, safety boundaries — in the system slot, and variable task content in the user turn; do not bury the output-format instruction in the middle of a long system prompt. As with a long RAG context, models attend most reliably to the start and end of a long prompt, so state the output contract at the top and repeat the hard constraint at the bottom as a checksum. Keep the system prompt declarative — what the assistant is and must never do — rather than a running commentary of hedges and disclaimers; a system prompt padded that way measurably raises the refusal and hedging rate on legitimate requests, because the model treats the hedging tone as a cue about how cautious to be.

## Few-shot example selection

Example count trades off against context budget with diminishing returns: three to five well-chosen examples usually outperform twenty generic ones. Select by semantic similarity to the current input when task inputs are heterogeneous — embed the input, retrieve the nearest labeled examples from a small curated bank — and deliberately add one diverse or edge-case example a pure nearest-neighbor pass would never surface, to cover boundary behavior. Order matters because of recency bias: the example shown last has outsized influence on the output, so place the example closest to the target behavior last, not first. Never construct a few-shot example for a boundary case whose correct output has not actually been verified — a wrong worked example teaches the wrong behavior with more authority than a plain instruction would, because the model treats a demonstration as ground truth.

## Chain-of-thought and self-consistency

Zero-shot chain-of-thought ("show your reasoning before answering") reliably improves multi-step arithmetic, logic, and planning tasks, at the cost of added latency and tokens; it does not help simple lookup or classification tasks, so apply it where the task actually decomposes into steps, not as a default. Few-shot CoT — worked reasoning traces in the examples, not just input-output pairs — transfers the reasoning style along with the answer format. Self-consistency samples k (typically 5-10) independent reasoning paths at nonzero temperature and takes the majority-vote answer; it reliably beats single-sample greedy decoding on tasks with a checkable answer, at k times the inference cost, so reserve it for requests where correctness is worth paying for — a regression-gated evaluation run, for instance, not every production call. Do not conflate "the model produced a plausible chain of reasoning" with "that reasoning caused the answer" — models sometimes emit a trace disconnected from how the answer was actually produced, so spot-check that the chain's logic and the final answer agree before trusting the pattern on a new task.

## Tool-use and structured-output prompting

For tool-calling, the tool's name, description, and parameter schema function as part of the prompt: an ambiguous parameter description causes wrong-argument calls as often as an ambiguous instruction does. Write tool descriptions the way a docstring is written for a developer who cannot ask a follow-up question — units, example arguments, and the boundary of what the tool does and does not cover. Keep the tool list short and non-overlapping; two tools with fuzzy boundary conditions produce systematic misrouting no prompt wording fixes, because the ambiguity lives in the tool design, not the prompt. For structured output, prefer the model's native schema-constrained decoding or tool-calling path over asking for "JSON" in prose and parsing the result afterward — a schema-enforced call cannot emit an unparseable response, while prose-requested JSON periodically wraps itself in markdown fences, adds commentary, or truncates near the token limit. Where schema enforcement is unavailable, validate every response against the schema (Pydantic or equivalent), and treat a validation failure as a first-class error path with a retry, not a silently accepted default.

## Iteration discipline

Version every prompt template like code: store it with the model name and version it was tuned against, since the same prompt string is not the same prompt across model versions. Change one variable at a time — wording, example set, or chain-of-thought scaffold — and measure the change against the eval harness owned by `llm_evaluation` before rolling it forward; a prompt change that "feels better" across a handful of manual tries is not evidence. Do not add an instruction to fix a failure that has not been reproduced in the eval set — an unverified fix grows prompt length without a checkable effect, and it eventually collides with another instruction added the same way.

## Common pitfalls

- Output-format instructions buried in the middle of a long system prompt, ignored due to positional attention bias.
- Few-shot examples chosen for topical similarity alone, missing the edge case that actually breaks the model.
- Chain-of-thought applied uniformly regardless of task shape, paying latency and token cost on lookups that never needed it.
- Self-consistency sampling treated as free extra safety instead of a costed choice made only where correctness is worth k times the inference spend.
- A verbose, hedge-filled system prompt that raises the refusal rate on legitimate requests.
- Requesting "JSON" in prose instead of schema-constrained or tool-calling output, then hand-patching markdown fences out of the response.
- Prompt edits deployed on a "feels better" basis with no eval-harness measurement, masking regressions nobody eyeballed.
- Tool descriptions written for the implementer's mental model instead of a naive caller, causing systematic wrong-argument calls.

## Definition of done

- [ ] System/user content separated along the stable-instruction versus variable-content boundary; output contract stated at both ends of a long prompt.
- [ ] Few-shot examples selected for relevance plus one deliberate edge case, ordered with the most relevant example last.
- [ ] Chain-of-thought applied only where the task decomposes into verifiable steps; self-consistency budget justified against its k-times cost.
- [ ] Tool schemas carry unambiguous descriptions and non-overlapping scope.
- [ ] Structured output enforced via schema or tool-calling where available; validated and retried where not.
- [ ] Every prompt is version-controlled with the model version it was tuned against.
- [ ] Prompt changes measured against `llm_evaluation`'s regression harness before rollout, not judged by manual spot check.
