import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from browser_agent.search import WebSearcher, SearchResult, SearchError


class WebsiteResolutionError(ValueError):
    """Raised when a website name cannot be resolved to a reliable URL."""
    pass


# Domains that are typically aggregators, social media, or encyclopedias
NON_OFFICIAL_DOMAINS = {
    "wikipedia.org",
    "wikimedia.org",
    "wikidata.org",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "reddit.com",
    "crunchbase.com",
    "pitchbook.com",
    "bloomberg.com",
    "reuters.com",
    "forbes.com",
    "techcrunch.com",
    "theverge.com",
    "medium.com",
    "quora.com",
    "glassdoor.com",
    "pinterest.com",
    "tiktok.com",
}


def _extract_target_entity(raw_input: str) -> str:
    """
    Strips conversational action phrases to isolate the brand or entity name.
    """
    cleaned = raw_input.strip()
    lower = cleaned.lower()

    prefixes = [
        "open the official website of the ",
        "open the official website of ",
        "open official website of the ",
        "open official website of ",
        "the official website of the ",
        "the official website of ",
        "official website of the ",
        "official website of ",
        "open the website of the ",
        "open the website of ",
        "open website of the ",
        "open website of ",
        "the website of the ",
        "the website of ",
        "website of the ",
        "website of ",
        "open the ",
        "open ",
        "go to ",
        "navigate to ",
        "visit ",
    ]

    for prefix in prefixes:
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            lower = cleaned.lower()
            break

    # Strip trailing filler words
    for suffix in [" official website", " website"]:
        if lower.endswith(suffix):
            cleaned = cleaned[:-len(suffix)].strip()
            lower = cleaned.lower()
            break

    return cleaned


def _score_candidate(candidate: SearchResult, target: str) -> float:
    """
    Scores how likely a search result URL represents the official website for target.
    """
    url = candidate.url.strip()
    if not url:
        return -100.0

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    path = parsed.path.lower()

    target_tokens = [w for w in re.findall(r"\w+", target.lower()) if len(w) > 1]
    if not target_tokens:
        return 0.0

    primary_brand = target_tokens[0]

    # Penalize aggregators, social networks, and encyclopedias
    is_blacklisted = any(domain == b or domain.endswith("." + b) for b in NON_OFFICIAL_DOMAINS)
    if is_blacklisted:
        if primary_brand not in domain:
            return -50.0

    score = 0.0

    # 1. Domain match with primary brand name
    if primary_brand in domain:
        score += 25.0
        domain_parts = domain.split(".")
        if domain_parts[0] == primary_brand:
            score += 15.0

    # 2. Secondary token match (e.g. country code)
    for sec_token in target_tokens[1:]:
        if sec_token in domain or sec_token in path:
            score += 10.0
        elif sec_token == "india" and (domain.endswith(".in") or "/in" in path):
            score += 15.0

    # 3. Path simplicity
    if path in ("", "/", "/in", "/in/", "/en", "/en/"):
        score += 10.0
    elif len(path.strip("/").split("/")) > 2:
        score -= 10.0

    # 4. Title cues
    title_lower = candidate.title.lower()
    if primary_brand in title_lower:
        score += 5.0
    if "official" in title_lower or "home" in title_lower:
        score += 5.0

    # 5. Factor in search relevance score
    score += candidate.score * 5.0

    return score


class WebsiteResolver:
    """
    Resolves website names or user requests to URLs.
    First checks deterministic known-site mappings, then falls back to WebSearcher.
    """

    MAPPING: Dict[str, str] = {
        "amazon": "https://www.amazon.in",
        "github": "https://github.com",
        "google": "https://www.google.com",
        "openai": "https://openai.com",
    }

    def __init__(
        self,
        mapping: Optional[Dict[str, str]] = None,
        searcher: Optional[WebSearcher] = None,
    ):
        self.mapping = mapping if mapping is not None else dict(self.MAPPING)
        self.searcher = searcher or WebSearcher()

    def resolve(self, site_name: str) -> str:
        """
        Resolves a website name or instruction to an official URL.
        1. Check known mapping
        2. If found -> return URL
        3. If not found -> use search
        4. Inspect search results and select most likely official website
        """
        cleaned = site_name.strip()
        lower = cleaned.lower()

        # Handle full URL pass-through
        if cleaned.startswith("http://") or cleaned.startswith("https://") or cleaned.startswith("file://"):
            return cleaned

        target_entity = _extract_target_entity(cleaned)
        entity_key = target_entity.lower()

        # 1. Check known-site mapping (does NOT call search)
        if entity_key in self.mapping:
            return self.mapping[entity_key]

        if lower in self.mapping:
            return self.mapping[lower]

        # 2. Search fallback via WebSearcher
        search_query = f"official website {target_entity}"
        try:
            results = self.searcher.search(search_query, max_results=5)
        except SearchError as e:
            raise WebsiteResolutionError(f"Search failed for '{site_name}': {e}") from e

        if not results:
            raise WebsiteResolutionError(f'No search results found for "{site_name}"')

        # 3. Inspect search results & select most likely official website
        scored_candidates: List[tuple[float, SearchResult]] = []
        for res in results:
            if not res.url:
                continue
            s = _score_candidate(res, target_entity)
            scored_candidates.append((s, res))

        if not scored_candidates:
            raise WebsiteResolutionError(f'No valid URLs found in search results for "{site_name}"')

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_candidate = scored_candidates[0]

        if best_score < 10.0:
            raise WebsiteResolutionError(
                f'Could not reliably identify official website for "{site_name}" (ambiguous results)'
            )

        return best_candidate.url
