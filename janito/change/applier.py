from typing import List
from pathlib import Path
from rich.console import Console
from janito.config import config
from .finder import find_range
from .edit_blocks import EditType, CodeChange
from .view.panels import create_diff_columns
from .view.summary import show_changes_summary

class ChangeApplier:
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.edits: List[CodeChange] = []
        self._last_changed_line = 0
        self.current_file = None
        self.current_content: List[str] = []
        self.console = Console()
        self.changes_summary = []

    def add_edit(self, edit: CodeChange):
        self.edits.append(edit)

    def start_file_edit(self, filename: str, edit_type: EditType):
        if self.current_file:
            self.end_file_edit()
        self._last_changed_line = 0
        self.current_file = filename
        self.current_edit_type = edit_type  # Store edit type for end_file_edit
        
        if edit_type == EditType.CREATE:
            self.current_content = []
        elif edit_type == EditType.DELETE:
            if not (self.target_dir / filename).exists():
                raise FileNotFoundError(f"Cannot delete non-existent file: {filename}")
            self.current_content = []
        else:
            self.current_content = (self.target_dir / filename).read_text(encoding="utf-8").splitlines()
    
    def end_file_edit(self):
        if self.current_file:
            target_path = self.target_dir / self.current_file
            if hasattr(self, 'current_edit_type') and self.current_edit_type == EditType.DELETE:
                if target_path.exists():
                    target_path.unlink()
            else:
                # Create parent directories if they don't exist
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text("\n".join(self.current_content), encoding="utf-8")
        self.current_file = None

    def apply(self):
        """Apply all edits and show summary of changes."""
        # Ensure target directory exists
        self.target_dir.mkdir(parents=True, exist_ok=True)
        
        # Track changes as we apply them
        changes = []
        current_file = None
        
        # Process edits in order as they were added
        for edit in self.edits:
            if current_file != edit.filename:
                self.end_file_edit()
                self.start_file_edit(str(edit.filename), edit.edit_type)
                current_file = edit.filename
           
            self._apply_and_collect_change(edit)

        self.end_file_edit()
        
        # Show summary table using rich table
        show_changes_summary(self.changes_summary, self.console)

    def _apply_and_collect_change(self, edit: CodeChange) -> dict:
        """Apply a single edit and collect its change information."""
        change_info = {
            'file': edit.filename,
            'type': edit.edit_type.name,
            'reason': edit.reason,
            'edit': edit,
            'block_marker': edit.block_marker,
            'lines_original': len(edit.original),
            'lines_modified': len(edit.modified)
        }

        if edit.edit_type == EditType.CREATE:
            self.current_content = edit.modified
            change_info.update({
                'lines_original': 0,
                'lines_modified': len(edit.modified),
                'range_start': 1,
                'range_end': len(edit.modified)
            })
            # Show new file content
            header, columns = create_diff_columns(
                [],  # No original content
                edit.modified,
                str(edit.filename),
                0,
                self.console.width
            )
            self.console.print(header)
            self.console.print(columns)

        elif edit.edit_type == EditType.DELETE:
            if config.debug and (self.target_dir / edit.filename).exists():
                old_content = (self.target_dir / edit.filename).read_text()
                syntax = Syntax(old_content, "python", line_numbers=True)
                Console().print("\n[red]Deleting File Content:[/red]")
                Console().print(syntax)
            change_info.update({
                'lines_original': len(self.current_content),
                'lines_modified': 0,
                'range_start': 1,
                'range_end': len(self.current_content)
            })
            self.current_content = []

        elif edit.edit_type == EditType.CLEAN:
            try:
                start_range = find_range(self.current_content, edit.original, self._last_changed_line)
                try:
                    end_range = find_range(self.current_content, edit.modified, start_range[1])
                except ValueError:
                    end_range = (start_range[1], start_range[1])

                change_info.update({
                    'lines_original': end_range[1] - start_range[0],
                    'lines_modified': 0,
                    'range_start': start_range[0] + 1,
                    'range_end': end_range[1]
                })
                
                # Show the section to be cleaned in deleted panel
                section = self.current_content[start_range[0]:end_range[1]]
                header, columns = create_diff_columns(
                    section,
                    [],  # No modified content for clean
                    str(edit.filename),
                    start_range[0],
                    self.console.width,
                    operation="Clean",
                    reason=edit.reason,
                    is_removal=True
                )
                self.console.print(header)
                self.console.print(columns)
                
                self.current_content[start_range[0]:end_range[1]] = []
                self._last_changed_line = start_range[0]
                
            except ValueError as e:
                raise ValueError(f"Failed to find clean section in {self.current_file}: {e}")

        else:  # EDIT operation
            edit_range = find_range(self.current_content, edit.original, self._last_changed_line)
            change_info.update({
                'lines_original': len(edit.original),
                'lines_modified': len(edit.modified),
                'range_start': edit_range[0] + 1,
                'range_end': edit_range[0] + len(edit.original)
            })
            
            # Create modified content
            modified_content = self.current_content[:]
            modified_content[edit_range[0]:edit_range[1]] = edit.modified
            
            # Show side-by-side diff using panels
            header, columns = create_diff_columns(
                self.current_content[edit_range[0]:edit_range[1]],  # Original section
                edit.modified,                                       # Modified section
                str(edit.filename),
                edit_range[0],
                self.console.width
            )
            self.console.print(header)
            self.console.print(columns)
            
            self._last_changed_line = edit_range[0] + len(edit.original)
            self.current_content[edit_range[0]:edit_range[1]] = edit.modified

        self.changes_summary.append(change_info)
        return change_info