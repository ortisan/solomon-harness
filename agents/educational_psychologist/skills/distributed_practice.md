---
name: distributed-practice
description: Governs scheduling learning sessions and practice tasks with spacing (Cepeda et al.; Ebbinghaus) and interleaving (Rohrer and Taylor), including the 1/7/30-day review cadence and the three-topic interleaving minimum. Use when designing a multi-day learning or onboarding schedule, or reviewing one for cramming or single-topic blocking.
---

# Distributed Practice

This skill governs the scheduling of learning sessions and practice tasks using spacing and interleaving to optimize long-term memory retention and enhance skill transfer.

## Theory and Background
Spaced repetition is the distribution of learning sessions over time rather than cramming them into a single block. According to research on spacing / distributed practice (Cepeda et al.; Ebbinghaus), expanding the interval between study sessions significantly improves long-term retention. Cramming may produce short-term performance gains, but it leads to rapid forgetting. Spacing allows memory traces to decay slightly before they are retrieved, making the retrieval process more effortful and strengthening the underlying memory schema.

Interleaving is the practice of mixing different topics or problem types within a single study session, rather than studying them in blocked units. According to research on interleaving (Rohrer and Taylor), interleaving forces learners to constantly choose the appropriate strategy for each problem type, rather than applying the same strategy repeatedly without thinking. This improves the learner's ability to select and apply correct schemas in novel contexts, promoting deeper understanding and better skill transfer.

The spacing effect is one of the most robust findings in cognitive psychology, dating back to Ebbinghaus's early memory experiments. It demonstrates that the interval between study sessions should increase as the target retention interval increases. Cepeda et al. showed that there is an optimal spacing interval for any given retention goal, with longer retention goals requiring longer spacing intervals.

## Design Standards and Concrete Guidelines
To implement spacing and interleaving effectively, learning designs must structure practice schedules deliberately. We establish a concrete spacing standard: reviews of core concepts must be scheduled at expanding intervals of 1 day, 7 days, and 30 days after initial exposure to maximize retention. This structured progression aligns with the optimal spacing ratios identified in empirical research.

For interleaving, we enforce a concrete standard: practice sessions must mix at least three distinct topics or problem types, rather than focusing on a single topic. For example, a math practice session should mix addition, subtraction, and multiplication problems rather than presenting them in separate blocks. This forces the learner to actively identify the correct operation for each problem.

### Worked Example: Onboarding Flow Design
When designing a developer onboarding flow for a complex codebase, do not present all documentation and code structure in a single week-long block. Instead, space the introduction of different modules. Introduce the core database client on day one, and ask the developer to run a basic query. On day three, review the database client and introduce the API routes, asking them to write a simple endpoint. On day seven, review both database and API routes and introduce the UI components.

Throughout this flow, interleave the practice tasks. Instead of giving five consecutive database tasks, give a database task, followed by a UI task, followed by an API task. This forces the developer to switch contexts and retrieve the appropriate schemas for each task, leading to a more robust understanding of the entire system architecture.

## Common pitfalls
- Block-practicing a single topic for an entire session, which creates a false sense of mastery and rapid decay of memory.
- Designing study schedules that rely on cramming immediately before an assessment, leading to quick forgetting.
- Failing to schedule review sessions at expanding intervals, resulting in the loss of critical knowledge over time.
- Presenting interleaved practice without explaining the relationships between the mixed topics, confusing the learner.
- Providing too much spacing between initial learning and the first review, causing complete forgetting and requiring re-teaching.

## Definition of done
- [ ] The skill is at least 600 words long.
- [ ] It contains the literal headers "## Common pitfalls" and "## Definition of done".
- [ ] It cites spacing / distributed practice (Cepeda et al.; Ebbinghaus) and interleaving (Rohrer and Taylor) and provides concrete standards (such as the 1/7/30 spacing interval and the three-topic interleaving minimum).
- [ ] No emojis or prohibited clichés are used.
- [ ] The first paragraph is a single-sentence summary.
