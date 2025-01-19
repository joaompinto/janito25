from datetime import datetime
from rich.live import Live
from rich.text import Text
from rich.console import Console
from rich.rule import Rule
from rich import print
from threading import Thread
from janito.agents import agent
from .config import config
from typing import Optional, List
from janito.config import config


console = Console()


def progress_send_message(message: str) -> Optional[str]:
    """Send a message to the AI agent with progress indication.

    Displays a progress spinner while waiting for the agent's response and shows
    token usage statistics after receiving the response. Uses a background thread
    to update the elapsed time display.

    Args:
        system_message: The system message to send to the AI agent
        message: The message to send to the AI agent

    Returns:
        Optional[str]: The response text from the AI agent, or None if interrupted

    Note:
        - Returns None if the operation is cancelled via Ctrl+C
        - If the request fails, raises the original exception
    """
    # read the system prompt from docs/system_prompt.txt
    with open('docs/system_prompt.txt', 'r') as file:
        system_message = file.read()

    if config.debug:
        console.print(f"[yellow]======= Sending message via {agent.__class__.__name__.replace('AIAgent', '')}[/yellow]")
        print(system_message)
        print(message)
        console.print("[yellow]======= End of message[/yellow]")

    start_time = datetime.now()


    response = None
    error = None

    def agent_thread():
        nonlocal response, error
        try:
            response = agent.send_message(system_message=system_message, message=message)
        except Exception as e:
            error = e

    agent_thread = Thread(target=agent_thread, daemon=True)
    agent_thread.start()

    try:
        with Live(Text("Waiting for response from AI agent...", justify="center"), refresh_per_second=4) as live:
            while agent_thread.is_alive():
                elapsed = datetime.now() - start_time
                elapsed_seconds = elapsed.seconds
                elapsed_minutes = elapsed_seconds // 60
                remaining_seconds = elapsed_seconds % 60
                time_str = f"{elapsed_minutes}m{remaining_seconds}s" if elapsed_minutes > 0 else f"{elapsed_seconds}s"
                live.update(Text.assemble(
                    "Waiting for response from AI agent... (",
                    (time_str, "magenta"),
                    ")",
                    justify="center"
                ))
                agent_thread.join(timeout=0.25)

            # Calculate final stats
            elapsed = datetime.now() - start_time
            elapsed_seconds = elapsed.seconds
            elapsed_minutes = elapsed_seconds // 60
            remaining_seconds = elapsed_seconds % 60
            time_str = f"{elapsed_minutes}m{remaining_seconds}s" if elapsed_minutes > 0 else f"{elapsed_seconds}s"

            if hasattr(response, 'usage'):
                usage = response.usage
                # Get total input tokens including cache if available
                total_input = (
                    getattr(usage, 'input_tokens', 0) +
                    getattr(usage, 'cache_creation_input_tokens', 0) +
                    getattr(usage, 'cache_read_input_tokens', 0)
                )
                output_tokens = getattr(usage, 'output_tokens', 0)

                # Update final message with stats
                stats_text = f"Response in {time_str} • [cyan]In:[/] [bold green]{total_input:,}[/] [cyan]Out:[/] [bold yellow]{output_tokens:,}[/]"
                live.update(Rule(stats_text))

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
        return None

    if error:
        if isinstance(error, KeyboardInterrupt):
            console.print("\n[yellow]Operation cancelled[/yellow]")
            return None
        raise error

    if config.debug:
        console.print("[yellow]======= Received response[/yellow]")
        print(response)
        console.print("[yellow]======= End of response[/yellow]")
    
    # Extract response text based on response type
    if hasattr(response, 'choices'):
        response_text = response.choices[0].message.content
    elif hasattr(response, 'content'):
        response_text = response.content[0].text
    else:
        response_text = str(response)
    
    return response_text
