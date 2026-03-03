import logging
import os
import urllib.request
import zipfile

from zipfile import ZipFile
from io import BytesIO

from tle import constants

URL_BASE = 'https://noto-website-2.storage.googleapis.com/pkgs/'
FONTS = [constants.NOTO_SANS_CJK_BOLD_FONT_PATH,
         constants.NOTO_SANS_CJK_REGULAR_FONT_PATH]

logger = logging.getLogger(__name__)


def _unzip(font, archive):
    with ZipFile(archive) as zipfile_obj:
        if font not in zipfile_obj.namelist():
            raise KeyError(f'Expected font file {font} not present in downloaded zip archive.')
        zipfile_obj.extract(font, constants.FONTS_DIR)


def _download(font_path):
    font = os.path.basename(font_path)
    logger.info(f'Downloading font `{font}`.')
    with urllib.request.urlopen(f'{URL_BASE}{font}.zip') as resp:
        _unzip(font, BytesIO(resp.read()))


def maybe_download():
    # Make sure the font directory exists
    os.makedirs(constants.FONTS_DIR, exist_ok=True)

    # 1. Download original fonts defined in constants (CJK fonts)
    for font_path in FONTS:
        if not os.path.isfile(font_path):
            _download(font_path)

    # 2. Download Arabic Font (New behavior for Arabic text rendering)
    arabic_font_path = os.path.join(constants.FONTS_DIR, 'NotoSansArabic-Regular.ttf')
    if not os.path.isfile(arabic_font_path):
        logger.info('Downloading Arabic font...')
        
        # Try a few stable direct TTF links since Google's zip bucket throws 403 Forbidden
        arabic_urls = [
            'https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSansArabic/NotoSansArabic-Regular.ttf',
            'https://raw.githubusercontent.com/googlefonts/noto-fonts/main/unhinted/ttf/NotoSansArabic/NotoSansArabic-Regular.ttf',
            'https://raw.githubusercontent.com/google/fonts/main/ofl/notosansarabic/static/NotoSansArabic-Regular.ttf'
        ]
        
        success = False
        for url in arabic_urls:
            try:
                # Adding a User-Agent header helps prevent 403 blocks from CDNs
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as resp, open(arabic_font_path, 'wb') as out_file:
                    out_file.write(resp.read())
                success = True
                logger.info(f'Successfully downloaded Arabic font from {url}')
                break
            except Exception as e:
                logger.warning(f"Failed to download from {url}: {e}")
                
        if not success:
            logger.error("Could not download the Arabic font from any source.")
