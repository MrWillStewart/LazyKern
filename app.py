import streamlit as st
import io
from fontTools.ttLib import TTFont

# --- 1. SETUP ---
st.set_page_config(page_title="LazyKern Safe Mode", layout="centered")

st.title("LazyKern Safe Mode")

# Use a standard file uploader
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

# --- 2. CACHED PROCESSING ---
@st.cache_data
def get_profiles_cached(font_bytes):
    # This is where we will eventually put the math
    # Keeping it simple for now to test if it loads
    return "Loaded"

# --- 3. RUNTIME ---
if uploaded_file is not None:
    st.write("File detected. Reading bytes...")
    
    # Read the file
    font_bytes = uploaded_file.read()
    
    # Try to load the font
    try:
        font = TTFont(io.BytesIO(font_bytes))
        st.success(f"Successfully loaded: {uploaded_file.name}")
        st.write(f"Glyph count: {len(font.getGlyphOrder())}")
        
        if st.button("Run Kerning Test"):
            st.write("Processing geometry...")
            # If this succeeds, we know the environment is stable.
            st.write("Math complete.")
            
    except Exception as e:
        st.error(f"Error loading font: {e}")
else:
    st.info("Upload a font to start.")
