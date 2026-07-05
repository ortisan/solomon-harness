# Structured Data

JSON-LD structured data is the page's machine-readable entity layer: it earns rich results, feeds the Knowledge Graph, and is now a primary input for LLM crawlers and answer engines. The stance: ship server-rendered JSON-LD for the types that still pay, keep the entity graph stable across pages, and treat eligibility rules as version-dated facts, not folklore.

## Format and delivery

- JSON-LD only for new work; Microdata and RDFa are maintenance-only legacies. JSON-LD keeps markup out of the visible DOM and is Google's recommended format.
- Server-render the block in the initial HTML. JSON-LD injected client-side (via GTM or a framework effect) is flaky in Google's render queue and completely invisible to non-JS crawlers — which includes most AI/answer-engine bots. This is the single most common structured-data deployment failure.
- Use the schema.org vocabulary; Google's search gallery documentation defines which types earn features and which properties are required versus recommended. Bing and Copilot consume the same markup.
- Mark up only content visible on the page. Invisible or inflated markup (fake reviews, off-page FAQs) is "spammy structured markup" and draws a manual action.

## Types worth shipping in 2026

- `Organization` with `logo`, `url`, and `sameAs` links to Wikipedia/Wikidata/LinkedIn: site identity for the Knowledge Graph and the anchor for entity resolution by LLMs.
- `WebSite` with `name` (controls the site name shown in results). The sitelinks search box was deprecated in late 2024 — remove `potentialAction`/`SearchAction` markup; it earns nothing.
- `BreadcrumbList`: cheap, robust, still rendered in results.
- `Article`/`NewsArticle` with `author` as a `Person` carrying `url` and `sameAs`, plus accurate `datePublished`/`dateModified`. This is the machine-readable E-E-A-T surface: it ties content to a findable author entity.
- `Product` with `Offer` (`price`, `priceCurrency`, `availability`), `AggregateRating`, and `Review` where truthful: required for merchant listing experiences; prices must match the page in real time.
- `LocalBusiness` (NAP, `geo`, `openingHoursSpecification`), `Event`, `VideoObject`, `JobPosting`, `Recipe` where the content genuinely matches.
- `ProfilePage` and `DiscussionForumPosting` for creator and forum content — added by Google in 2023-2024 and consumed by the "forums" surfaces.
- `FAQPage`: since August 2023 the rich result is restricted to authoritative government and health sites; `HowTo` was retired from results in September 2023. For everyone else these types earn nothing in the SERP — ship them only if the semantic value for answer engines justifies the bytes, and never expect the visual result.

## Eligibility is not a guarantee

Valid markup makes a page eligible; Google decides per query, per site, per quality assessment whether to show the feature. Required properties gate eligibility, recommended properties raise the odds, and a site-quality problem can suppress rich results sitewide with zero markup errors. Plan features as probabilities: measure rich-result impressions in GSC before and after, and never promise a stakeholder a guaranteed FAQ/star/product treatment.

## Entity graph and @id discipline

Give every entity a stable, URL-based `@id` and reference it across pages instead of redefining it. Stable IDs let crawlers merge facts into one entity — the same mechanism LLM pipelines use for disambiguation.

```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "@id": "https://www.example.com/blog/inp-guide#article",
  "headline": "A Field Guide to INP",
  "datePublished": "2026-05-11",
  "dateModified": "2026-06-02",
  "author": { "@id": "https://www.example.com/about/jane-doe#person" },
  "publisher": { "@id": "https://www.example.com/#organization" }
}
```

The `#organization` and `#person` nodes are defined once (home page, author page) with their `sameAs` links; every article references them by `@id`. Renaming IDs per deploy shreds the graph.

## Validation tooling

- Rich Results Test (search.google.com/test/rich-results): Google's eligibility verdict, run against the rendered page — this is the gate for feature eligibility.
- Schema Markup Validator (validator.schema.org): pure vocabulary/syntax validation, including types Google ignores.
- GSC enhancement reports: the regression monitor at scale; alerts when a template ships invalid items.
- In CI, per project TDD: snapshot the generated JSON-LD, assert required properties per type, and validate JSON syntax in a unit test, so a template refactor cannot silently drop the block. Both external validators must pass with zero errors before merge.

## Structured data for LLM crawlers (2025-2026)

Answer engines reward the same discipline for different mechanics: GPTBot, ClaudeBot, and PerplexityBot read the raw HTML without executing JavaScript, so server-rendered JSON-LD is often the cleanest factual signal they get — entity names, prices, dates, authorship — and consistent `sameAs`/`@id` graphs measurably reduce entity confusion in generated answers. Keep facts in markup synchronized with visible text so a quoting engine cannot pick up a stale price. The `llms.txt` proposal has no confirmed adoption by major engines; do not trade schema work for it.

## Common pitfalls

- JSON-LD injected client-side, so validators pass locally while AI crawlers and (intermittently) Google see nothing.
- Marking up content that is not on the page, or review stars on a template with no reviews: manual-action bait.
- `Product` price or availability drifting from the visible page because markup is generated from a different data path.
- Shipping `FAQPage`/`HowTo` in 2026 expecting rich results; or keeping deprecated `SearchAction` markup alive.
- Unstable `@id` values regenerated per build, splitting one entity into hundreds.
- Passing the Schema Markup Validator and assuming the rich result is guaranteed; eligibility and quality gates still apply.

## Definition of done

- [ ] JSON-LD is server-rendered in the initial HTML and present in a plain `curl` fetch of the page.
- [ ] Only types matching visible content are shipped; each block carries all required and the truthful recommended properties for its type.
- [ ] Entities use stable URL-based `@id`s; `Organization` and author `Person` nodes are defined once and referenced by `@id`, with `sameAs` links.
- [ ] Rich Results Test and Schema Markup Validator both pass with zero errors; deprecated markup (`SearchAction`, non-eligible FAQ/HowTo expectations) is removed.
- [ ] Markup values (price, availability, dates) are generated from the same data source as the visible page, covered by a unit test snapshot.
- [ ] GSC enhancement reports are checked after deploy; rich-result impressions are tracked as the outcome metric.
