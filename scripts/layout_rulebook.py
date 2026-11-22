"""
LAYOUT RULEBOOK (IMMUTABLE SPECIFICATIONS)
=========================================
This module is the single source of truth for all video layout architectures in HyperClip Studio.
Rules defined here are frozen dataclasses/mappings.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. 'circle' / 'circle_pip' is strictly isolated. Changes to other layouts NEVER bleed into circle_pip.
2. Coordinates, aspect ratios, subtitle margins, and filter complexes for each layout are locked.
3. Overrides cannot mutate these parameters at runtime.

DETAILED SPECIFICATIONS:
- Sample 1 ('split'): 50/50 Seam Split. Facecam top (1080x600), Gameplay bottom (1080x1320). Subtitle right at Y=600 divider (margin_v=1270).
- Sample 2 ('pip'): Floating Corner PiP. Fullscreen 9:16 gameplay with top-right bordered webcam box (428x241 at 612:80). Subtitle lower-third (margin_v=420).
- Sample 3 ('blur'): Blurred Mirror Backdrop. Centered 16:9 gameplay (Y=656), top centered webcam (548x308 at 266:250), soft boxblur=25:5 background. Subtitle lower-third (margin_v=460).
- Sample 4 ('circle' / 'circle_pip'): Circular PiP. 9:16 vertical gameplay + floating top-right (660:80) 360px circular facecam with animated completion timer ring. Subtitle lower-third (margin_v=420).
"""

from dataclasses import dataclass
from typing import Tuple, Dict, Any

@dataclass(frozen=True)
class LayoutRule:
    name: str
    sample_id: str           # 'sample1', 'sample2', 'sample3', 'sample4'
    description: str
    target_width: int
    target_height: int
    subtitle_margin_v: int
    subtitle_alignment: int  # ASS alignment (2 = bottom-center)
    square_pixel_sar: bool   # setsar=1:1
    has_background_blur: bool
    webcam_type: str         # 'circle', 'pip_rect', 'top_banner', 'none'
    webcam_crop_mode: str    # 'square_center', 'aspect_box', 'fixed'
    webcam_target_size: Tuple[int, int]
    webcam_overlay_pos: Tuple[int, int]
    webcam_border_pad: Tuple[int, int, str]  # (pad_w, pad_h, border_color) e.g. (428, 241, 'white')
    timer_ring_enabled: bool


# === MASTER IMMUTABLE RULEBOOK ===
LAYOUT_RULES: Dict[str, LayoutRule] = {
    # -------------------------------------------------------------
    # SAMPLE 1: 50 / 50 SEAM SPLIT (MODE A)
    # -------------------------------------------------------------
    'split': LayoutRule(
        name='split',
        sample_id='sample1',
        description='Facecam top (1080x600), Gameplay bottom (1080x1320), Bebas Glow subtitle right at Y=600 seam divider',
        target_width=1080,
        target_height=1920,
        subtitle_margin_v=1270,      # Positioned right at Y=600 divider
        subtitle_alignment=2,
        square_pixel_sar=True,
        has_background_blur=False,
        webcam_type='top_banner',
        webcam_crop_mode='aspect_box',
        webcam_target_size=(1080, 600),
        webcam_overlay_pos=(0, 0),
        webcam_border_pad=(1080, 600, 'none'),
        timer_ring_enabled=False
    ),

    # -------------------------------------------------------------
    # SAMPLE 2: FLOATING CORNER PIP (MODE B)
    # -------------------------------------------------------------
    'pip': LayoutRule(
        name='pip',
        sample_id='sample2',
        description='Fullscreen 9:16 gameplay with top-right bordered webcam box (428x241 at 612:80) and TikTok subtitles',
        target_width=1080,
        target_height=1920,
        subtitle_margin_v=420,       # Lower-third placement
        subtitle_alignment=2,
        square_pixel_sar=True,
        has_background_blur=False,
        webcam_type='pip_rect',
        webcam_crop_mode='aspect_box',
        webcam_target_size=(420, 233),
        webcam_overlay_pos=(612, 80),
        webcam_border_pad=(428, 241, 'white'),
        timer_ring_enabled=False
    ),

    # -------------------------------------------------------------
    # SAMPLE 3: BLURRED MIRROR BACKDROP (MODE D)
    # -------------------------------------------------------------
    'blur': LayoutRule(
        name='blur',
        sample_id='sample3',
        description='Centered 16:9 gameplay (Y=656), top centered webcam (548x308 at 266:250), soft blurred background fill (boxblur=25:5)',
        target_width=1080,
        target_height=1920,
        subtitle_margin_v=460,       # Lower-third placement under center gameplay
        subtitle_alignment=2,
        square_pixel_sar=True,
        has_background_blur=True,
        webcam_type='top_cam',
        webcam_crop_mode='aspect_box',
        webcam_target_size=(540, 300),
        webcam_overlay_pos=(266, 250),
        webcam_border_pad=(548, 308, 'white'),
        timer_ring_enabled=False
    ),

    # -------------------------------------------------------------
    # SAMPLE 4: CIRCLE PIP / THE LOCKED SIGNATURE FORMAT
    # -------------------------------------------------------------
    'circle': LayoutRule(
        name='circle',
        sample_id='sample4',
        description='Full 9:16 vertical gameplay + floating top-right circular webcam (360px at 660:80) with animated completion timer ring',
        target_width=1080,
        target_height=1920,
        subtitle_margin_v=420,       # Exact lower-third placement over gameplay
        subtitle_alignment=2,
        square_pixel_sar=True,       # Strict 1:1 SAR prevents oval distortion
        has_background_blur=False,   # Strictly NO background blur
        webcam_type='circle',
        webcam_crop_mode='square_center', # Crop center square of facecam
        webcam_target_size=(360, 360),
        webcam_overlay_pos=(660, 80),     # Top-right floating position
        webcam_border_pad=(360, 360, 'mask'),
        timer_ring_enabled=True
    ),
    'circle_pip': LayoutRule(
        name='circle_pip',
        sample_id='sample4',
        description='Alias for circle layout',
        target_width=1080,
        target_height=1920,
        subtitle_margin_v=420,
        subtitle_alignment=2,
        square_pixel_sar=True,
        has_background_blur=False,
        webcam_type='circle',
        webcam_crop_mode='square_center',
        webcam_target_size=(360, 360),
        webcam_overlay_pos=(660, 80),
        webcam_border_pad=(360, 360, 'mask'),
        timer_ring_enabled=True
    )
}


def get_layout_rule(layout_name: str) -> LayoutRule:
    """
    Retrieves the locked LayoutRule for the specified layout.
    Accepts layout name or sample alias ('sample1', 'sample2', 'sample3', 'sample4', '1', '2', '3', '4').
    Defaults to 'circle' if unspecified or unknown.
    """
    key = str(layout_name).strip().lower()
    if key in ('sample1', 'split', 'a', '1'):
        key = 'split'
    elif key in ('sample2', 'pip', 'b', '2'):
        key = 'pip'
    elif key in ('sample3', 'blur', 'd', '3'):
        key = 'blur'
    elif key in ('sample4', 'circle', 'circle_pip', 'c', '4'):
        key = 'circle'

    if key not in LAYOUT_RULES:
        print(f"[Layout Rulebook Warning] Unknown layout '{layout_name}'. Defaulting to locked 'circle' rule.")
        key = 'circle'

    return LAYOUT_RULES[key]


def build_filter_for_rule(rule: LayoutRule, ass_basename: str, cam_crop: Tuple[int, int, int, int]) -> str:
    """
    Builds the exact FFmpeg filter_complex string according to the immutable LayoutRule.
    Guarantees no cross-contamination between layouts.
    """
    cw, ch, cx, cy = cam_crop
    fonts_arg = f"ass=filename={ass_basename}:fontsdir=assets/fonts"
    sar_arg = ",setsar=1:1" if rule.square_pixel_sar else ""

    if rule.name in ('circle', 'circle_pip'):
        # STRICT LOCKED CIRCULAR PIP LOGIC:
        # 1. Base 9:16 center crop from 16:9 gameplay: crop=607:1080:656:0 -> scale=1080:1920
        # 2. Webcam square center crop: crop=ch:ch:cx+(cw-ch)//2:cy -> scale=360:360
        # 3. Alpha merge with circle mask [1:v]
        # 4. Overlay animated completion timer ring [2:v]
        # 5. Overlay on top-right at 660:80
        # 6. Overlay subtitles at locked margin without blur
        return (
            f"[0:v]setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos,split=2[v_bg_in][v_sq_in];"
            f"[v_bg_in]crop=607:1080:656:0,scale=1080:1920:flags=lanczos[bg];"
            f"[v_sq_in]crop={ch}:{ch}:{cx + (cw - ch) // 2}:{cy},scale=360:360:flags=lanczos[cam_sq];"
            f"[1:v]scale=360:360[mask];"
            f"[2:v]scale=360:360[timer_ring];"
            f"[cam_sq][mask]alphamerge[cam_circle];"
            f"[cam_circle][timer_ring]overlay=0:0[cam_ring];"
            f"[bg][cam_ring]overlay=660:80[v_circ];"
            f"[v_circ]{fonts_arg}{sar_arg}[outv]"
        )

    elif rule.name == 'split':
        # Split layout: top facecam 1080x600, bottom gameplay 1080x1320
        return (
            f"[0:v]setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos,split=2[v_cam_in][v_game_in];"
            f"[v_cam_in]crop={cw}:{ch}:{cx}:{cy},scale=1080:600:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:600[cam];"
            f"[v_game_in]crop=884:1080:518:0,scale=1080:1320:flags=lanczos[game];"
            f"[cam][game]vstack=inputs=2[v_split];"
            f"[v_split]{fonts_arg}{sar_arg}[outv]"
        )

    elif rule.name == 'pip':
        # Rectangular corner PIP: top-right at 612, 80 with white pad border
        return (
            f"[0:v]setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos,split=2[v_bg_in][v_pip_in];"
            f"[v_bg_in]crop=607:1080:656:0,scale=1080:1920:flags=lanczos[bg];"
            f"[v_pip_in]crop={cw}:{ch}:{cx}:{cy},scale=420:233:force_original_aspect_ratio=increase:flags=lanczos,crop=420:233,pad=428:241:4:4:white[cam_pip];"
            f"[bg][cam_pip]overlay=612:80[v_pip];"
            f"[v_pip]{fonts_arg}{sar_arg}[outv]"
        )

    else:
        # Blur layout
        return (
            f"[0:v]setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos,split=3[v_blur_in][v_game_in][v_top_in];"
            f"[v_blur_in]scale=3414:1920:flags=bilinear,crop=1080:1920,boxblur=25:5[bg_blur];"
            f"[v_game_in]scale=1080:608:flags=lanczos[center_game];"
            f"[v_top_in]crop={cw}:{ch}:{cx}:{cy},scale=540:300:force_original_aspect_ratio=increase:flags=lanczos,crop=540:300,pad=548:308:4:4:white[top_cam];"
            f"[bg_blur][center_game]overlay=0:656[v_mid];"
            f"[v_mid][top_cam]overlay=266:250[v_comp];"
            f"[v_comp]{fonts_arg}{sar_arg}[outv]"
        )
