from typing import Any, Dict, Optional
from langgraph.graph import StateGraph, START, END

from browser_agent.browser.controller import BrowserController
from browser_agent.resolver import WebsiteResolver, WebsiteResolutionError
from browser_agent.captcha.detector import CaptchaDetector
from browser_agent.workflow.state import BrowserState


def _extract_website_intent(query: str) -> Optional[str]:
    """
    Deterministic helper to extract a website name or URL from user query.
    Returns None if the query does not ask for or mention a website.
    """
    cleaned = query.strip()
    lower = cleaned.lower()

    if not cleaned:
        return None

    # Direct URL
    if lower.startswith("http://") or lower.startswith("https://") or lower.startswith("file://") or ("." in lower and " " not in lower):
        return cleaned

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
            target = cleaned[len(prefix):].strip()
            for suffix in [" official website", " website"]:
                if target.lower().endswith(suffix):
                    target = target[:-len(suffix)].strip()
            if target:
                return target

    known_sites = {"amazon", "github", "google", "openai", "flipkart", "youtube", "wikipedia"}
    if lower in known_sites:
        return cleaned

    return None


def create_check_website_node():
    """Factory for check_website node."""
    def check_website(state: BrowserState) -> Dict[str, Any]:
        query = state.get("user_query", "")
        target = _extract_website_intent(query)
        if target:
            return {
                "website_name": target,
                "error": None,
            }
        return {
            "website_name": None,
            "success": False,
            "error": "No website requested in query",
        }
    return check_website


def create_resolve_website_node(resolver: WebsiteResolver):
    """Factory for resolve_website node."""
    def resolve_website(state: BrowserState) -> Dict[str, Any]:
        website_name = state.get("website_name")
        if not website_name:
            return {
                "url": None,
                "success": False,
                "error": "No website name to resolve",
            }

        try:
            url = resolver.resolve(website_name)
            return {
                "url": url,
                "error": None,
            }
        except WebsiteResolutionError as e:
            return {
                "url": None,
                "success": False,
                "error": str(e),
            }
        except Exception as e:
            return {
                "url": None,
                "success": False,
                "error": f"Resolution failed: {e}",
            }
    return resolve_website


def create_open_website_node(controller: BrowserController):
    """Factory for open_website node."""
    def open_website(state: BrowserState) -> Dict[str, Any]:
        url = state.get("url")
        if not url:
            return {
                "success": False,
                "error": "No URL available to open",
            }

        nav_result = controller.open_url(url)
        if nav_result.success:
            return {
                "success": True,
                "url": nav_result.url,
                "page_title": nav_result.title,
                "error": None,
            }
        else:
            return {
                "success": False,
                "url": url,
                "error": nav_result.error,
            }
    return open_website


def create_check_human_verification_node(
    controller: BrowserController,
    detector: CaptchaDetector,
):
    """Factory for check_human_verification node."""
    def check_human_verification(state: BrowserState) -> Dict[str, Any]:
        result = detector.detect(controller)
        if result.get("detected"):
            return {
                "captcha_detected": True,
                "waiting_for_user": False,
                "error": f"Human verification required ({result.get('reason')})",
            }
        else:
            return {
                "captcha_detected": False,
                "waiting_for_user": False,
            }
    return check_human_verification


def create_human_handoff_node():
    """Factory for human_handoff node."""
    def human_handoff(state: BrowserState) -> Dict[str, Any]:
        message = (
            "Human verification required.\n"
            "Please complete the verification in the browser.\n"
            "The agent will continue after verification is completed."
        )
        print(f"\n[Human Handoff Triggered]\n{message}\n")
        return {
            "waiting_for_user": True,
            "success": False,
        }
    return human_handoff


# Conditional routing functions
def route_after_check(state: BrowserState) -> str:
    if state.get("website_name"):
        return "resolve_website"
    return END


def route_after_resolve(state: BrowserState) -> str:
    if state.get("url"):
        return "open_website"
    return END


def route_after_open(state: BrowserState) -> str:
    if state.get("success"):
        return "check_human_verification"
    return END


def route_after_verification_check(state: BrowserState) -> str:
    if state.get("captcha_detected"):
        return "human_handoff"
    return END


def build_browser_graph(
    controller: BrowserController,
    resolver: Optional[WebsiteResolver] = None,
    detector: Optional[CaptchaDetector] = None,
) -> Any:
    """
    Builds the LangGraph orchestrator:
      START
        ↓
      check_website ──(no)──► END
        ↓ (yes)
      resolve_website ──(no)──► END
        ↓ (yes)
      open_website ──(failure)──► END
        ↓ (success)
      check_human_verification
        ├── (no captcha) ──► END
        └── (captcha detected)
              ↓
            human_handoff ──► END (waiting_for_user=True)
    """
    res = resolver or WebsiteResolver()
    det = detector or CaptchaDetector()

    workflow = StateGraph(BrowserState)

    # Nodes
    workflow.add_node("check_website", create_check_website_node())
    workflow.add_node("resolve_website", create_resolve_website_node(res))
    workflow.add_node("open_website", create_open_website_node(controller))
    workflow.add_node("check_human_verification", create_check_human_verification_node(controller, det))
    workflow.add_node("human_handoff", create_human_handoff_node())

    # Edges
    workflow.add_edge(START, "check_website")

    workflow.add_conditional_edges(
        "check_website",
        route_after_check,
        {
            "resolve_website": "resolve_website",
            END: END,
        },
    )

    workflow.add_conditional_edges(
        "resolve_website",
        route_after_resolve,
        {
            "open_website": "open_website",
            END: END,
        },
    )

    workflow.add_conditional_edges(
        "open_website",
        route_after_open,
        {
            "check_human_verification": "check_human_verification",
            END: END,
        },
    )

    workflow.add_conditional_edges(
        "check_human_verification",
        route_after_verification_check,
        {
            "human_handoff": "human_handoff",
            END: END,
        },
    )

    workflow.add_edge("human_handoff", END)

    return workflow.compile()


def run_browser_workflow(
    user_query: str,
    controller: Optional[BrowserController] = None,
    resolver: Optional[WebsiteResolver] = None,
    detector: Optional[CaptchaDetector] = None,
    headless: bool = False,
) -> BrowserState:
    """
    Runs the initial workflow. Manages BrowserController lifecycle if not injected.
    """
    own_controller = controller is None
    ctrl = controller or BrowserController(headless=headless)
    res = resolver or WebsiteResolver()
    det = detector or CaptchaDetector()

    graph = build_browser_graph(controller=ctrl, resolver=res, detector=det)

    initial_state: BrowserState = {
        "user_query": user_query,
        "website_name": None,
        "url": None,
        "page_title": None,
        "success": False,
        "error": None,
        "captcha_detected": False,
        "waiting_for_user": False,
    }

    try:
        final_state = graph.invoke(initial_state)
        return final_state
    finally:
        # If paused in human handoff or controller was injected by caller, keep open!
        if own_controller and not final_state.get("waiting_for_user"):
            ctrl.close()


def resume_browser_workflow(
    state: BrowserState,
    controller: BrowserController,
    detector: Optional[CaptchaDetector] = None,
) -> BrowserState:
    """
    Resumes workflow after user completes manual verification in the SAME browser session.
    Re-inspects page with CaptchaDetector.
    """
    det = detector or CaptchaDetector()
    check_result = det.detect(controller)

    if check_result.get("detected"):
        # User has not finished verification yet
        state["waiting_for_user"] = True
        state["captcha_detected"] = True
        state["success"] = False
        state["error"] = f"Verification still pending: {check_result.get('reason')}"
        return state

    # Verification completed successfully
    page = controller._page
    state["waiting_for_user"] = False
    state["captcha_detected"] = False
    state["success"] = True
    state["error"] = None
    if page:
        state["url"] = page.url
        state["page_title"] = page.title()

    return state
