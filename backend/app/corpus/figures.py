"""Find the figures on a manual page and crop them from a render of the page.

The manuals draw their figures as vector line art, and a few use pictures. There is no
ready-made image to pull out and no caption: a figure has part labels only. So a figure
is found as a region of the page that is dense with drawing strokes or covered by a
picture, and is cut out of a render. The numbers below were set by looking at the crops
from several manuals; a table (straight rules) and a warning icon (too small) are left out.

Known limits: figures stacked closely in the newer step-table layout can come out as
one crop, and text beside a figure can be cut at the crop's edge.
"""

import io

import pypdfium2 as pdfium
import pypdfium2.raw as raw

GAP = 5  # pt: strokes closer than this belong to one figure
MIN_SIDE = 60  # pt: anything smaller is an icon, a bullet or a logo
MIN_CURVES = 150  # line art is made of curves, a table is not
MIN_DENSITY = 8  # curve segments per 1,000 square pt
MIN_PICTURE = 0.3  # share of a region covered by pictures
FRAME_SEGMENTS = 16  # a long path this simple is a rule or a frame, not part of a drawing
FRAME_SIDE = 90  # pt
MARGIN = 6  # pt kept around a figure
DPI = 110

# One candidate: left, bottom, right, top, curve segments, picture area.
Box = list[float]


def _curves(path) -> int:
    return sum(
        raw.FPDFPathSegment_GetType(raw.FPDFPath_GetPathSegment(path, i))
        == raw.FPDF_SEGMENT_BEZIERTO
        for i in range(raw.FPDFPath_CountSegments(path))
    )


def _curves_in_form(form) -> int:
    total = 0
    for i in range(raw.FPDFFormObj_CountObjects(form)):
        child = raw.FPDFFormObj_GetObject(form, i)
        kind = raw.FPDFPageObj_GetType(child)
        if kind == raw.FPDF_PAGEOBJ_PATH:
            total += _curves(child)
        elif kind == raw.FPDF_PAGEOBJ_FORM:
            total += _curves_in_form(child)
    return total


def _candidates(page: pdfium.PdfPage) -> list[Box]:
    """Every drawing object on the page that could be part of a figure."""
    width, height = page.get_size()
    boxes = []
    for obj in page.get_objects(max_depth=1):
        left, bottom, right, top = obj.get_bounds()
        left, bottom, right, top = max(left, 0), max(bottom, 0), min(right, width), min(top, height)
        if right <= left or top <= bottom:
            continue
        if obj.type == raw.FPDF_PAGEOBJ_PATH:
            simple = raw.FPDFPath_CountSegments(obj.raw) <= FRAME_SEGMENTS
            if not (simple and max(right - left, top - bottom) > FRAME_SIDE):
                boxes.append([left, bottom, right, top, _curves(obj.raw), 0.0])
        elif obj.type == raw.FPDF_PAGEOBJ_FORM:
            curves = _curves_in_form(obj.raw)
            if curves:  # a form holding only text or rules is not a drawing
                boxes.append([left, bottom, right, top, curves, 0.0])
        elif obj.type in (raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_SHADING):
            boxes.append([left, bottom, right, top, 0, (right - left) * (top - bottom)])
    return boxes


def _near(a: Box, b: Box) -> bool:
    return a[0] <= b[2] + GAP and b[0] <= a[2] + GAP and a[1] <= b[3] + GAP and b[1] <= a[3] + GAP


def regions(page: pdfium.PdfPage) -> list[tuple[float, float, float, float]]:
    """The figures on the page as (left, bottom, right, top) in points, in reading order."""
    boxes = _candidates(page)
    merged = True
    while merged:  # join boxes that touch or nearly touch, until nothing changes
        merged = False
        groups: list[Box] = []
        for box in sorted(boxes):
            for group in groups:
                if _near(box, group):
                    group[:] = [
                        min(group[0], box[0]),
                        min(group[1], box[1]),
                        max(group[2], box[2]),
                        max(group[3], box[3]),
                        group[4] + box[4],
                        group[5] + box[5],
                    ]
                    merged = True
                    break
            else:
                groups.append(box)
        boxes = groups
    found = []
    for left, bottom, right, top, curves, pictures in boxes:
        area = (right - left) * (top - bottom)
        if right - left < MIN_SIDE or top - bottom < MIN_SIDE:
            continue
        drawing = curves >= MIN_CURVES and curves / area * 1000 >= MIN_DENSITY
        if drawing or pictures / area >= MIN_PICTURE:
            found.append((left, bottom, right, top))
    return sorted(found, key=lambda box: (-box[3], box[0]))  # top first, then left


def page_figures(page: pdfium.PdfPage) -> list[bytes]:
    """Each figure on the page as PNG bytes, in reading order. Empty if there is none."""
    found = regions(page)
    if not found:
        return []
    scale = DPI / 72
    _, height = page.get_size()
    render = page.render(scale=scale).to_pil()
    figures = []
    for left, bottom, right, top in found:
        crop = render.crop(
            (
                max(int((left - MARGIN) * scale), 0),
                max(int((height - top - MARGIN) * scale), 0),
                min(int((right + MARGIN) * scale), render.width),
                min(int((height - bottom + MARGIN) * scale), render.height),
            )
        )
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG", optimize=True)
        figures.append(buffer.getvalue())
    return figures


PAGE_DPI = 100  # about 830 x 1170 px for A4: legible, and some 1,300 image tokens


def page_png(page: pdfium.PdfPage) -> bytes:
    """The whole page as PNG bytes, for the model to read (/ask)."""
    buffer = io.BytesIO()
    render = page.render(scale=PAGE_DPI / 72).to_pil().convert("RGB")
    render.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
