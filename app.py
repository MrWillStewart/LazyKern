import streamlit as st
import io
import time
import base64
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.boundsPen import BoundsPen # Added this to fix the error

# --- 1. TYPOGRAPHIC HEURISTIC ENGINE ---
def classify_glyph(font, glyph_set, name):
    """Accurately determines if a glyph is 'Straight' or 'Round'."""
    glyph = glyph_set[name]
    width = glyph.width
    if width == 0: return "other"
    
    # Use BoundsPen to safely calculate bounding box
    bp = BoundsPen(glyph_set)
    glyph.draw(bp)
    
    # If the pen didn't find any bounds (empty glyph), return early
    if not bp.bounds: return "other"
    
    min_x, _, max_x, _ = bp.bounds
    
    # Heuristic: If it hits the edges, it's a straight stem
    is_left_straight = min_x < (width * 0.15)
    is_right_straight = max_x > (width * 0.85)
    
    if is_left_straight and is_right_straight: return "straight_both"
    if is_left_straight: return "straight_left"
    if is_right_straight: return "straight_right"
    return "round"

def generate_kerning_rules(font, gap_strength):
    glyph_set = font.getGlyphSet()
    glyph_order = font.getGlyphOrder()
    
    # Pre-classify all glyphs
    classes = {name: classify_glyph(font, glyph_set, name) for name in glyph_order if name not in {'.notdef', 'space'}}
    
    kern_pairs = {}
    
    # Apply standard Type Design Rules
    for left in classes:
        for right in classes:
            l_type = classes[left]
            r_type = classes[right]
            
            # Base logic: Straight-Straight (H-H) needs tighter kerning
            # Round-Round (O-O) needs looser kerning to avoid collision
            adjustment = 0
            
            if l_type == "straight_right" and r_type == "straight_left":
                adjustment = -20
            elif l_type == "straight_right" or r_type == "straight_left":
                adjustment = -10
            elif l_type == "round" and r_type == "round":
                adjustment = 10
            
            # Factor in the user's "Kerning Strength" slider
            final_val = adjustment + gap_strength
            
            if final_val != 0:
                kern_pairs[(left, right)] = int(final_val)
                
    return kern_pairs

# --- 2. STREAMLIT UI ---
st.set_page_config(page_title="LazyKern Pro", layout="wide")
st.title("LazyKern: Metrics-Based Kerning")
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    font = TTFont(io.BytesIO(uploaded_file.read()))
    strength = st.slider("Kerning Strength (Adjust tightness)", -50, 50, 0, 5)
    
    if st.button("Apply Typographic Rules"):
        with st.spinner("Analyzing metrics..."):
            kern_pairs = generate_kerning_rules(font, strength)
            
            # Apply to font
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
        
        out = io.BytesIO()
        font.save(out)
        font_data = out.getvalue()
        
        unique_id = int(time.time())
        b64 = base64.b64encode(font_data).decode('utf-8')
        
        st.success(f"Applied {len(kern_pairs)} automated rules.")
        
        st.markdown(f"""
        <style>
        @font-face {{ font-family: 'LiveFont_{unique_id}'; src: url('data:font/ttf;charset=utf-8;base64,{b64}'); }}
        .tester {{ font-family: 'LiveFont_{unique_id}', sans-serif; font-size: 64px; width: 100%; border: 2px solid #ccc; padding: 20px; border-radius: 8px; background: white; color: black; }}
        </style>
        <textarea class="tester">HNHI OCO OHO</textarea>
        """, unsafe_allow_html=True)
        
        st.download_button("Download Kerned Font", font_data, f"kerned_{uploaded_file.name}")
