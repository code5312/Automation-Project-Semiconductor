"""PDF handover report generation.

Renders one event + its handover history into a printable "인수인계
보고서" (handover report) PDF. No new business logic lives here -- this
only formats event/handover dicts that src.storage.repository already
produces (the same ones the API/dashboard show).

Korean text: we embed an actual Korean TrueType font (Windows' Malgun
Gothic, found at a handful of common install paths) rather than
referencing one of ReportLab's built-in CID fonts by name only. The CID
approach ships no font file, but was tried first and rejected here --
verified by actually rendering a sample report: any viewer without a
matching system Korean font draws the Hangul glyphs as zero-width blanks,
which also breaks table column layout (cells collapse into their
neighbors). Embedding guarantees correct rendering regardless of the
viewer. If no Korean TTF is found on the machine building the PDF (e.g.
a non-Windows box with none installed), this falls back to the
non-embedded CID fonts with the caveat above -- see README.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# (regular, bold) candidate paths, checked in order, per platform.
_TTF_CANDIDATES: list[tuple[str, str]] = [
    (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"),  # Windows: Malgun Gothic
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", "/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
]


def _register_fonts() -> tuple[str, str]:
    """Returns (body_font_name, heading_font_name), embedding a real TTF
    when one can be found, else falling back to non-embedded CID fonts."""
    for regular_path, bold_path in _TTF_CANDIDATES:
        if Path(regular_path).is_file():
            pdfmetrics.registerFont(TTFont("KoreanBody", regular_path))
            bold_source = bold_path if Path(bold_path).is_file() else regular_path
            pdfmetrics.registerFont(TTFont("KoreanHeading", bold_source))
            return "KoreanBody", "KoreanHeading"

    body, heading = "HYSMyeongJo-Medium", "HYGothic-Medium"
    for font in (body, heading):
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(font))
    return body, heading


BODY_FONT, HEADING_FONT = _register_fonts()

INK_SECONDARY = colors.HexColor("#52514e")
BORDER = colors.HexColor("#e1e0d9")
HEADER_BG = colors.HexColor("#f2f1ec")

DEPT_LABELS = {
    "YI": "YI (수율개선)",
    "MFG": "MFG (제조)",
    "M-ENG": "M-ENG (설비기술)",
    "P-ENG": "P-ENG (공정기술)",
}


def _format_dt(iso_str: str) -> str:
    """Compact 'YYYY-MM-DD HH:MM' for table cells -- the full ISO8601
    string (with microseconds/offset) is too wide for a narrow column and
    overlaps the next cell."""
    try:
        return datetime.fromisoformat(iso_str).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_str


def _dept_label(dept: Optional[str]) -> str:
    if dept is None:
        return "(없음)"
    return DEPT_LABELS.get(dept, dept)


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("KTitle", parent=base["Title"], fontName=HEADING_FONT, fontSize=18, leading=22),
        "heading": ParagraphStyle(
            "KHeading", parent=base["Heading2"], fontName=HEADING_FONT,
            fontSize=12, leading=16, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle("KBody", parent=base["BodyText"], fontName=BODY_FONT, fontSize=9.5, leading=13),
        "small": ParagraphStyle(
            "KSmall", parent=base["BodyText"], fontName=BODY_FONT,
            fontSize=8, leading=11, textColor=INK_SECONDARY,
        ),
    }


def _table(rows: list[list[str]], col_widths: list[float], header: bool = True) -> Table:
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [
            ("FONTNAME", (0, 0), (-1, 0), HEADING_FONT),
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ]
    t.setStyle(TableStyle(style))
    return t


def _vibration_summary(vibration: dict) -> str:
    parts = [f"모드: {vibration['mode']}", f"RMS: {vibration['rms']:.4f}"]
    if vibration.get("health_index") is not None:
        parts.append(f"health_index: {vibration['health_index']:.2f}")
    elif vibration.get("kurtosis") is not None:
        parts.append(f"kurtosis: {vibration['kurtosis']:.2f}")
        parts.append(f"crest_factor: {vibration['crest_factor']:.2f}")
    return ", ".join(parts)


def generate_handover_pdf(event: dict, handovers: list[dict], out_path: str | Path) -> Path:
    """Render one event + its handover history to a PDF at out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    styles = _styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"인수인계 보고서 {event['event_id']}",
    )

    diagnosis = event["diagnosis"]
    signals = event["signals"]
    vision, sensor, vibration = signals["vision"], signals["sensor"], signals["vibration"]
    current_dept = handovers[-1]["to_dept"] if handovers else diagnosis["primary_dept"]

    story = [
        Paragraph("반도체 불량 대응 인수인계 보고서", styles["title"]),
        Paragraph(f"이벤트 ID: {event['event_id']}", styles["small"]),
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", color=colors.HexColor("#c3c2b7")),
        Spacer(1, 4 * mm),
        _table(
            [
                ["생성 시각", event["event_time"]],
                ["시나리오", event["scenario_id"]],
                ["시드", str(event["seed"])],
                ["시뮬레이션 데이터 여부", "예 (is_simulated=true)" if event["is_simulated"] else "아니오"],
            ],
            col_widths=[40 * mm, 130 * mm],
            header=False,
        ),
        Spacer(1, 6 * mm),
        Paragraph("판정 결과", styles["heading"]),
        _table(
            [
                ["규칙", diagnosis["rule_id"]],
                ["생성 시점 주관 부서", _dept_label(diagnosis["primary_dept"])],
                ["현재 담당 부서", _dept_label(current_dept)],
                ["보조 부서", ", ".join(_dept_label(d) for d in diagnosis["secondary_depts"]) or "-"],
                ["MFG Hold", "예" if diagnosis["mfg_hold"] else "아니오"],
            ],
            col_widths=[40 * mm, 130 * mm],
            header=False,
        ),
        Spacer(1, 4 * mm),
        Paragraph("판정 점수 (확률이 아닌, 근거 조합에 따른 상대 점수)", styles["body"]),
        _table(
            [["가설", "점수"]] + [[hyp, f"{score:.3f}"] for hyp, score in diagnosis["scores"].items()],
            col_widths=[60 * mm, 60 * mm],
        ),
        Spacer(1, 3 * mm),
    ]

    contrib_rows = [["가설", "세부 항목", "값"]]
    for hyp, contrib in diagnosis["contributions"].items():
        for item, val in contrib.items():
            contrib_rows.append([hyp, item, f"{val:.3f}"])
    story.append(_table(contrib_rows, col_widths=[35 * mm, 70 * mm, 30 * mm]))

    if diagnosis.get("notes"):
        story.append(Spacer(1, 3 * mm))
        for n in diagnosis["notes"]:
            story.append(Paragraph(f"• {n}", styles["small"]))

    story += [
        Spacer(1, 6 * mm),
        Paragraph("신호 요약", styles["heading"]),
        _table(
            [
                ["비전 (WM-811K)", f"패턴: {vision['pattern']} ({vision['pattern_group']})"],
                ["센서 (SECOM)", f"이상 점수: {sensor['anomaly_score']:.3f}"],
                ["진동 (NASA IMS)", _vibration_summary(vibration)],
            ],
            col_widths=[40 * mm, 130 * mm],
            header=False,
        ),
        Spacer(1, 6 * mm),
        Paragraph("핑퐁 (부서 재할당) 이력", styles["heading"]),
    ]

    if handovers:
        ho_rows = [["시각", "From", "To", "이유"]]
        for h in handovers:
            ho_rows.append(
                [_format_dt(h["created_at"]), _dept_label(h["from_dept"]), _dept_label(h["to_dept"]), h["reason"]]
            )
        story.append(_table(ho_rows, col_widths=[28 * mm, 34 * mm, 34 * mm, 74 * mm]))
    else:
        story.append(Paragraph("재할당 이력이 없습니다.", styles["body"]))

    story += [
        Spacer(1, 8 * mm),
        HRFlowable(width="100%", color=BORDER),
        Spacer(1, 2 * mm),
        Paragraph(
            "본 보고서는 실제 반도체 팹 데이터가 아닌 시뮬레이션 데이터(UCI SECOM / NASA IMS 베어링 / "
            "WM-811K 조합)로 생성된 PoC 결과입니다. 판정 점수는 확률이 아니며 근거 조합에 따른 상대 "
            "점수입니다.",
            styles["small"],
        ),
    ]

    doc.build(story)
    return out_path
