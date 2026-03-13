from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.pdf_extractor import (
    extract_invoice_from_pdf,
    extract_batch,
    extract_invoices_from_pdf,
)
from src.engine.models import AuditResult, FreightInvoice, RateContract, PDFExtractionResult
from src.engine.pdf_normalizer import normalize_extraction
from src.engine.policy_engine import load_rate_table_csv
from src.services.audit_service import (
    get_summary_stats,
    results_to_display_df,
    run_full_audit,
    run_full_audit_from_invoices,
)


st.set_page_config(
    page_title="Freight Billing Auditor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Minimal enterprise-style theming via CSS.
# NOTE: Uses unsafe_allow_html=True, but only to inject CSS (no scripts).
st.markdown(
    """
    <style>
    /* 5) Base typography */
    html, body, [class*="block-container"] {
        font-size: 15px;
    }

    /* 1) Metric cards: subtle bottom border in company color + slightly larger value text */
    div[data-testid="metric-container"] {
        border-bottom: 2px solid #0066CC;
        padding-bottom: 0.35rem;
        margin-bottom: 0.5rem;
    }
    div[data-testid="metric-container"] > div:nth-child(2) {
        font-size: 1.1rem;
    }

    /* 2) Expander headers — color by severity emoji */
    div.streamlit-expanderHeader {
        font-weight: 500;
    }
    div.streamlit-expanderHeader:has(span:contains("🚨")) {
        font-weight: 600;
        color: #CC0000;
    }
    div.streamlit-expanderHeader:has(span:contains("⚠️")) {
        color: #997700;
    }
    div.streamlit-expanderHeader:has(span:contains("✅")) {
        color: #006600;
    }

    /* 3) Info boxes: warmer background + left border accent */
    div[data-testid="stNotification"] {
        border-left: 4px solid #CC8800;
        background-color: #fff7ea;
    }

    /* 4) Dispute message code block: slightly larger font and line-height */
    code {
        font-size: 0.95rem;
        line-height: 1.6;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Material Symbols (Google Material Icons) for a sleeker, professional look.
st.markdown(
    """
    <link rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" />
    <style>
      .material-symbols-outlined {
        font-variation-settings:
          'FILL' 0,
          'wght' 400,
          'GRAD' 0,
          'opsz' 24;
        vertical-align: middle;
        margin-right: 4px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _rate_table_exists() -> bool:
    root = Path(__file__).resolve().parents[1]
    return (root / "data" / "master_rate_table.csv").exists() or any(
        (root / "data" / "reference").glob("*master_rate_table.csv")
    )


def _load_rate_table_default() -> Dict[Tuple[str, str], RateContract]:
    """
    Load a canonical rate table for both CSV and PDF flows.
    """
    ref_dir = ROOT / "data" / "reference"
    candidates = [
        ref_dir / "gen_invoice_master_rate_table.csv",
        ref_dir / "gen_data_master_rate_table.csv",
        ref_dir / "master_rate_table.csv",
    ]
    path = None
    for p in candidates:
        if p.exists():
            path = p
            break
    if path is None:
        legacy = ROOT / "data" / "master_rate_table.csv"
        if legacy.exists():
            path = legacy
        else:
            raise FileNotFoundError(
                "No rate table found. Expected data/reference/*master_rate_table*.csv "
                "or data/master_rate_table.csv"
            )
    return load_rate_table_csv(path)


def _init_session_state() -> None:
    if "audit_results" not in st.session_state:
        st.session_state.audit_results: List[AuditResult] = []
    if "summary_stats" not in st.session_state:
        st.session_state.summary_stats = {}
    if "display_df" not in st.session_state:
        st.session_state.display_df = None
    if "last_filename" not in st.session_state:
        st.session_state.last_filename = None


def _severity_from_status(status: str) -> str:
    if "HIGH" in status:
        return "HIGH"
    if "MEDIUM" in status:
        return "MEDIUM"
    if "LOW" in status:
        return "LOW"
    return "CLEAN"


def sidebar() -> dict:
    st.sidebar.markdown(
        "<h2><span class='material-symbols-outlined'>search</span>Freight Billing Auditor</h2>",
        unsafe_allow_html=True,
    )
    st.sidebar.caption("AI-powered invoice compliance engine")
    st.sidebar.divider()

    uploaded_files = st.sidebar.file_uploader(
        label="Upload Invoices (CSV or PDF)",
        type=["csv", "pdf"],
        accept_multiple_files=True,
    )

    # AI explanations toggle – disabled if GEMINI_API_KEY missing
    gemini_key_present = bool(os.getenv("GEMINI_API_KEY"))
    enable_ai = st.sidebar.toggle(
        "Enable AI Explanations",
        value=True,
        disabled=not gemini_key_present,
    )
    if not gemini_key_present:
        st.sidebar.warning(
            "⚠️ GEMINI_API_KEY not found. Add to .env to enable AI explanations."
        )

    severity_filter = st.sidebar.multiselect(
        "Filter by Severity",
        options=["HIGH", "MEDIUM", "LOW", "CLEAN"],
        default=["HIGH", "MEDIUM", "LOW"],
    )

    run_clicked = st.sidebar.button("▶ Run Audit", use_container_width=True)

    st.sidebar.divider()
    if _rate_table_exists():
        st.sidebar.success("✅ Master rate table detected")
    else:
        st.sidebar.error("❌ Master rate table missing (expected data/master_rate_table.csv)")

    st.sidebar.caption("Swastik Singh | Freight Auditor Prototype")

    return {
        "uploaded_files": uploaded_files,
        "enable_ai": enable_ai,
        "severity_filter": severity_filter,
        "run_clicked": run_clicked,
    }


def show_state_no_file() -> None:
    st.empty()
    st.markdown(
        "<div style='text-align: center; font-size: 48px;'>📄</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h2 style='text-align: center;'>Upload an invoice file to begin</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align: center;'>"
        "Upload either a CSV of invoices or a single PDF invoice. "
        "The auditor will check each invoice against the master rate table and "
        "flag billing discrepancies."
        "</p>",
        unsafe_allow_html=True,
    )

    with st.expander("Expected CSV format", expanded=False):
        st.write(
            """
The uploaded CSV should contain at least these columns:

- invoice_id
- carrier_name
- invoice_date
- lane_id
- origin_zip
- destination_zip
- shipment_weight_lbs
- freight_class
- base_rate_charged
- fuel_surcharge_pct_charged
- accessorial_liftgate
- accessorial_residential
- accessorial_inside_delivery
- total_charged
"""
        )


def render_audit_results(
    results: List[AuditResult],
    summary_stats: dict,
    severity_filter: list[str],
) -> None:
    # Summary metrics bar
    cols = st.columns(5)
    cols[0].metric("Invoices Audited", summary_stats.get("total_invoices", 0))
    cols[1].metric("Errors Found", summary_stats.get("invoices_with_errors", 0))
    cols[2].metric(
        "Recovery Opportunity",
        f"${summary_stats.get('total_recovery_opportunity', 0):,.0f}",
    )
    cols[3].metric("High Severity", summary_stats.get("high_severity_count", 0))
    cols[4].metric("Clean", summary_stats.get("clean_invoices", 0))

    st.markdown(
        "### <span class='material-symbols-outlined'>analytics</span>Audit Results",
        unsafe_allow_html=True,
    )
    df = results_to_display_df(results)
    if not df.empty:
        df["severity_for_filter"] = df["status"].apply(_severity_from_status)
        df_filtered = df[df["severity_for_filter"].isin(severity_filter)]
        st.dataframe(
            df_filtered.drop(columns=["severity_for_filter"]),
            use_container_width=True,
            hide_index=True,
            height=320,
        )
    else:
        st.info("No invoices to display.")

    st.markdown(
        "### <span class='material-symbols-outlined'>lightbulb</span>AI Audit Explanations",
        unsafe_allow_html=True,
    )
    st.caption(
        "Click any invoice to see why it was flagged and get a ready-to-send dispute message."
    )

    # Build mapping for explanations, filtered by severity
    for result in results:
        severity = result.max_severity or "CLEAN"
        if severity not in severity_filter or not result.findings:
            continue

        total_impact = result.total_dollar_impact
        if severity == "HIGH":
            emoji = "🚨"
        elif severity == "MEDIUM":
            emoji = "⚠️"
        elif severity == "LOW":
            emoji = "🔵"
        else:
            emoji = "✅"

        header = (
            f"{emoji} {result.invoice.invoice_id} — "
            f"{result.invoice.carrier_name} — "
            f"💰 ${total_impact:,.2f} recovery opportunity"
        )

        with st.expander(header):
            explanation = result.explanation
            if explanation is not None and explanation.summary:
                st.write("**Summary**")
                st.info(explanation.summary)

                st.write("**What We Found**")
                for text in explanation.findings_explained:
                    st.write(f"• {text}")

                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        "Recovery Opportunity",
                        f"${explanation.total_recovery_opportunity:,.2f}",
                    )
                with col2:
                    st.metric("Confidence", explanation.confidence)

                if explanation.dispute_recommended:
                    st.write("**📨 Dispute Message**")
                    st.code(explanation.dispute_message, language=None)
                else:
                    st.write("_Dispute not recommended for this invoice._")
            else:
                st.write("**Raw Findings (AI explanation not available)**")
                for f in result.findings:
                    st.write(
                        f"• **{f.rule_id}** — {f.description} — "
                        f"💰 ${f.dollar_impact:,.2f}"
                    )


def show_results(
    results: List[AuditResult],
    summary_stats: dict,
    severity_filter: list[str],
) -> None:
    """
    Backwards-compatible alias; delegates to render_audit_results.
    """
    render_audit_results(results, summary_stats, severity_filter)


def main() -> None:
    _init_session_state()
    controls = sidebar()

    uploaded_files = controls["uploaded_files"] or []
    enable_ai = controls["enable_ai"]
    severity_filter = controls["severity_filter"]
    run_clicked = controls["run_clicked"]

    if not uploaded_files:
        show_state_no_file()
        return

    csv_files = [f for f in uploaded_files if (f.name or "").lower().endswith(".csv")]
    pdf_files = [f for f in uploaded_files if (f.name or "").lower().endswith(".pdf")]

    if csv_files and pdf_files:
        st.error("Please upload either CSV files or PDF files in a single run, not both.")
        return

    if run_clicked:
        # CSV flow (supports multiple CSV files; they are concatenated).
        if csv_files:
            frames: list[pd.DataFrame] = []
            for f in csv_files:
                try:
                    frames.append(pd.read_csv(f))
                except Exception as e:  # noqa: BLE001
                    st.error(f"Failed to read uploaded CSV '{f.name}': {e}")
                    logger.exception("Failed to read uploaded CSV {}", f.name)
                    return

            if not frames:
                st.error("No CSV data found in uploaded files.")
                return

            df = pd.concat(frames, ignore_index=True)

            with st.spinner("🔍 Running policy engine..."):
                try:
                    results, summary = run_full_audit(
                        invoices_df=df,
                        explain=enable_ai,
                    )
                except ValueError as e:
                    st.error(str(e))
                    logger.warning("Audit aborted due to value error: {}", e)
                    return
                except Exception as e:  # noqa: BLE001
                    st.error("An unexpected error occurred while running the audit.")
                    logger.exception("Unexpected error in run_full_audit: {}", e)
                    return

                st.session_state.audit_results = results
                st.session_state.summary_stats = summary
                st.session_state.last_filename = ", ".join(f.name for f in csv_files)

        # PDF flow (supports multiple PDFs).
        elif pdf_files:
            tmp_dir = ROOT / "data" / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            pdf_paths: list[Path] = []
            for f in pdf_files:
                pdf_path = tmp_dir / f.name
                with pdf_path.open("wb") as fh:
                    fh.write(f.getbuffer())
                pdf_paths.append(pdf_path)

            with st.spinner("📄 Extracting invoice fields from PDF(s)..."):
                extractions: list[PDFExtractionResult] = []
                for p in pdf_paths:
                    extractions.extend(extract_invoices_from_pdf(p))

            total_fields = len(
                [
                    "invoice_id",
                    "carrier_name",
                    "invoice_date",
                    "origin_zip",
                    "destination_zip",
                    "shipment_weight_lbs",
                    "base_rate_charged",
                    "fuel_surcharge_pct_charged",
                    "total_charged",
                ]
            )

            with st.expander("🔍 Extraction Details", expanded=False):
                for extraction in extractions:
                    label = extraction.invoice_id or Path(extraction.pdf_path).name
                    st.markdown(f"**Invoice:** {label}")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric(
                            "Extraction Confidence",
                            extraction.overall_confidence.value,
                        )
                        st.metric(
                            "Fields Extracted",
                            f"{total_fields - len(extraction.missing_fields)}/{total_fields}",
                        )
                    with col2:
                        if extraction.missing_fields:
                            st.warning(
                                f"Missing fields: {', '.join(extraction.missing_fields)}"
                            )
                        if extraction.low_confidence_fields:
                            st.warning(
                                f"Low confidence: {', '.join(extraction.low_confidence_fields)}"
                            )

                    st.write("**Extracted Values:**")
                    st.json(
                        extraction.model_dump(
                            exclude={
                                "overall_confidence",
                                "missing_fields",
                                "low_confidence_fields",
                                "extraction_notes",
                                "requires_human_review",
                            }
                        )
                    )
                    st.markdown("---")

            try:
                rate_index = _load_rate_table_default()
            except FileNotFoundError as e:
                st.error(str(e))
                return

            with st.spinner("🔄 Normalizing extracted data..."):
                from src.engine.pdf_normalizer import normalize_batch

                norm_results = normalize_batch(extractions, rate_index)

            ready_norm = [nr for nr in norm_results if nr.ready_for_engine]
            blocked_norm = [nr for nr in norm_results if not nr.ready_for_engine]

            if blocked_norm:
                st.warning(
                    "Some invoices could not be processed automatically and require review."
                )
                for nr in blocked_norm:
                    label = nr.invoice.invoice_id if nr.invoice else Path(
                        nr.extraction.pdf_path
                    ).name
                    st.write(f"**Invoice:** {label}")
                    for err in nr.normalization_errors:
                        st.write(f"• {err}")

            if not ready_norm:
                st.error("⛔ No invoices were ready for engine processing.")
                st.write(
                    "Action required: Review the extracted values above and upload a corrected CSV manually."
                )
                return

            if any(nr.normalization_warnings for nr in ready_norm):
                st.warning(
                    "⚠️ Some invoices were processed with warnings — review before acting on findings:"
                )
                for nr in ready_norm:
                    label = nr.invoice.invoice_id
                    for w in nr.normalization_warnings:
                        st.write(f"• [{label}] {w}")

            with st.spinner("🔍 Running policy engine..."):
                try:
                    invoices_ready = [nr.invoice for nr in ready_norm if nr.invoice]
                    results, summary = run_full_audit_from_invoices(
                        invoices_ready, rate_index, explain=enable_ai
                    )
                except Exception as e:  # noqa: BLE001
                    st.error("An unexpected error occurred while running the audit.")
                    logger.exception(
                        "Unexpected error in run_full_audit_from_invoices: {}", e
                    )
                    return

                st.session_state.audit_results = results
                st.session_state.summary_stats = summary
                st.session_state.last_filename = ", ".join(f.name for f in pdf_files)

    if st.session_state.audit_results:
        render_audit_results(
            st.session_state.audit_results,
            st.session_state.summary_stats,
            severity_filter,
        )


if __name__ == "__main__":
    main()

