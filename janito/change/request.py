from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.table import Table
from janito.common import progress_send_message
from janito.workspace import workset
from janito.config import config
from pathlib import Path
import re

class CodeBlock:
    """Represents a code block from the AI response."""
    def __init__(self, path: str, content: str, block_id: str, is_creation: bool):
        self.path = path
        self.content = content
        self.block_id = block_id  # Will be a letter A-Z
        self.is_creation = is_creation  # True for creation, False for modification
        self.accepted = True

class ModificationBlock:
    """Represents a section of code to be modified."""
    def __init__(self, content: str, context_before: str = None, context_after: str = None):
        self.content = content
        self.context_before = context_before
        self.context_after = context_after

def parse_code_blocks(markdown: str) -> tuple[str, list[CodeBlock]]:
    """Parse markdown content to find code blocks and inject markers."""
    lines = markdown.split('\n')
    code_blocks = []
    new_lines = []
    block_count = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('```') and ':' in line:
            lang_path = line[3:].strip()
            if ':' in lang_path:
                _, path = lang_path.split(':', 1)
                content_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith('```'):
                    content_lines.append(lines[i])
                    i += 1
                if content_lines:
                    block_id = chr(65 + block_count)  # Convert 0-25 to A-Z
                    
                    # Check if this is a modification block
                    has_markers = any('existing code' in line.lower() or '...' in line 
                                    for line in content_lines)
                    is_creation = not has_markers
                    
                    if is_creation:
                        content = '\n'.join(content_lines)
                    else:
                        # Store the modification blocks for later processing
                        content = content_lines
                    
                    block = CodeBlock(path, content, block_id, is_creation)
                    code_blocks.append(block)
                    
                    # Add marker before code block
                    block_type = "New File" if is_creation else "Modify"
                    new_lines.append(f"\n[Block {block_id} - {block_type}]")
                    new_lines.append(line)
                    new_lines.extend(content_lines)
                    new_lines.append('```')
                    block_count += 1
                i += 1
                continue
        new_lines.append(line)
        i += 1
    
    return '\n'.join(new_lines), code_blocks

def display_code_blocks(code_blocks: list[CodeBlock]) -> str:
    """Display code blocks and get user selection."""
    console = Console()
    
    # Create a table to show code blocks
    table = Table(show_header=True, header_style="bold")
    table.add_column("Block", style="dim", width=6)
    table.add_column("Type", width=8)
    table.add_column("Path", style="blue")
    
    # Default value is all block IDs
    default_value = ''.join(block.block_id for block in code_blocks)
    
    for block in code_blocks:
        block_type = "[green]New[/green]" if block.is_creation else "[yellow]Modify[/yellow]"
        table.add_row(block.block_id, block_type, block.path)
    
    console.print("\n")
    console.print(table)
    
    # Get user selection
    selection = Prompt.ask(
        "\nEnter block letters to apply (empty to skip all)",
        default=default_value
    )
    
    return selection.upper()

def display_change_response(response: str, raw: bool = False) -> tuple[bool, list[CodeBlock]]:
    """Display the change response with rich markdown and handle code blocks."""
    if response is None:
        Console().print("\n[red]Error: No response received - the response was interrupted[/red]\n")
        return False, []
        
    if raw:
        Console().print(response)
        return True, []

    console = Console()
    marked_content, code_blocks = parse_code_blocks(response)
    
    # Display the markdown content
    console.print("\n")
    console.print(Panel(
        Markdown(marked_content),
        title="Review Proposed Changes",
        title_align="center",
        padding=(1, 2)
    ))
    
    if code_blocks:
        selection = display_code_blocks(code_blocks)
        if not selection:
            return False, code_blocks
            
        # Update accepted state based on selection
        for block in code_blocks:
            block.accepted = block.block_id in selection
        
        return True, code_blocks
    
    return True, []

def create_preview_files(code_blocks: list[CodeBlock]) -> tuple[bool, dict[str, Path]]:
    """Create or modify files in preview directory."""
    console = Console()
    success = True
    preview_files = {}
    
    # Get workspace instance
    from janito.workspace.workspace import Workspace
    workspace = Workspace()
    
    # Prepare clean preview directory (this copies the workspace)
    workspace.prepare_preview()
    
    console.print("\n[cyan]Preparing changes in preview directory...[/cyan]")
    
    for block in code_blocks:
        if not block.accepted:
            continue
            
        try:
            path = Path(block.path)
            preview_path = workspace.get_preview_path(path)
            preview_files[str(path)] = preview_path
            
            if block.is_creation:
                workspace.preview_create_file(path, block.content)
                console.print(f"[green]✓ Preview created:[/green] {block.path}")
            else:
                # For modifications, we can work directly with the preview file
                original_content = preview_path.read_text(encoding='utf-8')
                mod_blocks = parse_modification_content(block.content)
                new_content = apply_modifications(original_content, mod_blocks)
                preview_path.write_text(new_content, encoding='utf-8')
                console.print(f"[green]✓ Preview modified:[/green] {block.path}")
        except Exception as e:
            console.print(f"[red]✗ Failed to preview {block.path}: {str(e)}[/red]")
            success = False
            
    return success, preview_files

def apply_preview_changes(preview_files: dict[str, Path]) -> bool:
    """Apply changes from preview files to actual workspace."""
    console = Console()
    success = True
    
    from janito.workspace.workspace import Workspace
    workspace = Workspace()
    
    console.print("\n[cyan]Applying changes to workspace...[/cyan]")
    
    for orig_path, preview_path in preview_files.items():
        try:
            path = Path(orig_path)
            content = preview_path.read_text(encoding='utf-8')
            
            if not (config.workspace_dir / path).exists():
                workspace.create_file(path, content)
                console.print(f"[green]✓ Created file:[/green] {path}")
            else:
                workspace.modify_file(path, content)
                console.print(f"[green]✓ Modified file:[/green] {path}")
        except Exception as e:
            console.print(f"[red]✗ Failed to apply changes to {path}: {str(e)}[/red]")
            success = False
    
    return success

def request_change(request: str) -> str:
    """Process a change request for the codebase and return the response."""
    workset.refresh()

    # Get workspace instance
    from janito.workspace.workspace import Workspace
    workspace = Workspace()
    console = Console()

    # Always prepare a fresh preview directory
    workspace.prepare_preview()
    if config.debug:
        console.print(f"\n[cyan]Preview directory: {workspace.get_preview_dir()}[/cyan]")

    try:
        with open('docs/change_prompt.txt', 'r') as file:
            change_prompt = file.read()

        prompt = change_prompt.format(
            request=request,
            workset=workset.content
        )
        response = progress_send_message(prompt)
        if response is None:
            return "Sorry, the response was interrupted. Please try your request again."
        
        accepted, file_blocks = display_change_response(response)
        
        if accepted and file_blocks:
            # Create preview changes
            success, preview_files = create_preview_files(file_blocks)
            if not success:
                console.print("[red]Failed to create preview changes[/red]")
                return None
                
            # Ask for final confirmation after preview
            if Prompt.ask("\nApply these changes to workspace?", default=True):
                if not apply_preview_changes(preview_files):
                    return None
            else:
                return None
                
        return response if accepted else None
    finally:
        # Just show the preview directory location for debugging
        if config.debug:
            console.print(f"\n[cyan]Preview directory preserved at: {workspace.get_preview_dir()}[/cyan]")

def parse_modification_content(content_lines: list[str]) -> list[ModificationBlock]:
    """Parse content lines into modification blocks.
    
    Handles patterns like:
    // existing code...
    new code
    // ...
    more new code
    // existing code...
    """
    blocks = []
    current_lines = []
    context_before = None
    context_after = None
    
    i = 0
    while i < len(content_lines):
        line = content_lines[i].strip()
        
        # Look for context markers
        if 'existing code' in line.lower() or '...' in line:
            # If we have accumulated lines, create a block
            if current_lines:
                blocks.append(ModificationBlock(
                    '\n'.join(current_lines),
                    context_before,
                    context_after
                ))
                current_lines = []
            
            # Store this as context for the next block
            context_before = context_after
            context_after = line
        else:
            current_lines.append(content_lines[i])
        i += 1
    
    # Add any remaining lines as a final block
    if current_lines:
        blocks.append(ModificationBlock(
            '\n'.join(current_lines),
            context_before,
            context_after
        ))
    
    return blocks

def apply_modifications(original_content: str, mod_blocks: list[ModificationBlock]) -> str:
    """Apply modification blocks to the original content."""
    if not mod_blocks:
        return original_content
        
    lines = original_content.splitlines()
    result_lines = []
    i = 0
    
    for block in mod_blocks:
        # If this block has a context_before, find it in the remaining lines
        if block.context_before:
            # Skip lines until we find the context
            while i < len(lines):
                if block.context_before.replace('...', '').strip() in lines[i]:
                    i += 1
                    break
                result_lines.append(lines[i])
                i += 1
        
        # Add the new content
        result_lines.extend(block.content.splitlines())
        
        # If this block has a context_after, skip lines until we find it
        if block.context_after:
            while i < len(lines):
                if block.context_after.replace('...', '').strip() in lines[i]:
                    break
                i += 1
    
    # Add any remaining lines
    result_lines.extend(lines[i:])
    
    return '\n'.join(result_lines)
