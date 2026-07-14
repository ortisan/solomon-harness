---
name: backward-design
description: Governs planning learning programs with backward design (Wiggins and McTighe) and constructive alignment (Biggs), starting from desired results and evidence before designing activities. Use when planning an instructional module, training guide, or onboarding flow, or reviewing one where objectives came after the content.
---

# Backward Design

This skill governs the planning of learning programs and instructional materials by starting with the desired results, determining acceptable evidence of learning, and then designing the learning experiences.

## Theory and Background
Traditional lesson planning often starts with activities or content, leading to learning experiences that lack clear focus or purpose. According to the framework of backward design / Understanding by Design (Wiggins and McTighe), we must reverse this process. Planning begins by identifying what learners should know and be able to do at the end of the instruction. Only after defining these desired results do we determine how we will measure if they have been achieved. Finally, we design the instructional activities.

A key component of this approach is constructive alignment (Biggs). This theory asserts that the learning activities, the learning objectives, and the assessment tasks must be directly aligned with each other. If the learning objective is to write functional Python code, the assessment must require writing code, and the learning activities must practice writing code. If the assessment consists of a multiple-choice test on syntax, the alignment is broken, and the instruction fails to support the target learning outcome.

Backward design ensures that every activity and resource in a learning program directly supports a specific, measurable learning objective. This eliminates fluff and keeps the learner focused on what matters. It also helps designers identify what is nice to know versus what is essential to know, ensuring that working memory resources are dedicated to the core objectives.

## Design Standards and Concrete Guidelines
To implement backward design and constructive alignment, instructional planning must follow a three-stage sequence:
1. Identify desired results (what should the learner know or be able to do).
2. Determine acceptable evidence (how will we measure this ability).
3. Plan learning experiences and instruction (what activities will help them learn).

We establish a concrete standard: before any instructional text, slide, or video is created, the designer must define the target learning objectives using measurable verbs (such as write, analyze, or debug, avoiding vague verbs like understand or know) and create the rubric or assessment task. This rubric must list the specific criteria for success, and it must be documented before the learning activities are designed.

### Worked Example: Designing a Unit on Version Control
When designing a training module on git version control, we do not start by writing a slideshow about the history of git.
Stage 1 (Desired Results): The learner will be able to create a branch, stage changes, commit them with a Conventional Commits message, and push the branch to a remote repository.
Stage 2 (Evidence): The learner will create a local repository, make a change, create a branch named `feature/test-branch`, commit the change with a message starting with `feat:`, and push it to a mock origin. We write the automated verification script that checks these exact conditions.
Stage 3 (Learning Plan): We write the tutorial that guides the learner through the git commands required to complete the task. The tutorial focuses exclusively on these commands and does not include unnecessary details about git internal database design, keeping cognitive load low.

## Common pitfalls
- Designing instructional activities before defining the target learning objectives or how they will be assessed.
- Creating assessments that do not match the cognitive level of the learning objectives, breaking constructive alignment.
- Including excessive background information or "nice to know" content that does not support the core learning objectives, overloading the learner.
- Using vague, unmeasurable verbs (such as understand or learn) in the learning objectives, making assessment difficult.
- Designing high-stakes assessments without providing sufficient practice and formative feedback during the learning phase.

## Definition of done
- [ ] The skill is at least 600 words long.
- [ ] It contains the literal headers "## Common pitfalls" and "## Definition of done".
- [ ] It cites backward design / Understanding by Design (Wiggins and McTighe) and constructive alignment (Biggs) and provides concrete standards (such as the three-stage sequence and the requirement to write the rubric before instructional content).
- [ ] No emojis or prohibited clichés are used.
- [ ] The first paragraph is a single-sentence summary.
