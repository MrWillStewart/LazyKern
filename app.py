import streamlit as st
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
import io
import base64

# --- Kerning Engine ---
def apply_kerning_to_font(font_bytes, pair, adjustment):
    """Bakes the kerning pair into the font's GPOS table."""
    font = TTFont(io.BytesIO(font_bytes))
    
    # Define the OpenType Feature rule
    kerning_fea = f"""
    feature kern {{
        pos {pair[0]} {pair[1]} {adjustment};
    }} kern;
    """
    
    # Inject the feature into the font
    addOpenTypeFeatures(font, kerning_fea)
    
    # Save to buffer
    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    return output

# --- UI Setup ---
st.set_page_config(layout="wide")
st.title("LazyKern: Professional Font Engineering")

uploaded_file = st.file_uploader("Upload your font (.ttf/.otf)", type=['ttf', 'otf'])

if uploaded_file:
    font_bytes = uploaded_file.getvalue()
    
    # 1. Preview Rendering
    font_b64 = base64.b64encode(font_bytes).decode('utf-8')
    st.markdown(f"""
        <style>
        @font-face {{ font-family: 'UploadedFont'; src: url(data:font/ttf;base64,{font_b64}); }}
        .preview-box {{ font-family: 'UploadedFont'; font-size: 72px; padding: 20px; border: 2px solid #333; }}
        </style>
    """, unsafe_allow_html=True)
    
    preview_text = st.text_input("Preview Text:", value="LazyKern T.Y.P.E.")
    st.markdown(f'<div class="preview-box" contenteditable="true">{preview_text}</div>', unsafe_allow_html=True)
    
    # 2. Kerning Controls
    st.subheader("Manual Kerning Injection")
    col1, col2 = st.columns(2)
    kern_pair = col1.text_input("Target Pair (e.g., AV):", value="AV")
    kern_val = col2.number_input("Adjustment (Units):", value=-50)
    
    if st.button("Apply Kerning & Bake into File"):
        with st.spinner('Compiling GPOS table...'):
            # Convert string input to pair tuple
            if len(kern_pair) == 2:
                pair = (kern_pair[0], kern_pair[1])
                processed_font = apply_kerning_to_font(font_bytes, pair, kern_val)
                
                st.success("Kerning baked into font binary!")
                st.download_button(
                    label="Download Kerned Font",
                    data=processed_font,
                    file_name="LazyKern_Baked.ttf",
                    mime="font/ttf"
                )
            else:
                st.error("Please enter exactly two characters for the pair.")
else:
    st.info("Upload a font to initialize the engine.")
