## Readability and style


- Follow one style guide and enforce it: Google developer documentation style guide or the Microsoft Writing Style Guide. Pick one per project and do not mix.
- Target US grade 8 to 10 readability (Flesch-Kincaid). Average sentence under 25 words. Prefer active voice and present tense ("the service returns", not "the service will return").
- Second person ("you") for instructions. Define every acronym on first use. Maintain a project glossary and link to it.
- Lint prose in CI: Vale with a style package (Google/Microsoft), plus `markdownlint` for structure. Run `lychee` or `markdown-link-check` to fail the build on broken links.
- Honor the project humanizer rules: direct, concise, senior-engineer tone. No emojis or icons. Ban the cliches listed in the workspace rules (delve, leverage, testament, dive into, feel free, in summary, moreover, firstly, secondly, lastly). Add them to the Vale vocabulary as errors.
