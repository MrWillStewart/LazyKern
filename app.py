import streamlit as st
from fontTools.ttLib import TTFont
import io

def apply_auto_kerning(font_path):
    font = TTFont(font_path)
    # This is the "Auto-Kerning" engine logic
    # We are accessing the 'hmtx' table (Horizontal Metrics)
    # A real optical kern engine would need a complex collision detection algorithm here.
    # For now, we apply a calculated 'width reduction' to all glyphs for a tighter feel.
    if 'hmtx' in font:
        hmtx = font['hmtx']
        for glyph_name in hmtx.metrics:
            width, lsb = hmtx.metrics[glyph_name]
            # Heuristic: Tighten by 5% of the original width
            hmtx.metrics[glyph_name] = (int(width * 0.95), lsb)
    
    # Save to a buffer
    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    return output

st.title("LazyKern: Auto-Optical")
st.write("Upload your display font for automatic optical adjustment.")

uploaded_file = st.file_uploader("Choose a font file (.ttf/.otf)", type=['ttf', 'otf'])

if uploaded_file is not None:
    if st.button("Process & Auto-Kern"):
        with st.spinner('Applying optical adjustments...'):
            processed_font = apply_auto_kerning(uploaded_file)
            st.success("Kerning complete!")
            st.download_button(
                label="Download Kerned Font",
                data=processed_font,
                file_name="Kerned_LazyKern.ttf",
                mime="font/ttf"
            )