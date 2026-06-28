## Structured data


- Use JSON-LD. It is Google's recommended format and keeps markup out of the rendered DOM. Avoid Microdata and RDFa for new work.
- Use the schema.org vocabulary and only the types that match visible page content. Marking up content that is not on the page is a spam signal and can trigger a manual action.
- Common, eligibility-bearing types: `Organization` and `WebSite` (site identity), `BreadcrumbList` (breadcrumb trail), `Article` / `NewsArticle`, `Product` with `Offer` and `AggregateRating`, `Recipe`, `Event`, `VideoObject`, `LocalBusiness`. Fill all required and as many recommended properties as the page truthfully supports.
- Know the current eligibility rules: `FAQPage` and `HowTo` rich results were heavily restricted in 2023 (FAQ is limited to authoritative health and government sites; HowTo was retired from results), and the `WebSite` sitelinks search box was deprecated in late 2024. Mark up only what can actually win a result.
- Validate every block with the Rich Results Test (search.google.com/test/rich-results) for eligibility and the Schema Markup Validator (validator.schema.org) for syntax. Both must pass with zero errors before merge.
- Keep `@id` references stable so entities link across pages (for example, the same `Organization` `@id` referenced from `Article.publisher`).
