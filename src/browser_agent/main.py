import sys
from browser_agent.workflow import run_browser_workflow, BrowserState


def execute_command(command: str, headless: bool = False) -> BrowserState:
    """
    Executes a user command using the LangGraph orchestrator workflow.
    """
    print(f"User: {command}\n")

    state = run_browser_workflow(command, headless=headless)

    print("Agent:")
    if state.get("url"):
        print(f"Opening {state['url']} ...\n")

    if state.get("success"):
        print("Success")
        print(f"URL: {state['url']}")
        print(f"Title: {state.get('page_title', '')}")
    else:
        print("Failed")
        if state.get("url"):
            print(f"URL: {state['url']}")
        print(f"Error: {state.get('error', 'Unknown error')}")

    return state


def main() -> None:
    # Check for CLI arguments
    args = [arg for arg in sys.argv[1:] if arg != "--headless"]
    headless = "--headless" in sys.argv

    command = args[0] if args else "Open Amazon"
    execute_command(command, headless=headless)


if __name__ == "__main__":
    main()
