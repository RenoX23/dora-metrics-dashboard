import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── CONFIG ─────────────────────────────────────────
st.set_page_config(
    page_title="DORA Metrics Dashboard",
    page_icon="🚀",
    layout="wide"
)

BAND_COLORS = {
    'Elite':              '#22c55e',
    'High':               '#3b82f6',
    'Medium':             '#f59e0b',
    'Low':                '#ef4444',
    'Insufficient Data':  '#6b7280',
}

BAND_ORDER = ['Elite', 'High', 'Medium', 'Low', 'Insufficient Data']

# ── LOAD DATA ───────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv("data/dora_metrics.csv")
    df['repo_short'] = df['repo'].apply(lambda x: x.split('/')[-1])
    df['org'] = df['repo'].apply(lambda x: x.split('/')[0])
    df['has_data'] = df['health_score'] > 0
    return df

df = load_data()
df_active = df[df['has_data']].copy()
df_inactive = df[~df['has_data']].copy()

# ── HEADER ──────────────────────────────────────────
st.title("🚀 Engineering Team Health Dashboard")
st.markdown("**DORA Metrics Analysis** · Real GitHub data · June 2026")
st.divider()

# ── SIDEBAR ─────────────────────────────────────────
st.sidebar.header("Filters")
selected_repos = st.sidebar.multiselect(
    "Select Repos",
    options=df_active['repo'].tolist(),
    default=df_active['repo'].tolist()
)
st.sidebar.divider()
st.sidebar.markdown("### DORA Band Reference")
for band, color in BAND_COLORS.items():
    if band != 'Insufficient Data':
        st.sidebar.markdown(
            f'<span style="color:{color}">■</span> **{band}**',
            unsafe_allow_html=True
        )
st.sidebar.markdown("""
| Metric | Elite | High |
|--------|-------|------|
| Deploy Freq | >7/week | 1-7/week |
| Lead Time | <24h | <1 week |
| MTTR | <1h | <24h |
| CFR | <5% | <10% |
""")

filtered = df_active[df_active['repo'].isin(selected_repos)]

# ── PAGE 1: LEADERBOARD ─────────────────────────────
st.header("📊 Repo Health Leaderboard")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Repos Analyzed", len(df_active))
col2.metric("Avg Health Score", f"{df_active['health_score'].mean():.1f}/100")
col3.metric("Elite Lead Time Repos", len(df_active[df_active['lead_time_band']=='Elite']))
col4.metric("Elite CFR Repos", len(df_active[df_active['cfr_band']=='Elite']))

st.divider()

# Health Score Bar Chart
fig_scores = px.bar(
    filtered.sort_values('health_score', ascending=True),
    x='health_score',
    y='repo_short',
    orientation='h',
    color='health_score',
    color_continuous_scale=['#ef4444', '#f59e0b', '#3b82f6', '#22c55e'],
    range_color=[0, 100],
    text='health_score',
    labels={'health_score': 'Health Score', 'repo_short': 'Repository'},
    title='Engineering Health Score by Repository (0–100)'
)
fig_scores.update_traces(texttemplate='%{text}', textposition='outside')
fig_scores.update_layout(height=350, showlegend=False, coloraxis_showscale=False)
st.plotly_chart(fig_scores, use_container_width=True)

# DORA Band Matrix Table
st.subheader("DORA Band Matrix")

def color_band(val):
    color = BAND_COLORS.get(val, '#ffffff')
    text = 'white' if val != 'Insufficient Data' else '#374151'
    return f'background-color: {color}; color: {text}; font-weight: bold; text-align: center'

display_df = filtered[[
    'repo_short', 'health_score',
    'deploy_freq_band', 'lead_time_band', 'mttr_band', 'cfr_band'
]].rename(columns={
    'repo_short':         'Repository',
    'health_score':       'Score',
    'deploy_freq_band':   'Deploy Freq',
    'lead_time_band':     'Lead Time',
    'mttr_band':          'MTTR',
    'cfr_band':           'CFR',
})

styled = display_df.style.map(
    color_band,
    subset=['Deploy Freq', 'Lead Time', 'MTTR', 'CFR']
)
st.dataframe(styled, use_container_width=True, hide_index=True)

# ── PAGE 2: DORA BREAKDOWN ──────────────────────────
st.divider()
st.header("🔍 DORA Metric Deep Dive")

col_a, col_b = st.columns(2)

with col_a:
    # Lead Time
    fig_lt = px.bar(
        filtered.sort_values('lead_time_hours'),
        x='repo_short', y='lead_time_hours',
        color='lead_time_band',
        color_discrete_map=BAND_COLORS,
        title='Lead Time for Changes (hours) — lower is better',
        labels={'lead_time_hours': 'Hours', 'repo_short': 'Repo'}
    )
    fig_lt.add_hline(y=24,  line_dash='dash', line_color='green',
                     annotation_text='Elite threshold (24h)')
    fig_lt.add_hline(y=168, line_dash='dash', line_color='blue',
                     annotation_text='High threshold (1 week)')
    st.plotly_chart(fig_lt, use_container_width=True)

with col_b:
    # Deployment Frequency
    fig_df = px.bar(
        filtered.sort_values('deployment_frequency', ascending=False),
        x='repo_short', y='deployment_frequency',
        color='deploy_freq_band',
        color_discrete_map=BAND_COLORS,
        title='Deployment Frequency (per week) — higher is better',
        labels={'deployment_frequency': 'Deploys/week', 'repo_short': 'Repo'}
    )
    fig_df.add_hline(y=7, line_dash='dash', line_color='green',
                     annotation_text='Elite (7/week)')
    fig_df.add_hline(y=1, line_dash='dash', line_color='blue',
                     annotation_text='High (1/week)')
    st.plotly_chart(fig_df, use_container_width=True)

col_c, col_d = st.columns(2)

with col_c:
    # MTTR
    fig_mttr = px.bar(
        filtered.sort_values('mttr_hours'),
        x='repo_short', y='mttr_hours',
        color='mttr_band',
        color_discrete_map=BAND_COLORS,
        title='Mean Time to Recovery (hours) — lower is better',
        labels={'mttr_hours': 'Hours', 'repo_short': 'Repo'}
    )
    st.plotly_chart(fig_mttr, use_container_width=True)

with col_d:
    # CFR
    fig_cfr = px.bar(
        filtered.sort_values('change_failure_rate'),
        x='repo_short', y='change_failure_rate',
        color='cfr_band',
        color_discrete_map=BAND_COLORS,
        title='Change Failure Rate — lower is better',
        labels={'change_failure_rate': 'Rate', 'repo_short': 'Repo'}
    )
    fig_cfr.add_hline(y=0.05, line_dash='dash', line_color='green',
                      annotation_text='Elite (<5%)')
    st.plotly_chart(fig_cfr, use_container_width=True)

# ── PAGE 3: RADAR + INSIGHTS ────────────────────────
st.divider()
st.header("🎯 Repo Comparison Radar")

selected_repo = st.selectbox("Select repo for radar view", filtered['repo_short'].tolist())
repo_data = filtered[filtered['repo_short'] == selected_repo].iloc[0]

# Normalize scores 0-4 for radar
radar_vals = [
    BAND_COLORS.get(repo_data['deploy_freq_band'], 0),
    BAND_COLORS.get(repo_data['lead_time_band'],   0),
    BAND_COLORS.get(repo_data['mttr_band'],         0),
    BAND_COLORS.get(repo_data['cfr_band'],          0),
]

band_to_num = {'Elite': 4, 'High': 3, 'Medium': 2, 'Low': 1, 'Insufficient Data': 0}
radar_nums = [
    band_to_num[repo_data['deploy_freq_band']],
    band_to_num[repo_data['lead_time_band']],
    band_to_num[repo_data['mttr_band']],
    band_to_num[repo_data['cfr_band']],
]

fig_radar = go.Figure(data=go.Scatterpolar(
    r=radar_nums + [radar_nums[0]],
    theta=['Deploy Freq', 'Lead Time', 'MTTR', 'CFR', 'Deploy Freq'],
    fill='toself',
    line_color='#3b82f6',
    fillcolor='rgba(59, 130, 246, 0.2)'
))
fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 4],
               tickvals=[1,2,3,4], ticktext=['Low','Medium','High','Elite'])),
    title=f"DORA Profile: {selected_repo}",
    height=400
)
st.plotly_chart(fig_radar, use_container_width=True)

# ── INSUFFICIENT DATA NOTE ──────────────────────────
st.divider()
st.header("⚠️ Repos with Insufficient Data")
st.info(
    f"**{len(df_inactive)} repos** lack DORA measurability — "
    "no PR workflow, releases, or issue tracking detected. "
    "DORA metrics require team-based PR workflows to be meaningful."
)
st.dataframe(
    df_inactive[['repo', 'org']].rename(columns={'repo': 'Repository', 'org': 'Owner'}),
    use_container_width=True,
    hide_index=True
)

# ── FOOTER ──────────────────────────────────────────
st.divider()
st.caption(
    "Data sourced from GitHub API · June 2026 · "
    "Built by Renold Stephen · "
    "[GitHub](https://github.com/RenoX23/dora-metrics-dashboard)"
)
