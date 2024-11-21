def clear_file(file_path):
    """Clears the contents of the specified file."""
    try:
        with open(file_path, 'w') as file:
            pass  # Opening in 'w' mode clears the file
        print(f"File '{file_path}' has been cleared.")
    except Exception as e:
        print(f"Error clearing file '{file_path}': {e}")
