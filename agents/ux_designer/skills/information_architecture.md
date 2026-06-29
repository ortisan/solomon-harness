# Information Architecture

Structure content and navigation so users can find what they need and always know where they are, and validate the structure with card sorting and tree testing before it ships, never by internal consensus. Pick an organization scheme that matches how users think about the content, label everything in the user's language, keep the hierarchy shallow and scannable, and hand a sitemap and navigation model downstream as the IA artifact the frontend implements.

## Choose the organization scheme by how users seek the content

Rosenfeld and Morville split schemes into exact and ambiguous; the choice follows the user's mental model, not the org chart.

- Exact schemes (alphabetical, chronological, geographical) when the user already knows the item's name, date, or place: a staff directory, an archive of releases, store locations. They are unambiguous and need no validation, but they only help known-item lookup — a user who does not know the exact name is stranded.
- Ambiguous (topical) schemes — by topic, by task, by audience — when the user is exploring or does not know the exact label. By topic suits reference content (a help center); by task suits transactional flows ("file a claim", "track an order"); by audience suits sites serving distinct groups (patients versus clinicians) but only when users self-identify cleanly and do not span groups, otherwise they hunt across sections.
- Combine schemes per context rather than forcing one site-wide: a topical primary navigation with a chronological view inside a section is normal. The rule is one dominant scheme per level so the page does not present two competing logics at once.

## Build the taxonomy and label in the user's language

- Labels are the contract between the structure and the user's vocabulary. Use the words users use, sourced from card-sort labels, support tickets, and on-site search-query logs — not internal jargon, product code names, or department names. "Billing" beats "Revenue Operations"; "Help" beats "Customer Success Portal".
- Keep one term for one concept across the whole taxonomy. If the nav says "Orders", the page heading, breadcrumb, and link text say "Orders", never "Purchases" or "My Stuff" elsewhere. Inconsistent synonyms break the user's confidence that they are in the right place.
- Labels and hierarchy are the input the seo agent consumes for indexable structure and metadata; produce them clearly and coordinate, but indexability and metadata ownership stays with seo.

## Navigation patterns and location cues

- Global navigation: the persistent, site-wide primary menu exposing the top-level scheme. It is the single most consequential set of labels because it is the first click on most tasks (see tree testing below).
- Local navigation: sub-navigation within a section, showing siblings and children of the current area.
- Contextual navigation: in-content links to related items, which carry discoverability (below).
- Utility navigation: account, search, settings, sign-in, help — secondary and visually separated, typically grouped away from the primary menu so it does not compete for attention.
- Breadcrumbs: use location breadcrumbs (the item's fixed position in the hierarchy, "Home > Reports > Tax"), not path/history breadcrumbs that mirror how the user arrived, because location breadcrumbs answer "where am I" consistently regardless of entry point. They also give a one-click path back up each level.

## Findability versus discoverability

Both are IA outcomes and they need different structures.

- Findability: a user can locate a known item through navigation or search. It is served by a clean hierarchy, accurate labels, and breadcrumbs, and is what tree testing measures.
- Discoverability: a user encounters relevant content they did not know to look for. It is served by contextual cross-links, related-item lists, and faceted browsing. A structure can be highly findable and poorly discoverable — deep, siloed sections hide adjacent value — so design contextual links deliberately rather than relying on the primary tree alone.

## Validate with card sorting and tree testing

Treat the IA as a hypothesis and test it; the numbers below are the thresholds to plan for.

- Card sorting builds or checks the grouping. Open sort (participants name their own groups) early to generate the taxonomy; closed sort (participants file cards into your fixed categories) to verify a proposed structure. Qualitative insight stabilizes by roughly 15 participants; a quantitative card sort whose agreement scores you intend to report needs roughly 15-30 participants before the cluster-agreement matrix stops shifting with each new participant. Run it with a tool such as OptimalSort.
- Tree testing validates findability on the bare hierarchy (labels only, no visual design) so you measure the structure, not the layout. Score three metrics per task: success (reached the correct node), directness (reached it without backtracking up the tree), and first-click correctness (the first branch chosen was on the correct path). Plan for roughly 50 participants per tree test for stable task-level rates; tools such as Treejack report all three.
- First-click correctness is the lever to optimize. A correct first click is a strong predictor of overall task success — published first-click studies repeatedly show success roughly doubling when the first click lands on the right top-level branch versus a wrong one. Practically: when a task fails, fix the top-level label or its placement before touching anything deeper, because the deeper structure rarely gets exercised if the user never enters the right branch.

## Depth versus breadth

- Prefer shallower, scannable structures over deep ones. Broad-and-shallow hierarchies generally beat narrow-and-deep for findability because each level adds a decision point where the user can choose the wrong branch and the information scent fades.
- "7 plus or minus 2" is a debunked basis for menu length — it came from short-term memory recall of unrelated items, not from scanning a visible, persistent, grouped menu. Users scan menus, they do not memorize them, so a well-grouped list of 12-15 items is fine. Prioritize scannability and clear grouping (labeled clusters, logical order) over an arbitrary item cap. The "three-click rule" is equally unfounded; what predicts success is information scent at each step, not click count.

## The sitemap is the handed-off artifact

- Produce a hierarchical sitemap as the definitive IA deliverable: every node, its exact label, and its parent-child relationships, with the dominant organization scheme noted per level and cross-links called out. This is the structural source of truth.
- The sitemap plus the navigation model (which patterns appear where, and the breadcrumb rule) is the handoff to the frontend agent, which implements the navigation. It is also the input the seo agent maps to its XML sitemap and indexability work — coordinate on labels and hierarchy, but the frontend builds the navigation and seo owns crawl and metadata.

## Common pitfalls

- Organizing by the org chart or by internal feature names instead of user tasks: users do not share the company's mental model, so they cannot predict which section holds their goal.
- Using an audience scheme when users span audiences: a user who is both a buyer and a seller must guess which section applies and ends up checking both, doubling effort.
- Inconsistent labels for one concept across nav, headings, and breadcrumbs: it erodes the user's confidence they are in the right place and inflates perceived complexity.
- Shipping the IA without a tree test, or running a tree test on the designed page instead of the bare tree: the first skips validation entirely; the second measures visual layout, not the structure.
- Treating a wrong first click as a deep-navigation problem: the user never reached the deep levels, so reworking sub-pages fixes nothing — the top-level label is the defect.
- Capping menus at seven items on the strength of "7 plus or minus 2": it forces needless nesting that deepens the tree and lowers findability, trading a non-problem for a real one.
- Path/history breadcrumbs instead of location breadcrumbs: they show how the user arrived, not where they are, so the same item reads differently depending on entry point and stops answering "where am I".
- Claiming indexability or metadata ownership: that is the seo agent's mandate; the IA feeds it labels and hierarchy and stops there.

## Definition of done

- [ ] A dominant organization scheme is chosen per level (exact or ambiguous) and justified by how users seek the content, not by internal structure.
- [ ] Labels use validated user language drawn from card sorts, support tickets, or search-query logs, and one term maps to one concept across nav, headings, and breadcrumbs.
- [ ] The navigation model names which patterns apply where (global, local, contextual, utility) and specifies location breadcrumbs.
- [ ] The taxonomy was validated with a card sort (open then closed; roughly 15-30 participants for any quantitative agreement reported).
- [ ] The hierarchy passed a tree test on the bare tree with success, directness, and first-click correctness recorded (plan roughly 50 participants), and failing top-level labels were fixed before deeper nodes.
- [ ] The structure is shallow and scannable, with grouping prioritized over any fixed item cap, and contextual cross-links added for discoverability.
- [ ] A hierarchical sitemap (every node, exact label, parent-child relationships, scheme per level) plus the navigation model is handed to the frontend agent for implementation and shared with the seo agent for indexability.
- [ ] The IA decisions and validation results are recorded in the project memory so the next session inherits the rationale and the test data.
