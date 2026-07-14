---
name: technical-seo-audit
description: Defines an ordered, evidence-first technical SEO audit method — crawl, index, render, content, and links in dependency order, with Screaming Frog and GSC tooling, P0/P1/P2 severity triage, and a closed fix-verification loop. Use when running a technical SEO audit, triaging a batch of findings by severity, or verifying a fix with a re-crawl and GSC validation.
---

# Technical SEO Audit Playbook

An ordered, evidence-first audit method: crawl, then index, then render, then content, then links, with severity triage and a closed verification loop. The stance: audit stages in dependency order — every stage's findings can invalidate work downstream, so there is no point polishing content Google cannot crawl — and a finding is only closed by re-measurement, never by a deploy.

## The ordered playbook

1. Crawl. Run Screaming Frog (or Sitebulb) with a config that matches reality: JavaScript rendering enabled if the site needs it, the PSI and GSC APIs connected, sitemaps imported. Capture: 4xx/5xx URLs, redirect chains and loops, canonical targets, duplicate/missing titles and descriptions, missing or multiple `h1`s, hreflang errors, mixed content. Diff the crawl against the sitemap set: URLs in the sitemap but not reachable by links are orphans; URLs crawlable but absent from sitemaps are unmanaged.
2. Index. In GSC Page indexing, compare the indexable set from step 1 against what Google actually indexed. Classify every excluded bucket: "Discovered/Crawled - currently not indexed", "Duplicate", "Soft 404", robots/noindex exclusions. The gap between crawlable and indexed is the audit's core number. The `site:` operator is a sanity probe, not an inventory.
3. Render. For each key template, compare a plain `curl` fetch against URL Inspection's rendered HTML. Confirm the money content, internal links, canonicals, and JSON-LD exist before JavaScript runs — this is also the AI-crawler visibility check, since GPTBot/ClaudeBot/PerplexityBot do not execute JS.
4. Content. Near-duplicate detection (Screaming Frog's similarity hash), thin pages, template-duplicated titles and descriptions, heading-structure defects, and keyword cannibalization from GSC query data (two URLs alternating for one query). Check the E-E-A-T surface: authorship, dates, sources, contact/about pages — the quality inputs that gate both rankings and AI-answer citations.
5. Links. Internal: click depth (money pages within 3 clicks of the home page), orphan elimination, descriptive anchors, internal links pointing at redirects or 404s. External: broken outbound links. On sites past ~100k URLs, add log-file analysis here — it is the only ground truth for where Googlebot actually spends its budget.

## Tooling

- Screaming Frog is the crawler of record: version the crawl config in the repo, run scheduled headless CLI crawls, and export diffable reports so audits compare runs, not memories.
- GSC is the index truth: Page indexing, Sitemaps, Core Web Vitals, manual actions, security issues, and the URL Inspection API for spot checks.
- Lighthouse/PSI/CrUX for performance (field p75 is the verdict; lab is diagnosis).
- Bing Webmaster Tools: cheap second opinion, and Bing's index feeds Copilot answers.
- Log analysis (any log pipeline or Screaming Frog Log File Analyser) for crawl-budget reality on large sites.

## Severity triage

Score each finding as reach (URLs affected) x traffic value x confidence, then bucket:

- P0 — kills indexing sitewide or on a money template: sitewide `noindex`, robots.txt 5xx or `Disallow: /`, canonicals pointing at a staging host, a 5xx spike, sitemap serving the wrong domain. Treat as an incident: fix and verify same day.
- P1 — materially suppresses a section: index-coverage regression on a template, Core Web Vitals "poor" on money pages, hreflang cluster breakage, chained redirects on top landing pages. Schedule within the sprint.
- P2 — hygiene with compounding value: duplicate titles, missing alt text, sub-3-hop redirect chains, orphaned long-tail pages. Batch into backlog issues.

File every finding as its own issue with the evidence attached (crawl export row, GSC screenshot, curl output). One giant "SEO audit" ticket is where findings go to die.

## Fix verification loop

1. Reproduce the finding with the tool that reported it, on a named URL sample.
2. Write the failing test that asserts the corrected output (per project TDD: canonical count, robots directive, heading structure).
3. Fix, review, deploy.
4. URL Inspection live test on the sample; request indexing for the checked URLs.
5. Start "Validate fix" in GSC where a coverage issue exists (validation can take up to 28 days; track it, do not assume it).
6. Re-crawl the affected list with the identical Screaming Frog config and diff against the pre-fix export.
7. Record the outcome and any decision in project memory, and add the regression test to CI so the class of defect cannot silently return.

## Cadence and the AI-crawler check

Full audit quarterly; a delta crawl (changed templates only) before every release; a weekly review of GSC alerts and CrUX movement. After a confirmed Google core update, re-check the money templates against the content and E-E-A-T stages instead of reacting sitewide. Each audit also verifies that robots.txt policy for AI crawlers (GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended) still matches the business's citation-versus-training intent, and samples the top revenue queries for presence and correctness of citations in AI Overviews and answer engines.

## Common pitfalls

- Crawling a 200k-URL site with the default config — no JS rendering, no sitemap import — and declaring it healthy.
- Fixing downstream stages (content tweaks, link sculpting) while a P0 crawl block persists upstream.
- Closing findings on deploy without re-measurement; half of "fixed" canonicals regress at the next template change.
- Using the `site:` operator as an index inventory; it is approximate and unstable.
- Auditing render with view-source instead of rendered HTML, missing everything a framework injects or deletes.
- Skipping log files on large sites, then guessing at crawl-budget waste that the logs state outright.
- Shipping the audit as one monolithic document with no owner, no severity, and no issue per finding.

## Definition of done

- [ ] Crawl, index, render, content, and link stages each produce an evidence-backed findings list, run in that order with a versioned crawl config.
- [ ] The crawlable-vs-indexed gap is quantified from GSC Page indexing, with every exclusion bucket classified.
- [ ] Key templates verified in rendered HTML and in a no-JS fetch (AI-crawler visibility), with diffs recorded.
- [ ] Every finding filed as an individual issue with severity (P0/P1/P2), reach, and attached evidence; P0s resolved same day.
- [ ] Each fix has a covering regression test, a URL Inspection confirmation, a GSC validation started where applicable, and a post-fix re-crawl diff.
- [ ] Audit outcome, decisions, and the next-cadence date recorded in project memory.
