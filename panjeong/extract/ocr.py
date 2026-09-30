"""OCR — Tesseract(kor+eng). 한국어 traineddata가 음절 사이에 넣는 공백을 정리한다."""
from __future__ import annotations

import re
from pathlib import Path

_HANGUL_GAP = re.compile(r"(?<=[가-힣])[ \t]+(?=[가-힣])")
_OPEN_PAREN = re.compile(r"\([ \t]+")
_CLOSE_PAREN = re.compile(r"[ \t]+\)")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def clean_ocr_text(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        s = _HANGUL_GAP.sub("", line)
        s = _OPEN_PAREN.sub("(", s)
        s = _CLOSE_PAREN.sub(")", s)
        s = _MULTI_SPACE.sub(" ", s).strip()
        if s:
            lines.append(s)
    return "\n".join(lines)


# ---- 사진 전처리 (09-28) — 탁자 위에 놓고 찍은 영수증: 글자 덩어리를 찾아 기울기를 바로잡고 잘라 이진화한다.
# 종이를 밝기·채도로 찾으면 흰 대리석·스테인리스 탁자에서 무너져서(Gemini 합성 사진 R2·R3) 「흰 바탕 위 가는 검은 획」을 찾는다.
# 가장자리가 순백인 이미지(스캔·목데이터 data/images)는 손대지 않는다 — tools/ocr_smoke.py 20/20 유지.
_WORK_W = 800             # 찾기·기울기 추정은 이 폭으로 줄여서
_INK = 90                 # 검은 획 대비(주변 5px 최댓값 − 자기 값) 문턱. 대리석 결·나무결은 이보다 옅다.
_MERGE = 21               # 글자들을 한 덩어리로 잇는 거리(작업 폭 px)
_PAD = 12                 # 덩어리 밖 여유(작업 폭 px)
_MAX_TILT = 25
_SCAN_SAT, _SCAN_VAL, _SCAN_FRAME = 40, 235, 0.6   # 가장자리 띠의 60%가 순백이면 스캔


def _row_variance(ink, angle: float) -> float:
    from PIL import Image
    r = ink.rotate(angle, resample=Image.BILINEAR, expand=True)
    rows = r.resize((1, r.size[1]), Image.BOX).tobytes()          # 줄마다 잉크 평균(L 모드 1바이트)
    m = sum(rows) / len(rows)
    return sum((v - m) ** 2 for v in rows) / len(rows)


def _skew(ink) -> float:
    coarse = max((_row_variance(ink, a / 2), a / 2) for a in range(-_MAX_TILT * 2, _MAX_TILT * 2 + 1))[1]
    return max((_row_variance(ink, coarse + a / 4), coarse + a / 4) for a in range(-2, 3))[1]


def _is_scan(small) -> bool:
    from PIL import ImageChops
    _, sat, val = small.convert("HSV").split()
    white = ImageChops.multiply(sat.point(lambda v: 255 if v < _SCAN_SAT else 0), val.point(lambda v: 255 if v > _SCAN_VAL else 0))
    w, h = white.size
    b = max(2, int(min(w, h) * 0.04))
    strips = [white.crop(box) for box in ((0, 0, w, b), (0, h - b, w, h), (0, 0, b, h), (w - b, 0, w, h))]
    return sum(x.histogram()[255] for x in strips) / sum(x.size[0] * x.size[1] for x in strips) > _SCAN_FRAME


def _block_bbox(ink, tall: bool):
    """글자가 가장 빽빽한 곳과 이어진 글자 덩어리의 경계 상자 — 컵·수저·탁자 결은 떨어져 있어 빠진다.
    tall이면 세로를 반으로 눌러 이어 세로로는 두 배 거리까지 붙인다(큰 상호 줄은 아래 줄과 간격이 넓다 — R6)."""
    from PIL import Image, ImageDraw, ImageFilter
    blob = ink.resize((ink.size[0], max(1, ink.size[1] // 2)), Image.BOX).point(lambda v: 255 if v else 0) if tall else ink
    blob = blob.filter(ImageFilter.MaxFilter(_MERGE))
    w, h = blob.size
    cell = blob.resize((max(1, w // 8), max(1, h // 8)), Image.BOX).filter(ImageFilter.BoxBlur(3))
    cw = cell.size[0]
    data = cell.tobytes()
    i = max(range(len(data)), key=data.__getitem__)
    sx, sy = min(w - 1, (i % cw) * 8 + 4), min(h - 1, (i // cw) * 8 + 4)
    px = blob.load()
    if px[sx, sy] != 255:
        near = [(x, y) for x in range(max(0, sx - 60), min(w, sx + 60), 2) for y in range(max(0, sy - 60), min(h, sy + 60), 2)
                if px[x, y] == 255]
        if not near:
            return None
        sx, sy = min(near, key=lambda p: (p[0] - sx) ** 2 + (p[1] - sy) ** 2)
    ImageDraw.floodfill(blob, (sx, sy), 128)
    bb = blob.point(lambda v: 255 if v == 128 else 0).getbbox()
    if bb is None or not tall:
        return bb
    return (bb[0], bb[1] * 2, bb[2], min(ink.size[1], bb[3] * 2))


def _otsu(gray) -> int:
    hist = gray.histogram()
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    w0 = s0 = 0
    best, thr = -1.0, 128
    for t in range(256):
        w0 += hist[t]
        if w0 == 0 or w0 == total:
            continue
        s0 += t * hist[t]
        m0, m1 = s0 / w0, (sum_all - s0) / (total - w0)
        between = w0 * (total - w0) * (m0 - m1) ** 2
        if between > best:
            best, thr = between, t
    return thr


def prepare_photo(im):
    """사진이면 (후보 이미지 목록, 정보), 아니면 ([원본], 정보). 정보 = photo·angle·bbox.
    후보 = 글자 덩어리를 두 방식(보통·세로로 길게)으로 잘라 기울기를 바로잡고 이진화한 것 — 어느 쪽이 나은지는 사진마다 달라서
    image_to_text가 둘 다 읽고 Tesseract 신뢰도가 높은 쪽을 쓴다."""
    from PIL import Image, ImageChops, ImageFilter, ImageOps
    no = ([im], {"photo": False, "angle": 0.0, "bbox": None})
    rgb = im.convert("RGB")
    W, H = rgb.size
    k = _WORK_W / W
    small = rgb.resize((_WORK_W, max(1, round(H * k))))
    if _is_scan(small):
        return no
    L = small.convert("L")
    ink = ImageChops.subtract(L.filter(ImageFilter.MaxFilter(5)), L).point(lambda v: 255 if v > _INK else 0)
    b1 = _block_bbox(ink, tall=False)                       # 1차: 기울기 모른 채 글자 덩어리
    if b1 is None:
        return no
    angle = _skew(ink.crop(b1))                             # 그 안에서만 기울기 — 컵 테두리·탁자 결이 끼지 않게
    rot = ink.rotate(angle, expand=True)
    gray = rgb.convert("L").rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    kx, ky = gray.size[0] / rot.size[0], gray.size[1] / rot.size[1]
    cands, boxes = [], []
    for tall in (False, True):                              # 2차: 바로 세운 뒤 다시
        bbox = _block_bbox(rot, tall=tall)
        if bbox is None or (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < 0.03 * rot.size[0] * rot.size[1] or bbox in boxes:
            continue
        x0, y0, x1, y1 = bbox
        g = gray.crop((max(0, int((x0 - _PAD) * kx)), max(0, int((y0 - _PAD) * ky)),
                       min(gray.size[0], int((x1 + _PAD) * kx)), min(gray.size[1], int((y1 + _PAD) * ky))))
        g = ImageOps.autocontrast(g, cutoff=1)
        t = _otsu(g)
        cands.append(g.point(lambda v: 255 if v > t else 0))
        boxes.append(bbox)
    if not cands:
        return no
    return cands, {"photo": True, "angle": angle, "bbox": boxes[0]}


def _ocr_with_conf(img, lang: str):
    """(텍스트, 글자 수로 가중한 평균 신뢰도) — image_to_data 한 번으로 둘 다."""
    import pytesseract
    d = pytesseract.image_to_data(img, lang=lang, config="--psm 6", output_type=pytesseract.Output.DICT)
    lines: dict = {}
    num = den = 0.0
    for i, w in enumerate(d["text"]):
        w = (w or "").strip()
        c = float(d["conf"][i])
        if not w or c < 0:
            continue
        lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(w)
        num += c * len(w)
        den += len(w)
    return "\n".join(" ".join(ws) for ws in lines.values()), (num / den if den else 0.0)


def image_to_text(path: str | Path, lang: str = "kor+eng") -> str:
    import pytesseract
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)       # 폰 사진의 회전 정보
        cands, info = prepare_photo(im)
        if not info["photo"]:                  # 스캔·흰 바탕은 예전 그대로
            raw = pytesseract.image_to_string(cands[0].convert("RGB"), lang=lang, config="--psm 6")
        else:
            raw = max((_ocr_with_conf(c.convert("RGB"), lang) for c in cands), key=lambda tc: tc[1])[0]
    return clean_ocr_text(raw)
