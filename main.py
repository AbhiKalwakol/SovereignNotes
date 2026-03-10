import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import requests

st.set_page_config(page_title="Mood Tracker", layout="centered")

# --- Custom CSS for styling ---
st.markdown("""
<style>
.small-header {
    text-align: center;
    color: #888;
    font-size: 14px;
    font-weight: 600;
    margin-bottom: -10px;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.main-title {
    text-align: center;
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 30px;
    color: #222;
}
div.stButton > button {
    height: 100px;
    border-radius: 15px;
    font-weight: bold;
    border: 2px solid #eee;
    white-space: pre-wrap; /* Allows the emoji and text to stack */
}
div.stButton > button:hover {
    border-color: #aaa;
}
</style>
""", unsafe_allow_html=True)

# --- State Management ---
if "mood_history" not in st.session_state:
    st.session_state.mood_history = [
        {"day": "MON", "mood_score": 3, "mood": "OKAY"},
        {"day": "TUE", "mood_score": 4, "mood": "GOOD"},
        {"day": "WED", "mood_score": 1, "mood": "AWFUL"},
        {"day": "THU", "mood_score": 2, "mood": "BAD"},
        {"day": "FRI", "mood_score": None, "mood": None},
        {"day": "SAT", "mood_score": 5, "mood": "GREAT"},
        {"day": "SUN", "mood_score": None, "mood": None} 
    ]

def record_mood(mood_name, score):
    # Update Local App State for "SUN" (Simulated Today)
    for entry in st.session_state.mood_history:
        if entry["day"] == "SUN":
            entry["mood_score"] = score
            entry["mood"] = mood_name
            break

    # streamlit.toast() is only available in newer versions of Streamlit.
    # Fall back to a standard message for older versions.
    if hasattr(st, "toast"):
        st.toast(f"Mood '{mood_name}' recorded successfully!")
    else:
        st.success(f"Mood '{mood_name}' recorded successfully!")

# --- Header Section ---
st.markdown('<p class="small-header">4th Check-in</p>', unsafe_allow_html=True)
st.markdown('<p class="main-title">How are you today?</p>', unsafe_allow_html=True)

# --- Mood Buttons ---
col1, col2, col3, col4, col5 = st.columns(5)

# Note: \n is used to put the emoji above the text
with col1:
    if st.button("😣\nAWFUL", use_container_width=True):
        record_mood("AWFUL", 1)
with col2:
    if st.button("🙁\nBAD", use_container_width=True):
        record_mood("BAD", 2)
with col3:
    if st.button("😐\nOKAY", use_container_width=True):
        record_mood("OKAY", 3)
with col4:
    if st.button("🙂\nGOOD", use_container_width=True):
        record_mood("GOOD", 4)
with col5:
    if st.button("😄\nGREAT", use_container_width=True):
        record_mood("GREAT", 5)

st.markdown("---")

# --- Mood Analysis Section ---
st.subheader("Mood Analysis")
st.write("**This week**")



df = pd.DataFrame(st.session_state.mood_history)
df_valid = df.dropna(subset=['mood_score'])

if not df_valid.empty:
    fig = go.Figure()

    # Add a smooth line (Spline)
    fig.add_trace(go.Scatter(
        x=df_valid['day'], 
        y=df_valid['mood_score'],
        # Spline makes the curve smooth rather than jagged
        mode='lines',
        line=dict(shape='spline', width=4, color='#A0D4C2'), 
        hoverinfo='skip'
    ))

    # Add colored markers
    colors_map = {1: '#5C73F2', 2: '#56B0D8', 3: '#F2C94C', 4: '#8BC34A', 5: '#4CAF50'}
    marker_colors = [colors_map[score] for score in df_valid['mood_score']]

    fig.add_trace(go.Scatter(
        x=df_valid['day'],
        y=df_valid['mood_score'],
        mode='markers',
        marker=dict(size=18, color=marker_colors, line=dict(width=0)),
        name='Mood'
    ))

    fig.update_layout(
        xaxis=dict(
            showgrid=False,
            categoryorder='array',
            categoryarray=['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'],
            fixedrange=True
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#EAEAEA',
            zeroline=False,
            showticklabels=False,
            range=[0.5, 5.5],
            fixedrange=True
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        showlegend=False,
        margin=dict(l=10, r=10, t=20, b=20),
        height=250,
        hovermode="x"
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
else:
    st.info("No mood data recorded yet this week.")

st.markdown("---")

# --- Dev Info ---
with st.expander("🔌 Data Integration Info"):
    st.code(json.dumps(st.session_state.mood_history, indent=2), language="json")