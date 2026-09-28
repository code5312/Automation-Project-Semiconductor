"""Shared, cached resources for the Streamlit dashboard.

Like the FastAPI app's lifespan, this loads the heavy SamplingContext once
per Streamlit session (not on every page interaction) via st.cache_resource.
Pages call src.storage.repository / src.cli.build_event directly -- the
same pure-function pipeline the CLI and API use -- rather than going over
HTTP to the FastAPI app. For this single-machine PoC that avoids running
two servers just to view a dashboard; if this ever needs to run against a
FastAPI instance on a different machine, swap these two functions for
`requests` calls without touching the pages.

Note: the `sys.path` bootstrap that makes `from src...` resolve regardless
of launch cwd lives at the top of each page in pages/*.py, NOT here --
this module is itself reached via `from src.dashboard.common import ...`,
so by the time its own body runs, `src` must already be importable. Fixing
sys.path in here would be too late to help that very import.
"""
import streamlit as st

from src.cli import DEFAULT_DB_PATH, load_rules
from src.scenarios.catalog import SamplingContext, build_sampling_context


@st.cache_resource(show_spinner="데이터 로딩 중 (SECOM/진동/WM-811K)...")
def get_ctx() -> SamplingContext:
    return build_sampling_context()


@st.cache_resource(show_spinner=False)
def get_rules() -> dict:
    return load_rules()


def get_db_path() -> str:
    return DEFAULT_DB_PATH


# Fixed categorical color per department -- assigned in a fixed order (never
# cycled/recomputed) so the same dept always reads as the same color across
# every page. Hues are slots 1/2/3/4 of the project's validated categorical
# palette (see dataviz skill's references/palette.md): blue/orange/aqua/yellow.
DEPT_COLORS: dict[str, str] = {
    "YI": "#2a78d6",
    "MFG": "#eb6834",
    "M-ENG": "#1baf7a",
    "P-ENG": "#eda100",
}
_DEPT_FALLBACK_COLOR = "#898781"  # muted ink -- "(없음)" / unknown

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
BORDER = "rgba(11,11,11,0.10)"


def dept_color(dept: str | None) -> str:
    return DEPT_COLORS.get(dept, _DEPT_FALLBACK_COLOR)


def dept_badge(dept: str | None) -> str:
    """Small HTML pill for a department, in its fixed color. Render with
    st.markdown(..., unsafe_allow_html=True)."""
    label = dept or "(없음)"
    color = dept_color(dept)
    return (
        f'<span style="display:inline-block; padding:3px 12px; border-radius:999px; '
        f'background:{color}1a; color:{color}; border:1px solid {color}40; '
        f'font-weight:600; font-size:0.85rem;">{label}</span>'
    )


def inject_theme() -> None:
    """Shared CSS applied on every page, right after st.set_page_config().
    Kept conservative: only targets stable, documented data-testid hooks
    plus generic tags, so it degrades gracefully across Streamlit versions."""
    st.markdown(
        f"""
        <style>
        .block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1200px; }}
        [data-testid="stMetric"] {{
            background: #ffffff;
            border: 1px solid {BORDER};
            border-radius: 12px;
            padding: 1rem 1.25rem;
        }}
        [data-testid="stMetricLabel"] {{ color: {INK_SECONDARY}; font-weight: 500; }}
        [data-testid="stMetricValue"] {{ color: {INK_PRIMARY}; }}
        [data-testid="stSidebar"] {{ background: #f2f1ec; }}
        [data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 12px; }}
        h1, h2, h3 {{ color: {INK_PRIMARY}; letter-spacing: -0.01em; }}
        h1 {{ font-weight: 700; }}
        [data-testid="stCaptionContainer"] {{ color: {INK_MUTED}; }}
        hr {{ border-color: {BORDER}; }}
        .hp-eyebrow {{
            color: {INK_MUTED}; text-transform: uppercase; letter-spacing: 0.08em;
            font-size: 0.75rem; font-weight: 600; margin-bottom: -0.4rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
