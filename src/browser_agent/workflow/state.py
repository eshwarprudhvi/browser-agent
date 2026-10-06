from typing import Optional, TypedDict


class BrowserState(TypedDict):
    """
    Minimal state schema for the LangGraph orchestrator.
    Contains only what is needed for checking, resolving, opening websites,
    and handling human verification handoffs.
    """
    user_query: str
    website_name: Optional[str]
    url: Optional[str]
    page_title: Optional[str]
    success: bool
    error: Optional[str]

    captcha_detected: bool
    waiting_for_user: bool
