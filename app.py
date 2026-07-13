import streamlit as st
import os
import io
import math
import base64
import pandas as pd
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

class ProfilePen(BasePen):
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
        profiles[glyph_name] = {
            "left": left_profile, 
            "right": right_profile, 
            "advance": glyph.width,
            "nodes_count": len(pen.points)
        }
    return profiles

def analyze_character_set(font):
    cmap = font.getBestCmap()
    if not cmap: return {"type": "Unknown", "caps": 0, "lower": 0, "digits": 0, "punct": 0}
    caps, lower, digits, punct = 0, 0, 0, 0
    for char_code in cmap.keys():
        try:
            char = chr(char_code)
            if char.isupper(): caps += 1
            elif char.islower(): lower += 1
            elif char.isdigit(): digits += 1
            elif not char.isspace(): punct += 1
        except: continue
    if caps > 0 and lower == 0: font_type = "All-Caps Display Face"
    elif lower > 0 and caps == 0: font_type = "Lowercase-Only Quirky Face"
    elif caps > 0 and lower > 0: font_type = "Standard Full Alphanumeric"
    else: font_type = "Custom Specialty / Novelty Glyphs"
    return {"type": font_type, "caps": caps, "lower": lower, "digits": digits, "punct": punct}

def generate_intelligence_report(font, profiles):
    """Performs deep analysis of structural geometry to recommend kerning baselines."""
    upm = font['head'].unitsPerEm if 'head' in font else 1000
    
    # Calculate averages
    total_width = sum(p['advance'] for p in profiles.values())
    avg_width = total_width / len(profiles) if profiles else 500
    total_nodes = sum(p['nodes_count'] for p in profiles.values())
    avg_nodes = total_nodes / len(profiles) if profiles else 10
    
    width_ratio = avg_width / upm
    
    # 1. Evaluate Width Characteristics
    if width_ratio < 0.45:
        width_style = "Highly Condensed / Narrow"
        rec_gap = 35
    elif width_ratio > 0.68:
        width_style = "Expanded / Wide Extended"
        rec_gap = 65
    else:
        width_style = "Regular Proportion"
        rec_gap = 50
        
    # 2. Evaluate Vector Complexity
    if avg_nodes > 35:
        complexity_style = "Organic / Complex (High Node Count)"
        rec_buffer = 35
    elif avg_nodes < 12:
        complexity_style = "Minimalist / Geometric (Low Node Count)"
        rec_buffer = 15
    else:
        complexity_style = "Standard Vector Curves"
        rec_buffer = 20
        
    return {
        "width_style": width_style,
        "complexity_style": complexity_style,
        "rec_gap": rec_gap,
        "rec_buffer": rec_buffer,
        "avg_width": int(avg_width),
        "avg_nodes": int(avg_nodes)
    }

def calculate_kerning(profiles, pairs_to_kern, target_gap=40, max_adjustment=150, step_size=10, trap_buffer=20):
    kerning_table = {}
    for left_glyph, right_glyph in pairs_to_kern:
        if left_glyph not in profiles or right_glyph not in profiles: continue
        prof_a, prof_b = profiles[left_glyph], profiles[right_glyph]
        
        ys_a = prof_a["right"].keys()
        ys_b = prof_b["left"].keys()
        common_ys = set(ys_a).intersection(set(ys_b))
        if not common_ys: continue
        
        is_trap = False
        contact_height = len(common_ys) * step_size
        if contact_height < 150: is_trap = True
            
        span_a = max(ys_a) - min(ys_a) if ys_a else 0
        span_b = max(ys_b) - min(ys_b) if ys_b else 0
        if span_a < 250 or span_b < 250: is_trap = True
            
        effective_target = (target_gap + trap_buffer) if is_trap else target_gap
        
        min_distance = float('inf')
        for y in common_ys:
            edge_a = prof_a["right"][y]
            edge_b = prof_b["left"][y] + prof_a["advance"] 
            distance = edge_b - edge_a
            if distance < min_distance: min_distance = distance
                
        kern_value = int(effective_target - min_distance)
        if abs(kern_value) > 2 and abs(kern_value) < max_adjustment:
            kerning_table[(left_glyph, right_glyph)] = int(round(kern_value / 5.0) * 5)
    return kerning_table

# --- STREAMLIT UI ---
st.set_page_config(page_title="Autokern Studio Pro", page_icon="✒️", layout="wide")

st.title("✒️ Autokern Studio Pro")
st.write("Professional Font Engineering Environment featuring Automated Typographic DNA Calibration.")

# Sidebar Configuration Controls
st.sidebar.header("🛞 Manual Calibration Override")
target_gap = st.sidebar.slider("Target Optical Gap", min_value=10, max_value=120, value=50, step=5)
precision = st.sidebar.slider("Scanner Precision Slices", min_value=2, max_value=25, value=10, step=1)
trap_buffer = st.sidebar.slider("Trap Protection Buffer", min_value=0, max_value=60, value=20, step=5)

uploaded_file = st.file_uploader("Drop your unkerned production font file here", type=["otf", "ttf"])

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name
    base_name, ext = os.path.splitext(filename)
    
    try:
        font = TTFont(io.BytesIO(file_bytes))
        charset_analysis = analyze_character_set(font)
        profiles = get_glyph_profiles(font, step_size=precision)
        
        # --- NEW Feature: Automated Metrics Analysis Report ---
        intel_report = generate_intelligence_report(font, profiles)
        
        glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
        pairs_to_test = [(a, b) for a in glyphs for b in glyphs]
        
        kern_pairs = calculate_kerning(profiles, pairs_to_test, target_gap=target_gap, step_size=precision, trap_buffer=trap_buffer)
        
        if kern_pairs:
            fea_lines = ["feature kern {"]
            for (left, right), val in kern_pairs.items():
                fea_lines.append(f"    pos {left} {right} {val};")
            fea_lines.append("} kern;")
            addOpenTypeFeaturesFromString(font, "\n".join(fea_lines))
        
        output_buffer = io.BytesIO()
        font.save(output_buffer)
        b64_font = base64.b64encode(output_buffer.getvalue()).decode()
        font_mime = "font/otf" if ext.lower() == ".otf" else "font/ttf"
        
        st.markdown(f"""
            <style>
            @font-face {{
                font-family: 'LiveAutokernFont';
                src: url(data:{font_mime};base64,{b64_font}) format('opentype');
            }}
            .preview-display {{ font-family: 'LiveAutokernFont' !important; white-space: pre; background: #111; color: #fff; padding: 15px; border-radius: 6px; }}
            .size-lg {{ font-size: 64px !important; line-height: 1.1; }}
            .size-md {{ font-size: 36px !important; line-height: 1.2; }}
            .size-sm {{ font-size: 18px !important; line-height: 1.4; }}
            </style>
        """, unsafe_allow_html=True)
        
        # UI Columns
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("📦 Build Actions")
            st.success(f"Generated {len(kern_pairs)} unique rules.")
            st.download_button(
                label="📥 Download Compiled Binary",
                data=output_buffer.getvalue(),
                file_name=f"{base_name}-Autokerned{ext}",
                mime=font_mime,
                use_container_width=True
            )
            
            # Interactive Metrics Intelligence Dashboard card display
            st.subheader("🧠 Typographic Intelligence Report")
            st.markdown(f"""
            * **Visual Architecture:** `{intel_report['width_style']}` (Avg Advance Width: `{intel_report['avg_width']}` units)
            * **Vector Topology:** `{intel_report['complexity_style']}` (Avg `{intel_report['avg_nodes']}` control nodes per glyph)
            """)
            
            # Direct actionable recommendation notice box
            st.warning(f"""
            💡 **Engine Recommendations:**
            * Set **Target Optical Gap** to: `{intel_report['rec_gap']}`
            * Set **Trap Protection Buffer** to: `{intel_report['rec_buffer']}`
            """)
            
            st.subheader("🧬 Character Map Fingerprint")
            st.info(f"**Detected Archetype:** {charset_analysis['type']}")
            m_col1, m_col2 = st.columns(2)
            with m_col1:
                st.metric(label="A-Z Uppercase", value=charset_analysis['caps'])
                st.metric(label="0-9 Numbers", value=charset_analysis['digits'])
            with m_col2:
                st.metric(label="a-z Lowercase", value=charset_analysis['lower'])
                st.metric(label="Punctuation/Symbols", value=charset_analysis['punct'])
            
            st.subheader("📊 GPOS Table Audit")
            if kern_pairs:
                table_data = [{"Left": k[0], "Right": k[1], "Value": v} for k, v in kern_pairs.items()]
                df = pd.DataFrame(table_data)
                st.dataframe(df, use_container_width=True, height=180)

        with col2:
            st.subheader("🔍 Contextual Testing Sandboxes")
            default_test_string = "AVALANCHE TYPE FACE" if charset_analysis['type'] == "All-Caps Display Face" else "T. V, F-Y Hamburgevons"
            
            user_input = st.text_input("Custom Layout Tester String:", default_test_string)
            if user_input:
                st.markdown(f'<div class="preview-display size-lg">{user_input}</div>', unsafe_allow_html=True)
            
            st.write("---")
            st.subheader("🌊 Scale Waterfall")
            proof_text = "Hamburgevons 123!?." if charset_analysis['lower'] > 0 else "HAMBURGEVONS 123!?."
            st.caption("Display Level (64px)")
            st.markdown(f'<div class="preview-display size-lg">{proof_text}</div>', unsafe_allow_html=True)
            st.caption("Text Body Level (36px)")
            st.markdown(f'<div class="preview-display size-md">{proof_text}</div>', unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Engine compilation error: {e}")
