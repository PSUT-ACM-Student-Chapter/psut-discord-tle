# cd /home/ubuntu/psut-discord-tle

poetry run python -c "
import os, shutil
from tle import constants

# Ask the bot for the exact folder it wants
correct_dir = os.path.dirname(constants.NOTO_SANS_CJK_BOLD_FONT_PATH)
os.makedirs(correct_dir, exist_ok=True)

fonts = ['NotoSansCJK-Bold.ttc', 'NotoSansCJK-Regular.ttc', 'NotoSans-Regular.ttf', 'NotoSans-Bold.ttf', 'NotoSans-Italic.ttf']

for f in fonts:
    src_path = f'/home/ubuntu/psut-discord-tle/tle/assets/fonts/{f}'
    dest_path = os.path.join(correct_dir, f)
    
    # Move the font to the correct folder, or download it if it's somehow missing
    if os.path.exists(src_path):
        shutil.copy(src_path, dest_path)
        print(f'✅ Successfully placed {f} into {correct_dir}')
    else:
        print(f'Downloading {f} directly to {correct_dir}...')
        url = f'https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTC/{f}' if 'CJK' in f else f'https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/{f}'
        os.system(f'curl -s -L -o \"{dest_path}\" {url}')
"

# Fire it back up!
./run.sh
