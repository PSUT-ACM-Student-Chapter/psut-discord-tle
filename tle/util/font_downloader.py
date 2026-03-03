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

ARABIC_FONT_URL = 'https://noto-website-2.storage.googleapis.com/pkgs/NotoSansArabic-unhinted.zip'

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
    os.makedirs(constants.FONTS_DIR, exist_ok=True)

    for font_path in FONTS:
        if not os.path.isfile(font_path):
            _download(font_path)

    arabic_font_path = os.path.join(constants.FONTS_DIR, 'NotoSansArabic-Regular.ttf')
    if not os.path.isfile(arabic_font_path):
        logger.info('Downloading Arabic font...')
        urllib.request.urlretrieve(ARABIC_FONT_URL, 'arabic_font.zip')
        with ZipFile('arabic_font.zip', 'r') as zip_ref:
            zip_ref.extractall(constants.FONTS_DIR)
        os.remove('arabic_font.zip')
