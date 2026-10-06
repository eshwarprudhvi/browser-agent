from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page, Error as PlaywrightError


@dataclass
class NavigationResult:
    """Represents the outcome of a browser navigation."""
    success: bool
    url: str
    title: str = ""
    error: Optional[str] = None


class BrowserController:
    """
    Browser controller providing core interaction primitives:
    - open_url: Launches browser and navigates to URL
    - inspect_page: Extracts page metadata and interactive elements
    - click: Locates, validates, and clicks page elements
    - close: Cleans up browser resources
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def _ensure_browser(self) -> Page:
        """Launches the browser and creates a page if not already running."""
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        if self._browser is None:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
        if self._context is None:
            self._context = self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        if self._page is None:
            self._page = self._context.new_page()
        return self._page

    def open_url(self, url: str) -> NavigationResult:
        """
        Navigates to the given URL, waits for the page to load,
        and returns a NavigationResult with the final URL, title, and status.
        """
        try:
            page = self._ensure_browser()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Retrieve title, giving a brief wait if initially empty
            title = page.title()
            if not title:
                page.wait_for_timeout(2000)
                title = page.title()

            return NavigationResult(
                success=True,
                url=page.url or url,
                title=title,
            )
        except PlaywrightError as e:
            return NavigationResult(
                success=False,
                url=url,
                title="",
                error=str(e),
            )
        except Exception as e:
            return NavigationResult(
                success=False,
                url=url,
                title="",
                error=str(e),
            )

    def inspect_page(self) -> Dict[str, Any]:
        """
        Inspects the currently open page and returns structured representation:
        - title
        - url
        - visible_text
        - elements: list of interactive elements (tag, role, text, id, name, aria_label, placeholder, selector)
        """
        if not self._page:
            return {
                "title": "",
                "url": "",
                "visible_text": "",
                "elements": [],
                "error": "No page open. Call open_url() first.",
            }

        # Extract visible text summary from body
        try:
            visible_text = self._page.inner_text("body")
            if len(visible_text) > 400:
                visible_text = visible_text[:400] + "... [truncated]"
        except Exception:
            visible_text = ""

        # Query visible interactive DOM elements
        js_extract_elements = """
        () => {
            const selectors = 'button, a, input, select, textarea, [role="button"], [role="link"], [tabindex="0"]';
            const nodes = Array.from(document.querySelectorAll(selectors));
            const results = [];

            for (const el of nodes) {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                const isVisible = style.display !== 'none' && 
                                  style.visibility !== 'hidden' && 
                                  style.opacity !== '0' && 
                                  (rect.width > 0 || rect.height > 0);
                if (!isVisible) continue;

                const tag = el.tagName.toLowerCase();
                const id = el.id || '';
                const name = el.getAttribute('name') || '';
                const role = el.getAttribute('role') || (tag === 'button' ? 'button' : tag === 'a' ? 'link' : '');
                const ariaLabel = el.getAttribute('aria-label') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                
                let text = (el.innerText || el.textContent || el.value || '').trim();
                if (text.length > 80) text = text.substring(0, 80) + '...';

                // Build a suggested selector
                let selector = '';
                if (id) {
                    selector = `#${id}`;
                } else if (name) {
                    selector = `${tag}[name="${name}"]`;
                } else if (ariaLabel) {
                    selector = `${tag}[aria-label="${ariaLabel}"]`;
                } else if (text) {
                    selector = `${tag}:has-text("${text}")`;
                } else {
                    selector = tag;
                }

                results.push({
                    tag: tag,
                    role: role,
                    text: text,
                    id: id,
                    name: name,
                    aria_label: ariaLabel,
                    placeholder: placeholder,
                    selector: selector
                });
            }
            return results;
        }
        """

        try:
            elements: List[Dict[str, Any]] = self._page.evaluate(js_extract_elements)
        except Exception:
            elements = []

        return {
            "title": self._page.title(),
            "url": self._page.url,
            "visible_text": visible_text,
            "elements": elements,
        }

    def click(self, selector: str, timeout: int = 3000) -> Dict[str, Any]:
        """
        Locates the element specified by selector, verifies that it is interactable,
        clicks it, waits for updates, and returns a structured result.
        """
        if not self._page:
            return {
                "success": False,
                "element": selector,
                "error": "No page open. Call open_url() first.",
            }

        locator = self._page.locator(selector)

        # 1 & 2. Verify element exists and is interactable
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
        except Exception:
            # Check if element exists in DOM at all
            try:
                count = locator.count()
            except Exception:
                count = 0

            if count == 0:
                return {
                    "success": False,
                    "element": selector,
                    "error": "Element not found",
                }
            else:
                return {
                    "success": False,
                    "element": selector,
                    "error": "Element not visible or interactable",
                }

        # 3 & 4. Perform click
        try:
            locator.first.click(timeout=timeout)
            # Brief wait for load or DOM reaction
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=2000)
            except Exception:
                pass
            self._page.wait_for_timeout(300)

            return {
                "success": True,
                "element": selector,
                "url": self._page.url,
                "message": "Element clicked successfully",
            }
        except PlaywrightError as e:
            return {
                "success": False,
                "element": selector,
                "error": f"Click failed: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "element": selector,
                "error": f"Click failed: {e}",
            }

    def close(self) -> None:
        """Closes all browser instances and cleans up Playwright."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None

        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
