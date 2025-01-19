from pathlib import Path
from rich.console import Console
from janito.agents import agent

from janito.workspace import workset
from janito.workspace.models import ScanType
from janito.config import config
from janito.cli.history import save_to_history
from janito.qa import ask_question, display_answer
from janito.change.request import request_change


console = Console()

def handle_ask(question: str):
    """Process a question about the codebase

    Args:
        question: The question to ask about the codebase
        workset: Optional Workset instance for scoped operations
    """
    answer = ask_question(question)
    display_answer(answer)

def handle_scan():
    """Preview files that would be analyzed"""
    workset.show()

def handle_play(filepath: Path):
    """Replay a saved changes or debug file"""
    console.print(f"\n[cyan]Processing file:[/] [bold]{filepath.name}[/]")
    play_saved_changes(filepath)

def is_dir_empty(path: Path) -> bool:
    """Check if directory is empty or only contains empty directories."""
    if not path.is_dir():
        return False

    for item in path.iterdir():
        if item.name.startswith(('.', '__pycache__')):
            continue
        if item.is_file():
            return False
        if item.is_dir() and not is_dir_empty(item):
            return False
    return True

def handle_request(request: str = None):
    """Process modification request"""
    if not request:
        return

    is_empty = is_dir_empty(config.workspace_dir)
    if is_empty:
        console.print("\n[bold blue]Empty directory - will create new files as needed[/bold blue]")

    request_change(request)


# Command handler functions
COMMANDS = {
    'ask': handle_ask,
    'scan': handle_scan,
    'play': handle_play,
    'request': handle_request
}
