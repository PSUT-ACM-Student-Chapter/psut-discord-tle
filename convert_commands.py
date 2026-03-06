from pathlib import Path

def convert_to_hybrid():
    # Target the cogs folder
    cogs_dir = Path('tle/cogs')
    
    if not cogs_dir.exists():
        print("Error: Could not find 'tle/cogs'. Make sure you run this from the root folder.")
        return

    # Keep track of how many files we change
    count = 0

    # Loop through every Python file in the cogs folder and subfolders
    for filepath in cogs_dir.rglob('*.py'):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Store original content to check if changes were made
        original_content = content

        # 1. Change standard commands
        content = content.replace('@commands.command', '@commands.hybrid_command')
        
        # 2. Change command groups
        content = content.replace('@commands.group', '@commands.hybrid_group')
        
        # 3. Change 'brief=' to 'description=' (Slash commands require 'description')
        content = content.replace('brief=', 'description=')
        content = content.replace('brief =', 'description=')

        # If we modified the file, save it
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Converted commands in: {filepath.name}")
            count += 1

    print(f"\n🎉 Done! Successfully updated {count} files.")

if __name__ == '__main__':
    convert_to_hybrid()
