from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine.models import AuditResult
from src.services.audit_service import (
    get_summary_stats,
    results_to_display_df,
    run_full_audit,
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


def _rate_table_exists() -> bool:
    root = Path(__file__).resolve().parents[1]
    return (root / "data" / "master_rate_table.csv").exists() or any(
        (root / "data" / "reference").glob("*master_rate_table.csv")
    )


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
    st.sidebar.title("🔍 Freight Billing Auditor")
    st.sidebar.caption("AI-powered invoice compliance engine")
    st.sidebar.divider()

    uploaded_file = st.sidebar.file_uploader(
        label="Upload Invoice CSV",
        type=["csv"],
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
        "uploaded_file": uploaded_file,
        "enable_ai": enable_ai,
        "severity_filter": severity_filter,
        "run_clicked": run_clicked,
    }


def show_state_no_file() -> None:
    st.empty()
    st.markdown(
        "<div style='text-align: center; font-size: 48px;'>📋</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h2 style='text-align: center;'>Upload an invoice CSV to begin</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align: center;'>"
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


def show_results(
    results: List[AuditResult],
    summary_stats: dict,
    severity_filter: list[str],
) -> None:
    # Summary metrics bar
    cols = st.columns(5)
    cols[0].metric("📋 Invoices Audited", summary_stats.get("total_invoices", 0))
    cols[1].metric("🚨 Errors Found", summary_stats.get("invoices_with_errors", 0))
    cols[2].metric(
        "💰 Recovery Opportunity",
        f"${summary_stats.get('total_recovery_opportunity', 0):,.0f}",
    )
    cols[3].metric("⚠️ High Severity", summary_stats.get("high_severity_count", 0))
    cols[4].metric("✅ Clean", summary_stats.get("clean_invoices", 0))

    st.markdown("### Audit Results")
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

    st.markdown("### 🤖 AI Audit Explanations")
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


def main() -> None:
    _init_session_state()
    controls = sidebar()

    uploaded_file = controls["uploaded_file"]
    enable_ai = controls["enable_ai"]
    severity_filter = controls["severity_filter"]
    run_clicked = controls["run_clicked"]

    if uploaded_file is None:
        show_state_no_file()
        return

    # Only run when user clicks the button
    if run_clicked:
        try:
            df = pd.read_csv(uploaded_file)
        except Exception as e:  # noqa: BLE001
            st.error(f"Failed to read uploaded CSV: {e}")
            logger.exception("Failed to read uploaded CSV")
            return

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
            st.session_state.last_filename = uploaded_file.name

    if st.session_state.audit_results:
        show_results(
            st.session_state.audit_results,
            st.session_state.summary_stats,
            severity_filter,
        )
    else:
        show_state_no_file()


if __name__ == "__main__":
    main()

