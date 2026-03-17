import os
import re

def patch_font_downloader():
    filepath = 'tle/util/font_downloader.py'
    with open(filepath, 'r') as f:
        content = f.read()

    if 'NotoEmoji-unhinted.zip' in content:
        print('✅ font_downloader.py is already patched.')
        return

    # Add NotoEmoji link to the FONTS list
    target = "'https://noto-website-2.storage.googleapis.com/pkgs/NotoSansCJKjp-hinted.zip',"
    replacement = target + "\n    'https://noto-website-2.storage.googleapis.com/pkgs/NotoEmoji-unhinted.zip',"
    
    new_content = content.replace(target, replacement)
    
    with open(filepath, 'w') as f:
        f.write(new_content)
    print('✅ Patched tle/util/font_downloader.py')

def patch_graph_common():
    filepath = 'tle/util/graph_common.py'
    with open(filepath, 'r') as f:
        content = f.read()

    if "'Noto Emoji'" in content:
        print('✅ graph_common.py is already patched.')
        return

    # Look for plt.rcParams['font.sans-serif'] = [...] and insert 'Noto Emoji'
    pattern = r"(plt\.rcParams\['font\.sans-serif'\]\s*=\s*\[)([^\]]+)(\])"
    
    def replacer(match):
        prefix = match.group(1)
        items = match.group(2)
        suffix = match.group(3)
        # Add Noto Emoji as a fallback just before the generic 'sans-serif'
        if "'sans-serif'" in items:
            items = items.replace("'sans-serif'", "'Noto Emoji', 'sans-serif'")
        else:
            items += ", 'Noto Emoji'"
        return prefix + items + suffix

    new_content = re.sub(pattern, replacer, content)
    
    with open(filepath, 'w') as f:
        f.write(new_content)
    print('✅ Patched tle/util/graph_common.py')

if __name__ == '__main__':
    print('Patching TLE to support emojis in graphs...')
    
    if not os.path.exists('tle'):
        print('❌ Error: Please run this script from the root directory of the bot (where the "tle" folder is).')
    else:
        patch_font_downloader()
        patch_graph_common()
        print('\n🎉 Done! Next steps:')
        print('1. Run: python -m tle.util.font_downloader')
        print('2. Restart your discord bot.')
