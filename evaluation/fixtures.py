"""Synthetic deterministic financial PDF fixtures and test case definitions.

Provides deterministic multi-page financial PDF fixtures with conflicting values
on the same page, explicit table units, period headers, and known correct figures.
Used by scripts/evaluate.py to verify grounded retrieval, source selection locking,
abstention on missing evidence, and authorization denial boundaries.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AUDITED_REPORT_FILENAME = "alpha_fy2024_audited_report.pdf"
DRAFT_PROJECTIONS_FILENAME = "alpha_fy2024_draft_projections.pdf"

# Known financial truth for Alpha Technologies Inc.
KNOWN_FACTS = {
    "company": "Alpha Technologies Inc.",
    "audited": {
        "period": "FY 2024 (Ended Dec 31, 2024)",
        "currency_unit": "USD Millions",
        "total_revenue": "$1,250.0",
        "total_revenue_raw": 1250.0,
        "operating_income": "$320.0",
        "net_income": "$185.5",
        "diluted_eps": "$2.45",
        "cloud_revenue": "$750.0",
        "enterprise_revenue": "$500.0",
        "operating_cash_flow": "$290.0",
        "free_cash_flow": "$210.0",
        "capex": "$80.0",
        "revenue_page": 1,
        "net_income_page": 1,
        "segment_page": 2,
    },
    "conflicting_draft": {
        "period": "FY 2024 (Ended Dec 31, 2024)",
        "currency_unit": "USD Millions",
        "total_revenue": "$1,100.0",
        "total_revenue_raw": 1100.0,
        "operating_income": "$260.0",
        "net_income": "$140.0",
        "diluted_eps": "$1.85",
        "cloud_revenue": "$660.0",
        "enterprise_revenue": "$440.0",
        "revenue_page": 1,
        "net_income_page": 1,
        "segment_page": 2,
    },
}


def _get_document_styles():
    base_styles = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "DocTitle",
            parent=base_styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
            spaceAfter=12,
        ),
        "heading": ParagraphStyle(
            "DocHeading",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "DocBody",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13.5,
            textColor=colors.HexColor("#334155"),
            spaceAfter=8,
        ),
        "disclaimer": ParagraphStyle(
            "DocDisclaimer",
            parent=base_styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#B91C1C"),
            spaceAfter=8,
        ),
    }
    return styles


def build_audited_report_pdf(target_path: Path) -> Path:
    """Builds alpha_fy2024_audited_report.pdf with audited financial tables."""
    target_path = Path(target_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _get_document_styles()

    doc = SimpleDocTemplate(
        str(target_path),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    story = []

    # PAGE 1: Audited Consolidated Statements of Operations
    story.append(Paragraph("Alpha Technologies Inc.", styles["title"]))
    story.append(
        Paragraph(
            "FY2024 Audited Financial Results — Form 10-K Summary Report (Amounts in USD Millions, except per-share data)",
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Paragraph("Consolidated Statements of Operations (Audited)", styles["heading"])
    )

    table_data_p1 = [
        ["Reporting Period", "Total Revenue", "Operating Income", "Net Income", "Diluted EPS"],
        ["All figures in USD Millions", "USD Millions", "USD Millions", "USD Millions", "USD / Share"],
        ["FY 2024 (Ended Dec 31, 2024)", "$1,250.0", "$320.0", "$185.5", "$2.45"],
        ["FY 2023 (Ended Dec 31, 2023)", "$1,080.0", "$270.0", "$155.0", "$2.10"],
        ["FY 2022 (Ended Dec 31, 2022)", "$950.0", "$225.0", "$130.0", "$1.80"],
    ]

    t_p1 = Table(table_data_p1, colWidths=[160, 95, 95, 95, 95])
    t_p1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F1F5F9")),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#475569")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Oblique"),
                ("FONTSIZE", (0, 1), (-1, 1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_p1)
    story.append(Spacer(1, 14))

    p1_narrative = (
        "<b>Management Discussion & Financial Performance Analysis:</b><br/>"
        "For the fiscal year ended December 31, 2024, Alpha Technologies Inc. achieved audited "
        "total revenue of $1,250.0 million, representing an increase of $170.0 million or 15.7% from "
        "fiscal year 2023 total revenue of $1,080.0 million. Consolidated operating income reached $320.0 million, "
        "yielding an operating margin of 25.6%. Audited net income for fiscal year 2024 stood at $185.5 million, "
        "compared to $155.0 million in fiscal year 2023. Diluted earnings per share (EPS) was $2.45 based on 75.7 million "
        "diluted weighted-average shares outstanding. All financial figures in this statement have been audited "
        "by independent registered public accounting auditors."
    )
    story.append(Paragraph(p1_narrative, styles["body"]))

    # PAGE 2: Segment Breakdown and Cash Flows
    story.append(PageBreak())
    story.append(
        Paragraph("Segment Performance and Cash Flow Summary (Audited)", styles["heading"])
    )

    table_data_p2 = [
        ["Operating Segment", "FY 2024 Revenue", "FY 2023 Revenue", "YoY Growth", "Operating Margin"],
        ["Segment Breakdown", "USD Millions", "USD Millions", "Percentage", "Percentage"],
        ["Cloud Platforms", "$750.0", "$620.0", "+21.0%", "32.0%"],
        ["Enterprise Software", "$500.0", "$460.0", "+8.7%", "22.5%"],
        ["Consolidated Total", "$1,250.0", "$1,080.0", "+15.7%", "25.6%"],
    ]

    t_p2 = Table(table_data_p2, colWidths=[150, 95, 95, 100, 100])
    t_p2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F1F5F9")),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#475569")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Oblique"),
                ("FONTSIZE", (0, 1), (-1, 1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_p2)
    story.append(Spacer(1, 14))

    p2_narrative = (
        "<b>Liquidity, Capital Resources & Cash Flows:</b><br/>"
        "Net cash provided by operating activities for fiscal year 2024 was $290.0 million. "
        "Capital expenditures totaled $80.0 million, resulting in free cash flow of $210.0 million. "
        "Cash and cash equivalents as of December 31, 2024 totaled $340.0 million. "
        "Cloud Platforms continued as the primary growth engine, delivering $750.0 million in audited revenue."
    )
    story.append(Paragraph(p2_narrative, styles["body"]))

    doc.build(story)
    return target_path


def build_draft_projections_pdf(target_path: Path) -> Path:
    """Builds alpha_fy2024_draft_projections.pdf with conflicting values on Page 1."""
    target_path = Path(target_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _get_document_styles()

    doc = SimpleDocTemplate(
        str(target_path),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    story = []

    # PAGE 1: Preliminary Draft Statements of Operations (CONFLICTING ON PAGE 1)
    story.append(Paragraph("Alpha Technologies Inc.", styles["title"]))
    story.append(
        Paragraph(
            "FY2024 Preliminary Draft & Budget Forecast (Confidential Working Paper — Unaudited Estimates in USD Millions)",
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Paragraph("Consolidated Statements of Operations (Preliminary Working Draft)", styles["heading"])
    )

    table_data_p1 = [
        ["Reporting Period", "Total Revenue", "Operating Income", "Net Income", "Diluted EPS"],
        ["Preliminary Estimates", "USD Millions", "USD Millions", "USD Millions", "USD / Share"],
        # CONFLICTING ROW: $1,100.0M revenue vs $1,250.0M audited; $140.0M net income vs $185.5M audited
        ["FY 2024 (Ended Dec 31, 2024)", "$1,100.0", "$260.0", "$140.0", "$1.85"],
        ["FY 2023 (Ended Dec 31, 2023)", "$1,080.0", "$270.0", "$155.0", "$2.10"],
        ["FY 2022 (Ended Dec 31, 2022)", "$950.0", "$225.0", "$130.0", "$1.80"],
    ]

    t_p1 = Table(table_data_p1, colWidths=[160, 95, 95, 95, 95])
    t_p1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7F1D1D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FEF2F2")),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#991B1B")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Oblique"),
                ("FONTSIZE", (0, 1), (-1, 1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#FCA5A5")),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#FFF1F2")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_p1)
    story.append(Spacer(1, 14))

    p1_narrative = (
        "<b>Confidential Draft Working Notes & Disclaimer:</b><br/>"
        "This internal planning document contains preliminary working projections for fiscal year 2024 "
        "prepared prior to audit completion. Projected total revenue for fiscal year 2024 was estimated at $1,100.0 million, "
        "with preliminary operating income of $260.0 million and estimated net income of $140.0 million (diluted EPS of $1.85). "
        "<i>Caution: These working figures represent preliminary committee targets only and differ substantially from "
        "final audited financial statements. These figures must not be used for external reporting, compliance, or investor disclosure.</i>"
    )
    story.append(Paragraph(p1_narrative, styles["disclaimer"]))

    # PAGE 2: Preliminary Segment Breakdown
    story.append(PageBreak())
    story.append(
        Paragraph("Preliminary Segment Targets and Budget Allocation (Working Draft)", styles["heading"])
    )

    table_data_p2 = [
        ["Operating Segment", "FY 2024 Target", "FY 2023 Actual", "Target Growth", "Projected Margin"],
        ["Preliminary Estimates", "USD Millions", "USD Millions", "Percentage", "Percentage"],
        ["Cloud Platforms", "$660.0", "$620.0", "+6.5%", "28.0%"],
        ["Enterprise Software", "$440.0", "$460.0", "-4.3%", "20.0%"],
        ["Total Working Target", "$1,100.0", "$1,080.0", "+1.9%", "23.6%"],
    ]

    t_p2 = Table(table_data_p2, colWidths=[150, 95, 95, 100, 100])
    t_p2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7F1D1D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FEF2F2")),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#991B1B")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Oblique"),
                ("FONTSIZE", (0, 1), (-1, 1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#FCA5A5")),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#FFF1F2")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_p2)
    story.append(Spacer(1, 14))

    p2_narrative = (
        "<b>Internal Budget Planning Guidance:</b><br/>"
        "Preliminary operating cash flow for fiscal year 2024 was budgeted at $220.0 million, with planned "
        "capital expenditures of $95.0 million yielding estimated free cash flow of $125.0 million. "
        "Internal budget assumptions were based on conservative early-year forecasts and were revised upward in the final audit."
    )
    story.append(Paragraph(p2_narrative, styles["body"]))

    doc.build(story)
    return target_path


def generate_evaluation_pdfs(output_dir: Path) -> Dict[str, Path]:
    """Generates the two deterministic financial PDFs into output_dir and returns mapping."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    audited_path = output_dir / AUDITED_REPORT_FILENAME
    draft_path = output_dir / DRAFT_PROJECTIONS_FILENAME

    build_audited_report_pdf(audited_path)
    build_draft_projections_pdf(draft_path)

    return {
        "audited": audited_path,
        "draft": draft_path,
    }


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_evaluation_cases() -> List[Dict[str, Any]]:
    """Returns the structured specifications for the 6 evaluation cases."""
    return [
        {
            "case_id": "FIN-EVAL-01",
            "name": "grounded_known_revenue_with_source_locking",
            "category": "grounded_financial_query",
            "description": "Known number answer with correct document/page; source selection excludes conflicting draft on same page",
            "question": "What was Alpha Technologies' audited total revenue for fiscal year 2024?",
            "target_document": AUDITED_REPORT_FILENAME,
            "target_page": 1,
            "expected_figure": "$1,250.0",
            "expected_figure_tokens": ["1,250", "1250", "1,250.0"],
            "conflicting_figure_to_reject": "$1,100.0",
            "conflicting_figure_tokens": ["1,100", "1100", "1,100.0"],
            "excluded_document": DRAFT_PROJECTIONS_FILENAME,
            "expected_units": "USD Millions",
            "expected_unit_patterns": [r"\b(?:USD|U\.?S\.?\s+dollars?)\b", r"\bmillions?\b"],
            "require_live_model": True,
        },
        {
            "case_id": "FIN-EVAL-02",
            "name": "grounded_known_net_income_and_units",
            "category": "grounded_financial_query",
            "description": "Known net income figure with table units context on Page 1",
            "question": "What was Alpha Technologies' audited net income for fiscal year 2024 and in what unit of measurement is it reported?",
            "target_document": AUDITED_REPORT_FILENAME,
            "target_page": 1,
            "expected_figure": "$185.5",
            "expected_figure_tokens": ["185.5"],
            "conflicting_figure_to_reject": "$140.0",
            "conflicting_figure_tokens": ["140.0", "140"],
            "excluded_document": DRAFT_PROJECTIONS_FILENAME,
            "expected_units": "USD Millions",
            "expected_unit_patterns": [r"\b(?:USD|U\.?S\.?\s+dollars?)\b", r"\bmillions?\b"],
            "require_live_model": True,
        },
        {
            "case_id": "FIN-EVAL-03",
            "name": "abstention_on_missing_evidence",
            "category": "abstention",
            "description": "System abstains truthfully without fabricating figures or citations when evidence is missing",
            "question": "What was Alpha Technologies' capital expenditure for the solar energy division in fiscal year 2026?",
            "target_document": AUDITED_REPORT_FILENAME,
            "target_page": None,
            "expected_figure": None,
            "expected_abstention": True,
            "expected_chunks_used": 0,
            "expected_citations_count": 0,
            "require_live_model": False,
        },
        {
            "case_id": "FIN-EVAL-04",
            "name": "unauthorized_document_selection_denial",
            "category": "authorization_denial",
            "description": "Unauthorized employee attempting chat session with unshared document receives 404 Not Found (privacy contract)",
            "actor": "unauthorized_user",
            "action": "create_chat_session_with_unshared_doc",
            "expected_status_code": 404,
            "expected_error_detail_substring": "Document not found",
            "require_live_model": False,
        },
        {
            "case_id": "FIN-EVAL-05",
            "name": "unauthorized_source_download_denial",
            "category": "authorization_denial",
            "description": "Unauthorized employee attempting direct PDF download receives 404 Not Found",
            "actor": "unauthorized_user",
            "action": "get_document_source",
            "expected_status_code": 404,
            "require_live_model": False,
        },
        {
            "case_id": "FIN-EVAL-06",
            "name": "anonymous_access_denial",
            "category": "authorization_denial",
            "description": "Anonymous caller without Authorization header receives 401 Unauthorized",
            "actor": "anonymous",
            "action": "access_protected_documents_endpoint",
            "expected_status_code": 401,
            "require_live_model": False,
        },
    ]
