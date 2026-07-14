---
name: semantic-html-hierarchy
description: Governs markup as the extraction contract — single-h1 heading outlines with no skipped levels, landmark elements (main, nav, article, section), semantic elements over div soup, and the accessibility overlap with WCAG 2.2 AA. Use when structuring a page template's headings and landmarks, reviewing markup for crawler and screen-reader extraction, or fixing a heading or landmark violation.
---

# Semantic HTML Hierarchy

Markup is the extraction contract: headings, landmarks, and semantic elements are how search engines, assistive technology, and LLM crawlers segment a page into meaning. The stance: structure is written for machines that cannot see the layout — if the hierarchy only makes sense visually, it does not exist.

## Heading outline rules

- Exactly one `<h1>` per page, describing the page's primary topic and matching the search intent the page targets. The HTML5 document-outline algorithm (which would have scoped headings per `<section>`) was never implemented by any browser and was removed from the WHATWG spec in 2022, so heading rank is read literally as one flat outline.
- Never skip levels downward: `h1` then `h2` then `h3`. An `h4` directly under an `h1` is a defect. Moving back up any number of levels is fine.
- Headings mark structure, not style. If a design needs smaller text, restyle the correct level with CSS; picking `h4` for its font size corrupts the outline.
- Headings are chunk boundaries. Google's passage ranking and LLM retrieval pipelines both segment content by heading; a section whose heading states the question it answers ("How long does a refund take?") is the unit that gets cited in AI Overviews and answer engines. Vague headings ("More information") produce unquotable chunks.
- Write heading text as standalone descriptions: each `h2` should make sense read in isolation in an outline view, because that is exactly how screen-reader users and extraction pipelines consume them.

## Landmark elements

Landmarks let machines separate content from chrome — the difference between boilerplate and the part worth indexing.

- Exactly one `<main>` per page, wrapping the unique content. Top-level `<header>` and `<footer>` map to the `banner` and `contentinfo` roles.
- Multiple `<nav>` elements need distinguishing labels: `<nav aria-label="Primary">`, `<nav aria-label="Breadcrumb">`.
- `<article>` is for self-contained, independently distributable units (a post, a product card, a comment). `<section>` groups related content and only becomes a labeled region when it has an accessible name (`aria-labelledby` pointing at its heading). `<aside>` holds complementary material.

```html
<body>
  <header>site chrome</header>
  <nav aria-label="Primary">...</nav>
  <main>
    <article>
      <h1>The only h1</h1>
      <section aria-labelledby="specs">
        <h2 id="specs">Specifications</h2>
        ...
      </section>
    </article>
  </main>
  <footer>legal, secondary nav</footer>
</body>
```

## Semantic elements vs div soup

The element choice is machine-readable behavior, and crawlers exploit it:

- Navigation must be `<a href>`. Crawlers only follow real links; a `<div onclick>` or a JS `router.push` without an `href` is navigation that does not exist for Googlebot, produces no crawl path, and fails keyboard users. `<button>` is for actions, `<a>` for destinations.
- Lists are `<ul>`/`<ol>`, tabular data is `<table>` with `<th scope>` — tables are a top source for direct-answer extraction. Key-value specs fit `<dl>`.
- `<time datetime="2026-07-04">` makes dates machine-readable for freshness signals; `<figure>`/`<figcaption>` binds an image to its explanation; `<blockquote cite>` attributes quotations.
- Content hidden in the DOM (accordions, `<details>`/`<summary>`, tabs) is indexed under mobile-first indexing; content fetched only after a click, hover, or scroll event is not. Ship it in the initial DOM or accept that it is invisible.
- Descriptive anchor text: internal links carry the target's topic ("Core Web Vitals thresholds", not "click here" or a bare URL). Anchor text is both a ranking signal for the target and WCAG 2.4.4 compliance.

## Accessibility overlap

Semantic SEO and accessibility are the same work billed twice; the target is WCAG 2.2 level AA.

- Every meaningful image gets an `alt` describing content or function; decorative images get `alt=""` so AT skips them. Keyword-stuffed alt text harms both audiences.
- Set `<html lang="en">` (and `dir="rtl"` where applicable); it drives screen-reader pronunciation, translation, and language detection.
- The heading outline and landmarks above are exactly what screen-reader rotor navigation uses, and what an audit tool (axe, Lighthouse accessibility pass) verifies mechanically — so the assertions belong in unit tests: parse the rendered template, assert one `h1`, no skipped levels, one `main`, labeled `nav`s.
- E-E-A-T surface: visible author bylines, dates, and citations marked up with real elements (`<address>`, `<time>`, links to sources) are the on-page evidence both quality raters and answer engines look for.

## Common pitfalls

- Two `<h1>`s because the logo and the page title both use one; the topic signal blurs and the outline breaks.
- Skipped heading levels from copying a component styled as `h5` into an `h2` context.
- Click-handler divs as navigation: no crawl path, no keyboard access, no link equity flow.
- Landmark-free pages where extraction cannot separate boilerplate from content, diluting what gets indexed and quoted.
- Generic headings ("Overview", "More info") that produce unquotable chunks for passage ranking and AI answers.
- Primary content rendered only after user interaction or a client-side fetch — permanently unindexed.
- `section` used as a styling wrapper hundreds of times, adding noise instead of structure.

## Definition of done

- [ ] Exactly one `<h1>` that states the page topic; no skipped heading levels; verified by an automated parser test, not by eye.
- [ ] One `<main>`; top-level `<header>`/`<footer>`; every `<nav>` labeled; sections that act as regions have accessible names.
- [ ] All navigation uses `<a href>` with descriptive anchor text; buttons and links are not interchanged.
- [ ] Data uses the semantic element that matches it: tables for tabular data, lists for lists, `<time datetime>` for dates.
- [ ] Images carry correct `alt` values (empty for decorative); `<html lang>` is set; the page passes an axe or Lighthouse accessibility check with no heading/landmark violations.
- [ ] Primary content, including collapsed sections, is present in the initial DOM and visible in the URL Inspection rendered HTML.
