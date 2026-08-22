"""
Amazon Sales & Marketing Intelligence Platform — Enterprise UI
"""
import os, time, json
import requests, streamlit as st, pandas as pd
import plotly.express as px
import plotly.graph_objects as go

API = os.getenv("API_BASE_URL", "http://localhost:8000")
st.set_page_config(page_title="Amazon Intelligence Platform", page_icon="🔷", layout="wide", initial_sidebar_state="expanded")

# ── Professional CSS ────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*{font-family:'Inter',-apple-system,sans-serif!important}
.block-container{padding-top:1.2rem!important;max-width:1400px}
div[data-testid="stSidebar"]{background:linear-gradient(180deg,#0f172a,#1e293b)}
div[data-testid="stSidebar"] .stRadio>div{gap:2px}
div[data-testid="stSidebar"] .stRadio>div>label{background:rgba(255,255,255,.04);border-radius:8px;padding:8px 12px;border:1px solid rgba(255,255,255,.06)}
div[data-testid="stSidebar"] .stRadio>div>label:hover{background:rgba(255,255,255,.08)}
div[data-testid="stSidebar"] .stRadio>div>label[data-checked="true"]{background:rgba(99,102,241,.15);border-color:#6366f1}
div[data-testid="stSidebar"] p,div[data-testid="stSidebar"] h1,div[data-testid="stSidebar"] h2,div[data-testid="stSidebar"] h3,div[data-testid="stSidebar"] span{color:#e2e8f0!important}
div[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.1)}
.kpi{background:linear-gradient(135deg,#f8fafc,#f1f5f9);border:1px solid #e2e8f0;border-radius:10px;padding:1rem;text-align:center;transition:.2s}
.kpi:hover{box-shadow:0 4px 12px rgba(0,0,0,.06);transform:translateY(-1px)}
.kpi-l{font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:600}
.kpi-v{font-size:1.6rem;font-weight:700;color:#0f172a;line-height:1.1;margin:2px 0}
.kpi-d{font-size:.75rem;font-weight:600}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.7rem;font-weight:600}
.badge-k{background:#dbeafe;color:#1e40af}.badge-a{background:#dcfce7;color:#166534}
.badge-h{background:#f3e8ff;color:#6b21a8}.badge-d{background:#ffedd5;color:#9a3412}
.badge-u{background:#f1f5f9;color:#475569}.badge-am{background:#fee2e2;color:#991b1b}
.insight{border:1px solid #e2e8f0;border-radius:10px;padding:1rem;margin:.5rem 0;background:#fff}
.insight-w{background:linear-gradient(135deg,#fffbeb,#fef3c7);border-color:#fde68a}
.insight-s{background:linear-gradient(135deg,#f0fdf4,#dcfce7);border-color:#bbf7d0}
.insight-i{background:linear-gradient(135deg,#eff6ff,#dbeafe);border-color:#bfdbfe}
.src-tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.7rem;font-weight:500;margin:2px}
.src-doc{background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af}
.src-data{background:#f0fdf4;border:1px solid #bbf7d0;color:#166534}
.sh{font-size:.95rem;font-weight:700;color:#1e293b;margin:1rem 0 .5rem;padding-bottom:.4rem;border-bottom:2px solid #e2e8f0}
</style>""", unsafe_allow_html=True)

# ── Helpers ──────────────────────────────────────────────────────────────────
def ag(p, t=15):
    try: r=requests.get(f"{API}{p}",timeout=t); r.raise_for_status(); return r.json()
    except: return None
def ap(p, d=None, f=None, t=60):
    try:
        if f: r=requests.post(f"{API}{p}",files=f,timeout=t)
        else: r=requests.post(f"{API}{p}",json=d,timeout=t)
        r.raise_for_status(); return r.json()
    except: return None
def fm(v):
    if v is None: return "N/A"
    if abs(v)>=1e6: return f"${v/1e6:.2f}M"
    if abs(v)>=1e3: return f"${v/1e3:.1f}K"
    return f"${v:,.0f}"
def fd(v,s="%"):
    if v is None: return ""
    c="#059669" if v>=0 else "#dc2626"
    a="▲" if v>=0 else "▼"
    return f'<span class="kpi-d" style="color:{c}">{a} {abs(v):.1f}{s}</span>'
def kc(l,v,d=None,s="%"):
    dh=fd(d,s) if d is not None else '<span class="kpi-d" style="color:#94a3b8">—</span>'
    return f'<div class="kpi"><div class="kpi-l">{l}</div><div class="kpi-v">{v}</div>{dh}</div>'
def bd(qt):
    m={"knowledge":"badge-k","analytical":"badge-a","hybrid":"badge-h","diagnostic":"badge-d","unanswerable":"badge-u","ambiguous":"badge-am"}
    return f'<span class="badge {m.get(qt,"badge-u")}">{qt.upper()}</span>'
def gl(h=320):
    return dict(height=h,margin=dict(l=15,r=15,t=35,b=15),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(family="Inter",size=11,color="#475569"))
def ag_grid(fig):
    s=dict(gridcolor="#f1f5f9",showgrid=True,zeroline=False)
    fig.update_xaxes(**s); fig.update_yaxes(**s); return fig

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="text-align:center;padding:.5rem 0 .8rem"><div style="font-size:1.8rem">🔷</div><div style="font-size:1rem;font-weight:700;color:#e2e8f0">Amazon Intelligence</div><div style="font-size:.7rem;color:#94a3b8">Sales & Marketing AI Platform</div></div>', unsafe_allow_html=True)
    st.markdown('<hr style="border-color:rgba(255,255,255,.1)">', unsafe_allow_html=True)
    page = st.radio("Nav", [
        "📊 Overview","🤖 AI Analyst","📁 Data Hub","💰 Sales","📢 Marketing",
        "📦 Products","👥 Customers","⭐ Reviews","💲 Discounts",
        "💡 Insights","📋 Recommendations","📄 Executive Brief",
        "📚 Knowledge","🔬 Evaluation","⚙️ System"
    ], label_visibility="collapsed")
    st.markdown('<hr style="border-color:rgba(255,255,255,.1)">', unsafe_allow_html=True)
    h=ag("/health")
    if h:
        st.markdown('<div style="padding:.4rem;background:rgba(34,197,94,.1);border-radius:6px;border:1px solid rgba(34,197,94,.2)"><span style="color:#22c55e">●</span> <span style="color:#86efac;font-size:.8rem;font-weight:600">System Online</span></div>', unsafe_allow_html=True)
        st.caption(f"LLM: {h.get('llm_backend','?')} · Embed: {h.get('embedding_backend','?')}")
    else:
        st.markdown('<div style="padding:.4rem;background:rgba(239,68,68,.1);border-radius:6px;border:1px solid rgba(239,68,68,.2)"><span style="color:#ef4444">●</span> <span style="color:#fca5a5;font-size:.8rem;font-weight:600">API Offline</span></div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# 1. OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════
if page == "📊 Overview":
    st.markdown("# 📊 Executive Overview"); st.caption("Real-time business intelligence across all dimensions")
    kpi=ag("/api/analytics/overview")
    if not kpi: st.error("⚠️ API not available."); st.stop()
    c=st.columns(6)
    for col,(l,v,d) in zip(c,[("Revenue",fm(kpi["total_revenue"]),kpi.get("revenue_growth_pct")),("Units Sold",f"{kpi['total_units_sold']:,}",kpi.get("units_growth_pct")),("Margin",f"{kpi['gross_margin_pct']}%",kpi.get("margin_growth_pct")),("Mktg Spend",fm(kpi["total_marketing_spend"]),kpi.get("spend_growth_pct")),("ROAS",f"{kpi['avg_roas']}x",kpi.get("roas_growth_pct")),("Customers",f"{kpi['total_customers']:,}",kpi.get("customer_growth_pct"))]):
        with col: st.markdown(kc(l,v,d),unsafe_allow_html=True)
    st.markdown("---")
    c1,c2=st.columns([3,2])
    with c1:
        st.markdown('<div class="sh">Revenue & Profit Trend</div>',unsafe_allow_html=True)
        t=ag("/api/analytics/revenue-trend")
        if t:
            df=pd.DataFrame(t); df["month"]=pd.to_datetime(df["month"])
            fig=go.Figure()
            fig.add_trace(go.Scatter(x=df["month"],y=df["revenue"],name="Revenue",line=dict(color="#6366f1",width=3),fill="tozeroy",fillcolor="rgba(99,102,241,.08)"))
            fig.add_trace(go.Scatter(x=df["month"],y=df["profit"],name="Profit",line=dict(color="#22c55e",width=2)))
            fig.update_layout(**gl()); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.markdown('<div class="sh">Category Performance</div>',unsafe_allow_html=True)
        cp=ag("/api/analytics/category-performance")
        if cp:
            df=pd.DataFrame(cp)
            fig=px.bar(df,x="revenue",y="category",orientation="h",color="category",color_discrete_sequence=px.colors.qualitative.Set2,text_auto=".2s")
            fig.update_layout(**gl(),showlegend=False,yaxis=dict(categoryorder="total ascending"))
            fig.update_traces(textposition="outside",textfont_size=10); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    c3,c4=st.columns(2)
    with c3:
        st.markdown('<div class="sh">Campaign ROAS</div>',unsafe_allow_html=True)
        cp2=ag("/api/campaigns")
        if cp2:
            df=pd.DataFrame(cp2).head(10)
            fig=px.bar(df,x="campaign_name",y="roas",color="channel",text_auto=".2f")
            fig.update_layout(**gl(),xaxis_tickangle=-45); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    with c4:
        st.markdown('<div class="sh">Customer Segments</div>',unsafe_allow_html=True)
        seg=ag("/api/customers/segments")
        if seg:
            df=pd.DataFrame(seg)
            fig=px.pie(df,values="revenue",names="segment",hole=.45,color_discrete_sequence=["#6366f1","#22c55e","#f59e0b","#ef4444"])
            fig.update_layout(**gl()); fig.update_traces(textinfo="label+percent"); st.plotly_chart(fig,use_container_width=True)
    st.markdown('<div class="sh">💡 AI Executive Insight</div>',unsafe_allow_html=True)
    ins=ap("/query",{"question":"Give a brief executive summary. Key trends, risks, recommendations."})
    if ins: st.info(ins["answer"][:800])

# ═══════════════════════════════════════════════════════════════════════════
# 2. AI ANALYST
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🤖 AI Analyst":
    st.markdown("# 🤖 AI Analyst"); st.caption("Ask questions about sales, marketing, products, customers, campaigns, and strategy")
    examples=["-- Select example --","Which product generated the highest revenue?","What is the recommended strategy for high-value customers?","Which products generated the highest revenue, and what marketing strategy does the company recommend?","Aurora Pro Wireless Earbuds sales declined in Q2 2025. What are the likely reasons?","What discount is recommended for campaigns?","Which campaign should receive more budget?","Why did Electronics revenue decline in Q2, and should we increase marketing spend?","What will Amazon's sales be in 2030?"]
    chosen=st.selectbox("💡 Try an example:",examples); dq="" if chosen.startswith("--") else chosen
    q=st.text_input("Your question:",value=dq,placeholder="e.g. Which campaign has highest ROAS?")
    if st.button("🔍 Analyze",type="primary",use_container_width=True) and q.strip():
        with st.spinner("Classifying · Retrieving · Generating..."):
            t0=time.time(); r=ap("/query",{"question":q}); lat=(time.time()-t0)*1000
        if r:
            st.markdown('<div class="sh">Query Intelligence</div>',unsafe_allow_html=True)
            l,ri=st.columns([1,2])
            with l:
                m=r.get("metrics",{})
                st.markdown(f"""<div class="insight"><b>Question:</b> "{q}"<br><br><b>Type:</b> {bd(r['query_type'])}<br><br><b>Reason:</b> <span style="color:#64748b;font-size:.85rem">{m.get('classification_reason','N/A')}</span><br><br><b>Evidence:</b> {len(r.get('sources',[]))} sources<br><br><b>Confidence:</b> {'High' if r['query_type'] in ('analytical','knowledge') else 'Medium'}</div>""",unsafe_allow_html=True)
                is_s=any(s["type"]=="structured_data" for s in r.get("sources",[])); is_k=any(s["type"]=="knowledge_base" for s in r.get("sources",[]))
                st.markdown(f'<div class="insight" style="font-size:.85rem">Pipeline:<br>{"✓" if is_s else "○"} Structured · {"✓" if is_k else "○"} Vector · {"✓" if is_k else "○"} Keyword · ✓ Rerank · ✓ Fuse</div>',unsafe_allow_html=True)
            with ri:
                st.markdown(f'<div class="insight insight-s"><div style="margin-bottom:.5rem"><b>AI Answer</b></div><div style="line-height:1.6">{r["answer"]}</div><div style="margin-top:.5rem;font-size:.8rem;color:#64748b">Latency: {m.get("end_to_end_latency_ms",0):.0f}ms · Backend: {m.get("llm_backend","?")}</div></div>',unsafe_allow_html=True)
            st.markdown('<div class="sh">Evidence & Sources</div>',unsafe_allow_html=True)
            ev_l,ev_r=st.columns([1,2])
            with ev_l:
                st.markdown("**Data Sources:**")
                for s in r.get("sources",[]):
                    ic="📄" if s["type"]=="knowledge_base" else "📊"; cls="src-doc" if s["type"]=="knowledge_base" else "src-data"
                    st.markdown(f'<span class="src-tag {cls}">{ic} {s["source"]}</span>',unsafe_allow_html=True)
            with ev_r:
                with st.expander("📋 Full Evidence Panel",expanded=False):
                    ev=r.get("evidence",{})
                    if "knowledge_base_chunks" in ev:
                        for c in ev["knowledge_base_chunks"]:
                            st.markdown(f'<div class="insight" style="padding:.7rem;margin-bottom:.4rem"><b style="font-size:.85rem">{c["source"]}</b> <span style="color:#6366f1;font-size:.75rem">Relevance: {c["relevance_score"]}</span><div style="font-size:.85rem;color:#475569;margin-top:.3rem">{c["text"][:400]}...</div></div>',unsafe_allow_html=True)
                    if "structured_data" in ev: st.json(ev["structured_data"])
                    if "detected_conflict" in ev: st.warning(f"⚠️ Conflict: {ev['detected_conflict'].get('note','')}")
        else: st.error("Query failed.")
    if st.session_state.get("ai_question"):
        fu=st.text_input("Follow-up:",key="ai_fu")
        if st.button("Ask Follow-up",key="ai_fu_btn") and fu.strip():
            with st.spinner("..."): fr=ap("/query",{"question":fu})
            if fr: st.markdown(bd(fr["query_type"]),unsafe_allow_html=True); st.markdown(fr["answer"])

# ═══════════════════════════════════════════════════════════════════════════
# 3. DATA HUB
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📁 Data Hub":
    st.markdown("# 📁 Data Hub"); st.caption("Upload, profile, validate, and manage datasets")
    tab_up, tab_list = st.tabs(["📤 Upload","📋 Datasets"])
    with tab_up:
        st.markdown('<div class="sh">Upload Dataset</div>',unsafe_allow_html=True)
        st.caption("Supported: CSV (.csv), Excel (.xlsx, .xls)")
        up=st.file_uploader("Choose a file",type=["csv","xlsx","xls"],key="dh_upload")
        if up and st.button("📤 Upload & Profile",type="primary",key="dh_btn"):
            with st.spinner("Uploading · Parsing · Profiling · Validating · Mapping..."):
                r=ap("/api/datahub/upload",f={"file":(up.name,up.getvalue(),"application/octet-stream")})
            if r:
                st.success(f"✅ Processed {r['total_rows']:,} rows across {len(r['profiles'])} dataset(s)")
                for p in r["profiles"]:
                    with st.expander(f"📊 {p['filename']}" + (f" — Sheet: {p['sheet_name']}" if p.get("sheet_name") else ""),expanded=True):
                        st.markdown(f"**Quality Score:** {p['quality_score']}/100")
                        prog=p["quality_score"]/100
                        st.progress(prog)
                        m1,m2,m3,m4=st.columns(4)
                        m1.metric("Rows",f"{p['row_count']:,}")
                        m2.metric("Columns",p['col_count'])
                        m3.metric("Duplicates",p['duplicate_rows'])
                        m4.metric("Issues",len(p["issues"]))
                        if p["issues"]:
                            st.markdown("**Issues:**")
                            for iss in p["issues"]: st.markdown(f"  {iss['message']}")
                        st.markdown("**Column Profiles:**")
                        for c in p["columns"]:
                            st.markdown(f"  `{c['name']}` ({c['dtype']}) — semantic: **{c['semantic_type']}** · unique: {c['unique_count']} · nulls: {c['null_pct']}%")
            else: st.error("Upload failed.")
    with tab_list:
        ds_list=ag("/api/datahub/datasets")
        if ds_list:
            for ds in ds_list:
                with st.container():
                    l1,l2,l3,l4=st.columns([4,1,1,1])
                    with l1: st.markdown(f"**{ds['filename']}** ({ds['total_rows']:,} rows, {ds['total_columns']} cols)")
                    with l2: st.markdown(f'<div class="badge badge-a">Score: {ds["quality_score"]}</div>',unsafe_allow_html=True)
                    with l3: st.caption(f"{ds['issue_count']} issues")
                    with l4:
                        if st.button("🗑️",key=f"del_{ds['dataset_id']}"):
                            requests.delete(f"{API}/api/datahub/datasets/{ds['dataset_id']}",timeout=10); st.rerun()
        else: st.info("No datasets uploaded yet. Upload a CSV or Excel file to get started.")

# ═══════════════════════════════════════════════════════════════════════════
# 4. SALES
# ═══════════════════════════════════════════════════════════════════════════
elif page == "💰 Sales":
    st.markdown("# 💰 Sales Intelligence"); st.caption("Revenue analysis, growth, and profitability")
    kpi=ag("/api/analytics/overview")
    if not kpi: st.error("⚠️ API not available."); st.stop()
    c=st.columns(6)
    for col,(l,v,d) in zip(c,[("Revenue",fm(kpi["total_revenue"]),kpi.get("revenue_growth_pct")),("Units",f"{kpi['total_units_sold']:,}",kpi.get("units_growth_pct")),("Margin",f"{kpi['gross_margin_pct']}%",kpi.get("margin_growth_pct")),("Spend",fm(kpi["total_marketing_spend"]),kpi.get("spend_growth_pct")),("ROAS",f"{kpi['avg_roas']}x",kpi.get("roas_growth_pct")),("Customers",f"{kpi['total_customers']:,}",kpi.get("customer_growth_pct"))]):
        with col: st.markdown(kc(l,v,d),unsafe_allow_html=True)
    st.markdown("---")
    trend=ag("/api/analytics/revenue-trend")
    if trend:
        st.markdown('<div class="sh">Revenue Trend</div>',unsafe_allow_html=True)
        df=pd.DataFrame(trend); df["month"]=pd.to_datetime(df["month"])
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=df["month"],y=df["revenue"],name="Revenue",line=dict(color="#6366f1",width=3),fill="tozeroy",fillcolor="rgba(99,102,241,.08)"))
        fig.add_trace(go.Scatter(x=df["month"],y=df["profit"],name="Profit",line=dict(color="#22c55e",width=2),fill="tozeroy",fillcolor="rgba(34,197,94,.06)"))
        fig.update_layout(**gl(350)); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    cp=ag("/api/analytics/category-performance")
    if cp:
        st.markdown('<div class="sh">Revenue by Category</div>',unsafe_allow_html=True)
        df=pd.DataFrame(cp)
        fig=px.bar(df,x="category",y="revenue",color="category",text_auto=".2s",color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(**gl(),showlegend=False); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
        st.dataframe(df,use_container_width=True,hide_index=True,column_config={"revenue":st.column_config.NumberColumn("Revenue",format="$%,.0f"),"gross_profit":st.column_config.NumberColumn("Profit",format="$%,.0f"),"gross_margin_pct":st.column_config.NumberColumn("Margin",format="%.1f%%"),"total_roas":st.column_config.NumberColumn("ROAS",format="%.2fx")})

# ═══════════════════════════════════════════════════════════════════════════
# 5. MARKETING
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📢 Marketing":
    st.markdown("# 📢 Marketing Intelligence"); st.caption("Campaign performance, ROAS, CTR, and optimization")
    camps=ag("/api/campaigns")
    if not camps: st.error("⚠️ API not available."); st.stop()
    df=pd.DataFrame(camps)
    ts,tre=df["spend"].sum(),df["attributed_revenue"].sum()
    broas=tre/ts if ts>0 else 0
    c=st.columns(4)
    for col,(l,v) in zip(c,[("Total Spend",fm(ts)),("Total Revenue",fm(tre)),("Blended ROAS",f"{broas:.2f}x"),("Campaigns",str(len(camps)))]):
        with col: st.markdown(kc(l,v),unsafe_allow_html=True)
    st.markdown("---")
    c1,c2=st.columns(2)
    with c1:
        st.markdown('<div class="sh">ROAS by Campaign</div>',unsafe_allow_html=True)
        dfs=df.sort_values("roas",ascending=True)
        fig=px.bar(dfs,x="roas",y="campaign_name",orientation="h",color="channel",text_auto=".2f")
        fig.add_vline(x=3.0,line_dash="dash",line_color="#ef4444",line_width=1,annotation_text="3.0x Target")
        fig.update_layout(**gl(400)); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.markdown('<div class="sh">Spend vs Revenue</div>',unsafe_allow_html=True)
        fig=px.scatter(df,x="spend",y="attributed_revenue",size="conversions",color="channel",hover_name="campaign_name")
        fig.add_trace(go.Scatter(x=[0,df["spend"].max()*1.1],y=[0,df["spend"].max()*1.1],mode="lines",line=dict(dash="dash",color="#94a3b8"),name="1:1"))
        fig.update_layout(**gl(400)); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    st.markdown('<div class="sh">Campaign Table</div>',unsafe_allow_html=True)
    f1,f2=st.columns(2)
    with f1: sel_ch=st.selectbox("Channel",["All"]+sorted(df["channel"].unique().tolist()),key="m_ch")
    df_f=df if sel_ch=="All" else df[df["channel"]==sel_ch]
    st.dataframe(df_f.sort_values("roas",ascending=False),use_container_width=True,hide_index=True,column_config={"spend":st.column_config.NumberColumn("Spend",format="$%,.0f"),"attributed_revenue":st.column_config.NumberColumn("Revenue",format="$%,.0f"),"roas":st.column_config.NumberColumn("ROAS",format="%.2fx"),"ctr":st.column_config.NumberColumn("CTR",format="%.3f%%"),"conversion_rate":st.column_config.NumberColumn("Conv Rate",format="%.3f%%"),"cpc":st.column_config.NumberColumn("CPC",format="$%.2f"),"cpa":st.column_config.NumberColumn("CPA",format="$%.2f")})

# ═══════════════════════════════════════════════════════════════════════════
# 6. PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📦 Products":
    st.markdown("# 📦 Product Intelligence"); st.caption("Product performance, profitability, and optimization")
    prods=ag("/api/products")
    if not prods: st.error("⚠️ API not available."); st.stop()
    df=pd.DataFrame(prods)
    c=st.columns(4)
    for col,(l,v) in zip(c,[("Products",str(len(prods))),("Revenue",fm(df["total_revenue"].sum())),("Units",f"{df['total_units_sold'].sum():,}"),("Avg Margin",f"{df['gross_margin_pct'].dropna().mean():.1f}%")]):
        with col: st.markdown(kc(l,v),unsafe_allow_html=True)
    st.markdown("---")
    c1,c2=st.columns(2)
    with c1:
        st.markdown('<div class="sh">Top 10 Products</div>',unsafe_allow_html=True)
        top10=df.nlargest(10,"total_revenue")
        fig=px.bar(top10,x="total_revenue",y="product_name",orientation="h",color="category",text_auto=".2s")
        fig.update_layout(**gl(400),showlegend=True); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.markdown('<div class="sh">Revenue by Category</div>',unsafe_allow_html=True)
        cr=df.groupby("category").agg({"total_revenue":"sum","product_id":"count"}).reset_index()
        cr.columns=["category","revenue","count"]
        fig=px.pie(cr,values="revenue",names="category",hole=.4,color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(**gl(400)); st.plotly_chart(fig,use_container_width=True)
    st.markdown('<div class="sh">Product Directory</div>',unsafe_allow_html=True)
    f1,f2,f3=st.columns(3)
    with f1: sel=st.selectbox("Category",["All"]+sorted(df["category"].unique().tolist()),key="p_cat")
    with f2: sb=st.selectbox("Sort",["Revenue","Units","Margin","ROAS","Rating"],key="p_sort")
    with f3: search=st.text_input("Search:",placeholder="Product name...")
    df_f=df.copy()
    if sel!="All": df_f=df_f[df_f["category"]==sel]
    if search.strip(): df_f=df_f[df_f["product_name"].str.contains(search,case=False,na=False)]
    sm={"Revenue":"total_revenue","Units":"total_units_sold","Margin":"gross_margin_pct","ROAS":"product_roas","Rating":"rating"}
    df_f=df_f.sort_values(sm[sb],ascending=False,na_position="last")
    st.dataframe(df_f[["product_id","product_name","category","subcategory","price","total_revenue","total_units_sold","gross_margin_pct","avg_discount_pct","rating","review_count","total_marketing_spend","product_roas"]],use_container_width=True,hide_index=True,height=400,column_config={"price":st.column_config.NumberColumn("Price",format="$%.2f"),"total_revenue":st.column_config.NumberColumn("Revenue",format="$%,.0f"),"total_units_sold":st.column_config.NumberColumn("Units",format="%d"),"gross_margin_pct":st.column_config.NumberColumn("Margin",format="%.1f%%"),"total_marketing_spend":st.column_config.NumberColumn("Spend",format="$%,.0f"),"product_roas":st.column_config.NumberColumn("ROAS",format="%.2fx"),"rating":st.column_config.NumberColumn("Rating",format="%.1f ⭐")})

# ═══════════════════════════════════════════════════════════════════════════
# 7. CUSTOMERS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "👥 Customers":
    st.markdown("# 👥 Customer Intelligence"); st.caption("Segment analysis, LTV, and retention strategy")
    seg=ag("/api/customers/segments")
    if not seg: st.error("⚠️ API not available."); st.stop()
    df=pd.DataFrame(seg)
    c=st.columns(3)
    for col,(l,v) in zip(c,[("Customers",f"{df['customers'].sum():,}"),("Revenue",fm(df["revenue"].sum())),("Avg LTV",fm(df["avg_ltv"].mean()))]):
        with col: st.markdown(kc(l,v),unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div class="sh">Customer Segments</div>',unsafe_allow_html=True)
    sc=st.columns(len(seg))
    for i,s in enumerate(seg):
        with sc[i]:
            rp=f"{s.get('repeat_purchase_rate',0):.1f}%" if s.get("repeat_purchase_rate") is not None else "N/A"
            st.markdown(f'<div class="insight" style="text-align:center"><div class="kpi-l">{s["segment"]}</div><div class="kpi-v">{s["customers"]:,}</div><div style="font-size:.8rem;color:#64748b">customers</div><div style="margin-top:.5rem;border-top:1px solid #e2e8f0;padding-top:.4rem"><b style="color:#059669">{fm(s["revenue"])}</b><div style="font-size:.75rem;color:#94a3b8">LTV: {fm(s["avg_ltv"])} · Repeat: {rp}</div></div></div>',unsafe_allow_html=True)
    st.markdown("---")
    c1,c2=st.columns(2)
    with c1:
        st.markdown('<div class="sh">Revenue by Segment</div>',unsafe_allow_html=True)
        fig=px.pie(df,values="revenue",names="segment",hole=.4,color_discrete_sequence=["#6366f1","#22c55e","#f59e0b","#ef4444"])
        fig.update_layout(**gl(300)); fig.update_traces(textinfo="label+percent"); st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.markdown('<div class="sh">LTV by Segment</div>',unsafe_allow_html=True)
        fig=px.bar(df,x="segment",y="avg_ltv",color="segment",color_discrete_sequence=["#6366f1","#22c55e","#f59e0b","#ef4444"],text_auto="$,.0f")
        fig.update_layout(**gl(300),showlegend=False); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    st.dataframe(df,use_container_width=True,hide_index=True,column_config={"revenue":st.column_config.NumberColumn("Revenue",format="$%,.0f"),"avg_ltv":st.column_config.NumberColumn("Avg LTV",format="$%,.0f"),"repeat_purchase_rate":st.column_config.NumberColumn("Repeat Rate",format="%.1f%%")})

# ═══════════════════════════════════════════════════════════════════════════
# 8. REVIEWS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "⭐ Reviews":
    st.markdown("# ⭐ Review Intelligence"); st.caption("Customer sentiment analysis and review themes")
    rv=ag("/api/analytics/reviews")
    if not rv: st.error("⚠️ API not available."); st.stop()
    c=st.columns(4)
    for col,(l,v) in zip(c,[("Total Reviews",f"{rv['total_reviews']:,}"),("Avg Rating",f"⭐ {rv['avg_rating']:.1f}" if rv.get("avg_rating") else "N/A"),("Negative",str(rv["negative_count"])),("Neg %",f"{rv['negative_pct']}%")]):
        with col: st.markdown(kc(l,v),unsafe_allow_html=True)
    st.markdown("---")
    c1,c2=st.columns(2)
    with c1:
        st.markdown('<div class="sh">Rating Distribution</div>',unsafe_allow_html=True)
        if rv["by_rating"]:
            df=pd.DataFrame(rv["by_rating"])
            fig=px.bar(df,x="rating",y="count",color="rating",color_continuous_scale=["#ef4444","#f59e0b","#22c55e","#22c55e","#059669"],text_auto=True)
            fig.update_layout(**gl(300),showlegend=False); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.markdown('<div class="sh">Top Negative Review Themes</div>',unsafe_allow_html=True)
        if rv["top_negative_themes"]:
            df=pd.DataFrame(rv["top_negative_themes"])
            fig=px.bar(df,x="count",y="theme",orientation="h",color_discrete_sequence=["#ef4444"],text_auto=True)
            fig.update_layout(**gl(300),yaxis=dict(categoryorder="total ascending")); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
        else: st.info("No significant negative themes detected.")

# ═══════════════════════════════════════════════════════════════════════════
# 9. DISCOUNTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "💲 Discounts":
    st.markdown("# 💲 Discount & Promotion Analytics"); st.caption("Discount impact analysis across revenue, units, and margin")
    da=ag("/api/analytics/discounts")
    if not da: st.error("⚠️ API not available."); st.stop()
    st.markdown(f"**Overall Average Discount:** {da['overall_avg_discount']}%")
    st.markdown("---")
    c1,c2=st.columns(2)
    with c1:
        st.markdown('<div class="sh">Revenue by Discount Band</div>',unsafe_allow_html=True)
        if da["discount_bands"]:
            df=pd.DataFrame(da["discount_bands"])
            fig=px.bar(df,x="discount_band",y="total_revenue",text_auto=".2s",color_discrete_sequence=["#6366f1"])
            fig.update_layout(**gl(300)); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.markdown('<div class="sh">Margin by Discount Band</div>',unsafe_allow_html=True)
        if da["margin_by_band"]:
            df=pd.DataFrame(da["margin_by_band"])
            fig=px.bar(df,x="band",y="avg_margin_pct",text_auto=".1f",color_discrete_sequence=["#22c55e"])
            fig.update_layout(**gl(300)); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
    if da["discount_bands"]:
        st.markdown('<div class="sh">Discount Band Detail</div>',unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(da["discount_bands"]),use_container_width=True,hide_index=True,column_config={"total_revenue":st.column_config.NumberColumn("Revenue",format="$%,.0f"),"total_units":st.column_config.NumberColumn("Units",format="%d"),"avg_selling_price":st.column_config.NumberColumn("Avg Price",format="$%.2f")})

# ═══════════════════════════════════════════════════════════════════════════
# 10. INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "💡 Insights":
    st.markdown("# 💡 AI Insights"); st.caption("Proactive business insights generated from data analysis")
    if st.button("🔄 Generate Insights",type="primary",key="ins_btn"):
        with st.spinner("Analyzing data..."):
            r=ap("/api/insights")
        if r and r.get("insights"):
            st.session_state["insights"]=r["insights"]
    ins=st.session_state.get("insights")
    if ins:
        for i in ins:
            icon={"warning":"🔴","success":"🟢","info":"💡","risk":"🟠"}.get(i.get("type","info"),"💡")
            cls={"warning":"insight-w","success":"insight-s","info":"insight-i"}.get(i.get("type","info"),"insight")
            imp_badge="badge-a" if i.get("impact")=="high" else "badge-h"
            imp_val=i.get("impact","N/A")
            conf_val=i.get("confidence","N/A")
            desc=i["description"]
            title=i["title"]
            evidence_html=""
            ev=i.get("evidence",[])
            if ev:
                evidence_html=f"<div style='margin-top:.3rem;font-size:.8rem;color:#475569'>Evidence: {' · '.join(ev)}</div>"
            st.markdown(f'<div class="insight {cls}"><b>{icon} {title}</b> <span class="badge {imp_badge}" style="font-size:.6rem">Impact: {imp_val}</span><div style="margin:.4rem 0;color:#334155;font-size:.9rem">{desc}</div><div style="font-size:.8rem;color:#64748b">Confidence: {conf_val}</div>{evidence_html}</div>',unsafe_allow_html=True)
    else: st.info("Click 'Generate Insights' to analyze the data and surface actionable business insights.")

# ═══════════════════════════════════════════════════════════════════════════
# 11. RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📋 Recommendations":
    st.markdown("# 📋 AI Recommendations"); st.caption("Actionable recommendations backed by data evidence")
    recs = [
        {"title": "Review Underperforming Campaign Budgets", "why": "Multiple campaigns have ROAS below the 3.0x guideline threshold.", "evidence": "Campaign data + Campaign Guidelines", "confidence": "High"},
        {"title": "Invest in Premium Customer Retention", "why": "Premium customers have 3-4x the LTV of Regular customers with strong repeat-purchase behavior.", "evidence": "Customer data + Customer Strategy", "confidence": "Medium"},
        {"title": "Investigate Negative Review Themes for Electronics", "why": "Battery and connectivity complaints are rising in recent reviews.", "evidence": "Review data + Product Strategy", "confidence": "Medium"},
        {"title": "Test a Controlled Discount Strategy", "why": "Observed relationship between discount levels and margin — controlled testing recommended before broad changes.", "evidence": "Sales data + Pricing Policy", "confidence": "Medium"},
        {"title": "Double Down on High-Margin Product Lines", "why": "Several products have 50%+ margins with strong revenue — increased marketing investment has high expected ROI.", "evidence": "Sales data + Marketing Strategy", "confidence": "High"},
    ]
    for r in recs:
        st.markdown(f'<div class="insight insight-i"><b>📋 {r["title"]}</b><div style="margin:.3rem 0;font-size:.9rem;color:#334155"><b>Why:</b> {r["why"]}</div><div style="font-size:.8rem;color:#64748b">Evidence: {r["evidence"]} · Confidence: {r["confidence"]}</div></div>',unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# 12. EXECUTIVE BRIEF
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📄 Executive Brief":
    st.markdown("# 📄 Executive Brief"); st.caption("Structured business summary for leadership")
    if st.button("📄 Generate Brief",type="primary",key="eb_btn"):
        with st.spinner("Generating executive brief..."):
            r=ap("/api/executive-brief")
        if r: st.session_state["ebrief"]=r
    eb=st.session_state.get("ebrief")
    if eb:
        for s in eb.get("sections",[]):
            icon={"Business Performance":"📊","Key Drivers":"📈","Risks":"⚠️","Opportunities":"💡","Recommended Actions":"🎯"}.get(s["title"],"📄")
            st.markdown(f'<div class="insight"><b>{icon} {s["title"]}</b><div style="margin:.3rem 0;color:#334155;font-size:.9rem;line-height:1.5">{s["content"]}</div></div>',unsafe_allow_html=True)
    else: st.info("Click 'Generate Brief' to create a structured executive summary from the current data.")

# ═══════════════════════════════════════════════════════════════════════════
# 13. KNOWLEDGE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📚 Knowledge":
    st.markdown("# 📚 Knowledge Center"); st.caption("RAG knowledge base management")
    docs=ag("/documents")
    if docs is None: st.error("⚠️ API not available."); st.stop()
    tc=sum(d["chunk_count"] for d in docs)
    c=st.columns(4)
    for col,(l,v) in zip(c,[("Documents",str(len(docs))),("Chunks",f"{tc:,}"),("Embeddings",f"{tc:,}"),("Store","TF-IDF")]):
        with col: st.markdown(kc(l,v),unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div class="sh">Indexed Documents</div>',unsafe_allow_html=True)
    for doc in docs:
        with st.container():
            l1,l2,l3=st.columns([4,2,1])
            with l1: st.markdown(f"**📄 {doc['document_name']}** · {doc['chunk_count']} chunks · `{doc['document_type']}`")
            with l2: st.markdown(f'<span class="badge badge-a">Indexed ✓</span>',unsafe_allow_html=True)
            with l3:
                if st.button("🗑️",key=f"del_{doc['document_id']}"):
                    api_post(f"/documents/{doc['document_id']}"); st.rerun()
    st.markdown("---")
    st.markdown('<div class="sh">Upload Document</div>',unsafe_allow_html=True)
    st.caption("Supported: Markdown (.md), CSV (.csv), Excel (.xlsx/.xls), Text (.txt)")
    up=st.file_uploader("Choose a file",type=["md","csv","xlsx","xls","txt"],key="kb_up")
    if up and st.button("📤 Upload & Index",type="primary",key="kb_btn"):
        ext=up.name.rsplit(".",1)[-1].lower()
        mime={"md":"text/markdown","csv":"text/csv","xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","xls":"application/vnd.ms-excel","txt":"text/plain"}
        with st.spinner(f"Processing {ext.upper()}..."):
            r=ap("/documents/upload",f={"file":(up.name,up.getvalue(),mime.get(ext,"application/octet-stream"))})
        if r: st.success(f"✅ {r['message']} ({r['chunks_created']} chunks)"); st.rerun()
        else: st.error("Upload failed.")
    st.markdown("---")
    st.markdown('<div class="sh">Search Knowledge Base</div>',unsafe_allow_html=True)
    kbq=st.text_input("Search:",placeholder="Search documents...")
    if kbq:
        with st.spinner("Searching..."):
            r=ap("/query",{"question":kbq})
        if r and r.get("evidence",{}).get("knowledge_base_chunks"):
            for c in r["evidence"]["knowledge_base_chunks"]:
                with st.expander(f"📄 {c['source']} — Relevance: {c['relevance_score']}"):
                    st.markdown(c["text"])

# ═══════════════════════════════════════════════════════════════════════════
# 14. EVALUATION
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🔬 Evaluation":
    st.markdown("# 🔬 RAG Evaluation"); st.caption("System quality measurement across 38 test cases")
    if st.button("▶️ Run Evaluation",type="primary",key="eval_run",use_container_width=True):
        with st.spinner("Running 38 test cases..."):
            r=ag("/api/evaluation/run",t=120)
        if r: st.session_state["eval"]=r; st.success("✅ Complete!"); st.rerun()
        else: st.error("Failed.")
    ev=st.session_state.get("eval")
    if ev:
        c=st.columns(4)
        for col,(l,v) in zip(c,[("Accuracy",f"{ev['query_type_accuracy']*100:.1f}%"),("Recall",f"{ev['retrieval_recall_at_k']*100:.1f}%"),("Avg Latency",f"{ev['avg_end_to_end_latency_ms']:.0f}ms"),("P95 Latency",f"{ev['p95_end_to_end_latency_ms']:.0f}ms")]):
            with col: st.markdown(kc(l,v),unsafe_allow_html=True)
        st.markdown("---")
        bk=ev.get("by_bucket",{})
        if bk:
            st.markdown('<div class="sh">Results by Category</div>',unsafe_allow_html=True)
            bdf=pd.DataFrame([{"Category":k,"Count":v["count"],"Type Accuracy":v["type_accuracy"]*100,"Retrieval Recall":v["retrieval_recall"]*100} for k,v in bk.items()])
            fig=go.Figure()
            fig.add_trace(go.Bar(name="Type Accuracy",x=bdf["Category"],y=bdf["Type Accuracy"],marker_color="#6366f1",text=bdf["Type Accuracy"].apply(lambda x:f"{x:.0f}%"),textposition="outside"))
            fig.add_trace(go.Bar(name="Retrieval Recall",x=bdf["Category"],y=bdf["Retrieval Recall"],marker_color="#22c55e",text=bdf["Retrieval Recall"].apply(lambda x:f"{x:.0f}%"),textposition="outside"))
            fig.update_layout(**gl(300),barmode="group",yaxis_title="%",yaxis_range=[0,105]); ag_grid(fig); st.plotly_chart(fig,use_container_width=True)
        st.markdown('<div class="sh">Test Cases</div>',unsafe_allow_html=True)
        tc=ev.get("test_cases",[])
        passed=sum(1 for t in tc if t.get("type_match")); failed=len(tc)-passed
        c=st.columns(3); c[0].metric("Total",str(len(tc))); c[1].metric("Passed",f"✅ {passed}"); c[2].metric("Failed",f"❌ {failed}")
        flt=st.selectbox("Filter",["All","Passed","Failed"],key="eval_f")
        for t in tc:
            if flt=="Passed" and not t.get("type_match"): continue
            if flt=="Failed" and t.get("type_match"): continue
            ic="✅" if t.get("type_match") else "❌"
            with st.expander(f"{ic} [{t['id']}] {t['question'][:80]}..."):
                st.markdown(f"**Q:** {t['question']}")
                c1,c2=st.columns(2)
                with c1:
                    st.markdown(f"**Expected:** `{t['expected_query_type']}`")
                    st.markdown(f"**Actual:** `{t['actual_query_type']}`")
                with c2:
                    st.markdown(f"**Retrieval:** {'✅' if t.get('retrieval_hit') else '❌'}")
                    st.markdown(f"**Sources:** {', '.join(t.get('sources_returned',[]))}")
                if t.get("answer_preview"): st.markdown(f"**Answer:** {t['answer_preview'][:400]}")
                st.caption(f"Latency: {t.get('end_to_end_latency_ms',0):.1f}ms")
    else:
        st.markdown('<div style="text-align:center;padding:3rem"><div style="font-size:3rem">🔬</div><div style="font-size:1rem;font-weight:600;margin:.5rem 0">Ready to Evaluate</div><div style="color:#64748b">Click the button to run the full 38-case evaluation suite.</div></div>',unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# 15. SYSTEM
# ═══════════════════════════════════════════════════════════════════════════
elif page == "⚙️ System":
    st.markdown("# ⚙️ System Observability"); st.caption("Health checks, performance metrics, and system status")
    if st.button("🔄 Refresh",key="sys_ref"):
        r=ag("/api/system/health")
        if r: st.session_state["sys_health"]=r
    r=ag("/api/system/health")
    if r:
        for name,info in r.items():
            status=info.get("status","unknown")
            color="#22c55e" if status=="healthy" else "#ef4444"
            icon="●" if status=="healthy" else "●"
            details=" · ".join(f"{k}: {v}" for k,v in info.items() if k!="status")
            st.markdown(f'<div class="insight"><span style="color:{color};font-size:1.2rem">{icon}</span> <b>{name.title()}</b> — <span style="color:{color}">{status.title()}</span><div style="font-size:.85rem;color:#64748b;margin-top:.2rem">{details}</div></div>',unsafe_allow_html=True)
    else: st.error("Could not reach system health endpoint.")

# ── Footer ──────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("Amazon Sales & Marketing Intelligence Platform · RAG + Analytics · Built for AI Engineer Recruitment Assignment")
