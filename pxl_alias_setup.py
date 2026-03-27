import os

ALIAS_CODE = """from discord.ext import commands

# Save original functions to avoid recursion loops
_original_has_role = commands.has_role
_original_has_any_role = commands.has_any_role

# ==========================================
# ADD YOUR EXTRA ROLES HERE
# ==========================================
EQUIVALENT_ROLES = ['Pxl', 'Moon'] 

def _patched_has_role(item):
    \"\"\"Overrides has_role to treat 'Admin' as 'Admin' OR equivalent roles\"\"\"
    if isinstance(item, str) and item.lower() == 'admin':
        return _original_has_any_role('Admin', *EQUIVALENT_ROLES)
    return _original_has_role(item)

def _patched_has_any_role(*items):
    \"\"\"Overrides has_any_role to add equivalent roles if 'Admin' is checked\"\"\"
    items_lower = [i.lower() if isinstance(i, str) else i for i in items]
    if 'admin' in items_lower:
        # Add equivalent roles that aren't already in the list
        extra_roles = [role for role in EQUIVALENT_ROLES if role.lower() not in items_lower]
        if extra_roles:
            items = tuple(list(items) + extra_roles)
    return _original_has_any_role(*items)

def apply_alias():
    \"\"\"Applies the alias globally to discord.py decorators.\"\"\"
    commands.has_role = _patched_has_role
    commands.has_any_role = _patched_has_any_role
    print(f"[System] Loaded role aliases: {', '.join(EQUIVALENT_ROLES)} now have Admin permissions.")

# Automatically apply the alias when this module is imported
apply_alias()
"""

def install_alias():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tle_dir = os.path.join(base_dir, 'tle')
    alias_file_path = os.path.join(tle_dir, 'pxl_alias.py')
    main_file_path = os.path.join(tle_dir, '__main__.py')

    if not os.path.exists(tle_dir):
        print("Error: Could not find the 'tle' directory. Please run this script from the root folder of the bot.")
        return

    # 1. Create the alias module file inside the tle/ folder
    with open(alias_file_path, 'w', encoding='utf-8') as f:
        f.write(ALIAS_CODE)
    print(f"Created alias module at {os.path.relpath(alias_file_path)}")

    # 2. Inject the import into tle/__main__.py so it runs when the bot starts
    if os.path.exists(main_file_path):
        with open(main_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'import tle.pxl_alias' not in content:
            # Find the last import line to keep the file clean
            lines = content.split('\n')
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_idx = i + 1
            
            lines.insert(insert_idx, "import tle.pxl_alias  # Injects extra roles as Admin")
            
            with open(main_file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            print(f"Patched {os.path.relpath(main_file_path)} to load the alias automatically.")
        else:
            print(f"Alias import already exists in {os.path.relpath(main_file_path)}.")
    else:
        print(f"Warning: {main_file_path} not found. You'll need to manually add 'import tle.pxl_alias' to your bot's entry file.")

    print("\nSuccess! The role aliases have been successfully installed.")

if __name__ == '__main__':
    install_alias()
