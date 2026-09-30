"""사진 영수증 전처리 — 종이만 잘라 기울기를 바로잡은 뒤 OCR.
09-28 Gemini 합성 사진(나무 탁자 위 감열지, 12° 기울기)에서 전처리 없이는 상호가 사라지고 날짜가 깨졌다.
종이를 밝기·채도로 찾던 첫 방식은 흰 대리석·스테인리스 탁자에서 무너져 「흰 바탕 위 가는 검은 획」 덩어리를 찾는 방식으로 바꿨다.
흰 바탕 이미지(data/images 목데이터)는 손대지 않는다 — ocr_smoke 20/20이 그대로여야 한다."""
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from panjeong.extract.ocr import image_to_text, prepare_photo
from panjeong.extract.prompt import refine_with_text

WOOD = (160, 110, 60)
FIX = Path(__file__).parent / "fixtures"


def _receipt(w=400, h=600):
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    for i, y in enumerate(range(40, h - 40, 30)):
        d.rectangle((30, y, w - 40 - (i * 37) % 150, y + 12), fill="black")   # 글자 줄 대신 막대
    return im


def _photo(angle):
    paper = _receipt().rotate(angle, expand=True, fillcolor=WOOD)
    bg = Image.new("RGB", (900, 1100), WOOD)
    bg.paste(paper, (150, 120))
    return bg


@pytest.mark.parametrize("tilt", [12, -8])
def test_photo_on_a_table_is_cropped_and_deskewed(tilt):
    cands, info = prepare_photo(_photo(tilt))
    assert info["photo"] is True and cands
    assert abs(info["angle"] + tilt) <= 1          # 종이를 tilt만큼 돌려 놓았으니 -tilt만큼 되돌린다
    assert all(c.size[0] < 900 and c.size[1] < 1100 for c in cands)


def test_clean_white_image_is_left_alone():
    im = _receipt()
    cands, info = prepare_photo(im)
    assert info["photo"] is False and cands == [im]


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract 없음")
@pytest.mark.parametrize("name, vendor, when, total", [
    ("photo_R1_normal.jpeg", "한식당미가", "2026-06-12 12:40", 52800),   # 나무 탁자
    ("photo_R3_normal.jpeg", "국밥집온기", "2026-06-13 12:20", 33000),   # 스테인리스 탁자 — 밝기·채도로는 종이와 못 가른다
])
def test_gemini_receipt_photo_reads_vendor_datetime_and_total(name, vendor, when, total):
    t = image_to_text(FIX / name)
    assert vendor in t.replace(" ", "")
    assert when in t
    assert refine_with_text({"category": "회의비"}, t).get("amount_total") == total
