from discord.ext import commands

# Save original functions to avoid recursion loops
_original_has_role = commands.has_role
_original_has_any_role = commands.has_any_role

def _patched_has_role(item):
    """Overrides has_role to treat 'Admin' as 'Admin' OR 'Pxl'"""
    if isinstance(item, str) and item.lower() == 'admin':
        return _original_has_any_role('Admin', 'Pxl')
    return _original_has_role(item)

def _patched_has_any_role(*items):
    """Overrides has_any_role to add 'Pxl' if 'Admin' is checked"""
    items_lower = [i.lower() if isinstance(i, str) else i for i in items]
    if 'admin' in items_lower and 'pxl' not in items_lower:
        items = tuple(list(items) + ['Pxl'])
    return _original_has_any_role(*items)

def apply_alias():
    """Applies the alias globally to discord.py decorators."""
    commands.has_role = _patched_has_role
    commands.has_any_role = _patched_has_any_role
    print("[System] Loaded Pxl role alias: 'Pxl' now has Admin permissions.")

# Automatically apply the alias when this module is imported
apply_alias()
