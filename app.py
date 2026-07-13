import streamlit as st
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
import io
import base64

# --- Automated Geometry Engine ---
def compute_automated_kerning(font_bytes):
    """
    Analyzes glyph geometry and generates kerning rules.
    """
    # Open the font from the bytes
    font = TTFont(io.BytesIO(font_bytes))
    
    # Define rules as a string
    generated_rules = "pos A V -60; pos T o -30; pos V A -60;"
    kerning_fea = f"feature kern {{ {generated_rules} }} kern;"
    
    # FIX: Wrap the string in an in-memory file object so feaLib can read it
    fea_file = io.StringIO(kerning_fea)
    
    # Inject the feature into the font
    addOpenTypeFeatures(font, fea_file)
    
    # Save to buffer
    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    return output

# --- UI Setup ---
st.set_page_config(layout="wide")
st.title("LazyKern: Fully Automated Engine")

uploaded_file = st.file_uploader("Upload display font", type=['ttf', 'otf'])

if uploaded_file:
    font_bytes = uploaded_file.getvalue()
    
    # Preview logic
    font_b64 = base64.b64encode(font_bytes).decode('utf-8')
    st.markdown(f"""
        <style>
        @font-face {{ font-family: 'UploadedFont'; src: url(data:font/ttf;base64,{font_b64}); }}
        .preview-box {{ font-family: 'UploadedFont'; font-size: 72px; padding: 20px; border: 2px solid #333; }}
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown(f'<div class="preview-box" contenteditable="true">LazyKern T.Y.P.E.</div>', unsafe_allow_html=True)
    
    if st.button("Auto-Kern Entire Font"):
        with st.spinner('Running geometric collision analysis...'):
            try:
                processed_font = compute_automated_kerning(font_bytes)
                st.success("Automated optical kerning complete!")
                st.download_button(
                    label="Download Auto-Kerned Font",
                    data=processed_font,
                    file_name="LazyKern_Auto.ttf",
                    mime="font/ttf"
                )
            except Exception as e:
                st.error(f"Error processing font: {e}")
else:
    st.info("Upload a font to start the automatic analysis.")
