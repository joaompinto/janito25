from rich.console import Console
from janito.common import progress_send_message
from janito.workspace import workset, workspace
from janito.config import config
from pathlib import Path
import tempfile
from janito.change.applier import ChangeApplier
from janito.change.validator import Validator
from janito.change.edit_blocks import EditType, CodeChange, get_edit_blocks
from typing import List
import shutil
from rich.markdown import Markdown



def request_change(request: str) -> str:
    """Process a change request for the codebase and return the response."""

    with open('docs/change_prompt.txt', 'r') as file:
        change_prompt = file.read()

    prompt = change_prompt.format(
        request=request,
        workset=workset.content
    )
    response = progress_send_message(prompt)

    if response is None:
        return "Sorry, the response was interrupted. Please try your request again."


    # Create a static file name in the TEMP dir
    temp_file_path = Path(tempfile.gettempdir()) / 'janito_change_response.txt'
    temp_file_path.write_text(response, encoding='utf-8')
    if config.debug:
        print(f"Response saved to {temp_file_path}")
    handler = ResponseHandler(response)
    handler.process()

class ResponseHandler:

    def __init__(self, response: str):
        self.response = response
        self.console = Console()
        self.edit_blocks = []

    def process(self):
        self.edit_blocks, self.annotated_response = get_edit_blocks(self.response)
        self.console.print(Markdown(self.annotated_response))
        
        preview_dir = workspace.setup_preview_directory()
        applier = ChangeApplier(preview_dir)

        for block in self.edit_blocks:
            applier.add_edit(block)

        # Apply the changes to the preview directory
        applier.apply()

        # Collect files that need validation (excluding deleted files)
        files_to_validate = {edit.filename for edit in self.edit_blocks 
                           if edit.edit_type != EditType.DELETE}

        # Validate changes and run tests
        validator = Validator(preview_dir)
        validator.validate_files(files_to_validate)
        validator.run_tests()

        # Collect the list of created/modified/deleted files
        created_files = [edit.filename for edit in self.edit_blocks if edit.edit_type == EditType.CREATE]
        modified_files = set(edit.filename for edit in self.edit_blocks 
                           if edit.edit_type in (EditType.EDIT, EditType.CLEAN))  # Include cleaned files
        deleted_files = set(edit.filename for edit in self.edit_blocks if edit.edit_type == EditType.DELETE)

        # prompt the user if we want to apply the changes
        if config.auto_apply:
            apply_changes = True
        else:  
            self.console.print("\nApply changes to the workspace? [y/N] ", end="")
            response = input().lower()
            apply_changes = response.startswith('y')
            if not apply_changes:
                self.console.print("[yellow]Changes were not applied. Exiting...[/yellow]")
                return

        # Apply changes to workspace
        workspace.apply_changes(preview_dir, created_files, modified_files, deleted_files)

def replay_saved_response():
    temp_file_path = Path(tempfile.gettempdir()) / 'janito_change_response.txt'    
    print(temp_file_path)
    if not temp_file_path.exists():
        print("No saved response found")
        return
    
    with open(temp_file_path, 'r', encoding="utf-8") as file:
        response = file.read()
        
    handler = ResponseHandler(response)
    handler.process()