import os
import re
import urllib.request
import glob

def download_emoji_font():
    # URL for the most up-to-date black & white Noto Emoji font (version-locked to avoid 404s)
    font_url = "https://raw.githubusercontent.com/googlefonts/noto-emoji/v2.038/fonts/NotoEmoji-Regular.ttf"
    
    # TLE uses either tle/assets/fonts or data/assets/fonts depending on the version
    dirs_to_check = ['tle/assets/fonts', 'data/assets/fonts']
    success = False
    
    for d in dirs_to_check:
        if os.path.exists(d):
            filepath = os.path.join(d, 'NotoEmoji-Regular.ttf')
            if not os.path.exists(filepath):
                print(f"⬇️ Downloading Noto Emoji to {d}...")
                try:
                    # Using Request to add a User-Agent, preventing potential 403/404 blocks
                    req = urllib.request.Request(font_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as response, open(filepath, 'wb') as out_file:
                        out_file.write(response.read())
                    print(f"✅ Saved to {filepath}")
                    success = True
                except Exception as e:
                    print(f"❌ Failed to download to {d}: {e}")
            else:
                print(f"✅ Noto Emoji already exists in {d}")
                success = True
                
    return success

def patch_graph_common():
    filepath = 'tle/util/graph_common.py'
    if not os.path.exists(filepath):
        print(f"⚠️ Could not find {filepath}. Skipping.")
        return

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

def clear_matplotlib_cache():
    try:
        import matplotlib
        cachedir = matplotlib.get_cachedir()
        cache_files = glob.glob(os.path.join(cachedir, 'font*.json'))
        if not cache_files:
            print("✅ Matplotlib cache already clean.")
        for f in cache_files:
            os.remove(f)
            print(f"✅ Cleared matplotlib cache: {f}")
    except ImportError:
        print("⚠️ Matplotlib not installed in this python environment. Skipping cache clear.")
        print("   (If emojis still don't show, try running this script inside `poetry shell`)")
    except Exception as e:
        print(f"⚠️ Could not completely clear matplotlib cache: {e}")

if __name__ == '__main__':
    print('🔧 Applying advanced Emoji patch...')
    
    if not os.path.exists('tle'):
        print('❌ Error: Please run this script from the root directory of the bot (where the "tle" folder is).')
    else:
        download_emoji_font()
        patch_graph_common()
        clear_matplotlib_cache()
        
        print('\n🎉 Done! Next steps:')
        print('1. You do not need to run font_downloader manually anymore.')
        print('2. Restart your discord bot to see the emojis!')
