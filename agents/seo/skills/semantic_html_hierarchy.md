## Semantic HTML hierarchy


- Exactly one `<h1>` per page that describes the page's primary topic and matches search intent. Browsers never implemented the HTML5 document-outline algorithm, so heading rank is taken literally. Treat headings as a flat outline.
- Do not skip heading levels. `h1` then `h2` then `h3`. An `h4` directly under an `h1` is a defect.
- Use landmark elements, not `<div>` soup: one `<main>`, plus `<header>`, `<nav>`, `<article>`, `<section>`, `<aside>`, `<footer>`. One `<main>` per page.
- Descriptive link anchor text. No "click here", "read more", or bare URLs as the only anchor. Internal links should carry the target topic in the text.
- Every meaningful image needs an `alt` that describes content or function; decorative images get `alt=""`. Do not keyword-stuff alt text.
- Set `<html lang="...">`. Add `dir` for right-to-left content.
- Keep primary content in server-rendered HTML. Content that appears only after a click, hover, or client-side fetch is content Google may never index.
