import streamlit as st
import io
import time
import base64
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 1. TYPOGRAPHIC HEURISTIC ENGINE ---
def classify_glyph(font, name):
    """Determines if a glyph is effectively 'Straight' or 'Round'."""
    glyph = font.getGlyphSet()[name]
    width = glyph.width
    if width == 0: return "other"
    
    # Get bounding box
    bounds = glyph._getBounds(font.getGlyphSet())
    min_x, max_x = bounds[0], bounds[2]
    
    # Heuristic: If it hits the edges, it's a straight stem
    is_left_straight = min_x < (width * 0.15)
    is_right_straight = max_x > (width * 0.85)
    
    if is_left_straight and is_right_straight: return "straight_both"
    if is_left_straight: return "straight_left"
    if is_right_straight: return "straight_right"
    return "round"

def generate_kerning_rules(font, target_gap):
    glyph_order = font.getGlyphOrder()
    # Pre-classify all glyphs
    classes = {name: classify_glyph(font, name) for name in glyph_order if name not in {'.notdef', 'space'}}
    
    kern_pairs = {}
    
    # Apply standard Type Design Rules
    for left in classes:
        for right in classes:
            # Rule Table
            l_type = classes[left]
            r_type = classes[right]
            
            # Default gap
            adjustment = 0
            
            # The Jigsaw Logic (Typographic standard)
            if l_type == "straight_right" and r_type == "straight_left":
                adjustment = -20  # Tightest (e.g., H-H, H-N)
            elif l_type == "straight_right" or r_type == "straight_left":
                adjustment = -10  # Tight (e.g., H-O)
            elif l_type == "round" and r_type == "round":
                adjustment = 10   # Loose (e.g., O-O)
            
            if adjustment != 0:
                kern_pairs[(left, right)] = adjustment
                
    return kern_pairs

# --- 2. STREAMLIT UI ---
st.set_page_config(page_title="LazyKern Pro", layout="wide")
st.title("LazyKern: Metrics-Based Kerning")
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    font = TTFont(io.BytesIO(uploaded_file.read()))
    gap = st.slider("Kerning Strength", -50, 50, 0, 5)
    
    if st.button("Apply Typographic Rules"):
        with st.spinner("Applying expert rules..."):
            kern_pairs = generate_kerning_rules(font, gap)
            
            # Apply to font
            fea = ["feature kern {"] + [f"    pos {l} {r} {v + gap};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
        
        out = io.BytesIO()
        font.save(out)
        font_data = out.getvalue()
        
        # Unique ID for cache busting
        unique_id = int(time.time())
        b64 = base64.b64encode(font_data).decode('utf-8')
        
        st.success(f"Applied {len(kern_pairs)} automated rules.")
        
        st.markdown(f"""
        <style>
        @font-face {{ font-family: 'LiveFont_{unique_id}'; src: url('data:font/ttf;charset=utf-8;base64,{b64}'); }}
        .tester {{ font-family: 'LiveFont_{unique_id}', sans-serif; font-size: 64px; width: 100%; border: 2px solid #ccc; padding: 20px; border-radius: 8px; }}
        </style>
        <textarea class="tester">HNHI OCO OHO</textarea>
        """, unsafe_allow_html=True)
        
        st.download_button("Download Kerned Font", font_data, f"kerned_{uploaded_file.name}")
