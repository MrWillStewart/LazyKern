import streamlit as st
import os
import io
import math
import base64  # Needed to inject the font binary into HTML/CSS
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

class ProfilePen(BasePen):
    """Traces glyph vector paths and collects raw coordinates along the contours."""
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []

    def _moveTo(self, p): self.points.append(p)
    def _lineTo(self, p): self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        for i in range(1, 6):
            t = i / 5.0
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        for i in range(1, 4):
            t = i / 3.0
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font, step_size=10):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for glyph_name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        glyph = glyph_set[glyph_name]
        glyph.draw(pen)
        if not pen.points: continue
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            if y_slice not in slices: slices[y_slice] = []
            slices[y_slice].append(x)
        left_profile, right_profile = {}, {}
        for y_slice, x_vals in slices.items():
            left_profile[y_slice] = min(x_vals)
            right_profile[y_slice] = max(x_vals)
        profiles[glyph_name] = {"left": left_profile, "right": right_profile, "advance": glyph.width}
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=40, max_adjustment=150):
    kerning_table = {}
    for left_glyph, right_glyph in pairs_to_kern:
        if left_glyph not in profiles or right_glyph not in profiles: continue
        prof_a, prof_b = profiles[left_glyph], profiles[right_glyph]
        common_ys = set(prof_a["right"].keys()).intersection(set(prof_b["left"].keys()))
        if not common_ys: continue
        min_distance = float('inf')
        for y in common_ys:
            edge_a = prof_a["right"][y]
            edge_b = prof_b["left"][y] + prof_a["advance"] 
            distance = edge_b - edge_a
            if distance < min_distance: min_distance = distance
        kern_value = int(target_gap - min_distance)
        if abs(kern_value) > 2 and abs(kern_value) < max_adjustment:
            kerning_table[(left_glyph, right_glyph)] = int(round(kern_value / 5.0) * 5)
    return kerning_table

# --- STREAMLIT UI ---
st.set_page_config(page_title="Autokern Engine", page_icon="✒️", layout="wide")

st.title("✒️ The Interactive Font Autokerner")
st.write("Upload your unkerned file. Tweak parameters in the sidebar to see structural adjustments update in **real-time**.")

# Sidebar Controls
st.sidebar.header("🛞 Engine Calibration")
target_gap = st.sidebar.slider("Target Optical Gap", min_value=10, max_value=120, value=50, step=5)
precision = st.sidebar.slider("Scanner Precision Slices", min_value=2, max_value=25, value=10, step=1)

uploaded_file = st.file_uploader("Drop your unkerned .otf or .ttf file here", type=["otf", "ttf"])

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name
    base_name, ext = os.path.splitext(filename)
    
    # Run the engine automatically on change (no calculation button required anymore!)
    try:
        font = TTFont(io.BytesIO(file_bytes))
        profiles = get_glyph_profiles(font, step_size=precision)
        glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
        pairs_to_test = [(a, b) for a in glyphs for b in glyphs]
        
        kern_pairs = calculate_kerning(profiles, pairs_to_test, target_gap=target_gap)
        
        if kern_pairs:
            fea_lines = ["feature kern {"]
            for (left, right), val in kern_pairs.items():
                fea_lines.append(f"    pos {left} {right} {val};")
            fea_lines.append("} kern;")
            addOpenTypeFeaturesFromString(font, "\n".join(fea_lines))
        
        # Save output font into memory
        output_buffer = io.BytesIO()
        font.save(output_buffer)
        font_data = output_buffer.getvalue()
        
        # Convert compiled font data into Base64 for CSS Injection
        b64_font = base64.b64encode(font_data).decode()
        font_mime = "font/otf" if ext.lower() == ".otf" else "font/ttf"
        
        # Inject custom styles dynamically pointing directly to our in-memory string
        st.markdown(f"""
            <style>
            @font-face {{
                font-family: 'LiveAutokernFont';
                src: url(data:{font_mime};base64,{b64_font}) format('opentype');
            }}
            .font-preview {{
                font-family: 'LiveAutokernFont' !important;
                font-size: 42px !important;
                line-height: 1.3 !important;
                padding: 15px;
                background-color: #111111;
                color: #ffffff;
                border-radius: 8px;
                margin-bottom: 10px;
                white-space: pre;
            }}
            </style>
        """, unsafe_allow_html=True)
        
        # --- UI PANELS ---
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("📦 Export Status")
            st.success(f"Active Pairs: {len(kern_pairs)}")
            st.download_button(
                label="📥 Download This Build",
                data=output_buffer.getvalue(),
                file_name=f"{base_name}-Autokerned{ext}",
                mime=font_mime,
                use_container_width=True
            )
            
            st.subheader("📝 Custom Type Sandbox")
            user_test_input = st.text_input("Type anything here to check specific pairs:", "TypeVoLT")

        with col2:
            st.subheader("🔍 Typography Spacing Proofs")
            
            # Interactive Sandbox Output
            if user_test_input:
                st.markdown(f'<div class="font-preview">{user_test_input}</div>', unsafe_allow_html=True)
            
            # Classical Typography Kerning Test Sentences/Words
            st.caption("Standard Optical Proof (Hamburgevons)")
            st.markdown('<div class="font-preview">Hamburgevons</div>', unsafe_allow_html=True)
            
            st.caption("Diagonal & Capital Collision Pairs (AV, LT, Ye, To)")
            st.markdown('<div class="font-preview">AVALANCHE LATITUDE Yesterday Total</div>', unsafe_allow_html=True)
            
            st.caption("Straight-to-Round Controls (NN OO NO ON)")
            st.markdown('<div class="font-preview">NNNN OOOO NOON ONON</div>', unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Engine compilation error: {e}")        profiles[glyph_name] = {
            "left": left_profile,
            "right": right_profile,
            "advance": glyph.width
        }
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=40, max_adjustment=150):
    """Compares side-profiles of letter pairs to solve for perfect optical clearance."""
    kerning_table = {}
    
    for left_glyph, right_glyph in pairs_to_kern:
        if left_glyph not in profiles or right_glyph not in profiles:
            continue
            
        prof_a = profiles[left_glyph]
        prof_b = profiles[right_glyph]
        
        # Find overlapping heights where the letters actually face each other
        common_ys = set(prof_a["right"].keys()).intersection(set(prof_b["left"].keys()))
        if not common_ys:
            continue
            
        min_distance = float('inf')
        
        # Measure the raw distance at every height level
        for y in common_ys:
            edge_a = prof_a["right"][y]
            edge_b = prof_b["left"][y] + prof_a["advance"] 
            
            distance = edge_b - edge_a
            if distance < min_distance:
                min_distance = distance
                
        # Calculate the required structural shift
        kern_value = int(target_gap - min_distance)
        
        # Sanity check: Don't apply absurd values or tiny unnoticeable adjustments
        if abs(kern_value) > 2 and abs(kern_value) < max_adjustment:
            # Round off to the nearest 5 units for cleaner design tables
            kerning_table[(left_glyph, right_glyph)] = int(round(kern_value / 5.0) * 5)
            
    return kerning_table

def main():
    # --- CONFIGURATION ---
    input_font_path = "MyFont-Unkerned.otf"  # <-- Make sure this matches your file name!
    output_font_path = "MyFont-Autokerned.otf"
    TARGET_GAP = 50  # The optical clearance target (higher = looser spacing)
    
    if not os.path.exists(input_font_path):
        print(f"Error: Could not find '{input_font_path}' in this folder.")
        return

    print("Reading font vector data...")
    font = TTFont(input_font_path)
    
    print("Tracing geometry profiles...")
    profiles = get_glyph_profiles(font, step_size=10)
    
    # Generate the checklist combination lists from your glyph inventory
    glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
    pairs_to_test = [(a, b) for a in glyphs for b in glyphs]
    
    print(f"Evaluating {len(pairs_to_test)} structural combinations...")
    kern_pairs = calculate_kerning(profiles, pairs_to_test, target_gap=TARGET_GAP)
    
    if kern_pairs:
        print(f"Generating OpenType feature syntax for {len(kern_pairs)} pairs...")
        
        # Build standard Adobe Feature file text dynamically
        fea_lines = ["feature kern {"]
        for (left, right), val in kern_pairs.items():
            fea_lines.append(f"    pos {left} {right} {val};")
        fea_lines.append("} kern;")
        fea_text = "\n".join(fea_lines)
        
        print("Compiling GPOS table via feaLib...")
        # Compile the feature string directly into the font structure
        addOpenTypeFeaturesFromString(font, fea_text)
        
        font.save(output_font_path)
        print(f"Success! Saved fully compiled file to: '{output_font_path}'")
    else:
        print("No kerning adjustments were necessary for this configuration layout.")

if __name__ == "__main__":
    main()
