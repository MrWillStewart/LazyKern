import streamlit as st
from fontTools.ttLib import TTFont
import io
import base64

# --- Geometry Engine ---
def apply_metrics_kerning(font_bytes, adjustment_value):
    """
    Directly modifies the horizontal metrics (advanceWidth) of the font.
    This is 'baked-in' and will be visible in the browser preview.
    """
    font = TTFont(io.BytesIO(font_bytes))
    
    # Modify the 'hmtx' table (the source of truth for glyph spacing)
    if 'hmtx' in font:
        hmtx = font['hmtx']
        for glyph_name in hmtx.metrics:
            width, lsb = hmtx.metrics[glyph_name]
            # Apply the adjustment to the advanceWidth
            hmtx.metrics[glyph_name] = (int(width + adjustment_value), lsb)
            
    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    return output.getvalue()

# --- UI Setup ---
st.set_page_config(layout="wide")
st.title("LazyKern: Live Browser-Kerned Preview")

uploaded_file = st.file_uploader("Upload display font", type=['ttf', 'otf'])

if uploaded_file:
    font_bytes = uploaded_file.getvalue()
    
    # User adjustment control
    adjustment = st.slider("Adjust Spacing (Units):", -200, 200, 0)
    
    # Apply logic
    kerned_font_bytes = apply_metrics_kerning(font_bytes, adjustment)
    
    # Encode for Browser Preview
    font_b64 = base64.b64encode(kerned_font_bytes).decode('utf-8')
    
    st.markdown(f"""
        <style>
        @font-face {{ font-family: 'KernedFont'; src: url(data:font/ttf;base64,{font_b64}); }}
        .preview-box {{ font-family: 'KernedFont'; font-size: 80px; padding: 30px; border: 3px solid #000; }}
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="preview-box" contenteditable="true">LazyKern T.Y.P.E.</div>', unsafe_allow_html=True)
    
    st.download_button("Download Kerned Font", kerned_font_bytes, "LazyKern_Visible.ttf")
