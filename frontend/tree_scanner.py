import os
from pathlib import Path

def print_tree(directory, prefix=""):
    """
    Recursively prints a visual tree structure of a directory,
    ignoring hidden items (starting with '.') and 'node_modules'.
    """
    try:
        # Filter out items starting with '.' or named 'node_modules'
        items = [
            x for x in directory.iterdir() 
            if not x.name.startswith('.') and x.name != 'node_modules'
        ]
        # Sort: folders first, then files alphabetically
        items = sorted(items, key=lambda x: (x.is_file(), x.name.lower()))
    except PermissionError:
        return  # Skip directories without permission

    for i, item in enumerate(items):
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        
        print(f"{prefix}{connector}{item.name}")
        
        if item.is_dir():
            next_prefix = prefix + ("    " if is_last else "│   ")
            print_tree(item, next_prefix)

if __name__ == "__main__":
    # Get the directory where this script is located
    script_dir = Path(__file__).resolve().parent
    
    print(f"Directory Tree for: {script_dir}")
    print("📂 .")
    print_tree(script_dir)
