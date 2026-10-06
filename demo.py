import json
import sys
from pathlib import Path

# Ensure src/ is on sys.path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from browser_agent.browser.controller import BrowserController
from browser_agent.captcha.detector import CaptchaDetector
from browser_agent.workflow import (
    run_browser_workflow,
    resume_browser_workflow,
    BrowserState,
)


def run_demo() -> None:
    print("=== Milestone 6 Demo: CAPTCHA Detection + Human Handoff ===\n")
    headless = "--headless" in sys.argv

    detector = CaptchaDetector()

    # -------------------------------------------------------------------------
    # Test 1: Normal website (No CAPTCHA)
    # Expected flow: open_website -> check_human_verification -> NO -> continue
    # -------------------------------------------------------------------------
    print("-----------------------------------------------------------------")
    print("Test 1: Normal website with no CAPTCHA (https://example.com)")
    print("Expected: check_human_verification -> NO -> continue (no pause)")
    state_1 = run_browser_workflow("https://example.com", headless=headless)
    print("Final State:")
    print(json.dumps(state_1, indent=2))
    assert state_1["success"] is True, f"Expected success=True, got {state_1['success']}"
    assert state_1["captcha_detected"] is False, "Unexpected captcha detected on normal site!"
    assert state_1["waiting_for_user"] is False, "Workflow unexpectedly paused for user!"
    print("[Passed] Test 1: Normal site passed without pausing.\n")

    # -------------------------------------------------------------------------
    # Test 2: Simulated CAPTCHA page & Resume Mechanism
    # Expected flow:
    #   1. open_website -> check_human_verification -> YES -> human_handoff (WAITING_FOR_USER)
    #   2. User completes verification in browser
    #   3. resume_browser_workflow in SAME browser session -> verification clears -> continue
    # -------------------------------------------------------------------------
    print("-----------------------------------------------------------------")
    print("Test 2: Simulated CAPTCHA Page & Human Handoff / Resume")
    print("Expected: check_human_verification -> YES -> human_handoff -> WAITING_FOR_USER")

    captcha_fixture = (Path(__file__).parent / "tests" / "captcha_page.html").resolve().as_uri()

    with BrowserController(headless=headless) as controller:
        # Step 2a: Run workflow against CAPTCHA page
        paused_state = run_browser_workflow(captcha_fixture, controller=controller)
        print("Paused State after detection:")
        print(json.dumps(paused_state, indent=2))

        assert paused_state["captcha_detected"] is True, "Expected CAPTCHA detection to be True!"
        assert paused_state["waiting_for_user"] is True, "Expected waiting_for_user to be True!"
        assert paused_state["success"] is False, "Workflow should not report success while paused."
        print("[Passed] Step 2a: Detection correctly identified challenge and paused for user handoff.")

        # Step 2b: Simulate user solving the verification in the active browser window
        print("\nSimulating user completing verification in the browser...")
        controller.click("#solve-btn")

        # Step 2c: Resume the workflow in the SAME browser session
        print("Resuming workflow via resume_browser_workflow() in same browser session...")
        resumed_state = resume_browser_workflow(paused_state, controller=controller, detector=detector)
        print("Resumed State:")
        print(json.dumps(resumed_state, indent=2))

        assert resumed_state["captcha_detected"] is False, "Expected challenge to be cleared after resume."
        assert resumed_state["waiting_for_user"] is False, "Expected waiting_for_user=False after resume."
        assert resumed_state["success"] is True, "Expected success=True after successful verification resume."
        print("[Passed] Step 2b & 2c: Workflow successfully resumed in same session after manual completion.\n")

    # -------------------------------------------------------------------------
    # Test 3: False Positive Prevention
    # Documentation page containing the word 'captcha' in ordinary text
    # -------------------------------------------------------------------------
    print("-----------------------------------------------------------------")
    print("Test 3: False Positive Protection")
    print("Expected: Documentation page mentioning 'captcha' must NOT trigger detection")

    doc_fixture = (Path(__file__).parent / "tests" / "doc_page.html").resolve().as_uri()
    state_3 = run_browser_workflow(doc_fixture, headless=headless)
    print("Final State:")
    print(json.dumps(state_3, indent=2))

    assert state_3["success"] is True, f"Expected success=True, got {state_3['success']}"
    assert state_3["captcha_detected"] is False, "False positive! Word 'captcha' in text incorrectly flagged."
    assert state_3["waiting_for_user"] is False, "Should not wait for user on documentation page."
    print("[Passed] Test 3: False positive avoided. Ordinary text containing 'captcha' was not flagged.\n")

    print("=== All Milestone 6 tests passed successfully! ===")


if __name__ == "__main__":
    run_demo()
