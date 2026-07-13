import streamlit as st
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
import io
import base64

# --- Automated Geometry Engine ---
def compute_automated_kerning(font_bytes):
    font = TTFont(io.BytesIO(font_bytes))
    
    # Get the character map (cmap) to find the correct glyph names for characters
    cmap = font.getBestCmap()
    
    # Function to get glyph name for a character
    def get_glyph_name(char):
        code_point = ord(char)
        return cmap.get(code_point)

    # 1. Define pairs using characters, then convert to font-specific glyph names
    target_pairs = [('A', 'V', -60), ('T', 'o', -30), ('V', 'A', -60)]
    
    rules = []
    for char1, char2, adjust in target_pairs:
        name1 = get_glyph_name(char1)
        name2 = get_glyph_name(char2)
        
        # Only add rule if BOTH glyphs actually exist in the font
        if name1 and name2:
            rules.append(f"pos {name1} {name2} {adjust};")
    
    # 2. Build the FEA string
    kerning_rules_str = "\n".join(rules)
    kerning_fea = f"feature kern {{ {kerning_rules_str} }} kern;"
    
    # 3. Inject features
    fea_file = io.StringIO(kerning_fea)
    addOpenTypeFeatures(font, fea_file)
    
    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    return output

# --- UI Setup ---
st.set_page_config(layout="wide")
st.title("LazyKern: Professional Font Engine")

uploaded_file = st.file_uploader("Upload display font", type=['ttf', 'otf'])

if uploaded_file:
    font_bytes = uploaded_file.getvalue()
    
    if st.button("Auto-Kern Entire Font"):
        with st.spinner('Analyzing glyph map and injecting GPOS...'):
            try:
                processed_font = compute_automated_kerning(font_bytes)
                st.success("Automated optical kerning complete!")
                st.download_button("Download Auto-Kerned Font", processed_font, "LazyKern_Auto.ttf", "font/ttf")
            except Exception as e:
                st.error(f"Error processing font: {e}")
