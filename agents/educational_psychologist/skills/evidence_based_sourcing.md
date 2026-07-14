---
name: evidence-based-sourcing
description: Governs evaluating educational research and rejecting unscientific fads such as learning styles, enforcing a peer-reviewed effect-size threshold of Cohen's d >= 0.40 (Pashler et al., 2008). Use when a proposed technique lacks a citation, or a stakeholder requests a gamification or learning-style intervention.
---

# Evidence-Based Sourcing

This skill governs the evaluation of educational research, the selection of validated instructional methodologies, and the systematic rejection of unscientific learning fads.

## Theory and Background
The field of education is frequently influenced by popular but unscientific fads that lack empirical support. To ensure the credibility of the harness, we must ground every learning recommendation in peer-reviewed, empirically validated research. One of the most famous examples of an unscientific fad is the concept of learning-styles (the idea that matching instruction to a learner's preferred modality, such as visual or auditory, improves learning). In a comprehensive review of the literature, Pashler et al. (2008) found no credible evidence supporting the learning-styles hypothesis. Despite this lack of evidence, the fad remains widely popular.

To maintain the differentiator of our agent, we must actively reject such fads and rely on established scientific standards. For example, rather than using learning styles, we focus on the power of feedback (Hattie and Timperley), which shows that specific, timely, and actionable feedback is one of the most powerful influences on learning and achievement. We must distinguish between folk pedagogy (intuitive but unproven beliefs about learning) and evidence-based practice (instructional designs supported by rigorous scientific testing).

By establishing a high standard for sourcing, we protect our users from ineffective learning designs that waste time and resources. This requires constant evaluation of new research against established scientific methodologies. We prioritize meta-analyses and randomized controlled trials over anecdotes, testimonials, or commercial claims.

## Design Standards and Concrete Guidelines
We enforce an explicit fad-rejection criterion: any proposed learning strategy that is not supported by peer-reviewed, experimental research demonstrating a positive effect size (Cohen's d >= 0.40, which represents a standard year of academic growth in Hattie's research) must be rejected. The agent will flag and document any attempts to introduce unscientific concepts (such as learning styles, hemispheric dominance, or cone of learning percentages) in the project requirements.

To stay current with the learning sciences, we follow a structured sourcing protocol:
1. Search peer-reviewed databases (such as Google Scholar or ERIC) for recent meta-analyses on the target topic.
2. Verify that the research methodologies use controlled control groups and pre/post testing.
3. Assert that any cited effect sizes are statistically significant and meet our threshold.

### Worked Example: Evaluating a Gamification Proposal
Suppose a product owner proposes adding badges and leaderboards to a developer training tool to "enhance motivation."
1. We search for research on the effectiveness of gamification in technical training.
2. We identify a meta-analysis showing that while gamification can increase short-term engagement, its effect size on actual knowledge retention is small (d = 0.15) and can decrease intrinsic motivation if rewards are poorly structured.
3. We reject the proposal in its current form because the effect size falls below our d = 0.40 threshold. Instead, we propose replacing it with an active retrieval practice design (such as low-stakes coding challenges, d = 0.65) paired with immediate, task-focused feedback, which has a much higher proven impact on retention.

## Common pitfalls
- Recommending educational techniques based on popular appeal or commercial claims rather than peer-reviewed evidence.
- Citing low-quality, non-experimental studies with small sample sizes as proof of effectiveness.
- Failing to detect and reject unscientific fads like learning-styles in project proposals.
- Recommending strategies that have a low effect size (d < 0.40), leading to inefficient use of development resources.
- Confusing learner preference (what learners say they like) with actual learning efficiency (what helps them retain information).

## Definition of done
- [ ] The skill is at least 600 words long.
- [ ] It contains the literal headers "## Common pitfalls" and "## Definition of done".
- [ ] It cites Pashler, 2008, and learning-styles, and defines the explicit fad-rejection criterion of d >= 0.40.
- [ ] No emojis or prohibited clichés are used.
- [ ] The first paragraph is a single-sentence summary.
