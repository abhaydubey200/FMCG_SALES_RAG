"""
Amazon Sales & Marketing Intelligence Platform
Enterprise-Grade AI Decision Intelligence Workspace
"""
import os, time, json, requests, streamlit as st, pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="QueryBridge — Sales & Marketing Intelligence",
    page_icon="🔷", layout="wide", initial_sidebar_state="expanded",
    menu_items={"About": "AI Sales & Marketing Intelligence Platform"}
)

# ═══════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
:root {
  --bg-primary: #ffffff; --bg-secondary: #f8fafc; --bg-tertiary: #f1f5f9;
  --text-primary: #0f172a; --text-secondary: #475569; --text-muted: #94a3b8;
  --border: #e2e8f0; --border-light: #f1f5f9;
  --accent: #4f46e5; --accent-light: #eef2ff;
  --success: #059669; --success-bg: #ecfdf5; --success-border: #a7f3d0;
  --warning: #d97706; --warning-bg: #fffbeb; --warning-border: #fde68a;
  --danger: #dc2626; --danger-bg: #fef2f2; --danger-border: #fecaca;
  --info: #2563eb; --info-bg: #eff6ff; --info-border: #bfdbfe;
  --radius: 6px; --radius-lg: 8px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,.05);
  --shadow: 0 1px 3px rgba(0,0,0,.08);
}
*{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif!important;box-sizing:border-box}
html{scroll-behavior:smooth}
.block-container{padding-top:.8rem!important;padding-bottom:1rem!important;max-width:1440px}
h1{font-size:1.4rem!important;font-weight:700!important;color:var(--text-primary)!important;margin-bottom:.2rem!important}
h2,h3{font-size:1.05rem!important;font-weight:600!important;color:var(--text-primary)!important;margin-bottom:.4rem!important}

/* Sidebar */
section[data-testid="stSidebar"]{background:#0f172a!important;border-right:1px solid #1e293b}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
section[data-testid="stSidebar"] label{color:#cbd5e1!important;font-size:.82rem}
section[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.08)!important;margin:.3rem 0}
section[data-testid="stSidebar"] .stRadio>div>label{background:transparent;border-radius:var(--radius)!important;padding:6px 10px!important;margin:0!important;border:1px solid transparent!important;transition:all .15s}
section[data-testid="stSidebar"] .stRadio>div>label:hover{background:rgba(255,255,255,.06)!important}
section[data-testid="stSidebar"] .stRadio>div>label[data-checked="true"]{background:rgba(99,102,241,.12)!important;border-color:rgba(99,102,241,.25)!important}

/* Layout helpers */
.section-header{font-size:.9rem;font-weight:700;color:var(--text-primary);padding:.5rem 0 .3rem;margin:1rem 0 .5rem;border-bottom:2px solid var(--border);display:flex;align-items:center;gap:.5rem}
.section-header:first-child{margin-top:0}
.data-hint{font-size:.75rem;color:var(--text-muted);padding:.3rem 0}

/* KPI cards */
.kpi-card{background:var(--bg-primary);border:1px solid var(--border);border-radius:var(--radius-lg);padding:.7rem .9rem;transition:box-shadow .15s}
.kpi-card:hover{box-shadow:var(--shadow)}
.kpi-label{font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted);font-weight:600}
.kpi-value{font-size:1.35rem;font-weight:700;color:var(--text-primary);line-height:1.15;margin:1px 0}
.kpi-delta{font-size:.72rem;font-weight:600}
.kpi-delta.up{color:var(--success)}
.kpi-delta.down{color:var(--danger)}
.kpi-delta.neutral{color:var(--text-muted)}

/* Badges */
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;font-size:.68rem;font-weight:600;gap:3px}
.badge-knowledge{background:var(--info-bg);color:var(--info);border:1px solid var(--info-border)}
.badge-analytical{background:var(--success-bg);color:var(--success);border:1px solid var(--success-border)}
.badge-hybrid{background:#f5f3ff;color:#7c3aed;border:1px solid #ddd6fe}
.badge-diagnostic{background:var(--warning-bg);color:var(--warning);border:1px solid var(--warning-border)}
.badge-unanswerable{background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border)}
.badge-high{background:var(--danger-bg);color:var(--danger);border:1px solid var(--danger-border)}
.badge-medium{background:var(--warning-bg);color:var(--warning);border:1px solid var(--warning-border)}
.badge-low{background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border)}
.badge-open{background:var(--info-bg);color:var(--info);border:1px solid var(--info-border)}
.badge-progress{background:var(--warning-bg);color:var(--warning);border:1px solid var(--warning-border)}
.badge-completed{background:var(--success-bg);color:var(--success);border:1px solid var(--success-border)}
.badge-dismissed{background:var(--bg-tertiary);color:var(--text-muted);border:1px solid var(--border)}

/* Insight cards */
.insight-card{background:var(--bg-primary);border:1px solid var(--border);border-radius:var(--radius-lg);padding:.8rem 1rem;margin-bottom:.5rem;transition:box-shadow .15s}
.insight-card:hover{box-shadow:var(--shadow)}
.insight-card.warning{border-left:3px solid var(--warning)}
.insight-card.success{border-left:3px solid var(--success)}
.insight-card.info{border-left:3px solid var(--info)}
.insight-card.danger{border-left:3px solid var(--danger)}
.insight-title{font-weight:600;font-size:.88rem;color:var(--text-primary);margin-bottom:.3rem}
.insight-body{font-size:.82rem;color:var(--text-secondary);line-height:1.5}
.insight-meta{font-size:.72rem;color:var(--text-muted);margin-top:.3rem;display:flex;gap:.8rem}

/* Evidence panel */
.evidence-panel{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-lg);padding:.8rem 1rem}
.evidence-item{padding:.4rem 0;border-bottom:1px solid var(--border-light);font-size:.82rem}
.evidence-item:last-child{border-bottom:none}
.evidence-source{font-weight:600;color:var(--text-primary)}
.evidence-detail{color:var(--text-secondary)}

/* Tables */
.stDataFrame{border:1px solid var(--border)!important;border-radius:var(--radius)!important;overflow:hidden}

/* Status indicators */
.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.status-dot.healthy{background:var(--success)}
.status-dot.warning{background:var(--warning)}
.status-dot.error{background:var(--danger)}
.status-dot.unknown{background:var(--text-muted)}

/* Investigation tree */
.tree-node{padding:.4rem .6rem;margin:.2rem 0;border-radius:var(--radius);font-size:.82rem;cursor:pointer;border:1px solid var(--border-light);transition:all .15s}
.tree-node:hover{background:var(--accent-light);border-color:var(--accent)}
.tree-node.active{background:var(--accent-light);border-color:var(--accent);font-weight:600}

/* Search */
.search-result{padding:.6rem .8rem;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:.4rem;transition:all .15s}
.search-result:hover{border-color:var(--accent);background:var(--accent-light)}
.search-type{font-size:.65rem;text-transform:uppercase;font-weight:600;letter-spacing:.03em}

/* Progress bars */
.quality-bar{height:6px;background:var(--bg-tertiary);border-radius:3px;overflow:hidden;margin:.3rem 0}
.quality-fill{height:100%;border-radius:3px;transition:width .3s}
.quality-fill.good{background:var(--success)}
.quality-fill.ok{background:var(--warning)}
.quality-fill.bad{background:var(--danger)}

/* Tab styling */
.stTabs [data-baseweb="tab-list"]{gap:0;border-bottom:1px solid var(--border)}
.stTabs [data-baseweb="tab"]{font-size:.82rem;font-weight:500;padding:.5rem 1rem}
</style>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def ag(path, timeout=15):
    try:
        r = requests.get(f"{API}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def ap(path, data=None, files=None, timeout=60):
    try:
        if files:
            r = requests.post(f"{API}{path}", files=files, timeout=timeout)
        else:
            r = requests.post(f"{API}{path}", json=data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def put(path, data=None, timeout=10):
    try:
        r = requests.put(f"{API}{path}", json=data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def fm(v):
    """Format money."""
    if v is None: return "N/A"
    if abs(v) >= 1e6: return f"${v/1e6:.2f}M"
    if abs(v) >= 1e3: return f"${v/1e3:.1f}K"
    return f"${v:,.0f}"

def fd_pct(v):
    """Format delta percentage."""
    if v is None: return '<span class="kpi-delta neutral">—</span>'
    cls = "up" if v >= 0 else "down"
    arrow = "▲" if v >= 0 else "▼"
    return f'<span class="kpi-delta {cls}">{arrow} {abs(v):.1f}%</span>'

def kpi(label, value, delta=None):
    d = fd_pct(delta) if delta is not None else '<span class="kpi-delta neutral">—</span>'
    return f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div>{d}</div>'

def badge(text, variant="knowledge"):
    return f'<span class="badge badge-{variant}">{text}</span>'

def chart_base(h=320):
    return dict(
        height=h, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", size=11, color="#475569")
    )

def chart_grid(fig):
    s = dict(gridcolor="#f1f5f9", showgrid=True, zeroline=False)
    fig.update_xaxes(**s)
    fig.update_yaxes(**s)
    return fig

def section(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)

def empty_state(icon, title, subtitle):
    st.markdown(f"""
    <div style="text-align:center;padding:3rem 2rem;color:var(--text-muted)">
        <div style="font-size:2.5rem;margin-bottom:.5rem">{icon}</div>
        <div style="font-size:1rem;font-weight:600;color:var(--text-primary);margin-bottom:.3rem">{title}</div>
        <div style="font-size:.85rem">{subtitle}</div>
    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style="padding:.4rem 0 .6rem">
        <div style="font-size:1.1rem;font-weight:800;color:#e2e8f0;letter-spacing:-.02em">QueryBridge</div>
        <div style="font-size:.68rem;color:#94a3b8;font-weight:500">Sales & Marketing Intelligence</div>
    </div>""", unsafe_allow_html=True)
    st.markdown('<hr>', unsafe_allow_html=True)

    page = st.radio("Nav", [
        "📊 Overview",
        "🤖 AI Analyst",
        "─── Intelligence ───",
        "💰 Sales",
        "📢 Marketing",
        "📦 Products",
        "👥 Customers",
        "📢 Campaigns",
        "⭐ Reviews",
        "💲 Discounts",
        "─── Data ───",
        "📁 Data Hub",
        "🔍 Data Quality",
        "📚 Knowledge",
        "📐 Semantic Layer",
        "─── AI ───",
        "💡 Insights",
        "📋 Recommendations",
        "🔬 Investigation",
        "🧪 Evaluation",
        "─── Reports ───",
        "📄 Executive Reports",
        "✅ Actions",
        "─── System ───",
        "⚙️ System Health",
    ], label_visibility="collapsed")

    st.markdown('<hr>', unsafe_allow_html=True)

    # System status
    h = ag("/health")
    if h:
        st.markdown("""
        <div style="padding:.35rem .5rem;background:rgba(34,197,94,.08);border-radius:var(--radius);border:1px solid rgba(34,197,94,.15);font-size:.75rem">
            <span style="color:#22c55e">●</span>
            <span style="color:#86efac;font-weight:600"> System Online</span>
        </div>""", unsafe_allow_html=True)
        st.caption(f"LLM: {h.get('llm_backend','?')} · Embed: {h.get('embedding_backend','?')}")
    else:
        st.markdown("""
        <div style="padding:.35rem .5rem;background:rgba(239,68,68,.08);border-radius:var(--radius);border:1px solid rgba(239,68,68,.15);font-size:.75rem">
            <span style="color:#ef4444">●</span>
            <span style="color:#fca5a5;font-weight:600"> API Offline</span>
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. EXECUTIVE OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════
if page == "📊 Overview":
    st.markdown("# Executive Business Overview")
    kpi = ag("/api/analytics/overview")
    if not kpi:
        empty_state("⚠️", "API Not Available", "Start the backend API to view analytics")
        st.stop()

    section("Key Business Metrics")
    c = st.columns(6)
    metrics = [
        ("Revenue", fm(kpi["total_revenue"]), kpi.get("revenue_growth_pct")),
        ("Orders", f"{kpi['total_units_sold']:,}", kpi.get("units_growth_pct")),
        ("Gross Margin", f"{kpi['gross_margin_pct']}%", kpi.get("margin_growth_pct")),
        ("Marketing Spend", fm(kpi["total_marketing_spend"]), kpi.get("spend_growth_pct")),
        ("ROAS", f"{kpi['avg_roas']}x", kpi.get("roas_growth_pct")),
        ("Customers", f"{kpi['total_customers']:,}", kpi.get("customer_growth_pct")),
    ]
    for col, (label, value, delta) in zip(c, metrics):
        with col:
            st.markdown(kpi(label, value, delta), unsafe_allow_html=True)

    section("Performance Trends")
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Revenue & Profit Trend**")
        trend = ag("/api/analytics/revenue-trend")
        if trend:
            df = pd.DataFrame(trend)
            df["month"] = pd.to_datetime(df["month"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["month"], y=df["revenue"], name="Revenue",
                line=dict(color="#4f46e5", width=2.5), fill="tozeroy", fillcolor="rgba(79,70,229,.06)"))
            fig.add_trace(go.Scatter(x=df["month"], y=df["profit"], name="Profit",
                line=dict(color="#059669", width=2)))
            fig.update_layout(**chart_base(280), legend=dict(orientation="h", y=1.12))
            chart_grid(fig)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("**Revenue by Category**")
        cp = ag("/api/analytics/category-performance")
        if cp:
            df = pd.DataFrame(cp)
            fig = px.bar(df, x="revenue", y="category", orientation="h", color="category",
                color_discrete_sequence=["#4f46e5", "#059669", "#d97706", "#dc2626", "#7c3aed"],
                text_auto=".2s")
            fig.update_layout(**chart_base(280), showlegend=False,
                yaxis=dict(categoryorder="total ascending"))
            fig.update_traces(textposition="outside", textfont_size=10)
            chart_grid(fig)
            st.plotly_chart(fig, use_container_width=True)

    section("AI Business Insights")
    insights = ap("/api/insights")
    if insights and insights.get("insights"):
        for i in insights["insights"][:4]:
            ic = {"warning": "warning", "success": "success", "info": "info"}.get(i.get("type"), "info")
            st.markdown(f"""<div class="insight-card {ic}">
                <div class="insight-title">{i["title"]}</div>
                <div class="insight-body">{i["description"]}</div>
                <div class="insight-meta">
                    <span>Impact: {badge(i.get("impact","N/A").title(), i.get("impact","low"))}</span>
                    <span>Confidence: {i.get("confidence","N/A")}</span>
                </div>
            </div>""", unsafe_allow_html=True)

    section("Top Risks & Opportunities")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**⚠️ Risks**")
        rv = ag("/api/analytics/reviews")
        if rv and rv.get("negative_pct", 0) > 10:
            st.markdown(f"""<div class="insight-card warning">
                <div class="insight-title">Negative Review Rate: {rv["negative_pct"]}%</div>
                <div class="insight-body">{rv["negative_count"]} negative reviews detected across {rv["total_reviews"]} total. Review quality issues.</div>
            </div>""", unsafe_allow_html=True)
        camps = ag("/api/campaigns")
        if camps:
            low_roas = [c for c in camps if c.get("roas") and c["roas"] < 3.0]
            if low_roas:
                st.markdown(f"""<div class="insight-card warning">
                    <div class="insight-title">{len(low_roas)} Campaigns Below 3.0x ROAS Target</div>
                    <div class="insight-body">Campaigns requiring budget review: {", ".join(c["campaign_name"] for c in low_roas[:3])}</div>
                </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("**💡 Opportunities**")
        st.markdown("""<div class="insight-card success">
            <div class="insight-title">Premium Customer Retention</div>
            <div class="insight-body">Premium customers have significantly higher LTV. Retention investment in this segment has outsized ROI potential.</div>
        </div>""", unsafe_allow_html=True)
        high_margin = ag("/api/investigation/margin")
        if high_margin and high_margin.get("top_entities"):
            top3 = high_margin["top_entities"][:3]
            st.markdown(f"""<div class="insight-card info">
                <div class="insight-title">High-Margin Products</div>
                <div class="insight-body">{len(top3)} products with strong margins. Consider increased marketing investment: {", ".join(p["product_name"] for p in top3)}.</div>
            </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# 2. AI ANALYST
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🤖 AI Analyst":
    st.markdown("# AI Analyst")
    st.caption("Ask questions about sales, marketing, products, customers, campaigns, and strategy")

    examples = [
        "-- Select example --",
        "Which category generated the highest revenue?",
        "What is the recommended strategy for high-value customers?",
        "Which products generated the highest revenue, and what marketing strategy does the company recommend?",
        "Why did Electronics revenue decline in Q2?",
        "Which campaign should receive more budget?",
        "What does the marketing strategy recommend for premium customers?",
        "Which products have declining revenue and margin?",
        "Should we increase marketing investment in Electronics?",
        "What is the relationship between discounts and margin?",
        "What will Amazon sales be in 2035?",
    ]
    chosen = st.selectbox("💡 Try an example:", examples)
    dq = "" if chosen.startswith("--") else chosen
    q = st.text_input("Your question:", value=dq, placeholder="e.g. Why did revenue decline?")

    if st.button("🔍 Analyze", type="primary", use_container_width=True) and q.strip():
        with st.spinner("Classifying · Retrieving · Analyzing · Generating..."):
            t0 = time.time()
            r = ap("/query", {"question": q})
            lat = (time.time() - t0) * 1000

        if r:
            # Query Intelligence Panel
            section("Query Intelligence")
            ic1, ic2 = st.columns([1, 2])
            with ic1:
                m = r.get("metrics", {})
                qt = r["query_type"]
                st.markdown(f"""<div class="evidence-panel">
                    <div style="margin-bottom:.5rem"><strong>Question</strong><br><em>"{q}"</em></div>
                    <div style="margin-bottom:.5rem"><strong>Query Type</strong> {badge(qt.upper(), qt)}</div>
                    <div style="margin-bottom:.5rem"><strong>Classification</strong><br><span style="color:var(--text-secondary);font-size:.82rem">{m.get("classification_reason","N/A")}</span></div>
                    <div style="margin-bottom:.5rem"><strong>Evidence Sources</strong> {len(r.get("sources",[]))}</div>
                    <div><strong>Confidence</strong> {"High" if qt in ("analytical","knowledge") else "Medium"}</div>
                </div>""", unsafe_allow_html=True)
                is_structured = any(s["type"] == "structured_data" for s in r.get("sources", []))
                is_knowledge = any(s["type"] == "knowledge_base" for s in r.get("sources", []))
                st.markdown(f"""<div class="evidence-panel" style="margin-top:.5rem;font-size:.8rem">
                    <strong>Pipeline:</strong>
                    {"✅" if is_structured else "○"} Structured Data · {"✅" if is_knowledge else "○"} Vector Search · {"✅" if is_knowledge else "○"} Keyword · ✅ Rerank · ✅ Fuse
                </div>""", unsafe_allow_html=True)

            with ic2:
                # AI Answer with classification
                answer = r["answer"]
                st.markdown(f"""<div class="insight-card success" style="border-left:3px solid var(--success)">
                    <div class="insight-title">AI Answer</div>
                    <div class="insight-body" style="line-height:1.65;margin-top:.3rem">{answer}</div>
                    <div class="insight-meta" style="margin-top:.5rem">
                        <span>Latency: {m.get("end_to_end_latency_ms",0):.0f}ms</span>
                        <span>Backend: {m.get("llm_backend","?")}</span>
                    </div>
                </div>""", unsafe_allow_html=True)

            section("Evidence & Sources")
            ev1, ev2 = st.columns([1, 2])
            with ev1:
                st.markdown("**Data Sources:**")
                for s in r.get("sources", []):
                    is_doc = s["type"] == "knowledge_base"
                    ic = "📄" if is_doc else "📊"
                    cls = "knowledge" if is_doc else "analytical"
                    src_name = s["source"]
                    st.markdown(badge(f"{ic} {src_name}", cls), unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
            with ev2:
                with st.expander("📋 Full Evidence Panel", expanded=False):
                    ev = r.get("evidence", {})
                    if "knowledge_base_chunks" in ev:
                        st.markdown("**Knowledge Base Chunks:**")
                        for c in ev["knowledge_base_chunks"]:
                            st.markdown(f"""<div class="evidence-item">
                                <span class="evidence-source">{c["source"]}</span>
                                <span style="color:var(--accent);font-size:.75rem"> Relevance: {c["relevance_score"]}</span>
                                <div class="evidence-detail">{c["text"][:350]}...</div>
                            </div>""", unsafe_allow_html=True)
                    if "structured_data" in ev:
                        st.markdown("**Structured Data:**")
                        st.json(ev["structured_data"])
                    if "detected_conflict" in ev:
                        st.warning(f"⚠️ Conflict detected: {ev['detected_conflict'].get('note','')}")
        else:
            st.error("Query failed. Please check the API connection.")

    # Follow-up
    if "ai_history" not in st.session_state:
        st.session_state.ai_history = []


# ═══════════════════════════════════════════════════════════════════════════
# 3. SALES INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "💰 Sales":
    st.markdown("# Sales Intelligence")
    kpi_data = ag("/api/analytics/overview")
    if not kpi_data:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    section("Sales Performance")
    c = st.columns(6)
    for col, (l, v, d) in zip(c, [
        ("Revenue", fm(kpi_data["total_revenue"]), kpi_data.get("revenue_growth_pct")),
        ("Units Sold", f"{kpi_data['total_units_sold']:,}", kpi_data.get("units_growth_pct")),
        ("Gross Margin", f"{kpi_data['gross_margin_pct']}%", kpi_data.get("margin_growth_pct")),
        ("Marketing Spend", fm(kpi_data["total_marketing_spend"]), kpi_data.get("spend_growth_pct")),
        ("ROAS", f"{kpi_data['avg_roas']}x", kpi_data.get("roas_growth_pct")),
        ("Customers", f"{kpi_data['total_customers']:,}", kpi_data.get("customer_growth_pct")),
    ]):
        with col: st.markdown(kpi(l, v, d), unsafe_allow_html=True)

    section("Revenue & Profit Trend")
    trend = ag("/api/analytics/revenue-trend")
    if trend:
        df = pd.DataFrame(trend)
        df["month"] = pd.to_datetime(df["month"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["month"], y=df["revenue"], name="Revenue",
            line=dict(color="#4f46e5", width=2.5), fill="tozeroy", fillcolor="rgba(79,70,229,.06)"))
        fig.add_trace(go.Scatter(x=df["month"], y=df["profit"], name="Profit",
            line=dict(color="#059669", width=2), fill="tozeroy", fillcolor="rgba(5,150,105,.04)"))
        fig.update_layout(**chart_base(300), legend=dict(orientation="h", y=1.12))
        chart_grid(fig)
        st.plotly_chart(fig, use_container_width=True)

    section("Revenue by Category")
    cp = ag("/api/analytics/category-performance")
    if cp:
        df = pd.DataFrame(cp)
        fig = px.bar(df, x="category", y="revenue", color="category",
            text_auto=".2s", color_discrete_sequence=["#4f46e5", "#059669", "#d97706", "#dc2626", "#7c3aed"])
        fig.update_layout(**chart_base(280), showlegend=False)
        chart_grid(fig)
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df, use_container_width=True, hide_index=True, column_config={
            "revenue": st.column_config.NumberColumn("Revenue", format="$%,.0f"),
            "gross_profit": st.column_config.NumberColumn("Profit", format="$%,.0f"),
            "gross_margin_pct": st.column_config.NumberColumn("Margin", format="%.1f%%"),
            "total_roas": st.column_config.NumberColumn("ROAS", format="%.2fx"),
        })


# ═══════════════════════════════════════════════════════════════════════════
# 4. MARKETING INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📢 Marketing":
    st.markdown("# Marketing Intelligence")
    camps = ag("/api/campaigns")
    if not camps:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    df = pd.DataFrame(camps)
    ts, tre = df["spend"].sum(), df["attributed_revenue"].sum()
    broas = tre / ts if ts > 0 else 0

    section("Marketing Performance")
    c = st.columns(5)
    for col, (l, v) in zip(c, [
        ("Total Spend", fm(ts)), ("Attributed Revenue", fm(tre)),
        ("Blended ROAS", f"{broas:.2f}x"), ("Campaigns", str(len(camps))),
        ("Total Conversions", f"{df['conversions'].sum():,}"),
    ]):
        with col: st.markdown(kpi(l, v), unsafe_allow_html=True)

    section("ROAS by Campaign")
    c1, c2 = st.columns(2)
    with c1:
        dfs = df.sort_values("roas", ascending=True)
        fig = px.bar(dfs, x="roas", y="campaign_name", orientation="h", color="channel",
            text_auto=".2f", color_discrete_sequence=["#4f46e5", "#059669", "#d97706", "#7c3aed"])
        fig.add_vline(x=3.0, line_dash="dash", line_color="#dc2626", line_width=1, annotation_text="3.0x Target")
        fig.update_layout(**chart_base(400))
        chart_grid(fig)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("**Spend vs Revenue (bubble = conversions)**")
        fig = px.scatter(df, x="spend", y="attributed_revenue", size="conversions",
            color="channel", hover_name="campaign_name",
            color_discrete_sequence=["#4f46e5", "#059669", "#d97706", "#7c3aed"])
        fig.add_trace(go.Scatter(x=[0, df["spend"].max()*1.1], y=[0, df["spend"].max()*1.1],
            mode="lines", line=dict(dash="dash", color="#94a3b8"), name="1:1"))
        fig.update_layout(**chart_base(400))
        chart_grid(fig)
        st.plotly_chart(fig, use_container_width=True)

    section("Campaign Directory")
    f1, f2 = st.columns(2)
    with f1: sel_ch = st.selectbox("Filter by Channel", ["All"] + sorted(df["channel"].unique().tolist()))
    df_f = df if sel_ch == "All" else df[df["channel"] == sel_ch]
    st.dataframe(df_f.sort_values("roas", ascending=False), use_container_width=True, hide_index=True, column_config={
        "spend": st.column_config.NumberColumn("Spend", format="$%,.0f"),
        "attributed_revenue": st.column_config.NumberColumn("Revenue", format="$%,.0f"),
        "roas": st.column_config.NumberColumn("ROAS", format="%.2fx"),
        "ctr": st.column_config.NumberColumn("CTR", format="%.3f%%"),
        "conversion_rate": st.column_config.NumberColumn("Conv Rate", format="%.3f%%"),
        "cpc": st.column_config.NumberColumn("CPC", format="$%.2f"),
        "cpa": st.column_config.NumberColumn("CPA", format="$%.2f"),
    })


# ═══════════════════════════════════════════════════════════════════════════
# 5. PRODUCT INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📦 Products":
    st.markdown("# Product Intelligence")
    prods = ag("/api/products")
    if not prods:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    df = pd.DataFrame(prods)
    section("Product Summary")
    c = st.columns(4)
    for col, (l, v) in zip(c, [
        ("Products", str(len(prods))), ("Revenue", fm(df["total_revenue"].sum())),
        ("Units Sold", f"{df['total_units_sold'].sum():,}"),
        ("Avg Margin", f"{df['gross_margin_pct'].dropna().mean():.1f}%"),
    ]):
        with col: st.markdown(kpi(l, v), unsafe_allow_html=True)

    section("Top 10 Products by Revenue")
    top10 = df.nlargest(10, "total_revenue")
    fig = px.bar(top10, x="total_revenue", y="product_name", orientation="h",
        color="category", text_auto=".2s",
        color_discrete_sequence=["#4f46e5", "#059669", "#d97706", "#dc2626", "#7c3aed"])
    fig.update_layout(**chart_base(380))
    chart_grid(fig)
    st.plotly_chart(fig, use_container_width=True)

    section("Revenue by Category")
    cr = df.groupby("category").agg({"total_revenue": "sum", "product_id": "count"}).reset_index()
    cr.columns = ["category", "revenue", "count"]
    fig = px.pie(cr, values="revenue", names="category", hole=.45,
        color_discrete_sequence=["#4f46e5", "#059669", "#d97706", "#dc2626", "#7c3aed"])
    fig.update_layout(**chart_base(300))
    st.plotly_chart(fig, use_container_width=True)

    section("Product Directory")
    f1, f2, f3 = st.columns(3)
    with f1: sel = st.selectbox("Category", ["All"] + sorted(df["category"].unique().tolist()))
    with f2: sb = st.selectbox("Sort by", ["Revenue", "Units", "Margin", "ROAS", "Rating"])
    with f3: search = st.text_input("Search products:", placeholder="Product name...")
    df_f = df.copy()
    if sel != "All": df_f = df_f[df_f["category"] == sel]
    if search.strip(): df_f = df_f[df_f["product_name"].str.contains(search, case=False, na=False)]
    sm = {"Revenue": "total_revenue", "Units": "total_units_sold", "Margin": "gross_margin_pct", "ROAS": "product_roas", "Rating": "rating"}
    df_f = df_f.sort_values(sm[sb], ascending=False, na_position="last")
    st.dataframe(df_f, use_container_width=True, hide_index=True, height=400, column_config={
        "price": st.column_config.NumberColumn("Price", format="$%.2f"),
        "total_revenue": st.column_config.NumberColumn("Revenue", format="$%,.0f"),
        "total_units_sold": st.column_config.NumberColumn("Units", format="%d"),
        "gross_margin_pct": st.column_config.NumberColumn("Margin", format="%.1f%%"),
        "total_marketing_spend": st.column_config.NumberColumn("Spend", format="$%,.0f"),
        "product_roas": st.column_config.NumberColumn("ROAS", format="%.2fx"),
        "rating": st.column_config.NumberColumn("Rating", format="%.1f ⭐"),
    })


# ═══════════════════════════════════════════════════════════════════════════
# 6. CUSTOMER INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "👥 Customers":
    st.markdown("# Customer Intelligence")
    seg = ag("/api/customers/segments")
    if not seg:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    df = pd.DataFrame(seg)
    section("Customer Overview")
    c = st.columns(3)
    for col, (l, v) in zip(c, [
        ("Customers", f"{df['customers'].sum():,}"),
        ("Revenue", fm(df["revenue"].sum())),
        ("Avg LTV", fm(df["avg_ltv"].mean())),
    ]):
        with col: st.markdown(kpi(l, v), unsafe_allow_html=True)

    section("Customer Segments")
    sc = st.columns(len(seg))
    for i, s in enumerate(seg):
        with sc[i]:
            rp = f"{s.get('repeat_purchase_rate',0):.1f}%" if s.get("repeat_purchase_rate") is not None else "N/A"
            st.markdown(f"""<div class="insight-card" style="text-align:center">
                <div class="kpi-label">{s["segment"]}</div>
                <div class="kpi-value" style="font-size:1.2rem">{s["customers"]:,}</div>
                <div style="font-size:.75rem;color:var(--text-muted)">customers</div>
                <div style="margin-top:.5rem;border-top:1px solid var(--border);padding-top:.4rem">
                    <div style="color:var(--success);font-weight:700;font-size:.95rem">{fm(s["revenue"])}</div>
                    <div style="font-size:.72rem;color:var(--text-muted)">LTV: {fm(s["avg_ltv"])} · Repeat: {rp}</div>
                </div>
            </div>""", unsafe_allow_html=True)

    section("Segment Analysis")
    c1, c2 = st.columns(2)
    with c1:
        fig = px.pie(df, values="revenue", names="segment", hole=.45,
            color_discrete_sequence=["#4f46e5", "#059669", "#d97706", "#dc2626"])
        fig.update_layout(**chart_base(280), title="Revenue by Segment")
        fig.update_traces(textinfo="label+percent")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(df, x="segment", y="avg_ltv", color="segment",
            color_discrete_sequence=["#4f46e5", "#059669", "#d97706", "#dc2626"], text_auto="$,.0f")
        fig.update_layout(**chart_base(280), showlegend=False, title="Average LTV by Segment")
        chart_grid(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        "revenue": st.column_config.NumberColumn("Revenue", format="$%,.0f"),
        "avg_ltv": st.column_config.NumberColumn("Avg LTV", format="$%,.0f"),
        "repeat_purchase_rate": st.column_config.NumberColumn("Repeat Rate", format="%.1f%%"),
    })


# ═══════════════════════════════════════════════════════════════════════════
# 7. CAMPAIGN INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📢 Campaigns":
    st.markdown("# Campaign Intelligence")
    camps = ag("/api/campaigns")
    if not camps:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    df = pd.DataFrame(camps)
    section("Campaign Performance Overview")
    ts, tre = df["spend"].sum(), df["attributed_revenue"].sum()
    broas = tre / ts if ts > 0 else 0
    c = st.columns(5)
    for col, (l, v) in zip(c, [
        ("Spend", fm(ts)), ("Revenue", fm(tre)),
        ("ROAS", f"{broas:.2f}x"), ("CTR", f"{df['ctr'].mean():.3f}%"),
        ("Conv Rate", f"{df['conversion_rate'].mean():.3f}%"),
    ]):
        with col: st.markdown(kpi(l, v), unsafe_allow_html=True)

    section("ROAS vs Target (3.0x)")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["campaign_name"], y=df["roas"], marker_color=["#059669" if r >= 3 else "#dc2626" for r in df["roas"]], text=df["roas"].apply(lambda x: f"{x:.2f}x"), textposition="outside"))
    fig.add_hline(y=3.0, line_dash="dash", line_color="#dc2626", annotation_text="Target 3.0x")
    fig.update_layout(**chart_base(320), xaxis_tickangle=-45)
    chart_grid(fig)
    st.plotly_chart(fig, use_container_width=True)

    section("All Campaigns")
    st.dataframe(df.sort_values("roas", ascending=False), use_container_width=True, hide_index=True, column_config={
        "spend": st.column_config.NumberColumn("Spend", format="$%,.0f"),
        "attributed_revenue": st.column_config.NumberColumn("Revenue", format="$%,.0f"),
        "roas": st.column_config.NumberColumn("ROAS", format="%.2fx"),
        "ctr": st.column_config.NumberColumn("CTR", format="%.3f%%"),
        "conversion_rate": st.column_config.NumberColumn("Conv Rate", format="%.3f%%"),
        "cpc": st.column_config.NumberColumn("CPC", format="$%.2f"),
        "cpa": st.column_config.NumberColumn("CPA", format="$%.2f"),
    })


# ═══════════════════════════════════════════════════════════════════════════
# 8. REVIEW INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "⭐ Reviews":
    st.markdown("# Review Intelligence")
    rv = ag("/api/analytics/reviews")
    if not rv:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    section("Review Summary")
    c = st.columns(4)
    for col, (l, v) in zip(c, [
        ("Total Reviews", f"{rv['total_reviews']:,}"),
        ("Avg Rating", f"⭐ {rv['avg_rating']:.1f}" if rv.get("avg_rating") else "N/A"),
        ("Negative Reviews", str(rv["negative_count"])),
        ("Negative Rate", f"{rv['negative_pct']}%"),
    ]):
        with col: st.markdown(kpi(l, v), unsafe_allow_html=True)

    section("Rating Distribution & Themes")
    c1, c2 = st.columns(2)
    with c1:
        if rv["by_rating"]:
            df = pd.DataFrame(rv["by_rating"])
            fig = px.bar(df, x="rating", y="count", color="rating",
                color_continuous_scale=["#dc2626", "#d97706", "#94a3b8", "#059669", "#059669"],
                text_auto=True)
            fig.update_layout(**chart_base(280), showlegend=False)
            chart_grid(fig)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("**Top Negative Review Themes**")
        if rv["top_negative_themes"]:
            df = pd.DataFrame(rv["top_negative_themes"])
            fig = px.bar(df, x="count", y="theme", orientation="h",
                color_discrete_sequence=["#dc2626"], text_auto=True)
            fig.update_layout(**chart_base(280), yaxis=dict(categoryorder="total ascending"))
            chart_grid(fig)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No significant negative themes detected.")


# ═══════════════════════════════════════════════════════════════════════════
# 9. DISCOUNT INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "💲 Discounts":
    st.markdown("# Discount & Promotion Analytics")
    da = ag("/api/analytics/discounts")
    if not da:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    st.markdown(f"**Overall Average Discount:** {da['overall_avg_discount']}%")
    st.info("ℹ️ Observed correlations between discounts and margins are presented below. These represent observed relationships, not proven causation.", icon="ℹ️")

    section("Discount Analysis")
    c1, c2 = st.columns(2)
    with c1:
        if da["discount_bands"]:
            df = pd.DataFrame(da["discount_bands"])
            fig = px.bar(df, x="discount_band", y="total_revenue", text_auto=".2s",
                color_discrete_sequence=["#4f46e5"])
            fig.update_layout(**chart_base(280), title="Revenue by Discount Band")
            chart_grid(fig)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        if da["margin_by_band"]:
            df = pd.DataFrame(da["margin_by_band"])
            fig = px.bar(df, x="band", y="avg_margin_pct", text_auto=".1f",
                color_discrete_sequence=["#059669"])
            fig.update_layout(**chart_base(280), title="Avg Margin by Discount Band")
            chart_grid(fig)
            st.plotly_chart(fig, use_container_width=True)

    if da["discount_bands"]:
        st.dataframe(pd.DataFrame(da["discount_bands"]), use_container_width=True, hide_index=True, column_config={
            "total_revenue": st.column_config.NumberColumn("Revenue", format="$%,.0f"),
            "total_units": st.column_config.NumberColumn("Units", format="%d"),
            "avg_selling_price": st.column_config.NumberColumn("Avg Price", format="$%.2f"),
        })


# ═══════════════════════════════════════════════════════════════════════════
# 10. DATA HUB
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📁 Data Hub":
    st.markdown("# Data Hub")
    st.caption("Upload, profile, validate, and manage structured datasets")

    tab_up, tab_list = st.tabs(["📤 Upload Dataset", "📋 Connected Sources"])

    with tab_up:
        section("Upload & Profile Dataset")
        st.caption("Upload a CSV or Excel file for automatic profiling, validation, and semantic mapping.")
        up = st.file_uploader("Choose a file", type=["csv", "xlsx", "xls"], key="dh_upload")
        if up and st.button("📤 Upload & Profile", type="primary", key="dh_btn"):
            with st.spinner("Uploading · Parsing · Profiling · Validating · Mapping..."):
                r = ap("/api/datahub/upload", files={"file": (up.name, up.getvalue(), "application/octet-stream")})
            if r:
                st.success(f"✅ Processed {r['total_rows']:,} rows across {len(r['profiles'])} dataset(s)")
                for p in r["profiles"]:
                    with st.expander(f"📊 {p['filename']}" + (f" — Sheet: {p['sheet_name']}" if p.get("sheet_name") else ""), expanded=True):
                        st.markdown(f"**Quality Score:** {p['quality_score']}/100")
                        st.progress(p["quality_score"] / 100)
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Rows", f"{p['row_count']:,}")
                        m2.metric("Columns", p["col_count"])
                        m3.metric("Duplicates", p["duplicate_rows"])
                        m4.metric("Issues", len(p["issues"]))
                        if p["issues"]:
                            st.markdown("**Issues Detected:**")
                            for iss in p["issues"]:
                                st.warning(iss["message"])
                        st.markdown("**Column Profiles:**")
                        for c in p["columns"]:
                            st.markdown(f"  `{c['name']}` ({c['dtype']}) — semantic: **{c['semantic_type']}** · unique: {c['unique_count']} · nulls: {c['null_pct']}%")
            else:
                st.error("Upload failed. Please check the file and try again.")

    with tab_list:
        section("Connected Data Sources")
        ds_list = ag("/api/datahub/datasets")
        if ds_list:
            for ds in ds_list:
                st.markdown(f"""<div class="insight-card">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <div>
                            <div class="insight-title">{ds['filename']}</div>
                            <div class="insight-meta">
                                <span>{ds['total_rows']:,} rows</span>
                                <span>{ds['total_columns']} columns</span>
                                <span>{badge(f"Score: {ds['quality_score']}", "analytical")}</span>
                            </div>
                        </div>
                    </div>
                </div>""", unsafe_allow_html=True)
        else:
            empty_state("📁", "No Datasets Connected", "Upload a CSV or Excel file to get started.")


# ═══════════════════════════════════════════════════════════════════════════
# 11. DATA QUALITY
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🔍 Data Quality":
    st.markdown("# Data Quality Assessment")
    dq = ag("/api/data-quality")
    if not dq:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    section("Overall Data Quality")
    score = dq.get("overall_score", 0)
    total = dq.get("total_checks", 0)
    passed = dq.get("passed_checks", 0)
    c = st.columns(3)
    c[0].markdown(kpi("Quality Score", f"{score:.0f}/100"), unsafe_allow_html=True)
    c[1].markdown(kpi("Checks Passed", f"{passed}/{total}"), unsafe_allow_html=True)
    c[2].markdown(kpi("Tables Analyzed", str(len(dq.get("tables", {})))), unsafe_allow_html=True)

    cls = "good" if score >= 90 else ("ok" if score >= 70 else "bad")
    st.markdown(f'<div class="quality-bar"><div class="quality-fill {cls}" style="width:{score}%"></div></div>', unsafe_allow_html=True)

    section("Table-Level Quality")
    for table_name, table_data in dq.get("tables", {}).items():
        with st.expander(f"📋 {table_name.title()} — {table_data['total_rows']:,} rows, {len(table_data['checks'])} checks", expanded=False):
            for check in table_data["checks"]:
                status_icon = "✅" if check["status"] == "pass" else "⚠️"
                st.markdown(f'{status_icon} **{check["column"]}** — completeness: {check["completeness"]}% · nulls: {check["null_count"]}')
                if check["completeness"] < 100:
                    st.progress(check["completeness"] / 100)
            if table_data.get("duplicate_count", 0) > 0:
                st.warning(f"⚠️ {table_data['duplicate_count']} duplicate key(s) detected")


# ═══════════════════════════════════════════════════════════════════════════
# 12. KNOWLEDGE CENTER
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📚 Knowledge":
    st.markdown("# Knowledge Center")
    st.caption("RAG knowledge base — document management, ingestion, and retrieval")

    docs = ag("/documents")
    if docs is None:
        empty_state("⚠️", "API Not Available", "Start the backend API"); st.stop()

    tc = sum(d["chunk_count"] for d in docs)
    section("Knowledge Base Status")
    c = st.columns(4)
    for col, (l, v) in zip(c, [
        ("Documents", str(len(docs))), ("Chunks", f"{tc:,}"),
        ("Embeddings", f"{tc:,}"), ("Vector Store", "TF-IDF + BM25"),
    ]):
        with col: st.markdown(kpi(l, v), unsafe_allow_html=True)

    section("Indexed Documents")
    for doc in docs:
        st.markdown(f"""<div class="insight-card">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <div class="insight-title">📄 {doc['document_name']}</div>
                    <div class="insight-meta">
                        <span>{doc['chunk_count']} chunks</span>
                        <span>{doc['document_type']}</span>
                    </div>
                </div>
                <div>{badge("Indexed ✓", "analytical")}</div>
            </div>
        </div>""", unsafe_allow_html=True)

    section("Upload Document")
    st.caption("Supported: Markdown (.md), CSV (.csv), Excel (.xlsx/.xls), Text (.txt)")
    up = st.file_uploader("Choose a file", type=["md", "csv", "xlsx", "xls", "txt"], key="kb_up")
    if up and st.button("📤 Upload & Index", type="primary", key="kb_btn"):
        ext = up.name.rsplit(".", 1)[-1].lower()
        mime = {"md": "text/markdown", "csv": "text/csv",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "xls": "application/vnd.ms-excel", "txt": "text/plain"}
        with st.spinner(f"Processing {ext.upper()} document..."):
            r = ap("/documents/upload", files={"file": (up.name, up.getvalue(), mime.get(ext, "application/octet-stream"))})
        if r:
            st.success(f"✅ {r['message']} ({r['chunks_created']} chunks)")
            st.rerun()
        else:
            st.error("Upload failed. Please check the file format.")

    section("Search Knowledge Base")
    kbq = st.text_input("Search:", placeholder="Search documents...")
    if kbq:
        with st.spinner("Searching knowledge base..."):
            r = ap("/query", {"question": kbq})
        if r and r.get("evidence", {}).get("knowledge_base_chunks"):
            for c in r["evidence"]["knowledge_base_chunks"]:
                with st.expander(f"📄 {c['source']} — Relevance: {c['relevance_score']}"):
                    st.markdown(c["text"])


# ═══════════════════════════════════════════════════════════════════════════
# 13. SEMANTIC LAYER
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📐 Semantic Layer":
    st.markdown("# Semantic & Metric Layer")
    st.caption("Business metric definitions and dimension catalog")

    metrics_data = ag("/api/semantic/metrics")
    dims_data = ag("/api/semantic/dimensions")

    section("Business Metrics")
    if metrics_data and metrics_data.get("metrics"):
        for m in metrics_data["metrics"]:
            st.markdown(f"""<div class="insight-card">
                <div style="display:flex;justify-content:space-between;align-items:start">
                    <div>
                        <div class="insight-title">{m["name"]}</div>
                        <div class="insight-body">{m["definition"]}</div>
                    </div>
                    {badge(m["source"], "analytical")}
                </div>
                <div style="margin-top:.4rem;font-size:.82rem">
                    <code style="background:var(--bg-tertiary);padding:2px 6px;border-radius:3px">{m["formula"]}</code>
                </div>
                <div class="insight-meta">
                    <span>Dimensions: {", ".join(m["dimensions"])}</span>
                </div>
            </div>""", unsafe_allow_html=True)

    section("Dimensions Catalog")
    if dims_data and dims_data.get("dimensions"):
        for d in dims_data["dimensions"]:
            cols = ", ".join(d.get("columns", d.get("values", [])))
            st.markdown(f"""<div class="insight-card">
                <div class="insight-title">{d["name"]}</div>
                <div class="insight-body">Source: {d["source"]} · Columns: {cols}</div>
            </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# 14. AI INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "💡 Insights":
    st.markdown("# AI Insights")
    st.caption("Proactive business insights generated from data analysis")

    if st.button("🔄 Generate Insights", type="primary", key="ins_btn"):
        with st.spinner("Analyzing data patterns..."):
            r = ap("/api/insights")
        if r and r.get("insights"):
            st.session_state["insights"] = r["insights"]

    ins = st.session_state.get("insights")
    if ins:
        section(f"Generated Insights ({len(ins)})")
        for i in ins:
            ic = {"warning": "warning", "success": "success", "info": "info"}.get(i.get("type"), "info")
            icon = {"warning": "⚠️", "success": "✅", "info": "💡"}.get(i.get("type"), "💡")
            st.markdown(f"""<div class="insight-card {ic}">
                <div class="insight-title">{icon} {i["title"]}</div>
                <div class="insight-body">{i["description"]}</div>
                <div class="insight-meta">
                    <span>Impact: {badge(i.get("impact","N/A").title(), i.get("impact","low"))}</span>
                    <span>Confidence: {i.get("confidence","N/A")}</span>
                </div>
                {"<div style='margin-top:.3rem;font-size:.78rem;color:var(--text-secondary)'>Evidence: " + " · ".join(i.get("evidence",[])) + "</div>" if i.get("evidence") else ""}
            </div>""", unsafe_allow_html=True)
    else:
        empty_state("💡", "No Insights Generated", "Click 'Generate Insights' to analyze the data and surface actionable business insights.")


# ═══════════════════════════════════════════════════════════════════════════
# 15. RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📋 Recommendations":
    st.markdown("# AI Recommendations")
    st.caption("Evidence-backed recommendations for business decisions")

    # Generate from data
    if st.button("🔄 Generate Recommendations", type="primary", key="rec_btn"):
        with st.spinner("Analyzing data and generating recommendations..."):
            r = ap("/api/insights")
            if r and r.get("insights"):
                st.session_state["recs"] = [
                    {"title": i["title"], "why": i["description"],
                     "evidence": " · ".join(i.get("evidence", [])),
                     "confidence": i.get("confidence", "Medium"),
                     "impact": i.get("impact", "medium")}
                    for i in r["insights"]
                ]

    recs = st.session_state.get("recs", [])
    if recs:
        section(f"Recommendations ({len(recs)})")
        for i, rec in enumerate(recs):
            st.markdown(f"""<div class="insight-card info">
                <div class="insight-title">📋 {rec["title"]}</div>
                <div class="insight-body"><strong>Why:</strong> {rec["why"]}</div>
                <div class="insight-meta">
                    <span>Evidence: {rec["evidence"]}</span>
                    <span>Confidence: {badge(rec["confidence"], "analytical" if rec["confidence"]=="High" else "diagnostic")}</span>
                    <span>Impact: {badge(rec.get("impact","medium").title(), rec.get("impact","medium"))}</span>
                </div>
            </div>""", unsafe_allow_html=True)
            if st.button(f"✅ Create Action", key=f"create_action_{i}"):
                ap("/api/actions", {"title": rec["title"], "description": rec["why"],
                    "source_insight": rec["evidence"], "expected_outcome": "Improvement expected based on data evidence"})
                st.success(f"Action created for: {rec['title']}")
    else:
        empty_state("📋", "No Recommendations", "Click 'Generate Recommendations' to get evidence-backed suggestions.")


# ═══════════════════════════════════════════════════════════════════════════
# 16. INVESTIGATION WORKSPACE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🔬 Investigation":
    st.markdown("# Investigation Workspace")
    st.caption("Structured business analysis and drill-down investigation")

    metric = st.selectbox("Investigate metric:", ["revenue", "roas", "margin", "customers", "campaigns"])
    if st.button("🔬 Start Investigation", type="primary", key="inv_btn"):
        with st.spinner(f"Investigating {metric}..."):
            inv = ag(f"/api/investigation/{metric}")
        if inv:
            st.session_state["investigation"] = inv

    inv = st.session_state.get("investigation")
    if inv:
        section(f"Investigation: {metric.title()}")

        # Breakdown
        for key, data in inv.get("breakdowns", {}).items():
            section(f"Breakdown: {key.replace('by_', '').replace('_', ' ').title()}")
            if isinstance(data, list) and data:
                df = pd.DataFrame(data)
                # Find numeric columns for charting
                num_cols = df.select_dtypes(include=["number"]).columns.tolist()
                cat_col = [c for c in df.columns if c not in num_cols]
                if cat_col and num_cols:
                    fig = px.bar(df, x=cat_col[0], y=num_cols[0] if num_cols else None, text_auto=".2s",
                        color_discrete_sequence=["#4f46e5"])
                    fig.update_layout(**chart_base(280))
                    chart_grid(fig)
                    st.plotly_chart(fig, use_container_width=True)
                st.dataframe(df, use_container_width=True, hide_index=True)

        # Trend
        if inv.get("trend"):
            section("Time Series Trend")
            df = pd.DataFrame(inv["trend"])
            if "month" in df.columns:
                df["month"] = pd.to_datetime(df["month"])
                fig = go.Figure()
                for col in ["revenue", "profit"]:
                    if col in df.columns:
                        fig.add_trace(go.Scatter(x=df["month"], y=df[col], name=col.title(),
                            line=dict(width=2)))
                fig.update_layout(**chart_base(280))
                chart_grid(fig)
                st.plotly_chart(fig, use_container_width=True)

        # Top entities
        if inv.get("top_entities"):
            section("Top Entities")
            df = pd.DataFrame(inv["top_entities"])
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Drill-down action
            if "category" in df.columns:
                cats = df["category"].unique().tolist()
                sel_cat = st.selectbox("Drill into category:", ["All"] + cats)
                if sel_cat != "All":
                    filtered = df[df["category"] == sel_cat]
                    st.dataframe(filtered, use_container_width=True, hide_index=True)
    else:
        empty_state("🔬", "Ready to Investigate", "Select a metric and click 'Start Investigation' to begin structured analysis.")


# ═══════════════════════════════════════════════════════════════════════════
# 17. EVALUATION
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🧪 Evaluation":
    st.markdown("# RAG Evaluation")
    st.caption("System quality measurement across 38 test cases")

    if st.button("▶️ Run Evaluation Suite", type="primary", key="eval_run", use_container_width=True):
        with st.spinner("Running 38 test cases..."):
            r = ag("/api/evaluation/run", timeout=120)
        if r:
            st.session_state["eval"] = r
            st.success("✅ Evaluation complete!")
            st.rerun()
        else:
            st.error("Evaluation failed. Please check the API.")

    ev = st.session_state.get("eval")
    if ev:
        section("Evaluation Metrics")
        c = st.columns(4)
        for col, (l, v) in zip(c, [
            ("Type Accuracy", f"{ev['query_type_accuracy']*100:.1f}%"),
            ("Retrieval Recall", f"{ev['retrieval_recall_at_k']*100:.1f}%"),
            ("Avg Latency", f"{ev['avg_end_to_end_latency_ms']:.0f}ms"),
            ("P95 Latency", f"{ev['p95_end_to_end_latency_ms']:.0f}ms"),
        ]):
            with col: st.markdown(kpi(l, v), unsafe_allow_html=True)

        section("Results by Category")
        bk = ev.get("by_bucket", {})
        if bk:
            bdf = pd.DataFrame([{"Category": k, "Count": v["count"],
                "Type Accuracy": v["type_accuracy"]*100,
                "Retrieval Recall": v["retrieval_recall"]*100} for k, v in bk.items()])
            fig = go.Figure()
            fig.add_trace(go.Bar(name="Type Accuracy", x=bdf["Category"], y=bdf["Type Accuracy"],
                marker_color="#4f46e5", text=bdf["Type Accuracy"].apply(lambda x: f"{x:.0f}%"), textposition="outside"))
            fig.add_trace(go.Bar(name="Retrieval Recall", x=bdf["Category"], y=bdf["Retrieval Recall"],
                marker_color="#059669", text=bdf["Retrieval Recall"].apply(lambda x: f"{x:.0f}%"), textposition="outside"))
            fig.update_layout(**chart_base(280), barmode="group", yaxis_title="%", yaxis_range=[0, 110])
            chart_grid(fig)
            st.plotly_chart(fig, use_container_width=True)

        section("Test Cases")
        tc = ev.get("test_cases", [])
        passed = sum(1 for t in tc if t.get("type_match"))
        c = st.columns(3)
        c[0].metric("Total", str(len(tc)))
        c[1].metric("Passed", f"✅ {passed}")
        c[2].metric("Failed", f"❌ {len(tc) - passed}")

        flt = st.selectbox("Filter:", ["All", "Passed", "Failed"], key="eval_f")
        for t in tc:
            if flt == "Passed" and not t.get("type_match"): continue
            if flt == "Failed" and t.get("type_match"): continue
            ic = "✅" if t.get("type_match") else "❌"
            with st.expander(f"{ic} [{t['id']}] {t['question'][:80]}"):
                st.markdown(f"**Q:** {t['question']}")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Expected:** `{t['expected_query_type']}`")
                    st.markdown(f"**Actual:** `{t['actual_query_type']}`")
                with c2:
                    st.markdown(f"**Retrieval:** {'✅' if t.get('retrieval_hit') else '❌'}")
                    st.markdown(f"**Sources:** {', '.join(t.get('sources_returned', []))}")
                if t.get("answer_preview"):
                    st.markdown(f"**Answer:** {t['answer_preview'][:400]}")
                st.caption(f"Latency: {t.get('end_to_end_latency_ms',0):.1f}ms")
    else:
        empty_state("🧪", "Ready to Evaluate", "Click the button to run the full 38-case evaluation suite.")


# ═══════════════════════════════════════════════════════════════════════════
# 18. EXECUTIVE REPORTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📄 Executive Reports":
    st.markdown("# Executive Reports")
    st.caption("Structured business reports for leadership")

    if st.button("📄 Generate Executive Report", type="primary", key="eb_btn"):
        with st.spinner("Generating executive report from current data..."):
            r = ap("/api/executive-brief")
        if r:
            st.session_state["ebrief"] = r

    eb = st.session_state.get("ebrief")
    if eb:
        section("Executive Report")
        for s in eb.get("sections", []):
            icon = {"Business Performance": "📊", "Key Drivers": "📈", "Risks": "⚠️",
                    "Opportunities": "💡", "Recommended Actions": "🎯"}.get(s["title"], "📄")
            st.markdown(f"""<div class="insight-card">
                <div class="insight-title">{icon} {s["title"]}</div>
                <div class="insight-body" style="line-height:1.6">{s["content"]}</div>
            </div>""", unsafe_allow_html=True)
        st.caption(f"Generated: {eb.get('generated_at', 'N/A')}")
    else:
        empty_state("📄", "No Report Generated", "Click 'Generate Executive Report' to create a structured business summary.")


# ═══════════════════════════════════════════════════════════════════════════
# 19. ACTION & OUTCOME TRACKING
# ═══════════════════════════════════════════════════════════════════════════
elif page == "✅ Actions":
    st.markdown("# Action & Outcome Tracking")
    st.caption("Track recommendations through to business outcomes")

    section("Create New Action")
    with st.form("new_action"):
        a1, a2 = st.columns(2)
        with a1:
            title = st.text_input("Action Title", placeholder="e.g. Review Campaign B budget")
            owner = st.text_input("Owner", placeholder="e.g. Marketing Manager")
        with a2:
            desc = st.text_area("Description", placeholder="Describe the action and expected outcome...")
            expected = st.text_input("Expected Outcome", placeholder="e.g. ROAS improvement from 2.8x to 3.5x")
        if st.form_submit_button("✅ Create Action", type="primary"):
            if title:
                r = ap("/api/actions", {"title": title, "description": desc, "owner": owner, "expected_outcome": expected})
                if r:
                    st.success(f"Action created: {r['id']}")
                    st.rerun()

    section("Active Actions")
    actions_data = ag("/api/actions")
    if actions_data and actions_data.get("actions"):
        for a in actions_data["actions"]:
            status_cls = {"open": "open", "in_progress": "progress", "completed": "completed", "dismissed": "dismissed"}.get(a["status"], "open")
            status_label = {"open": "Open", "in_progress": "In Progress", "completed": "Completed", "dismissed": "Dismissed"}.get(a["status"], a["status"])

            st.markdown(f"""<div class="insight-card">
                <div style="display:flex;justify-content:space-between;align-items:start">
                    <div>
                        <div class="insight-title">{a["title"]}</div>
                        <div class="insight-body">{a.get("description","")}</div>
                        <div class="insight-meta">
                            <span>Owner: {a.get("owner","Unassigned")}</span>
                            <span>Created: {a.get("created_at","")[:10]}</span>
                        </div>
                    </div>
                    <div>{badge(status_label, status_cls)}</div>
                </div>
            </div>""", unsafe_allow_html=True)

            # Status update
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                new_status = st.selectbox("Status:", ["open", "in_progress", "completed", "dismissed"],
                    index=["open", "in_progress", "completed", "dismissed"].index(a["status"]),
                    key=f"status_{a['id']}")
            with c2:
                outcome = st.text_input("Actual Outcome:", value=a.get("actual_outcome") or "",
                    placeholder="e.g. ROAS improved to 3.4x", key=f"outcome_{a['id']}")
            with c3:
                if st.button("💾 Save", key=f"save_{a['id']}"):
                    put(f"/api/actions/{a['id']}", {"status": new_status, "actual_outcome": outcome})
                    st.rerun()
    else:
        empty_state("✅", "No Actions Yet", "Create actions from Recommendations or manually to track business outcomes.")


# ═══════════════════════════════════════════════════════════════════════════
# 20. SYSTEM HEALTH
# ═══════════════════════════════════════════════════════════════════════════
elif page == "⚙️ System Health":
    st.markdown("# System & Data Health")
    st.caption("Health checks, performance metrics, and observability")

    if st.button("🔄 Refresh Status", key="sys_ref"):
        st.session_state.pop("sys_health", None)

    section("Service Health")
    r = ag("/api/system/health")
    if r:
        for name, info in r.items():
            status = info.get("status", "unknown")
            color = "healthy" if status == "healthy" else ("warning" if status == "not_configured" else "error")
            details = " · ".join(f"{k}: {v}" for k, v in info.items() if k != "status")
            st.markdown(f"""<div class="insight-card">
                <div style="display:flex;align-items:center;gap:8px">
                    <span class="status-dot {color}"></span>
                    <strong>{name.replace("_", " ").title()}</strong>
                    <span>{badge(status.title(), "analytical" if status == "healthy" else "diagnostic")}</span>
                </div>
                <div style="font-size:.82rem;color:var(--text-secondary);margin-top:.3rem">{details}</div>
            </div>""", unsafe_allow_html=True)
    else:
        empty_state("⚠️", "Cannot Reach API", "The backend API is not available. Check if it's running on port 8000.")

    section("Data Freshness")
    with sql_layer.get_conn() if True else st.empty():
        try:
            from src.analytics import sql_layer
            with sql_layer.get_conn() as conn:
                last_sale = conn.execute("SELECT MAX(order_date) FROM sales").fetchone()[0]
                total_sales = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
                total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
                total_campaigns = conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
            st.markdown(f"""<div class="evidence-panel">
                <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem">
                    <div><div class="kpi-label">Latest Data</div><div style="font-weight:600">{last_sale or "N/A"}</div></div>
                    <div><div class="kpi-label">Sales Records</div><div style="font-weight:600">{total_sales:,}</div></div>
                    <div><div class="kpi-label">Products</div><div style="font-weight:600">{total_products:,}</div></div>
                    <div><div class="kpi-label">Campaigns</div><div style="font-weight:600">{total_campaigns:,}</div></div>
                </div>
            </div>""", unsafe_allow_html=True)
        except Exception:
            st.info("Database stats unavailable")


# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL SEARCH (hidden page accessible from sidebar)
# ═══════════════════════════════════════════════════════════════════════════
# Note: Streamlit doesn't have a global search bar natively. The search
# functionality is available via the /api/search endpoint.


# ═══════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("QueryBridge · Sales & Marketing Intelligence Platform · AI Decision Intelligence · Built for Enterprise")
