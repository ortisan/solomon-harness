## Page-level standards


- Title is a noun phrase (reference/explanation) or a task in imperative or gerund form (how-to: "Rotate API keys", "Configuring TLS").
- Every page carries front matter metadata: `owner`, `status` (draft/reviewed/deprecated), `last_reviewed` (ISO date), and the product version or commit it was validated against.
- One H1 per page. Heading depth no greater than H4. Sections short enough to scan.
- Procedures are numbered steps, one action per step, with the expected result stated after steps that produce visible output.
- Every command and code block is copy-pasteable and tested. Show real, runnable examples, not `<placeholder>` soup; when placeholders are unavoidable, define each one immediately below the block.
- Use semantic line breaks (one sentence or clause per line) in source. It keeps diffs reviewable and review comments precise.
- Provide alt text for every image and diagram. Store diagram source (Mermaid, PlantUML, or Structurizr DSL), not only the exported PNG, so diagrams are diffable and editable.
