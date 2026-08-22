"""
QueryBridge — Sales & Marketing Intelligence Platform
Enterprise AI Decision Intelligence Workspace
"""
import os, time, json, requests, streamlit as st, pandas as pd
import plotly.express as px
import plotly.graph_objects as go

API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="QueryBridge — Intelligence",
    page_icon="🔷", layout="wide", initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
*{font-family:'Inter',-apple-system,sans-serif!important;box-sizing:border-box}
html{scroll-behavior:smooth}
.block-container{padding-top:.6rem!important;padding-bottom:1rem!important;max-width:1440px}
h1{font-size:1.35rem!important;font-weight:700!important;color:#0f172a!important;margin-bottom:.15rem!important}
h2,h3{font-size:1rem!important;font-weight:600!important;color:#0f172a!important}

/* Sidebar */
section[data-testid="stSidebar"]{background:#0f172a!important;border-right:1px solid #1e293b}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] label{color:#cbd5e1!important;font-size:.8rem}
section[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.08)!important;margin:.25rem 0}
section[data-testid="stSidebar"] .stRadio>div>label{background:transparent;border-radius:5px!important;padding:5px 10px!important;margin:0!important;border:1px solid transparent!important;transition:all .12s;font-size:.8rem}
section[data-testid="stSidebar"] .stRadio>div>label:hover{background:rgba(255,255,255,.06)!important}
section[data-testid="stSidebar"] .stRadio>div>label[data-checked="true"]{background:rgba(99,102,241,.12)!important;border-color:rgba(99,102,241,.25)!important}

/* KPI */
.kpi{background:#fff;border:1px solid #e2e8f0;border-radius:5px;padding:.6rem .75rem}
.kpi-l{font-size:.65rem;text-transform:uppercase;letter-spacing:.04em;color:#94a3b8;font-weight:600}
.kpi-v{font-size:1.25rem;font-weight:700;color:#0f172a;line-height:1.15;margin:1px 0}
.kpi-d{font-size:.7rem;font-weight:600}
.up{color:#059669}.down{color:#dc2626}.neutral{color:#94a3b8}

/* Badges */
.b{display:inline-flex;align-items:center;padding:2px 7px;border-radius:3px;font-size:.65rem;font-weight:600;gap:2px}
.bk{background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe}
.ba{background:#ecfdf5;color:#166534;border:1px solid #a7f3d0}
.bh{background:#f5f3ff;color:#7c3aed;border:1px solid #ddd6fe}
.bd{background:#fffbeb;color:#92400e;border:1px solid #fde68a}
.bu{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0}
.bhigh{background:#fef2f2;color:#991b1b;border:1px solid #fecaca}
.bmed{background:#fffbeb;color:#92400e;border:1px solid #fde68a}
.blow{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0}

/* Cards */
.card{background:#fff;border:1px solid #e2e8f0;border-radius:5px;padding:.7rem .85rem;margin-bottom:.4rem;transition:box-shadow .12s}
.card:hover{box-shadow:0 1px 4px rgba(0,0,0,.06)}
.card-w{border-left:3px solid #d97706}
.card-s{border-left:3px solid #059669}
.card-i{border-left:3px solid #2563eb}
.card-d{border-left:3px solid #dc2626}
.ct{font-weight:600;font-size:.85rem;color:#0f172a;margin-bottom:.2rem}
.cb{font-size:.8rem;color:#475569;line-height:1.5}
.cm{font-size:.7rem;color:#94a3b8;margin-top:.25rem;display:flex;gap:.6rem}

/* Evidence */
.ev{background:#f8fafc;border:1px solid #e2e8f0;border-radius:5px;padding:.7rem .85rem}
.ev-item{padding:.35rem 0;border-bottom:1px solid #f1f5f9;font-size:.8rem}
.ev-item:last-child{border-bottom:none}
.ev-src{font-weight:600;color:#0f172a}
.ev-det{color:#475569}

/* Section */
.sec{font-size:.85rem;font-weight:700;color:#0f172a;padding:.4rem 0 .25rem;margin:.8rem 0 .4rem;border-bottom:2px solid #e2e8f0}

/* Empty state */
.empty{text-align:center;padding:3rem 2rem;color:#94a3b8}
.empty-icon{font-size:2.5rem;margin-bottom:.5rem}
.empty-title{font-size:1rem;font-weight:600;color:#0f172a;margin-bottom:.25rem}
.empty-sub{font-size:.82rem;color:#64748b;max-width:400px;margin:0 auto}

/* AI message */
.msg-user{background:#f1f5f9;border-radius:8px;padding:.8rem 1rem;margin:.5rem 0;font-size:.88rem;line-height:1.6}
.msg-ai{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:.8rem 1rem;margin:.5rem 0;font-size:.88rem;line-height:1.6}
.msg-ai .classification{margin-bottom:.5rem;padding-bottom:.5rem;border-bottom:1px solid #f1f5f9}

/* Tables */
.stDataFrame{border:1px solid #e2e8f0!important;border-radius:5px!important}

/* Quality bar */
.qbar{height:5px;background:#f1f5f9;border-radius:3px;overflow:hidden;margin:.25rem 0}
.qfill{height:100%;border-radius:3px}
.qfill.good{background:#059669}.qfill.ok{background:#d97706}.qfill.bad{background:#dc2626}
</style>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def ag(p, t=15):
    try: r=requests.get(f"{API}{p}",timeout=t); r.raise_for_status(); return r.json()
    except: return None

def ap(p, d=None, f=None, t=60):
    try:
        if f: r=requests.post(f"{API}{p}",files=f,timeout=t)
        else: r=requests.post(f"{API}{p}",json=d,timeout=t)
        r.raise_for_status(); return r.json()
    except: return None

def put(p, d=None, t=10):
    try: r=requests.put(f"{API}{p}",json=d,timeout=t); r.raise_for_status(); return r.json()
    except: return None

def fm(v):
    if v is None: return "N/A"
    if abs(v)>=1e6: return f"${v/1e6:.2f}M"
    if abs(v)>=1e3: return f"${v/1e3:.1f}K"
    return f"${v:,.0f}"

def fd(v):
    if v is None: return '<span class="kpi-d neutral">—</span>'
    c="up" if v>=0 else "down"; a="▲" if v>=0 else "▼"
    return f'<span class="kpi-d {c}">{a} {abs(v):.1f}%</span>'

def kpi_card(l, v, d=None):
    dh = fd(d) if d is not None else '<span class="kpi-d neutral">—</span>'
    return f'<div class="kpi"><div class="kpi-l">{l}</div><div class="kpi-v">{v}</div>{dh}</div>'

def bdg(text, variant="bk"):
    return f'<span class="b {variant}">{text}</span>'

def chart_base(h=300):
    return dict(height=h, margin=dict(l=10,r=10,t=25,b=10), paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter",size=11,color="#475569"))

def chart_grid(fig):
    s=dict(gridcolor="#f1f5f9",showgrid=True,zeroline=False)
    fig.update_xaxes(**s); fig.update_yaxes(**s); return fig

def sec(title):
    st.markdown(f'<div class="sec">{title}</div>', unsafe_allow_html=True)

def empty(icon, title, sub):
    st.markdown(f'<div class="empty"><div class="empty-icon">{icon}</div><div class="empty-title">{title}</div><div class="empty-sub">{sub}</div></div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""<div style="padding:.3rem 0 .5rem">
        <div style="font-size:1rem;font-weight:800;color:#e2e8f0;letter-spacing:-.02em">QueryBridge</div>
        <div style="font-size:.65rem;color:#94a3b8;font-weight:500">Sales & Marketing Intelligence</div>
    </div>""", unsafe_allow_html=True)
    st.markdown('<hr>', unsafe_allow_html=True)

    page = st.radio("Nav", [
        "🤖 AI Analyst",
        "── Intelligence ──",
        "📊 Overview",
        "💡 Insights",
        "🔬 Investigations",
        "📋 Recommendations",
        "── Data ──",
        "📁 Data Hub",
        "📚 Knowledge",
        "📐 Semantic Layer",
        "── System ──",
        "📄 Reports",
        "⚙️ Data Sources",
        "🔍 Data Quality",
    ], label_visibility="collapsed")

    st.markdown('<hr>', unsafe_allow_html=True)
    h = ag("/health")
    if h:
        st.markdown('<div style="padding:.3rem .5rem;background:rgba(34,197,94,.08);border-radius:5px;border:1px solid rgba(34,197,94,.15);font-size:.72rem"><span style="color:#22c55e">●</span> <span style="color:#86efac;font-weight:600"> Online</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="padding:.3rem .5rem;background:rgba(239,68,68,.08);border-radius:5px;border:1px solid rgba(239,68,68,.15);font-size:.72rem"><span style="color:#ef4444">●</span> <span style="color:#fca5a5;font-weight:600"> Offline</span></div>', unsafe_allow_html=True)

    # Data status indicator
    ds = ag("/api/data-status")
    if ds:
        has_structured = ds.get("has_data", False)
        has_knowledge = ds.get("has_knowledge", False)
        if has_structured or has_knowledge:
            items = []
            if has_structured: items.append("📊 Data")
            if has_knowledge: items.append("📚 KB")
            st.caption(f"Connected: {' · '.join(items)}")
        else:
            st.caption("No data connected")


# ═══════════════════════════════════════════════════════════════════════════
# 1. AI ANALYST — PRIMARY EXPERIENCE
# ═══════════════════════════════════════════════════════════════════════════
if page == "🤖 AI Analyst":
    # Check data status
    ds = ag("/api/data-status")
    has_data = ds and ds.get("has_data", False)
    has_kb = ds and ds.get("has_knowledge", False)

    # Session state for conversation
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "show_evidence" not in st.session_state:
        st.session_state.show_evidence = {}

    # Header
    st.markdown("# AI Analyst")
    if not has_data and not has_kb:
        st.info("💡 Connect data sources or upload documents to start asking questions. The AI Analyst works best with structured data (CSV/Excel) and business knowledge documents.")
    elif not has_data:
        st.info("💡 Structured data not connected. Upload CSV/Excel in Data Hub for analytics questions. Document knowledge is available for strategy questions.")
    elif not has_kb:
        st.info("💡 Knowledge base is empty. Upload documents in Knowledge for strategy and policy questions.")

    # Suggested prompts
    if not st.session_state.messages:
        suggestions = []
        if has_data:
            suggestions = [
                "Which category generated the highest revenue?",
                "Why did Electronics revenue decline in Q2?",
                "Which campaign has the highest ROAS?",
                "Which customer segment has the highest LTV?",
                "Should we increase marketing investment in Electronics?",
                "What is the relationship between discounts and margin?",
            ]
        if has_kb:
            suggestions.extend([
                "What does the marketing strategy recommend?",
                "What discount policy does the pricing policy specify?",
            ])
        if suggestions:
            st.markdown("**Suggested questions:**")
            cols = st.columns(min(3, len(suggestions)))
            for i, s in enumerate(suggestions):
                with cols[i % len(cols)]:
                    if st.button(s, key=f"sug_{i}", use_container_width=True):
                        st.session_state.messages.append({"role": "user", "content": s})
                        st.rerun()

    # Conversation history
    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            st.markdown(f'<div class="msg-user"><strong>You:</strong> {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            r = msg.get("result")
            if r:
                qt = r.get("query_type", "unknown")
                variant = {"knowledge":"bk","analytical":"ba","hybrid":"bh","diagnostic":"bd","unanswerable":"bu","ambiguous":"bu"}.get(qt,"bu")
                # Classification bar
                is_s = any(s["type"]=="structured_data" for s in r.get("sources",[]))
                is_k = any(s["type"]=="knowledge_base" for s in r.get("sources",[]))
                pipe = f"{'✅' if is_s else '○'} Data {'✅' if is_k else '○'} RAG ✅ Reason"
                m = r.get("metrics",{})
                lat = m.get("end_to_end_latency_ms",0)

                st.markdown(f'''<div class="msg-ai">
                    <div class="classification">
                        {bdg(qt.upper(), variant)}
                        <span style="font-size:.72rem;color:#94a3b8;margin-left:.5rem">{pipe} · {lat:.0f}ms</span>
                    </div>
                    <div style="line-height:1.65">{r["answer"]}</div>
                </div>''', unsafe_allow_html=True)

                # Evidence panel
                sources = r.get("sources", [])
                evidence = r.get("evidence", {})
                if sources:
                    with st.expander(f"📋 Evidence ({len(sources)} sources)", expanded=False):
                        for s in sources:
                            is_doc = s["type"] == "knowledge_base"
                            ic = "📄" if is_doc else "📊"
                            cls = "bk" if is_doc else "ba"
                            src_name = s["source"]
                            st.markdown(bdg(f"{ic} {src_name}", cls), unsafe_allow_html=True)
                        if evidence.get("knowledge_base_chunks"):
                            st.markdown("**Knowledge Chunks:**")
                            for c in evidence["knowledge_base_chunks"]:
                                st.markdown(f"""<div class="ev-item">
                                    <span class="ev-src">{c["source"]}</span> <span style="color:#4f46e5;font-size:.72rem">relevance: {c["relevance_score"]}</span>
                                    <div class="ev-det">{c["text"][:300]}...</div>
                                </div>""", unsafe_allow_html=True)
                        if evidence.get("structured_data"):
                            st.markdown("**Structured Data:**")
                            st.json(evidence["structured_data"])
                        if evidence.get("detected_conflict"):
                            st.warning(f"⚠️ {evidence['detected_conflict'].get('note','')}")

                # Action buttons
                ac1, ac2 = st.columns(2)
                with ac1:
                    if st.button("🔬 Investigate", key=f"inv_{i}"):
                        metric = "revenue"
                        for word in ["revenue","roas","margin","campaign","customer"]:
                            if word in msg["content"].lower():
                                metric = "campaigns" if word == "campaign" else word
                                break
                        st.session_state["invest_metric"] = metric
                        st.session_state["nav"] = "🔬 Investigations"
                        st.rerun()
                with ac2:
                    if st.button("📋 Create Action", key=f"act_{i}"):
                        ap("/api/actions", {"title": f"Follow-up: {msg['content'][:80]}", "description": r["answer"][:200], "source_insight": "AI Analyst conversation"})
                        st.toast("Action created")
            else:
                st.markdown(f'<div class="msg-ai">{msg["content"]}</div>', unsafe_allow_html=True)

    # Input
    st.markdown("---")
    q = st.chat_input("Ask a business question..." if (has_data or has_kb) else "Upload data first, then ask questions here...")
    if q:
        st.session_state.messages.append({"role": "user", "content": q})
        with st.spinner("Analyzing..."):
            r = ap("/query", {"question": q})
        if r:
            st.session_state.messages.append({"role": "assistant", "content": r["answer"], "result": r})
        else:
            st.session_state.messages.append({"role": "assistant", "content": "Unable to process the query. Please check that the API is running and data is available."})
        st.rerun()

    # New chat button
    if st.session_state.messages:
        if st.button("🗑️ New Chat", key="new_chat"):
            st.session_state.messages = []
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# 2. OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📊 Overview":
    st.markdown("# Executive Overview")
    ds = ag("/api/data-status")
    if not ds or not ds.get("has_data"):
        empty("📊", "No Data Connected", "Upload a CSV or Excel file in Data Hub to see your business overview.")
        if st.button("📁 Go to Data Hub", key="go_dh"):
            st.session_state["nav"] = "📁 Data Hub"; st.rerun()
        st.stop()

    kpi = ag("/api/analytics/overview")
    if not kpi:
        empty("⚠️", "Analytics Unavailable", "Unable to load analytics data."); st.stop()

    sec("Key Metrics")
    c = st.columns(6)
    for col, (l,v,d) in zip(c, [
        ("Revenue", fm(kpi["total_revenue"]), kpi.get("revenue_growth_pct")),
        ("Orders", f"{kpi['total_units_sold']:,}", kpi.get("units_growth_pct")),
        ("Margin", f"{kpi['gross_margin_pct']}%", kpi.get("margin_growth_pct")),
        ("Spend", fm(kpi["total_marketing_spend"]), kpi.get("spend_growth_pct")),
        ("ROAS", f"{kpi['avg_roas']}x", kpi.get("roas_growth_pct")),
        ("Customers", f"{kpi['total_customers']:,}", kpi.get("customer_growth_pct")),
    ]):
        with col: st.markdown(kpi_card(l,v,d), unsafe_allow_html=True)

    sec("Trends")
    c1, c2 = st.columns([3,2])
    with c1:
        trend = ag("/api/analytics/revenue-trend")
        if trend:
            df = pd.DataFrame(trend); df["month"] = pd.to_datetime(df["month"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["month"], y=df["revenue"], name="Revenue", line=dict(color="#4f46e5",width=2.5), fill="tozeroy", fillcolor="rgba(79,70,229,.06)"))
            fig.add_trace(go.Scatter(x=df["month"], y=df["profit"], name="Profit", line=dict(color="#059669",width=2)))
            fig.update_layout(**chart_base(260), legend=dict(orientation="h",y=1.12))
            chart_grid(fig); st.plotly_chart(fig, use_container_width=True)
    with c2:
        cp = ag("/api/analytics/category-performance")
        if cp:
            df = pd.DataFrame(cp)
            fig = px.bar(df, x="revenue", y="category", orientation="h", color="category",
                color_discrete_sequence=["#4f46e5","#059669","#d97706","#dc2626","#7c3aed"], text_auto=".2s")
            fig.update_layout(**chart_base(260), showlegend=False, yaxis=dict(categoryorder="total ascending"))
            fig.update_traces(textposition="outside", textfont_size=10); chart_grid(fig)
            st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# 3. INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "💡 Insights":
    st.markdown("# AI Insights")
    ds = ag("/api/data-status")
    if not ds or not ds.get("has_data"):
        empty("💡", "No Data for Insights", "Upload structured data to generate AI-powered business insights.")
        st.stop()

    if st.button("🔄 Generate Insights", type="primary"):
        with st.spinner("Analyzing data patterns..."):
            r = ap("/api/insights")
        if r: st.session_state["insights"] = r.get("insights", [])

    ins = st.session_state.get("insights", [])
    if ins:
        for i in ins:
            ic = {"warning":"card-w","success":"card-s","info":"card-i"}.get(i.get("type"),"card-i")
            icon = {"warning":"⚠️","success":"✅","info":"💡"}.get(i.get("type"),"💡")
            st.markdown(f'''<div class="card {ic}">
                <div class="ct">{icon} {i["title"]}</div>
                <div class="cb">{i["description"]}</div>
                <div class="cm">
                    <span>Impact: {bdg(i.get("impact","N/A").title(), "bhigh" if i.get("impact")=="high" else "bmed")}</span>
                    <span>Confidence: {i.get("confidence","N/A")}</span>
                </div>
                {"<div style='margin-top:.25rem;font-size:.75rem;color:#64748b'>Evidence: " + " · ".join(i.get("evidence",[])) + "</div>" if i.get("evidence") else ""}
            </div>''', unsafe_allow_html=True)
    else:
        empty("💡", "No Insights Yet", "Click 'Generate Insights' to analyze your data for actionable patterns.")


# ═══════════════════════════════════════════════════════════════════════════
# 4. INVESTIGATIONS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🔬 Investigations":
    st.markdown("# Investigation Workspace")
    ds = ag("/api/data-status")
    if not ds or not ds.get("has_data"):
        empty("🔬", "No Data to Investigate", "Upload structured data to enable drill-down investigations.")
        st.stop()

    metric = st.selectbox("Investigate:", ["revenue", "roas", "margin", "customers", "campaigns"],
        index=["revenue","roas","margin","customers","campaigns"].index(st.session_state.get("invest_metric","revenue")))
    if st.button("🔬 Start Investigation", type="primary"):
        with st.spinner(f"Investigating {metric}..."):
            inv = ag(f"/api/investigation/{metric}")
        if inv: st.session_state["investigation"] = inv

    inv = st.session_state.get("investigation")
    if inv:
        sec(f"Investigation: {metric.title()}")
        for key, data in inv.get("breakdowns", {}).items():
            sec(key.replace("by_", "").replace("_", " ").title())
            if isinstance(data, list) and data:
                df = pd.DataFrame(data)
                num_cols = df.select_dtypes(include=["number"]).columns.tolist()
                cat_col = [c for c in df.columns if c not in num_cols]
                if cat_col and num_cols:
                    fig = px.bar(df, x=cat_col[0], y=num_cols[0], text_auto=".2s", color_discrete_sequence=["#4f46e5"])
                    fig.update_layout(**chart_base(260)); chart_grid(fig)
                    st.plotly_chart(fig, use_container_width=True)
                st.dataframe(df, use_container_width=True, hide_index=True)

        if inv.get("trend"):
            sec("Trend")
            df = pd.DataFrame(inv["trend"])
            if "month" in df.columns:
                df["month"] = pd.to_datetime(df["month"])
                fig = go.Figure()
                for col in ["revenue","profit"]:
                    if col in df.columns:
                        fig.add_trace(go.Scatter(x=df["month"], y=df[col], name=col.title(), line=dict(width=2)))
                fig.update_layout(**chart_base(260)); chart_grid(fig)
                st.plotly_chart(fig, use_container_width=True)

        if inv.get("top_entities"):
            sec("Top Entities")
            st.dataframe(pd.DataFrame(inv["top_entities"]), use_container_width=True, hide_index=True)
    else:
        empty("🔬", "Ready to Investigate", "Select a metric and click 'Start Investigation' to drill into your business data.")


# ═══════════════════════════════════════════════════════════════════════════
# 5. RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📋 Recommendations":
    st.markdown("# Recommendations")
    ds = ag("/api/data-status")
    if not ds or not ds.get("has_data"):
        empty("📋", "No Data for Recommendations", "Upload structured data to receive evidence-backed recommendations.")
        st.stop()

    if st.button("🔄 Generate Recommendations", type="primary"):
        with st.spinner("Analyzing data..."):
            r = ap("/api/insights")
            if r and r.get("insights"):
                st.session_state["recs"] = [
                    {"title": i["title"], "why": i["description"],
                     "evidence": " · ".join(i.get("evidence",[])),
                     "confidence": i.get("confidence","Medium"),
                     "impact": i.get("impact","medium")}
                    for i in r["insights"]
                ]

    recs = st.session_state.get("recs", [])
    if recs:
        for rec in recs:
            st.markdown(f'''<div class="card card-i">
                <div class="ct">📋 {rec["title"]}</div>
                <div class="cb"><strong>Why:</strong> {rec["why"]}</div>
                <div class="cm">
                    <span>Evidence: {rec["evidence"]}</span>
                    <span>Confidence: {bdg(rec["confidence"], "ba" if rec["confidence"]=="High" else "bd")}</span>
                </div>
            </div>''', unsafe_allow_html=True)
    else:
        empty("📋", "No Recommendations", "Click 'Generate Recommendations' to get evidence-backed suggestions.")


# ═══════════════════════════════════════════════════════════════════════════
# 6. DATA HUB
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📁 Data Hub":
    st.markdown("# Data Hub")

    tab_up, tab_list = st.tabs(["📤 Upload", "📋 Sources"])
    with tab_up:
        sec("Upload Structured Data")
        st.caption("Upload CSV or Excel files for automatic profiling, validation, and analytics.")
        up = st.file_uploader("Choose file", type=["csv","xlsx","xls"], key="dh")
        if up and st.button("📤 Upload & Profile", type="primary"):
            with st.spinner("Uploading · Parsing · Profiling · Validating..."):
                r = ap("/api/datahub/upload", f={"file":(up.name, up.getvalue(), "application/octet-stream")})
            if r:
                st.success(f"✅ Processed {r['total_rows']:,} rows")
                for p in r["profiles"]:
                    with st.expander(f"📊 {p['filename']}" + (f" — {p['sheet_name']}" if p.get("sheet_name") else ""), expanded=True):
                        st.markdown(f"**Quality:** {p['quality_score']}/100")
                        st.progress(p["quality_score"]/100)
                        m1,m2,m3,m4 = st.columns(4)
                        m1.metric("Rows", f"{p['row_count']:,}"); m2.metric("Cols", p["col_count"])
                        m3.metric("Dups", p["duplicate_rows"]); m4.metric("Issues", len(p["issues"]))
                        for iss in p["issues"]: st.warning(iss["message"])
                        for c in p["columns"]:
                            st.caption(f"`{c['name']}` ({c['dtype']}) — {c['semantic_type']} · unique: {c['unique_count']} · nulls: {c['null_pct']}%")
            else: st.error("Upload failed.")

    with tab_list:
        sec("Connected Sources")
        ds_list = ag("/api/datahub/datasets")
        if ds_list:
            for ds in ds_list:
                st.markdown(f'''<div class="card">
                    <div class="ct">{ds["filename"]}</div>
                    <div class="cm"><span>{ds["total_rows"]:,} rows · {ds["total_columns"]} cols</span>
                    <span>{bdg(f"Score: {ds['quality_score']}", "ba")}</span></div>
                </div>''', unsafe_allow_html=True)
        else:
            empty("📁", "No Data Sources", "Upload a CSV or Excel file to get started.")


# ═══════════════════════════════════════════════════════════════════════════
# 7. KNOWLEDGE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📚 Knowledge":
    st.markdown("# Knowledge Center")
    docs = ag("/documents")
    if docs is None:
        empty("⚠️", "API Unavailable", "Start the backend API."); st.stop()

    tc = sum(d["chunk_count"] for d in docs)
    sec("Status")
    c = st.columns(3)
    for col,(l,v) in zip(c,[("Documents",str(len(docs))),("Chunks",f"{tc:,}"),("Vector Store","TF-IDF + BM25")]):
        with col: st.markdown(kpi_card(l,v), unsafe_allow_html=True)

    sec("Indexed Documents")
    if docs:
        for doc in docs:
            st.markdown(f'''<div class="card">
                <div class="ct">📄 {doc["document_name"]}</div>
                <div class="cm"><span>{doc["chunk_count"]} chunks · {doc["document_type"]}</span>
                {bdg("Indexed ✓", "ba")}</div>
            </div>''', unsafe_allow_html=True)
    else:
        empty("📚", "No Documents", "Upload documents (PDF, TXT, MD, CSV) to build your knowledge base.")

    sec("Upload Document")
    st.caption("Supported: Markdown, CSV, Excel, Text")
    up = st.file_uploader("Choose file", type=["md","csv","xlsx","xls","txt"], key="kb")
    if up and st.button("📤 Upload & Index", type="primary"):
        ext = up.name.rsplit(".",1)[-1].lower()
        mime = {"md":"text/markdown","csv":"text/csv","xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","xls":"application/vnd.ms-excel","txt":"text/plain"}
        with st.spinner(f"Processing {ext.upper()}..."):
            r = ap("/documents/upload", f={"file":(up.name,up.getvalue(),mime.get(ext,"application/octet-stream"))})
        if r: st.success(f"✅ {r['message']} ({r['chunks_created']} chunks)"); st.rerun()
        else: st.error("Upload failed.")

    sec("Search")
    kbq = st.text_input("Search:", placeholder="Search documents...")
    if kbq:
        with st.spinner("Searching..."):
            r = ap("/query", {"question": kbq})
        if r and r.get("evidence",{}).get("knowledge_base_chunks"):
            for c in r["evidence"]["knowledge_base_chunks"]:
                with st.expander(f"📄 {c['source']} — Relevance: {c['relevance_score']}"):
                    st.markdown(c["text"])


# ═══════════════════════════════════════════════════════════════════════════
# 8. SEMANTIC LAYER
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📐 Semantic Layer":
    st.markdown("# Semantic & Metric Layer")

    metrics_data = ag("/api/semantic/metrics")
    dims_data = ag("/api/semantic/dimensions")

    sec("Business Metrics")
    if metrics_data and metrics_data.get("metrics"):
        for m in metrics_data["metrics"]:
            st.markdown(f'''<div class="card">
                <div style="display:flex;justify-content:space-between;align-items:start">
                    <div><div class="ct">{m["name"]}</div><div class="cb">{m["definition"]}</div></div>
                    {bdg(m["source"], "ba")}
                </div>
                <div style="margin-top:.3rem;font-size:.78rem"><code style="background:#f1f5f9;padding:2px 5px;border-radius:3px">{m["formula"]}</code></div>
                <div class="cm"><span>Dimensions: {", ".join(m["dimensions"])}</span></div>
            </div>''', unsafe_allow_html=True)
    else:
        empty("📐", "No Metrics Defined", "Metrics are auto-detected from your data sources.")

    sec("Dimensions")
    if dims_data and dims_data.get("dimensions"):
        for d in dims_data["dimensions"]:
            cols = ", ".join(d.get("columns", d.get("values",[])))
            st.markdown(f'''<div class="card"><div class="ct">{d["name"]}</div>
                <div class="cb">Source: {d["source"]} · Columns: {cols}</div></div>''', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# 9. REPORTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📄 Reports":
    st.markdown("# Executive Reports")
    ds = ag("/api/data-status")
    if not ds or not ds.get("has_data"):
        empty("📄", "No Data for Reports", "Upload structured data to generate executive reports.")
        st.stop()

    if st.button("📄 Generate Report", type="primary"):
        with st.spinner("Generating report..."):
            r = ap("/api/executive-brief")
        if r: st.session_state["ebrief"] = r

    eb = st.session_state.get("ebrief")
    if eb:
        for s in eb.get("sections",[]):
            icon = {"Business Performance":"📊","Key Drivers":"📈","Risks":"⚠️","Opportunities":"💡","Recommended Actions":"🎯"}.get(s["title"],"📄")
            st.markdown(f'''<div class="card"><div class="ct">{icon} {s["title"]}</div>
                <div class="cb" style="line-height:1.6">{s["content"]}</div></div>''', unsafe_allow_html=True)
    else:
        empty("📄", "No Report Generated", "Click 'Generate Report' to create a structured business summary.")


# ═══════════════════════════════════════════════════════════════════════════
# 10. DATA SOURCES
# ═══════════════════════════════════════════════════════════════════════════
elif page == "⚙️ Data Sources":
    st.markdown("# Data Sources & Settings")

    sec("System Health")
    r = ag("/api/system/health")
    if r:
        for name, info in r.items():
            status = info.get("status","unknown")
            color = "#059669" if status=="healthy" else ("#d97706" if status=="not_configured" else "#dc2626")
            details = " · ".join(f"{k}: {v}" for k,v in info.items() if k!="status")
            st.markdown(f'''<div class="card">
                <div style="display:flex;align-items:center;gap:6px">
                    <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:{color}"></span>
                    <strong style="font-size:.85rem">{name.replace("_"," ").title()}</strong>
                    {bdg(status.title(), "ba" if status=="healthy" else "bd")}
                </div>
                <div style="font-size:.78rem;color:#64748b;margin-top:.2rem">{details}</div>
            </div>''', unsafe_allow_html=True)
    else:
        empty("⚠️", "Cannot Reach API", "Backend API is not available.")

    sec("Data Status")
    ds = ag("/api/data-status")
    if ds:
        tables = ds.get("structured",{})
        kb = ds.get("knowledge",{})
        st.markdown(f'''<div class="ev">
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:.8rem">
                <div><div class="kpi-l">Products</div><div style="font-weight:600">{tables.get("products",0):,}</div></div>
                <div><div class="kpi-l">Sales</div><div style="font-weight:600">{tables.get("sales",0):,}</div></div>
                <div><div class="kpi-l">Campaigns</div><div style="font-weight:600">{tables.get("campaigns",0):,}</div></div>
                <div><div class="kpi-l">Reviews</div><div style="font-weight:600">{tables.get("reviews",0):,}</div></div>
            </div>
            <div style="margin-top:.5rem;display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem;border-top:1px solid #e2e8f0;padding-top:.5rem">
                <div><div class="kpi-l">Documents</div><div style="font-weight:600">{kb.get("documents",0)}</div></div>
                <div><div class="kpi-l">Chunks</div><div style="font-weight:600">{kb.get("chunks",0):,}</div></div>
                <div><div class="kpi-l">Vector Store</div><div style="font-weight:600">TF-IDF</div></div>
            </div>
        </div>''', unsafe_allow_html=True)

    sec("Actions")
    actions_data = ag("/api/actions")
    if actions_data and actions_data.get("actions"):
        for a in actions_data["actions"]:
            sc = {"open":"bu","in_progress":"bd","completed":"ba","dismissed":"bu"}.get(a["status"],"bu")
            sl = {"open":"Open","in_progress":"In Progress","completed":"Completed","dismissed":"Dismissed"}.get(a["status"],a["status"])
            st.markdown(f'''<div class="card">
                <div style="display:flex;justify-content:space-between;align-items:start">
                    <div><div class="ct">{a["title"]}</div>
                    <div class="cm"><span>Owner: {a.get("owner","—")}</span><span>Created: {a.get("created_at","")[:10]}</span></div></div>
                    {bdg(sl, sc)}
                </div>
            </div>''', unsafe_allow_html=True)
            c1,c2,c3 = st.columns([2,2,1])
            with c1:
                ns = st.selectbox("Status:", ["open","in_progress","completed","dismissed"],
                    index=["open","in_progress","completed","dismissed"].index(a["status"]), key=f"s_{a['id']}")
            with c2:
                ao = st.text_input("Outcome:", value=a.get("actual_outcome") or "", key=f"o_{a['id']}")
            with c3:
                if st.button("💾", key=f"u_{a['id']}"):
                    put(f"/api/actions/{a['id']}", {"status":ns,"actual_outcome":ao}); st.rerun()
    else:
        empty("✅", "No Actions", "Create actions from recommendations to track business outcomes.")


# ═══════════════════════════════════════════════════════════════════════════
# 11. DATA QUALITY
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🔍 Data Quality":
    st.markdown("# Data Quality")
    dq = ag("/api/data-quality")
    if not dq:
        empty("🔍", "No Data to Assess", "Upload structured data to see quality metrics.")
        st.stop()

    sec("Quality Score")
    score = dq.get("overall_score",0)
    c = st.columns(3)
    c[0].markdown(kpi_card("Score", f"{score:.0f}/100"), unsafe_allow_html=True)
    c[1].markdown(kpi_card("Checks", f"{dq.get('passed_checks',0)}/{dq.get('total_checks',0)}"), unsafe_allow_html=True)
    c[2].markdown(kpi_card("Tables", str(len(dq.get("tables",{})))), unsafe_allow_html=True)
    cls = "good" if score>=90 else ("ok" if score>=70 else "bad")
    st.markdown(f'<div class="qbar"><div class="qfill {cls}" style="width:{score}%"></div></div>', unsafe_allow_html=True)

    sec("Tables")
    for tbl, td in dq.get("tables",{}).items():
        with st.expander(f"📋 {tbl.title()} — {td['total_rows']:,} rows, {len(td['checks'])} checks"):
            for ck in td["checks"]:
                icon = "✅" if ck["status"]=="pass" else "⚠️"
                st.markdown(f'{icon} **{ck["column"]}** — {ck["completeness"]}% complete · {ck["null_count"]} nulls')
            if td.get("duplicate_count",0) > 0:
                st.warning(f"⚠️ {td['duplicate_count']} duplicate keys")


# ═══════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("QueryBridge · Sales & Marketing Intelligence · AI Decision Intelligence")
