import streamlit as st
from database import authenticate
from pathlib import Path

st.set_page_config(page_title="AI Mood Dashboard", layout="centered")

def login_screen():
    st.title("🔒 Secure Login")
    st.markdown("Please enter your password to access your dashboard.")
    pw = st.text_input("Password", type="password")
    login_btn = st.button("Login", type="primary")
    login_fail = False
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if login_btn and pw:
        if authenticate(pw):
            st.session_state.authenticated = True
            st.success("Successfully logged in!")
        else:
            login_fail = True
            st.session_state.authenticated = False

    if login_fail:
        st.error("Login failed. Please try again.")

def main_dashboard():
    st.title("Welcome to Your Mood Dashboard! 🌈")

    # --- File Uploader ---
    st.header("Upload a File")
    uploaded_file = st.file_uploader(
        "Upload Image, PDF, or TXT",
        type=["png", "jpg", "jpeg", "pdf", "txt"]
    )
    if uploaded_file:
        file_details = {
            "filename": uploaded_file.name,
            "size": uploaded_file.size,
            "type": uploaded_file.type,
        }
        st.write("File uploaded:", file_details)
        file_ext = Path(uploaded_file.name).suffix.lower()
        if file_ext in [".png", ".jpg", ".jpeg"]:
            st.image(uploaded_file, caption=uploaded_file.name)
        elif file_ext == ".txt":
            file_content = uploaded_file.read().decode("utf-8")
            st.text_area("Text File Content", file_content, height=200)
        elif file_ext == ".pdf":
            st.info("PDF file uploaded. (Rendering/viewing requires extra logic.)")

    # --- Feelings Log ---
    st.header("Log Your Feelings & Thoughts")
    thoughts = st.text_area("How are you feeling today?", height=150)
    if st.button("Save Log"):
        if thoughts.strip():
            if "logs" not in st.session_state:
                st.session_state.logs = []
            st.session_state.logs.append(thoughts)
            st.success("Your feelings and thoughts were logged! 🙏")
        else:
            st.warning("Please write something before saving.")

    if "logs" in st.session_state and st.session_state.logs:
        st.markdown("### Past Entries")
        for idx, log in enumerate(reversed(st.session_state.logs), 1):
            st.markdown(f"**Entry {idx}:** {log}")

# ---- Main Render Logic ----
if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    login_screen()
else:
    main_dashboard()