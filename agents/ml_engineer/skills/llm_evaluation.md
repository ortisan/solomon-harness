---
name: llm-evaluation
description: Governs how LLM-based applications are evaluated for quality and safety through automated metrics, human rating protocols, LLM-as-judge pipelines, and regression gates. Use when building an evaluation harness for an LLM feature, running an LLM-as-judge comparison, or gating a prompt or model change against a regression suite before release.
---

# LLM Evaluation

This skill governs how LLM-based applications are evaluated for quality and safety, covering automated metrics, human rating protocols, LLM-as-judge pipelines, and the regression gates that block a prompt or model change from shipping. Adapted from the wshobson/agents llm-application-dev plugin (MIT). An LLM application without a versioned evaluation harness is unshippable by the same standard `reproducibility` applies to a trained model: if a quality claim cannot be regenerated from a pinned eval set plus a prompt and model version, it is not a result, it is an anecdote.

## Automated metrics and where they mislead

Surface-overlap metrics (BLEU, ROUGE) count n-gram overlap against a reference and correlate weakly with human quality judgments on open-ended or abstractive generation — they penalize a correct paraphrase as harshly as a wrong answer, so treat them as a cheap regression tripwire, never as the quality bar itself. BERTScore (contextual-embedding similarity) is a better semantic proxy but still carries no groundedness signal: a fluent, on-topic, unsupported answer scores well. Perplexity measures the model's own confidence in a sequence, not task success, and is only meaningful when comparing checkpoints of the same model family. Where the LLM output is effectively a classification (routing, intent, extraction into a fixed label set), score it like any classifier — accuracy, precision/recall/F1, confusion matrix — and hand significance testing on the delta between two configurations to `statistical_modeling` rather than eyeballing a percentage-point gap. Retrieval-quality metrics (MRR, NDCG, Recall@k, Precision@k) measure whether a RAG system found the right evidence; the pipeline that produces that evidence is owned by `rag_implementation`, this skill owns only how its output quality is measured and gated.

## Human evaluation protocol

Fix the rubric before collecting a single rating: faithfulness/accuracy, coherence, relevance, harmlessness, and helpfulness, each on an anchored Likert scale (1-5, with a one-sentence description of what a 2 versus a 4 looks like) rather than left to rater intuition. Compute inter-rater agreement (Cohen's kappa for two raters, Krippendorff's alpha for more) before trusting the ratings; below roughly 0.6, the fix is sharper anchors, not more raters. Size the sample so the confidence interval on the metric of interest is tight enough to decide — a rubric run on 20 examples cannot detect a moderate quality delta; 200-300 is a more realistic floor for a Likert-scale comparison, with the actual test statistics coming from `statistical_modeling`.

## LLM-as-judge: design and bias controls

Pairwise comparison (which of two responses is better) is more reliable than pointwise absolute scoring for close calls, because it removes the judge's need to anchor an absolute scale; use reference-based judging whenever a gold answer exists, since it removes most judge subjectivity, and reserve reference-free judging for genuinely open-ended generation. Use a judge from a different, generally stronger model family than the model under test — a model judging its own family's outputs measurably favors them (self-preference bias). Control position bias by swapping candidate order and averaging or randomizing per item; control verbosity bias by instructing the judge explicitly to ignore length, since judges default to rewarding longer responses independent of quality. Before trusting a judge at scale, calibrate it: score 50-100 items with both the judge and a human rater and report their agreement; recalibrate whenever the judge model version changes, since a judge upgrade silently shifts the scale.

## Regression gates and golden sets

Maintain a versioned golden/eval set, checked into the repository or a tracked artifact, and never use it as a few-shot source or a tuning target — reusing it that way is the same contamination failure `data_leakage_prevention` names for training data, applied to the eval set instead. Gate every prompt or model change in CI against this set: fail the merge if the primary metric regresses beyond a stated tolerance (for example, more than two points on a 100-point rubric, or a statistically significant drop under a paired test), and fail hard, independent of the aggregate score, whenever a previously-passing golden case flips to failing. Track latency (P50/P95) and cost per eval run alongside quality in the same report — a quality improvement that triples latency or cost is a different tradeoff decision, not an automatic ship. Prefer an established harness (promptfoo, DeepEval, Ragas for RAG-specific checks, MLflow's LLM evaluate, or the OpenAI evals format) over a bespoke one, so the eval set stays portable and diffable across runs and reviewers.

## Common pitfalls

- Trusting BLEU or ROUGE as the quality bar for open-ended or abstractive generation, where they penalize valid paraphrases.
- Using a judge model from the same family as the model under test with no calibration check, inflating self-preference.
- No position-swap control in pairwise judging, silently rewarding whichever candidate is shown first.
- Reusing the eval set as a few-shot source or tuning target, contaminating the regression signal.
- Reporting an aggregate score with no per-case regression check, letting a previously-passing case silently break.
- A human rubric with no fixed anchors, producing low inter-rater agreement that gets ignored instead of fixed.
- Ignoring latency and cost in the gate, shipping a quality win that is operationally unusable.

## Definition of done

- [ ] Metric mix matches the task: surface metrics only as a cheap proxy, embedding or semantic metrics for content, judge or human evaluation for open-ended quality.
- [ ] LLM-judge calibrated against a human-labeled sample with agreement reported before trusting it at scale.
- [ ] Position and verbosity bias controlled in pairwise judging.
- [ ] Golden eval set versioned, held out from tuning, and diffed for per-case regressions on every change.
- [ ] Regression-gate thresholds and tolerances stated explicitly and wired into CI.
- [ ] Latency and cost tracked alongside quality in the same report.
- [ ] Human rubric dimensions and anchors documented; inter-rater agreement measured whenever human raters are used.
