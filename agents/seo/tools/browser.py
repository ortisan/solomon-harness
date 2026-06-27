import urllib.request
import urllib.parse


class BrowserClient:
    """A client to simulate web browsing and searching capabilities."""

    def navigate(self, url: str) -> str:
        """Navigates to a specific URL and returns the page content as a string.

        Args:
            url: The destination URL.

        Returns:
            The body or content of the retrieved page.

        Raises:
            ValueError: If the URL is invalid or the request fails.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "SolomonHarness/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode("utf-8", errors="ignore")
                return content
        except Exception as e:
            raise ValueError(f"Failed to navigate to {url}: {e}")

    def search(self, query: str) -> list:
        """Performs a web search for the given query and returns a list of results.

        Args:
            query: The search term.

        Returns:
            A list of dictionary results, each containing 'title', 'url', and 'snippet'.
        """
        if not query.strip():
            return []

        # Create structured mock search results based on the query.
        results = [
            {
                "title": f"Result for {query} - Reference Documentation",
                "url": f"https://example.com/search?q={urllib.parse.quote(query)}",
                "snippet": f"This is a simulated snippet showing search results for: {query}."
            },
            {
                "title": f"Advanced guides on {query}",
                "url": f"https://example.org/docs/{urllib.parse.quote(query)}",
                "snippet": f"Find comprehensive tutorials, API references, and code examples for {query}."
            }
        ]
        return results
