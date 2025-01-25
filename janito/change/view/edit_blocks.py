# ...existing code...
            elif current_command == "Edit":
                original = trim_block(before_block or [])
                modified = trim_block(current_block)
                # Remove debug print
                edit_blocks.append(CodeChange(
                    filename, reason,
                    original,
                    modified,
                    EditType.EDIT,
                    current_marker
                ))
# ...existing code...
