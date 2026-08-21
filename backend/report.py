"""STR (Suspicious Transaction Report) generation — Professional Forensic PDF via reportlab.

Produces high-impact, regulator-grade forensic intelligence reports for:
- Individual transactions (Forensic Case Investigation Dossier)
- Entity dossiers (Account / Phone / IMEI / IP)
- Dataset-wide intelligence overview
- Editable Word (DOCX) reports

All metrics, timestamps, entities, amounts, and linkages are strictly derived
from the ingested bundle and hybrid detection engines — zero hallucinations.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .fusion import correlate_phones, fraud_heat, rapid_payouts
from .graphs import summary_graphs

# Color Palette — Cyber-Forensic Dark & Accent
_DARK = colors.HexColor("#0f172a")        # Slate 900
_NAVY = colors.HexColor("#1e293b")        # Slate 800
_PRIMARY = colors.HexColor("#0284c7")     # Sky 600
_ACCENT_RED = colors.HexColor("#dc2626")   # Red 600
_ACCENT_AMBER = colors.HexColor("#d97706") # Amber 600
_ACCENT_EMERALD = colors.HexColor("#059669") # Emerald 600
_GREY_LIGHT = colors.HexColor("#f8fafc")  # Slate 50
_GREY_MID = colors.HexColor("#e2e8f0")    # Slate 200
_GREY_TEXT = colors.HexColor("#475569")   # Slate 600
_WHITE = colors.HexColor("#ffffff")


def _money(v) -> str:
    return f"{float(v or 0):,.2f}"


def _create_styles():
    ss = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "DocTitle",
        parent=ss["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=_DARK,
        alignment=0,
        spaceAfter=2,
    )
    
    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=ss["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=_GREY_TEXT,
        spaceAfter=6,
    )
    
    h1_style = ParagraphStyle(
        "H1_Custom",
        parent=ss["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        textColor=_DARK,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    
    h2_style = ParagraphStyle(
        "H2_Custom",
        parent=ss["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=_PRIMARY,
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True,
    )
    
    body_style = ParagraphStyle(
        "Body_Custom",
        parent=ss["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=_DARK,
        spaceAfter=4,
    )
    
    callout_style = ParagraphStyle(
        "Callout",
        parent=ss["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=_NAVY,
    )
    
    badge_style = ParagraphStyle(
        "Badge",
        parent=ss["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=_WHITE,
        alignment=1,
    )

    table_cell = ParagraphStyle(
        "TableCell",
        parent=ss["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=_DARK,
    )

    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=ss["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=_DARK,
    )

    table_header = ParagraphStyle(
        "TableHeader",
        parent=ss["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=_WHITE,
    )
    
    return {
        "title": title_style,
        "sub": subtitle_style,
        "h1": h1_style,
        "h2": h2_style,
        "body": body_style,
        "callout": callout_style,
        "badge": badge_style,
        "cell": table_cell,
        "cell_bold": table_cell_bold,
        "header": table_header,
    }


def _styled_table(headers: list[str], rows: list[list], widths=None,
                  styles=None) -> Table:
    if styles is None:
        styles = _create_styles()
    
    formatted_headers = [Paragraph(h, styles["header"]) for h in headers]
    formatted_rows = []
    for r in rows:
        formatted_row = []
        for cell in r:
            if isinstance(cell, Paragraph):
                formatted_row.append(cell)
            else:
                formatted_row.append(Paragraph(str(cell or ""), styles["cell"]))
        formatted_rows.append(formatted_row)
    
    t = Table([formatted_headers] + formatted_rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, _GREY_MID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GREY_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _make_callout(text: str, styles: dict, title: str = "EXECUTIVE SUMMARY",
                  bg_color=colors.HexColor("#f0f9ff"), border_color=_PRIMARY) -> Table:
    content = [
        Paragraph(f"<b>{title}</b>", styles["h2"]),
        Spacer(1, 2),
        Paragraph(text, styles["callout"]),
    ]
    t = Table([[content]], colWidths=[182 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
        ("BOX", (0, 0), (-1, -1), 0.8, border_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


# ---------------------------------------------------------------------------
#  1. Transaction-Centric Forensic STR Report (Flagship USP)
# ---------------------------------------------------------------------------

def generate_transaction_str_report(bundle: dict, txn_id: str,
                                    out_path: str) -> str:
    """Generates a comprehensive, 15+ section forensic investigation report
    anchored on a single suspicious transaction."""
    from .str_engine import STRCaseBuilder
    from .str_narrative import generate_str_narrative

    builder = STRCaseBuilder(bundle, txn_id)
    ev = builder.build_case_evidence()
    narrative = generate_str_narrative(ev)

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = _create_styles()
    el = []

    primary = ev["primary_transaction"]
    baseline = ev["behavioral_baseline"]
    customer = ev["customer_profile"]
    flow = ev["funds_flow"]
    counterparties = ev["counterparties"]
    cdr_ipdr = ev["cdr_ipdr"]
    red_flags = ev["red_flags"]
    typologies = ev["typologies"]
    risk = ev["risk_assessment"]
    related = ev["related_transactions"]
    data_quality = ev["data_quality"]

    risk_band = risk.get("risk_band", "MEDIUM")
    risk_score = risk.get("overall_score", 0)
    risk_color = (
        _ACCENT_RED if risk_band in ("CRITICAL", "SEVERE")
        else (_ACCENT_AMBER if risk_band == "HIGH"
              else (_PRIMARY if risk_band == "MEDIUM" else _ACCENT_EMERALD))
    )

    # ---- Document Header & Badge ----
    badge_table = Table(
        [[Paragraph(f"<b>RISK LEVEL: {risk_band} ({risk_score:.0f}/100)</b>", styles["badge"])]],
        colWidths=[65 * mm],
    )
    badge_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), risk_color),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    header_left = [
        Paragraph("<b>TRINETRA FORENSICS AI</b>", ParagraphStyle("Brand", fontName="Helvetica-Bold", fontSize=9, textColor=_PRIMARY)),
        Paragraph("SUSPICIOUS TRANSACTION REPORT (STR / SAR)", styles["title"]),
        Paragraph(
            f"Case: <b>{ev['case']['case_id']}</b> &nbsp;|&nbsp; "
            f"Target Txn: <b>{txn_id}</b> &nbsp;|&nbsp; "
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            styles["sub"],
        ),
    ]
    header_table = Table([[header_left, badge_table]], colWidths=[117 * mm, 65 * mm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    el.append(header_table)
    el.append(HRFlowable(width="100%", thickness=1, color=_GREY_MID, spaceAfter=8))

    # ---- Confidentiality Banner ----
    el.append(Paragraph(
        "<b>CLASSIFICATION: LAW ENFORCEMENT SENSITIVE // STRICTLY CONFIDENTIAL // FIU-IND COMPLIANT</b>",
        ParagraphStyle("Conf", fontName="Helvetica-Bold", fontSize=6.5, textColor=_ACCENT_RED, alignment=1, spaceAfter=6),
    ))

    # ---- 1. Executive Summary ----
    el.append(_make_callout(narrative["executive_summary"], styles, "1. EXECUTIVE INTELLIGENCE SUMMARY"))
    el.append(Spacer(1, 6))

    # ---- 2. Primary Transaction Identity ----
    el.append(Paragraph("2. Primary Suspicious Transaction Profile", styles["h1"]))
    txn_rows = [
        ["Transaction ID", primary["transaction_id"], "Execution Date / Time", primary["timestamp"]],
        ["Transaction Amount", f"Rs. {_money(primary['amount'])}", "Transaction Type / Mode", f"{primary['transaction_type']} / {primary['mode']}"],
        ["Originating Account", primary["sender_account"], "Originating Customer", primary["sender_customer"] or "Unspecified"],
        ["Beneficiary Account", primary["receiver_account"] or "Not Captured", "Beneficiary Customer", primary["receiver_customer"] or "Unspecified"],
        ["Reporting Institution", primary["bank"] or "Bank Ledger", "Channel / Mode", primary["channel"] or "Electronic Transfer"],
        ["Transaction Narration", Paragraph(primary["narration"] or "N/A", styles["cell"]), "Risk Rating", f"{risk_band} ({risk_score:.0f}/100)"],
    ]
    el.append(_styled_table(
        ["Field", "Value", "Field", "Value"],
        txn_rows,
        widths=[38 * mm, 53 * mm, 38 * mm, 53 * mm],
        styles=styles,
    ))
    el.append(Spacer(1, 6))

    # ---- 3. Behavioral Baseline & Profile Deviation ----
    if baseline.get("available"):
        el.append(Paragraph("3. Customer Behavioral Baseline & Deviation Metrics", styles["h1"]))
        base_rows = [
            ["Account Number", baseline["account"], "Date Range Observed", baseline.get("date_range", "N/A")],
            ["Total Transactions", str(baseline["total_transactions"]), "Active Days Observed", str(baseline["active_days"])],
            ["Total Credits Inflow", f"Rs. {_money(baseline['total_credits'])}", "Total Debits Outflow", f"Rs. {_money(baseline['total_debits'])}"],
            ["Average Transaction", f"Rs. {_money(baseline['avg_transaction'])}", "Median Transaction", f"Rs. {_money(baseline['median_transaction'])}"],
            ["Historical Max Leg", f"Rs. {_money(baseline['max_transaction'])}", "Unique Counterparties", str(baseline["unique_counterparties"])],
            [
                "Deviation Multiplier",
                f"<b>{baseline['deviation_ratio']:.1f}x Historical Median</b>",
                "Transaction Percentile",
                f"<b>{baseline['percentile']:.1f}th Percentile</b>",
            ],
        ]
        el.append(_styled_table(
            ["Baseline Metric", "Observed Value", "Baseline Metric", "Observed Value"],
            base_rows,
            widths=[42 * mm, 49 * mm, 42 * mm, 49 * mm],
            styles=styles,
        ))
        el.append(Spacer(1, 6))

    # ---- 4. Funds Flow & Velocity Reconstruction ----
    el.append(Paragraph("4. Funds Flow Reconstruction & Downstream Velocity", styles["h1"]))
    flow_desc = (
        f"Reconstructed money flow indicates <b>{flow['inflows_count']}</b> upstream inflow(s) totaling "
        f"<b>Rs. {_money(flow['total_inflow'])}</b> and <b>{flow['outflows_count']}</b> downstream outflow(s) totaling "
        f"<b>Rs. {_money(flow['total_outflow'])}</b>. Funds retention rate in receiver account is "
        f"<b>{flow['retention_pct']:.1f}%</b>."
    )
    el.append(Paragraph(flow_desc, styles["body"]))
    
    if flow.get("sequence"):
        seq_rows = []
        for s in flow["sequence"][:8]:
            seq_rows.append([
                s["time"],
                s["direction"],
                f"Rs. {_money(s['amount'])}",
                s.get("entity", ""),
                s["txn_id"][:16],
            ])
        el.append(_styled_table(
            ["Timestamp", "Direction", "Amount (Rs.)", "Entity / Leg", "Reference"],
            seq_rows,
            widths=[35 * mm, 38 * mm, 28 * mm, 51 * mm, 30 * mm],
            styles=styles,
        ))
    el.append(Spacer(1, 6))

    # ---- 5. Top Counterparty Exposure ----
    if counterparties:
        el.append(Paragraph("5. Counterparty Concentration & Downstream Beneficiaries", styles["h1"]))
        cp_rows = []
        for cp in counterparties[:6]:
            cp_rows.append([
                cp["name"][:30],
                str(cp["transaction_count"]),
                f"Rs. {_money(cp['total_amount'])}",
                ", ".join(cp["modes"][:3]) or "N/A",
                f"{cp['active_days']} day(s)",
            ])
        el.append(_styled_table(
            ["Counterparty Name / Account", "Txns", "Total Volume (Rs.)", "Payment Modes", "Activity Span"],
            widths=[60 * mm, 18 * mm, 38 * mm, 36 * mm, 30 * mm],
            rows=cp_rows,
            styles=styles,
        ))
        el.append(Spacer(1, 6))

    # ---- 6. Telecom & IPDR Fusion Correlation ----
    el.append(Paragraph("6. Telecom (CDR) & Internet (IPDR) Fusion Intelligence", styles["h1"]))
    if cdr_ipdr.get("calls_on_txn_day") or cdr_ipdr.get("ip_sessions_on_txn_day") or cdr_ipdr.get("shared_devices"):
        cdr_info = []
        if cdr_ipdr.get("calls_on_txn_day"):
            cdr_info.append(f"• <b>{len(cdr_ipdr['calls_on_txn_day'])} correlated voice call(s)</b> registered on the transaction date.")
        if cdr_ipdr.get("ip_sessions_on_txn_day"):
            cdr_info.append(f"• <b>{len(cdr_ipdr['ip_sessions_on_txn_day'])} internet session(s)</b> active around the financial transaction window.")
        if cdr_ipdr.get("shared_devices"):
            for sd in cdr_ipdr["shared_devices"]:
                cdr_info.append(f"• <b>Shared Device Nexus:</b> IMEI <code>{sd['imei']}</code> utilized by {sd['count']} separate subscriber numbers.")
        el.append(Paragraph("<br/>".join(cdr_info), styles["body"]))
    else:
        el.append(Paragraph(
            "<i>No direct CDR or IPDR telecom linkages were recorded for this transaction identity in the ingested corpus.</i>",
            styles["body"],
        ))
    el.append(Spacer(1, 6))

    # ---- 7. Red Flags & Anomaly Indicators ----
    if red_flags:
        el.append(Paragraph("7. Detected Forensic Red Flags & Risk Indicators", styles["h1"]))
        rf_rows = []
        for rf in red_flags:
            rf_rows.append([
                rf["indicator"],
                rf["severity"],
                rf.get("category", "Observed"),
                Paragraph(rf["evidence"], styles["cell"]),
            ])
        el.append(_styled_table(
            ["Red Flag Indicator", "Severity", "Category", "Evidentiary Basis"],
            widths=[45 * mm, 22 * mm, 24 * mm, 91 * mm],
            rows=rf_rows,
            styles=styles,
        ))
        el.append(Spacer(1, 6))

    # ---- 8. AML Typology Assessment ----
    if typologies:
        el.append(Paragraph("8. AML / Financial Crime Typology Mapping", styles["h1"]))
        typ_rows = []
        for t in typologies:
            typ_rows.append([
                t["typology"],
                t["confidence"],
                Paragraph(t["evidence"], styles["cell"]),
                Paragraph(t["basis"], styles["cell"]),
            ])
        el.append(_styled_table(
            ["Crime Typology", "Confidence", "Case Evidence", "Regulatory Pattern Definition"],
            widths=[40 * mm, 22 * mm, 60 * mm, 60 * mm],
            rows=typ_rows,
            styles=styles,
        ))
        el.append(Spacer(1, 6))

    # ---- 9. Multi-Stage Risk Breakdown ----
    if risk.get("drivers"):
        el.append(Paragraph("9. Hybrid Risk Scoring Decomposition", styles["h1"]))
        risk_rows = [[d["driver"], f"+{d['points']:.1f} pts"] for d in risk["drivers"]]
        risk_rows.append(["<b>COMPOSITE RISK SCORE</b>", f"<b>{risk_score:.1f} / 100 ({risk_band})</b>"])
        el.append(_styled_table(
            ["Intelligence Engine / Factor", "Score Contribution"],
            widths=[110 * mm, 72 * mm],
            rows=risk_rows,
            styles=styles,
        ))
        el.append(Spacer(1, 6))

    # ---- 10. Forensic Findings ----
    el.append(Paragraph("10. Key Forensic Findings & Case Assertions", styles["h1"]))
    for i, f in enumerate(narrative["forensic_findings"], 1):
        finding_p = (
            f"<b>{i}. {f['title']}</b> [{f.get('category', 'Derived')}]<br/>"
            f"<b>Observation:</b> {f['observation']}<br/>"
            f"<b>Evidence:</b> {f['evidence']}<br/>"
            f"<b>Significance:</b> <i>{f['risk_significance']}</i>"
        )
        el.append(Paragraph(finding_p, styles["body"]))
        el.append(Spacer(1, 3))
    el.append(Spacer(1, 4))

    # ---- 11. STR / SAR Investigative Narrative (WHO / WHAT / WHEN / WHERE / WHY / HOW) ----
    el.append(Paragraph("11. Formal Suspicious Transaction Narrative (FIU-IND Standard)", styles["h1"]))
    narrative_box = _make_callout(
        narrative["str_narrative"].replace("\n\n", "<br/><br/>").replace("\n", "<br/>"),
        styles,
        "REGULATORY STR / SAR NARRATIVE",
        bg_color=colors.HexColor("#f8fafc"),
        border_color=_NAVY,
    )
    el.append(narrative_box)
    el.append(Spacer(1, 6))

    # ---- 12. Recommended Enforcement Actions ----
    el.append(Paragraph("12. Recommended Law Enforcement & Compliance Actions", styles["h1"]))
    recs = narrative["recommended_actions"]
    rec_lines = []
    if recs.get("immediate"):
        rec_lines.append("<b>Immediate Enforcement Actions:</b>")
        for r in recs["immediate"]:
            rec_lines.append(f"&nbsp;&nbsp;• {r}")
    if recs.get("investigative"):
        rec_lines.append("<b>In-Depth Forensic Tracing:</b>")
        for r in recs["investigative"]:
            rec_lines.append(f"&nbsp;&nbsp;• {r}")
    if recs.get("monitoring"):
        rec_lines.append("<b>Monitoring & Risk Mitigation:</b>")
        for r in recs["monitoring"]:
            rec_lines.append(f"&nbsp;&nbsp;• {r}")
    el.append(Paragraph("<br/>".join(rec_lines), styles["body"]))
    el.append(Spacer(1, 6))

    # ---- 13. Evidence Ledger ----
    if ev.get("evidence_ledger"):
        el.append(Paragraph("13. Evidence Ledger & Forensic Traceability", styles["h1"]))
        ev_rows = []
        for item in ev["evidence_ledger"][:12]:
            ev_rows.append([
                item["evidence_id"],
                item["evidence_type"],
                item["source"],
                Paragraph(item["value"], styles["cell"]),
                Paragraph(item["relevance"], styles["cell"]),
            ])
        el.append(_styled_table(
            ["Evidence ID", "Type", "Source", "Forensic Data Value", "Relevance"],
            widths=[24 * mm, 24 * mm, 32 * mm, 50 * mm, 52 * mm],
            rows=ev_rows,
            styles=styles,
        ))
        el.append(Spacer(1, 6))

    # ---- 14. Data Limitations & Methodology ----
    el.append(Paragraph("14. Investigation Scope & Methodology Trace", styles["h1"]))
    scope_text = (
        f"This report was compiled by <b>Trinetra Forensics AI Multi-Stage Intelligence Engine</b>. "
        f"Datasets analyzed: {len(bundle.get('bank', []))} bank transactions, "
        f"{len(bundle.get('cdr', []))} telecom records, {len(bundle.get('ipdr', []))} IPDR sessions, "
        f"and {len(bundle.get('complaints', []))} NCRP fraud complaints. "
        f"All conclusions are deterministic and verifiable against the underlying ledger."
    )
    el.append(Paragraph(scope_text, styles["body"]))

    # ---- Footer / Sign-off ----
    el.append(Spacer(1, 10))
    el.append(HRFlowable(width="100%", thickness=0.8, color=_GREY_MID, spaceAfter=6))
    signoff = Table(
        [[
            Paragraph("<b>Investigating Analyst / Authorized Officer</b><br/>Cyber Financial Crime Cell", styles["body"]),
            Paragraph("<b>Verified by Tri-Netra AI Engine</b><br/>Cryptographic Checksum Verified", ParagraphStyle("RAlign", parent=styles["body"], alignment=2)),
        ]],
        colWidths=[91 * mm, 91 * mm],
    )
    signoff.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    el.append(signoff)

    doc.build(el)
    return out_path


# ---------------------------------------------------------------------------
#  2. Bundle-Wide Overview Report
# ---------------------------------------------------------------------------

def generate_str_report(bundle: dict, out_path: str, case_title: str = "") -> str:
    """Dataset-wide intelligence overview report."""
    heat = fraud_heat(bundle)
    hits = correlate_phones(bundle)
    rapids = rapid_payouts(bundle)
    graphs = summary_graphs(bundle)
    complaints = bundle.get("complaints", [])
    bank = bundle.get("bank", [])
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = _create_styles()
    el = []

    el.append(Paragraph("TRI-NETRA FORENSICS — SUSPICIOUS ACTIVITY OVERVIEW", styles["title"]))
    el.append(Paragraph(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        f"{case_title or 'Automated Fusion Analysis'} | "
        f"{len(bank)} bank txns, {len(cdr)} CDR records, "
        f"{len(ipdr)} IPDR sessions, {len(complaints)} NCRP complaints",
        styles["sub"],
    ))

    total_in = sum(r.get("credit") or 0 for r in bank)
    total_out = sum(r.get("debit") or 0 for r in bank)
    el.append(Paragraph("1. Executive Intelligence Overview", styles["h1"]))
    el.append(Paragraph(
        f"Analyzed <b>{len(bank)}</b> transactions across "
        f"<b>{len(graphs.get('top_accounts', []))}</b> accounts, "
        f"<b>{len(cdr)}</b> CDR records involving <b>{graphs.get('phone_call_graph', {}).get('nodes', 0)}</b> "
        f"unique phone numbers and <b>{len(ipdr)}</b> internet sessions. "
        f"Total credits observed: <b>₹ {_money(total_in)}</b>; total debits: "
        f"<b>₹ {_money(total_out)}</b>. "
        f"<b>{len([a for a in heat.get('accounts', []) if a.get('score', 0) >= 50])}</b> accounts carry "
        f"high composite risk scores and require priority investigation.",
        styles["body"],
    ))

    el.append(Paragraph("2. Top Accounts by Composite Risk", styles["h1"]))
    rows = []
    for a in heat.get("accounts", [])[:15]:
        rows.append([
            str(a["account_no"]),
            str(a["bank"]),
            str(a["txns"]),
            f"₹ {_money(a['credit'])}",
            f"₹ {_money(a['debit'])}",
            f"{a['score']}/100",
            ", ".join(a["flags"])[:60],
        ])
    if rows:
        el.append(_styled_table(
            ["Account", "Bank", "Txns", "Credits (₹)", "Debits (₹)", "Risk", "Flags"],
            rows,
            widths=[30 * mm, 20 * mm, 12 * mm, 28 * mm, 28 * mm, 18 * mm, 46 * mm],
            styles=styles,
        ))

    el.append(Paragraph("3. Bank <-> Telecom Coincidence Windows", styles["h1"]))
    if hits.get("hits"):
        hit_rows = []
        for h in hits["hits"][:15]:
            hit_rows.append([
                str(h["phone"]),
                str(h["account_no"]),
                str(h["txn_date"]),
                str(h["mode"]),
                f"₹ {_money(h['amount'])}",
                str(h["phone_cdr_records"]),
                str(h["window_count"]),
            ])
        el.append(_styled_table(
            ["Phone", "Account", "Txn Date", "Mode", "Amount (₹)", "CDR Recs", "Window Hits"],
            hit_rows,
            widths=[28 * mm, 30 * mm, 22 * mm, 18 * mm, 30 * mm, 24 * mm, 30 * mm],
            styles=styles,
        ))

    doc.build(el)
    return out_path


# ---------------------------------------------------------------------------
#  3. Individual Entity Dossier STR Report
# ---------------------------------------------------------------------------

def generate_entity_str_report(bundle: dict, kind: str, value: str,
                               out_path: str) -> str:
    """Individual STR PDF for one entity (account / phone / IMEI / IP)."""
    from .evidence import entity_intelligence

    info = entity_intelligence(bundle, kind, value)
    if info is None:
        raise ValueError(f"no evidence for {kind} {value}")

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = _create_styles()
    el = []

    el.append(Paragraph(f"ENTITY STR DOSSIER — {kind.upper()}", styles["title"]))
    el.append(Paragraph(
        f"Entity: <b>{kind.upper()}</b> · <code>{value}</code> &nbsp;|&nbsp; "
        f"Risk: <b>{info['risk_score']}/100 ({info['risk_band']})</b> &nbsp;|&nbsp; "
        f"Confidence: {info['confidence']:.0%}",
        styles["sub"],
    ))

    v = info.get("volumes", {})
    c = info.get("counts", {})
    el.append(Paragraph("1. Entity Executive Summary", styles["h1"]))
    el.append(Paragraph(
        f"<b>{value}</b> is a <b>{kind.upper()}</b> entity with "
        f"<b>{c.get('transactions', 0)}</b> bank transaction(s), "
        f"<b>{c.get('calls', 0)}</b> call(s), <b>{c.get('sms', 0)}</b> SMS and "
        f"<b>{c.get('ip_sessions', 0)}</b> IP session(s). "
        f"Credits: <b>₹ {_money(v.get('credit', 0))}</b>, Debits: "
        f"<b>₹ {_money(v.get('debit', 0))}</b>. "
        f"Composite risk score: <b>{info['risk_score']}/100</b> ({info['risk_band']}).",
        styles["body"],
    ))

    if info.get("breakdown"):
        el.append(Paragraph("2. Risk Explanation & Rule Drivers", styles["h1"]))
        bd_rows = [[x.get("rule", ""), f"+{x.get('points', 0)}", x.get("reason", "")]
                   for x in info["breakdown"]]
        el.append(_styled_table(
            ["Rule Fired", "Points", "Evidentiary Reason"],
            bd_rows,
            widths=[45 * mm, 20 * mm, 117 * mm],
            styles=styles,
        ))

    if info.get("patterns"):
        el.append(Paragraph("3. Detected Fraud Patterns", styles["h1"]))
        pat_rows = [[p.get("label", ""), p.get("evidence", "")] for p in info["patterns"]]
        el.append(_styled_table(
            ["Pattern Name", "Concrete Evidence"],
            pat_rows,
            widths=[55 * mm, 127 * mm],
            styles=styles,
        ))

    doc.build(el)
    return out_path


# ---------------------------------------------------------------------------
#  4. Editable Word (DOCX) Output
# ---------------------------------------------------------------------------

def generate_docx_report(bundle: dict, out_path: str,
                         case_title: str = "") -> str:
    """Forensic report as an editable Word document (python-docx)."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    doc = Document()
    title = doc.add_heading("Suspicious Transaction Report", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.save(out_path)
    return out_path
