import os
import math
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

class ProfilePen(BasePen):
    """Traces glyph vector paths and collects raw coordinates along the contours."""
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []

    def _moveTo(self, p):
        self.points.append(p)

    def _lineTo(self, p):
        self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        # Sample points along cubic Bezier curves (typical for OTF/CFF)
        p0 = self._getCurrentPoint()
        for i in range(1, 6):
            t = i / 5.0
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))

    def _qCurveToOne(self, p1, p2):
        # Sample points along quadratic Bezier curves (if TTF formatting is present)
        p0 = self._getCurrentPoint()
        for i in range(1, 4):
            t = i / 3.0
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font, step_size=10):
    """Calculates the left and right side-profiles of every glyph across its height."""
    glyph_set = font.getGlyphSet()
    profiles = {}
    
    for glyph_name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        glyph = glyph_set[glyph_name]
        glyph.draw(pen)
        
        if not pen.points:
            continue # Skip space bar or empty glyphs
            
        # Group captured points into horizontal "slices"
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            if y_slice not in slices:
                slices[y_slice] = []
            slices[y_slice].append(x)
            
        # Determine the absolute outer edges for this glyph
        left_profile = {}
        right_profile = {}
        for y_slice, x_vals in slices.items():
            left_profile[y_slice] = min(x_vals)
            right_profile[y_slice] = max(x_vals)
            
        profiles[glyph_name] = {
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
