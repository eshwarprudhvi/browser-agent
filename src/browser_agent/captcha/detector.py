from typing import Any, Dict, Optional
from browser_agent.browser.controller import BrowserController


class CaptchaDetector:
    """
    Heuristic-based detector for CAPTCHAs and human verification challenges.
    Strictly performs detection only (does not attempt to bypass or solve challenges).
    """

    CHALLENGE_TITLES = [
        "attention required! | cloudflare",
        "just a moment...",
        "robot check",
        "security check",
        "verify you are human",
        "human verification",
    ]

    CHALLENGE_SELECTORS = [
        "#human-verification",
        "#captcha-box",
        "#cf-challenge-running",
        ".cf-turnstile",
        ".g-recaptcha",
        ".h-captcha",
        "[data-sitekey]",
        "iframe[src*='recaptcha']",
        "iframe[src*='turnstile']",
        "iframe[src*='hcaptcha']",
        "iframe[src*='arkoselabs']",
    ]

    CHALLENGE_PHRASES = [
        "verify you are human",
        "verify that you are a human",
        "human verification",
        "confirm you are not a robot",
        "press & hold",
        "press and hold",
        "security check to access",
        "complete the challenge below",
        "please solve the challenge",
    ]

    def detect(self, controller: BrowserController) -> Dict[str, Any]:
        """
        Inspects the active page in the browser controller and returns:
          { "detected": bool, "reason": Optional[str] }
        """
        page = controller._page
        if not page:
            return {"detected": False, "reason": None}

        # 1. Check page title
        try:
            title = page.title().lower()
            for ct in self.CHALLENGE_TITLES:
                if ct in title:
                    return {
                        "detected": True,
                        "reason": f"Challenge indicated in page title: '{page.title()}'",
                    }
        except Exception:
            pass

        # 2. Check DOM selectors via in-page evaluation
        js_detector = f"""
        () => {{
            const selectors = {self.CHALLENGE_SELECTORS};
            for (const sel of selectors) {{
                const el = document.querySelector(sel);
                if (el) {{
                    return {{ detected: true, reason: `Challenge element found: ${{sel}}` }};
                }}
            }}

            const phrases = {self.CHALLENGE_PHRASES};
            const prominentElements = Array.from(document.querySelectorAll(
                'h1, h2, h3, #human-verification, .verification, .challenge, .security-check'
            ));

            for (const el of prominentElements) {{
                const text = (el.innerText || '').toLowerCase();
                for (const phrase of phrases) {{
                    if (text.includes(phrase)) {{
                        return {{ detected: true, reason: `Verification instruction in heading: "${{phrase}}"` }};
                    }}
                }}
            }}

            const bodyText = (document.body ? document.body.innerText : '').toLowerCase();
            for (const phrase of phrases) {{
                if (bodyText.includes(phrase)) {{
                    return {{ detected: true, reason: `Verification instruction found in body: "${{phrase}}"` }};
                }}
            }}

            return {{ detected: false, reason: null }};
        }}
        """

        try:
            result = page.evaluate(js_detector)
            return result
        except Exception:
            return {"detected": False, "reason": None}

    def detect_from_text(self, title: str, text: str) -> Dict[str, Any]:
        """
        Evaluates detection on static text strings (useful for unit testing).
        Prevents false positives on single occurrences of 'captcha' in regular content.
        """
        title_lower = title.lower()
        for ct in self.CHALLENGE_TITLES:
            if ct in title_lower:
                return {"detected": True, "reason": f"Challenge in title: '{title}'"}

        text_lower = text.lower()
        for phrase in self.CHALLENGE_PHRASES:
            if phrase in text_lower:
                return {"detected": True, "reason": f"Verification phrase: '{phrase}'"}

        return {"detected": False, "reason": None}
