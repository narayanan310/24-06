"""
dashboard/app.py
Edge Auto Assistant — Live Cockpit Dashboard

Reads /tmp/assistant_state.json written by main.py after every command.
Auto-refreshes every 1 second to show live vehicle state.

Run with:
    streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0
Then open: http://raspberrypi1.local:8501
"""

import json
import time
import os
import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title  = "Edge Auto Assistant",
    page_icon   = "🚗",
    layout      = "wide",
    initial_sidebar_state = "collapsed",
)

# Auto-refresh every 1 second
st_autorefresh(interval=1000, key="dash_refresh")

STATE_FILE = "/tmp/assistant_state.json"

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Base ── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.stApp { background: #070b14; color: #e2e8f0; }

/* ── Header ── */
.cockpit-header {
    background: linear-gradient(135deg, #0f1629 0%, #141d35 50%, #0f1629 100%);
    border: 1px solid rgba(99,179,237,0.2);
    border-radius: 16px;
    padding: 20px 32px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 0 40px rgba(99,179,237,0.08), inset 0 1px 0 rgba(255,255,255,0.05);
}
.cockpit-title {
    font-size: 26px;
    font-weight: 700;
    background: linear-gradient(90deg, #63b3ed, #9f7aea, #63b3ed);
    background-size: 200%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
}
.cockpit-subtitle { font-size: 13px; color: #718096; margin-top: 4px; font-weight: 400; }
.status-pill {
    background: rgba(72,187,120,0.15);
    border: 1px solid rgba(72,187,120,0.4);
    color: #68d391;
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1px;
    animation: pulse-green 2s infinite;
}
@keyframes pulse-green {
    0%, 100% { box-shadow: 0 0 0 0 rgba(72,187,120,0.4); }
    50%       { box-shadow: 0 0 0 6px rgba(72,187,120,0); }
}

/* ── Cards ── */
.metric-card {
    background: linear-gradient(135deg, #0f1629 0%, #141d35 100%);
    border: 1px solid rgba(99,179,237,0.15);
    border-radius: 14px;
    padding: 20px;
    text-align: center;
    transition: all 0.3s ease;
    box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}
.metric-card:hover { border-color: rgba(99,179,237,0.4); transform: translateY(-2px); }
.metric-label { font-size: 11px; color: #718096; letter-spacing: 1.5px; text-transform: uppercase; font-weight: 600; margin-bottom: 8px; }
.metric-value { font-size: 32px; font-weight: 700; line-height: 1; }
.metric-unit  { font-size: 14px; color: #718096; margin-top: 4px; font-weight: 400; }

.card-cyan   { color: #63b3ed; }
.card-green  { color: #68d391; }
.card-red    { color: #fc8181; }
.card-purple { color: #b794f4; }
.card-orange { color: #f6ad55; }
.card-pink   { color: #f687b3; }

/* ── Command panel ── */
.command-panel {
    background: linear-gradient(135deg, #0f1629, #141d35);
    border: 1px solid rgba(99,179,237,0.15);
    border-radius: 14px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}
.transcript-box {
    background: rgba(0,0,0,0.4);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    padding: 14px 18px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    color: #e2e8f0;
    margin: 10px 0;
    min-height: 44px;
    word-wrap: break-word;
}
.response-box {
    background: rgba(99,179,237,0.08);
    border: 1px solid rgba(99,179,237,0.2);
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 14px;
    color: #bee3f8;
    margin: 10px 0;
    min-height: 44px;
    line-height: 1.6;
}
.section-label { font-size: 11px; letter-spacing: 1.5px; color: #718096; text-transform: uppercase; font-weight: 600; margin-bottom: 6px; }

/* ── Resolver badge ── */
.badge {
    display: inline-block;
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}
.badge-regex   { background: rgba(72,187,120,0.15); color: #68d391; border: 1px solid rgba(72,187,120,0.4); }
.badge-slm     { background: rgba(159,122,234,0.15); color: #b794f4; border: 1px solid rgba(159,122,234,0.4); }
.badge-rag     { background: rgba(246,173,85,0.15);  color: #f6ad55; border: 1px solid rgba(246,173,85,0.4); }
.badge-macro   { background: rgba(99,179,237,0.15);  color: #63b3ed; border: 1px solid rgba(99,179,237,0.4); }
.badge-context { background: rgba(246,135,179,0.15); color: #f687b3; border: 1px solid rgba(246,135,179,0.4); }
.badge-none    { background: rgba(113,128,150,0.15); color: #718096; border: 1px solid rgba(113,128,150,0.4); }

/* ── Confidence bar ── */
.conf-track {
    background: rgba(255,255,255,0.06);
    border-radius: 6px;
    height: 8px;
    width: 100%;
    margin-top: 8px;
    overflow: hidden;
}
.conf-fill {
    height: 100%;
    border-radius: 6px;
    transition: width 0.5s ease;
}

/* ── CAN message ── */
.can-box {
    background: rgba(0,0,0,0.5);
    border: 1px solid rgba(99,179,237,0.2);
    border-radius: 10px;
    padding: 12px 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: #63b3ed;
}

/* ── Analytics ── */
.analytics-card {
    background: linear-gradient(135deg, #0f1629, #141d35);
    border: 1px solid rgba(99,179,237,0.15);
    border-radius: 14px;
    padding: 24px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}

/* ── Toggle indicators ── */
.toggle-on  { color: #68d391; font-weight: 700; }
.toggle-off { color: #718096; font-weight: 400; }

/* ── Timestamp ── */
.timestamp { font-size: 11px; color: #4a5568; font-family: 'JetBrains Mono', monospace; }

/* ── Hide streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 24px !important; padding-bottom: 0 !important; }
</style>
""", unsafe_allow_html=True)


# ── Load state ────────────────────────────────────────────────────────────────
def load_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

state = load_state()
vs    = state.get("vehicle_state", {})
ana   = state.get("analytics", {})


# ── Helpers ───────────────────────────────────────────────────────────────────
def resolver_badge_html(resolver: str) -> str:
    r = (resolver or "none").lower()
    if "regex"   in r: return '<span class="badge badge-regex">⚡ Regex</span>'
    if "rag"     in r: return '<span class="badge badge-rag">📖 RAG</span>'
    if "llama"   in r or "slm" in r: return '<span class="badge badge-slm">🧠 SLM</span>'
    if "macro"   in r: return '<span class="badge badge-macro">🎯 Macro</span>'
    if "context" in r: return '<span class="badge badge-context">🔁 Context</span>'
    return '<span class="badge badge-none">— Idle</span>'

def conf_color(pct: int) -> str:
    if pct >= 85: return "#68d391"
    if pct >= 70: return "#f6ad55"
    return "#fc8181"

def gauge(value, min_val, max_val, title, unit, color, steps=None):
    steps = steps or [
        {"range": [min_val, (max_val - min_val) * 0.4 + min_val], "color": "rgba(255,255,255,0.03)"},
        {"range": [(max_val - min_val) * 0.4 + min_val, max_val], "color": "rgba(255,255,255,0.06)"},
    ]
    fig = go.Figure(go.Indicator(
        mode  = "gauge+number",
        value = value,
        number = {"suffix": unit, "font": {"size": 28, "color": "#e2e8f0", "family": "Inter"}},
        gauge = {
            "axis":  {"range": [min_val, max_val], "tickcolor": "#4a5568", "tickwidth": 1,
                      "tickfont": {"color": "#718096", "size": 10}},
            "bar":   {"color": color, "thickness": 0.25},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": steps,
            "threshold": {"line": {"color": color, "width": 2}, "thickness": 0.8, "value": value},
        },
        title = {"text": title, "font": {"size": 13, "color": "#718096", "family": "Inter"}},
        domain = {"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(
        paper_bgcolor = "rgba(0,0,0,0)",
        plot_bgcolor  = "rgba(0,0,0,0)",
        font_color    = "#e2e8f0",
        margin        = dict(t=60, b=10, l=20, r=20),
        height        = 200,
    )
    return fig


# ── Header ────────────────────────────────────────────────────────────────────
ts = state.get("timestamp", "—")
st.markdown(f"""
<div class="cockpit-header">
  <div>
    <div class="cockpit-title">🚗 Edge Auto Assistant</div>
    <div class="cockpit-subtitle">Offline AI Cockpit · Raspberry Pi 4 · Vosk + Llama 3.2 1B</div>
  </div>
  <div style="display:flex; align-items:center; gap:16px;">
    <span class="timestamp">Last update: {ts}</span>
    <span class="status-pill">● LIVE</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Row 1: Vehicle state gauges ───────────────────────────────────────────────
temp    = vs.get("ac_temperature",   22)
fan     = vs.get("fan_speed",         2)
sunroof = vs.get("sunroof_position",   0)
bright  = vs.get("brightness",        50)
ac_on   = vs.get("ac_enabled",     False)
hl_on   = vs.get("headlights",     False)

g1, g2, g3, g4 = st.columns(4)
with g1:
    st.plotly_chart(
        gauge(temp, 17, 29, "TEMPERATURE", "°C", "#63b3ed"),
        use_container_width=True, config={"displayModeBar": False}
    )
with g2:
    st.plotly_chart(
        gauge(fan, 1, 5, "FAN SPEED", "", "#9f7aea",
              steps=[{"range": [1, 3], "color": "rgba(255,255,255,0.03)"},
                     {"range": [3, 5], "color": "rgba(255,255,255,0.06)"}]),
        use_container_width=True, config={"displayModeBar": False}
    )
with g3:
    st.plotly_chart(
        gauge(sunroof, 0, 100, "SUNROOF", "%", "#f6ad55"),
        use_container_width=True, config={"displayModeBar": False}
    )
with g4:
    st.plotly_chart(
        gauge(bright, 0, 100, "BRIGHTNESS", "%", "#f687b3"),
        use_container_width=True, config={"displayModeBar": False}
    )

# ── Row 2: Toggle states ──────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    ac_class = "card-green" if ac_on else "card-red"
    ac_txt   = "ON" if ac_on else "OFF"
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">Air Conditioning</div>
      <div class="metric-value {ac_class}">{ac_txt}</div>
      <div class="metric-unit">{'❄️ Active' if ac_on else '○ Standby'}</div>
    </div>""", unsafe_allow_html=True)
with c2:
    hl_class = "card-orange" if hl_on else "card-red"
    hl_txt   = "ON" if hl_on else "OFF"
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">Headlights</div>
      <div class="metric-value {hl_class}">{hl_txt}</div>
      <div class="metric-unit">{'💡 Active' if hl_on else '○ Off'}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Row 3: Last Command Panel + Analytics ────────────────────────────────────
left, right = st.columns([3, 2])

with left:
    transcript = state.get("transcript", "—")
    response   = state.get("response",   "Waiting for command...")
    resolver   = state.get("resolver",   "none")
    latency    = state.get("latency",    "0ms")
    confidence = state.get("confidence", 0)
    command    = state.get("command",    "")
    value      = state.get("value",      "")
    conf_c     = conf_color(confidence)

    badge_html = resolver_badge_html(resolver)

    can_html = ""
    if command and command not in ("", "none", "STATUS_QUERY", "RAG_RESPONSE"):
        can_html = f"""
        <div class="section-label" style="margin-top:16px;">CAN Bus Message</div>
        <div class="can-box">
            <span style="color:#4a5568;">TX </span>
            <span style="color:#63b3ed;">{command}</span>
            <span style="color:#4a5568;"> → </span>
            <span style="color:#68d391; font-weight:600;">{value}</span>
        </div>"""

    st.markdown(f"""
    <div class="command-panel">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
        <div style="font-size:15px; font-weight:600; color:#e2e8f0;">Last Command</div>
        <div style="display:flex; align-items:center; gap:12px;">
          {badge_html}
          <span class="timestamp">⏱ {latency}</span>
        </div>
      </div>

      <div class="section-label">🎤 Heard</div>
      <div class="transcript-box">{transcript or '—'}</div>

      <div style="margin-top:4px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span class="section-label">STT Confidence</span>
          <span style="font-size:12px; color:{conf_c}; font-weight:600; font-family:'JetBrains Mono';">{confidence}%</span>
        </div>
        <div class="conf-track">
          <div class="conf-fill" style="width:{confidence}%; background: linear-gradient(90deg, {conf_c}, {conf_c}88);"></div>
        </div>
      </div>

      <div class="section-label" style="margin-top:16px;">💬 Assistant Response</div>
      <div class="response-box">{response or '—'}</div>

      {can_html}
    </div>
    """, unsafe_allow_html=True)

with right:
    total       = max(ana.get("total", 1), 1)
    regex_h     = ana.get("regex_hits",   0)
    context_h   = ana.get("context_hits", 0)
    rag_h       = ana.get("rag_hits",     0)
    slm_h       = ana.get("slm_hits",     0)
    macro_h     = ana.get("macro_hits",   0)
    failed_h    = ana.get("failed",       0) + ana.get("blocked", 0)
    lat_count   = ana.get("latency_count", 0)
    lat_sum     = ana.get("latency_sum",   0.0)
    avg_lat_ms  = (lat_sum / lat_count * 1000) if lat_count else 0

    labels = ["Regex ⚡", "Context 🔁", "RAG 📖", "SLM 🧠", "Macro 🎯", "Failed ✗"]
    values = [regex_h, context_h, rag_h, slm_h, macro_h, failed_h]
    colors = ["#68d391", "#f687b3", "#f6ad55", "#b794f4", "#63b3ed", "#fc8181"]

    fig_pie = go.Figure(go.Pie(
        labels    = labels,
        values    = values,
        hole      = 0.55,
        marker    = dict(colors=colors, line=dict(color="#070b14", width=3)),
        textfont  = dict(size=12, color="#e2e8f0"),
        hovertemplate = "<b>%{label}</b><br>%{value} commands<br>%{percent}<extra></extra>",
    ))
    fig_pie.update_layout(
        paper_bgcolor = "rgba(0,0,0,0)",
        plot_bgcolor  = "rgba(0,0,0,0)",
        font_color    = "#e2e8f0",
        margin        = dict(t=10, b=10, l=10, r=10),
        height        = 220,
        showlegend    = True,
        legend        = dict(
            font      = dict(size=11, color="#718096"),
            bgcolor   = "rgba(0,0,0,0)",
            x=1.0, y=0.5, xanchor="right",
        ),
        annotations   = [{
            "text": f"<b>{total}</b><br><span style='font-size:10px'>cmds</span>",
            "x": 0.5, "y": 0.5,
            "showarrow": False,
            "font": {"size": 16, "color": "#e2e8f0", "family": "Inter"},
        }],
    )

    st.markdown('<div class="analytics-card">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:15px; font-weight:600; color:#e2e8f0; margin-bottom:4px;">Session Analytics</div>', unsafe_allow_html=True)
    st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})

    # Stats row
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        st.markdown(f"""
        <div style="text-align:center;">
          <div class="section-label">Avg Latency</div>
          <div style="font-size:20px; font-weight:700; color:#63b3ed; font-family:'JetBrains Mono';">{avg_lat_ms:.0f}<span style="font-size:12px; color:#718096;">ms</span></div>
        </div>""", unsafe_allow_html=True)
    with sc2:
        regex_pct = int(regex_h / total * 100)
        st.markdown(f"""
        <div style="text-align:center;">
          <div class="section-label">Regex Rate</div>
          <div style="font-size:20px; font-weight:700; color:#68d391; font-family:'JetBrains Mono';">{regex_pct}<span style="font-size:12px; color:#718096;">%</span></div>
        </div>""", unsafe_allow_html=True)
    with sc3:
        st.markdown(f"""
        <div style="text-align:center;">
          <div class="section-label">Failed</div>
          <div style="font-size:20px; font-weight:700; color:#fc8181; font-family:'JetBrains Mono';">{failed_h}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding: 20px 0 8px; color: #2d3748; font-size:11px; letter-spacing:1px;">
  EDGE AUTO ASSISTANT · OFFLINE · RASPBERRY PI 4
</div>""", unsafe_allow_html=True)
