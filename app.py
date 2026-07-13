import streamlit as st
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools.pens.boundsPen import BoundsPen
import io
import base64

# --- Geometry Engine ---
def get_glyph_bounds(font, glyph_name):
    """Calculates the bounding box of a glyph to estimate its width."""
    glyph_set = font.getGlyphSet()
    if glyph_name not in glyph_set: return None
    pen = BoundsPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    return pen.bounds # (xmin, ymin, xmax, ymax)

def compute_kerning_value(font, g1, g2):
    """Calculates a kerning offset based on the bounding box overlap."""
    b1 = get_glyph_bounds(font, g1)
    b2 = get_glyph_bounds(font, g2)
    if not b1 or not b2: return 0
    
    # Logic: The gap is the distance between the Right-side of G1 and Left-side of G2
    # We calculate the 'tightness' based on the average width of the characters
    width1 = b1[2] - b1[0]
    width2 = b2[2] - b2[0]
    current_gap = b2[0] - b1[2]
    
    # We want to pull them together if the gap is too large
    # This is the "Automated Optical Logic"
    return int(-(current_gap * 0.5))

# --- Engine Core ---
def compute_automated_kerning(font_bytes):
    font = TTFont(io.BytesIO(font_bytes))
    cmap = font.getBestCmap()
    
    # 1. Select pairs to kern
    pairs = [('A', 'V'), ('T', 'o'), ('V', 'A'), ('P', 'o'), ('T', 'a')]
    
    rules = []
    for char1, char2 in pairs:
        g1, g2 = cmap.get(ord(char1)), cmap.get(ord(char2))
        if g1 and g2:
            adjustment = compute_kerning_value(font, g1, g2)
            rules.append(f"pos {g1} {g2} {adjustment};")
    
    # 2. Inject features
    kerning_fea = f"feature kern {{ {' '.join(rules)} }} kern;"
    addOpenTypeFeatures(font, io.StringIO(kerning_fea))
    
    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    return output

# --- UI Setup ---
st.title("LazyKern: Geometry Engine v2")
uploaded_file = st.file_uploader("Upload display font", type=['ttf', 'otf'])

if uploaded_file:
    if st.button("Generate Optical Kerning"):
        processed_font = compute_automated_kerning(uploaded_file.getvalue())
        st.download_button("Download Baked Font", processed_font, "LazyKern_Baked.ttf")
