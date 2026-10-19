import cv2
import numpy as np
import os
import time
import math
from datetime import datetime
import HandTrackingModule as htm

# ─────────────────────────────────────────────────────────────
# RESOLUTION & DIRECTORIES
# ─────────────────────────────────────────────────────────────
WEBCAM_WIDTH = 1280
WEBCAM_HEIGHT = 720
TOP_BAR_HEIGHT = 100

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")
RECORDING_DIR = os.path.join(BASE_DIR, "recordings")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# PALETTE & BRUSH PRESETS
# ─────────────────────────────────────────────────────────────
COLOR_PALETTE = [
    ("Violet",   (235, 70, 215)),    # Neon Violet
    ("Cyan",     (255, 200, 0)),     # Electric Cyan
    ("Mint",     (30, 235, 120)),    # Neon Emerald Mint
    ("Amber",    (0, 180, 255)),     # Sunburst Amber
    ("Coral",    (70, 70, 255)),     # Sunset Coral
    ("White",    (255, 255, 255)),   # Pure White
    ("Rainbow",  None)               # Dynamic Rainbow Mode
]

BRUSH_SIZES = [
    ("XS", 4),
    ("S",  8),
    ("M",  16),
    ("L",  28),
    ("XL", 44)
]

# ─────────────────────────────────────────────────────────────
# HIGH-SPEED CAMERA INITIALIZATION (True 60 FPS MJPG)
# ─────────────────────────────────────────────────────────────
# Try CAP_DSHOW with MJPG for 60FPS; fallback to standard if needed
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WEBCAM_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, WEBCAM_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, 60)

if not cap.isOpened():
    print("Error: Could not access webcam. Please check permissions or device connection.")
    exit(1)

# Hand detector in low-latency VIDEO mode
detector = htm.HandDetector(detectionCon=0.48, trackCon=0.48, maxHands=1)

# Canvas buffer (BGR, 0 = black / transparent)
imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)

# ─────────────────────────────────────────────────────────────
# STATE VARIABLES
# ─────────────────────────────────────────────────────────────
active_color_idx = 1
active_color_name = COLOR_PALETTE[active_color_idx][0]
active_color = COLOR_PALETTE[active_color_idx][1]
rainbow_hue = 0.0

active_size_idx = 2
active_brush_size = BRUSH_SIZES[active_size_idx][1]
glow_ink_mode = False

# Coordinate tracking & adaptive smoothing
xp, yp = 0, 0
smooth_x, smooth_y = 0, 0
prev_palm_x, prev_palm_y = 0, 0
smooth_palm_x, smooth_palm_y = 0, 0
stroke_velocity = 0.0
lost_frames = 0  # Grace window prevents on-and-off signature drops

# Dwell Hover Selection
dwell_target = None
dwell_start_time = 0.0
DWELL_TIME = 0.35  # 350ms to activate hands-free

# Video Recording State
is_recording = False
video_writer = None
rec_start_time = 0.0
current_rec_path = ""

# Animations & UI feedback
pulse_t = 0.0
prev_time = time.time()
fps = 60
flash_alpha = 0.0
toast_msg = "Welcome! Index finger to sign/draw, Open Palm to erase."
toast_expiry = time.time() + 3.5

# ─────────────────────────────────────────────────────────────
# TOP CONTROL BAR LAYOUT DEFINITIONS
# ─────────────────────────────────────────────────────────────
def get_button_layout():
    buttons = []
    # Row 1: Colors & Modes (y: 10 to 48)
    # Row 2: Brush Sizes & Actions (y: 52 to 90)

    # 1. Colors (Row 1)
    cx = 175
    btn_w = 42
    gap = 8
    for idx, (cname, bgr) in enumerate(COLOR_PALETTE):
        bx1 = cx
        bx2 = bx1 + btn_w
        buttons.append({
            "id": f"color_{idx}",
            "type": "color",
            "idx": idx,
            "rect": (bx1, 10, bx2, 48),
            "label": cname,
            "color": bgr
        })
        cx = bx2 + gap

    # Glow Ink toggle button (Row 1)
    bx1 = cx + 8
    bx2 = bx1 + 68
    buttons.append({
        "id": "toggle_glow",
        "type": "glow",
        "rect": (bx1, 10, bx2, 48),
        "label": "GLOW"
    })

    # 2. Brush Sizes (Row 2)
    sx = 175
    s_btn_w = 42
    for s_idx, (sname, sz) in enumerate(BRUSH_SIZES):
        bx1 = sx
        bx2 = bx1 + s_btn_w
        buttons.append({
            "id": f"size_{s_idx}",
            "type": "size",
            "idx": s_idx,
            "rect": (bx1, 52, bx2, 90),
            "label": sname,
            "size": sz
        })
        sx = bx2 + gap

    # 3. Actions Hub (Right Side, Rows 1 & 2)
    ax = 640
    # Record Button
    buttons.append({
        "id": "action_record",
        "type": "action",
        "action": "record",
        "rect": (ax, 10, ax + 115, 48),
        "label": "RECORD"
    })
    # Snapshot Button
    buttons.append({
        "id": "action_snapshot",
        "type": "action",
        "action": "snapshot",
        "rect": (ax + 125, 10, ax + 235, 48),
        "label": "SNAPSHOT"
    })
    # Clear Canvas
    buttons.append({
        "id": "action_clear",
        "type": "action",
        "action": "clear",
        "rect": (ax, 52, ax + 115, 90),
        "label": "CLEAR"
    })
    # Exit Button
    buttons.append({
        "id": "action_quit",
        "type": "action",
        "action": "quit",
        "rect": (ax + 125, 52, ax + 235, 90),
        "label": "EXIT"
    })

    return buttons

BUTTONS = get_button_layout()

# Helper: Convert HSV to BGR for Rainbow Mode
def get_rainbow_color(hue):
    h = int(hue % 180)
    hsv_pixel = np.uint8([[[h, 255, 255]]])
    bgr_pixel = cv2.cvtColor(hsv_pixel, cv2.COLOR_HSV2BGR)
    return (int(bgr_pixel[0,0,0]), int(bgr_pixel[0,0,1]), int(bgr_pixel[0,0,2]))

# Helper: Toggle Video Recording
def toggle_recording():
    global is_recording, video_writer, rec_start_time, current_rec_path, toast_msg, toast_expiry
    if not is_recording:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_rec_path = os.path.join(RECORDING_DIR, f"painting_{ts}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(current_rec_path, fourcc, 30.0, (WEBCAM_WIDTH, WEBCAM_HEIGHT))
        if video_writer.isOpened():
            is_recording = True
            rec_start_time = time.time()
            toast_msg = "Recording Started 🔴"
            toast_expiry = time.time() + 2.0
        else:
            toast_msg = "Error starting VideoWriter"
            toast_expiry = time.time() + 2.0
    else:
        is_recording = False
        if video_writer is not None:
            video_writer.release()
            video_writer = None
        ts_name = os.path.basename(current_rec_path)
        toast_msg = f"Saved: recordings/{ts_name}"
        toast_expiry = time.time() + 3.0

cv2.namedWindow("AI Virtual Painter", cv2.WINDOW_AUTOSIZE)

# ─────────────────────────────────────────────────────────────
# MAIN REAL-TIME LOOP
# ─────────────────────────────────────────────────────────────
while True:
    now = time.time()
    dt = now - prev_time
    prev_time = now
    if dt > 0:
        fps = int(0.92 * fps + 0.08 * (1.0 / dt)) if fps > 0 else int(1.0 / dt)

    pulse_t += 0.14
    pulse_val = (math.sin(pulse_t) + 1.0) / 2.0  # 0.0 to 1.0

    rainbow_hue = (rainbow_hue + 1.8) % 180
    current_pen_color = get_rainbow_color(rainbow_hue) if active_color_name == "Rainbow" else active_color

    # 1. Read camera frame
    success, img = cap.read()
    if not success or img is None:
        continue

    img = cv2.resize(img, (WEBCAM_WIDTH, WEBCAM_HEIGHT))
    img = cv2.flip(img, 1)

    # 2. Hand tracking
    img = detector.findHands(img, draw=False)
    lmList = detector.findPosition(img, draw=False)

    mode = "STANDBY"
    hovered_btn = None
    target_cursor_pt = None

    if len(lmList) >= 21:
        fingers = detector.fingersUp()
        thumb_up = fingers[0]
        index_up = fingers[1]
        middle_up = fingers[2]
        ring_up = fingers[3]
        pinky_up = fingers[4]

        # ── CLASSIFY GESTURES WITH ROBUST HYSTERESIS ──
        # Open Palm: 4+ fingers up
        is_palm_mode = (sum(fingers) >= 4) or (index_up == 1 and middle_up == 1 and ring_up == 1 and pinky_up == 1)

        # Selection Mode: Peace sign (Index + Middle up, others down)
        is_select_mode = (index_up == 1 and middle_up == 1 and ring_up == 0 and pinky_up == 0) and not is_palm_mode

        # Drawing Mode: Index finger pointing (unconstrained by loose ring/pinky)
        is_draw_mode = (index_up == 1) and not is_palm_mode and not is_select_mode

        # ─────────────────────────────────────────────────────
        # GESTURE 1: 🖐️ PALM ERASER (Full-Screen Continuous Wipe)
        # ─────────────────────────────────────────────────────
        if is_palm_mode:
            mode = "PALM ERASER"
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
            lost_frames = 0

            palm_center, palm_radius = detector.getPalmCenter()
            if palm_center:
                raw_px, raw_py = palm_center

                # Smooth palm center
                if smooth_palm_x == 0 and smooth_palm_y == 0:
                    smooth_palm_x, smooth_palm_y = raw_px, raw_py
                else:
                    smooth_palm_x = int(smooth_palm_x * 0.35 + raw_px * 0.65)
                    smooth_palm_y = int(smooth_palm_y * 0.35 + raw_py * 0.65)

                if prev_palm_x == 0 and prev_palm_y == 0:
                    prev_palm_x, prev_palm_y = smooth_palm_x, smooth_palm_y

                # Anti-aliased canvas clear
                cv2.circle(imgCanvas, (smooth_palm_x, smooth_palm_y), palm_radius, (0, 0, 0), cv2.FILLED)
                cv2.line(imgCanvas, (prev_palm_x, prev_palm_y), (smooth_palm_x, smooth_palm_y), (0, 0, 0), palm_radius * 2, lineType=cv2.LINE_AA)
                prev_palm_x, prev_palm_y = smooth_palm_x, smooth_palm_y

                # Holographic animated vortex around palm
                glow_r = palm_radius + int(5 * pulse_val)
                cv2.circle(img, (smooth_palm_x, smooth_palm_y), glow_r, (255, 130, 40), 2, lineType=cv2.LINE_AA)
                cv2.circle(img, (smooth_palm_x, smooth_palm_y), palm_radius - 8, (255, 190, 80), 1, lineType=cv2.LINE_AA)
                cv2.circle(img, (smooth_palm_x, smooth_palm_y), 5, (255, 255, 255), cv2.FILLED, lineType=cv2.LINE_AA)
                cv2.putText(img, "PALM ERASER", (smooth_palm_x - 52, smooth_palm_y - palm_radius - 10),
                            cv2.FONT_HERSHEY_DUPLEX, 0.52, (255, 200, 100), 1, lineType=cv2.LINE_AA)

        # ─────────────────────────────────────────────────────
        # GESTURE 2: ✌️ SELECTION & TOP BAR DWELL CONTROLS
        # ─────────────────────────────────────────────────────
        elif is_select_mode:
            mode = "SELECTION"
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
            prev_palm_x, prev_palm_y = 0, 0
            lost_frames = 0

            x1, y1 = lmList[8][1], lmList[8][2]
            x2, y2 = lmList[12][1], lmList[12][2]
            mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2
            target_cursor_pt = (mid_x, mid_y)

            # Laser beam between fingertips with target crosshair
            cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 2, lineType=cv2.LINE_AA)
            cv2.circle(img, (mid_x, mid_y), 7, current_pen_color, cv2.FILLED, lineType=cv2.LINE_AA)
            cv2.circle(img, (mid_x, mid_y), 15 + int(pulse_val * 4), (0, 240, 255), 2, lineType=cv2.LINE_AA)

            # Check if pointing at top control bar
            if mid_y < TOP_BAR_HEIGHT:
                for btn in BUTTONS:
                    bx1, by1, bx2, by2 = btn["rect"]
                    if bx1 <= mid_x <= bx2 and by1 <= mid_y <= by2:
                        hovered_btn = btn
                        break

            # Dwell selection logic
            if hovered_btn is not None:
                if dwell_target == hovered_btn["id"]:
                    dwell_pct = min(1.0, (now - dwell_start_time) / DWELL_TIME)
                    # Dwell circular neon progress ring
                    progress_angle = int(dwell_pct * 360)
                    cv2.ellipse(img, (mid_x, mid_y), (22, 22), -90, 0, progress_angle, (0, 255, 255), 3, lineType=cv2.LINE_AA)

                    if dwell_pct >= 1.0:
                        b_type = hovered_btn["type"]
                        if b_type == "color":
                            active_color_idx = hovered_btn["idx"]
                            active_color_name = hovered_btn["label"]
                            active_color = hovered_btn["color"]
                            toast_msg = f"Color: {active_color_name}"
                        elif b_type == "glow":
                            glow_ink_mode = not glow_ink_mode
                            toast_msg = f"Glow Ink: {'ON ✨' if glow_ink_mode else 'OFF'}"
                        elif b_type == "size":
                            active_size_idx = hovered_btn["idx"]
                            active_brush_size = hovered_btn["size"]
                            toast_msg = f"Size: {hovered_btn['label']} ({active_brush_size}px)"
                        elif b_type == "action":
                            act = hovered_btn["action"]
                            if act == "clear":
                                imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)
                                toast_msg = "Canvas Cleared!"
                            elif act == "snapshot":
                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                save_path = os.path.join(SNAPSHOT_DIR, f"painting_{ts}.png")
                                canvas_m = (imgCanvas > 0)
                                out_img = np.where(canvas_m, imgCanvas, img)
                                cv2.imwrite(save_path, out_img)
                                flash_alpha = 1.0
                                toast_msg = f"Snapshot Saved: {ts}.png"
                            elif act == "record":
                                toggle_recording()
                            elif act == "quit":
                                break

                        toast_expiry = time.time() + 2.0
                        dwell_target = None
                else:
                    dwell_target = hovered_btn["id"]
                    dwell_start_time = now
            else:
                dwell_target = None

        # ─────────────────────────────────────────────────────
        # GESTURE 3: ☝️ DRAWING / SIGNATURE (Zero-Lag Spline Stream)
        # ─────────────────────────────────────────────────────
        elif is_draw_mode:
            mode = "SIGN / DRAW"
            dwell_target = None
            prev_palm_x, prev_palm_y = 0, 0
            lost_frames = 0

            x1, y1 = lmList[8][1], lmList[8][2]

            # Adaptive EMA: instantaneous velocity-based tracking
            if smooth_x == 0 and smooth_y == 0:
                smooth_x, smooth_y = x1, y1
            else:
                vel = math.hypot(x1 - smooth_x, y1 - smooth_y)
                stroke_velocity = 0.85 * stroke_velocity + 0.15 * vel
                # Higher speed = higher alpha (zero lag when flicking fast for signature)
                alpha = min(0.96, max(0.55, 0.55 + vel * 0.015))
                smooth_x = int(smooth_x * (1 - alpha) + x1 * alpha)
                smooth_y = int(smooth_y * (1 - alpha) + y1 * alpha)

            if xp == 0 and yp == 0:
                xp, yp = smooth_x, smooth_y

            # Draw onto canvas when below the top control bar
            if smooth_y > TOP_BAR_HEIGHT:
                dist = math.hypot(smooth_x - xp, smooth_y - yp)
                steps = max(1, int(dist / 3))  # Dense sub-step interpolation

                # Optional Glow Ink halo effect
                if glow_ink_mode:
                    halo_c = tuple(int(c * 0.45) for c in current_pen_color)
                    halo_sz = active_brush_size + 14
                    for s in range(1, steps + 1):
                        ix = int(xp + (smooth_x - xp) * (s / steps))
                        iy = int(yp + (smooth_y - yp) * (s / steps))
                        cv2.circle(imgCanvas, (ix, iy), halo_sz // 2, halo_c, cv2.FILLED, lineType=cv2.LINE_AA)

                # Solid core calligraphic stroke
                for s in range(1, steps + 1):
                    ix = int(xp + (smooth_x - xp) * (s / steps))
                    iy = int(yp + (smooth_y - yp) * (s / steps))
                    cv2.circle(imgCanvas, (ix, iy), active_brush_size // 2, current_pen_color, cv2.FILLED, lineType=cv2.LINE_AA)

                cv2.line(imgCanvas, (xp, yp), (smooth_x, smooth_y), current_pen_color, active_brush_size, lineType=cv2.LINE_AA)
                xp, yp = smooth_x, smooth_y
            else:
                xp, yp = 0, 0

            # Dynamic glowing reticle at fingertip
            r_outer = int(active_brush_size // 2 + 7 + 3 * pulse_val)
            cv2.circle(img, (smooth_x, smooth_y), r_outer, current_pen_color, 2, lineType=cv2.LINE_AA)
            cv2.circle(img, (smooth_x, smooth_y), max(3, active_brush_size // 2), current_pen_color, cv2.FILLED, lineType=cv2.LINE_AA)
            cv2.circle(img, (smooth_x, smooth_y), 2, (255, 255, 255), cv2.FILLED, lineType=cv2.LINE_AA)

        else:
            # Fist or neutral hand - allow up to 4 grace frames before terminating stroke
            lost_frames += 1
            if lost_frames > 4:
                xp, yp = 0, 0
                smooth_x, smooth_y = 0, 0
            prev_palm_x, prev_palm_y = 0, 0
            dwell_target = None

    else:
        # Hand temporarily lost - grace period prevents stroke fragmentation
        lost_frames += 1
        if lost_frames > 4:
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
        prev_palm_x, prev_palm_y = 0, 0
        dwell_target = None

    # ─────────────────────────────────────────────────────────
    # MERGE CANVAS ONTO WEBCAM (Ultra-Fast Array Indexing)
    # ─────────────────────────────────────────────────────────
    canvas_mask = (imgCanvas > 0)
    img = np.where(canvas_mask, imgCanvas, img)

    # ─────────────────────────────────────────────────────────
    # RENDER AAA CYBER GLASSMORPHIC TOP CONTROL BAR
    # ─────────────────────────────────────────────────────────
    # Glass backdrop with high transparency
    bar_overlay = img[0:TOP_BAR_HEIGHT, 0:WEBCAM_WIDTH].copy()
    cv2.rectangle(bar_overlay, (0, 0), (WEBCAM_WIDTH, TOP_BAR_HEIGHT), (12, 16, 24), cv2.FILLED)
    cv2.addWeighted(bar_overlay, 0.88, img[0:TOP_BAR_HEIGHT, 0:WEBCAM_WIDTH], 0.12, 0, img[0:TOP_BAR_HEIGHT, 0:WEBCAM_WIDTH])

    # Bottom glowing separator border
    cv2.line(img, (0, TOP_BAR_HEIGHT - 2), (WEBCAM_WIDTH, TOP_BAR_HEIGHT - 2), (35, 45, 65), 1)
    cv2.line(img, (0, TOP_BAR_HEIGHT - 1), (WEBCAM_WIDTH, TOP_BAR_HEIGHT - 1), current_pen_color, 2)

    # Brand Title & Status Beacon (Left Side)
    cv2.putText(img, "NEO STUDIO", (18, 38), cv2.FONT_HERSHEY_DUPLEX, 0.76, (255, 255, 255), 2, lineType=cv2.LINE_AA)
    beacon_glow = int(5 * pulse_val)
    cv2.circle(img, (20, 58), 4 + beacon_glow, current_pen_color, 1, lineType=cv2.LINE_AA)
    cv2.circle(img, (20, 58), 4, current_pen_color, cv2.FILLED, lineType=cv2.LINE_AA)
    cv2.putText(img, "AI Hand Canvas 60FPS", (32, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (170, 185, 205), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, "Open Palm = Eraser", (18, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 180, 50), 1, lineType=cv2.LINE_AA)

    # Render Interactive Buttons
    for btn in BUTTONS:
        bx1, by1, bx2, by2 = btn["rect"]
        is_hovered = (hovered_btn is not None and hovered_btn["id"] == btn["id"])

        if btn["type"] == "color":
            is_active = (btn["idx"] == active_color_idx)
            bg_c = (30, 36, 48) if not is_hovered else (50, 65, 88)
            cv2.rectangle(img, (bx1, by1), (bx2, by2), bg_c, cv2.FILLED)

            cx, cy = (bx1 + bx2) // 2, (by1 + by2) // 2
            if btn["label"] == "Rainbow":
                # Multi-color swatch representation
                cv2.circle(img, (cx, cy), 13, current_pen_color, cv2.FILLED, lineType=cv2.LINE_AA)
                cv2.putText(img, "RGB", (bx1 + 8, by2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (255, 255, 255), 1, lineType=cv2.LINE_AA)
            else:
                cv2.circle(img, (cx, cy), 13, btn["color"], cv2.FILLED, lineType=cv2.LINE_AA)
                if btn["label"] == "White":
                    cv2.circle(img, (cx, cy), 13, (120, 120, 120), 1, lineType=cv2.LINE_AA)

            if is_active:
                cv2.rectangle(img, (bx1, by1), (bx2, by2), current_pen_color, 2, lineType=cv2.LINE_AA)
                cv2.circle(img, (cx, by2 - 4), 2, current_pen_color, cv2.FILLED, lineType=cv2.LINE_AA)
            elif is_hovered:
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (0, 240, 255), 2, lineType=cv2.LINE_AA)

        elif btn["type"] == "glow":
            bg_c = (20, 50, 70) if glow_ink_mode else (30, 36, 48)
            if is_hovered: bg_c = (40, 75, 100)
            cv2.rectangle(img, (bx1, by1), (bx2, by2), bg_c, cv2.FILLED)
            txt_c = (0, 255, 255) if glow_ink_mode else (180, 180, 180)
            cv2.putText(img, "GLOW", (bx1 + 10, by1 + 24), cv2.FONT_HERSHEY_DUPLEX, 0.42, txt_c, 1, lineType=cv2.LINE_AA)
            state_str = "ON ✨" if glow_ink_mode else "OFF"
            cv2.putText(img, state_str, (bx1 + 14, by1 + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.30, txt_c, 1, lineType=cv2.LINE_AA)
            if is_hovered or glow_ink_mode:
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (0, 255, 255), 2, lineType=cv2.LINE_AA)

        elif btn["type"] == "size":
            is_active = (btn["idx"] == active_size_idx)
            bg_c = (30, 36, 48) if not is_hovered else (50, 65, 88)
            cv2.rectangle(img, (bx1, by1), (bx2, by2), bg_c, cv2.FILLED)

            cv2.putText(img, btn["label"], (bx1 + 10, by1 + 18), cv2.FONT_HERSHEY_DUPLEX, 0.38, (220, 220, 220), 1, lineType=cv2.LINE_AA)
            cx, cy = (bx1 + bx2) // 2, by1 + 27
            r = max(2, btn["size"] // 3)
            cv2.circle(img, (cx, cy), r, (255, 255, 255), cv2.FILLED, lineType=cv2.LINE_AA)

            if is_active:
                cv2.rectangle(img, (bx1, by1), (bx2, by2), current_pen_color, 2, lineType=cv2.LINE_AA)
            elif is_hovered:
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (0, 240, 255), 2, lineType=cv2.LINE_AA)

        elif btn["type"] == "action":
            act = btn["action"]
            if act == "record":
                if is_recording:
                    rec_dur = int(now - rec_start_time)
                    mins, secs = divmod(rec_dur, 60)
                    btn_text = f"REC {mins:02d}:{secs:02d}"
                    bg_c = (30, 30, 180) if (int(pulse_t * 3) % 2 == 0) else (60, 20, 100)
                else:
                    btn_text = "⏺ RECORD"
                    bg_c = (45, 30, 50) if not is_hovered else (75, 40, 80)
            elif act == "snapshot":
                btn_text = "📸 SNAP"
                bg_c = (30, 50, 45) if not is_hovered else (45, 80, 70)
            elif act == "clear":
                btn_text = "🧹 CLEAR"
                bg_c = (45, 45, 35) if not is_hovered else (75, 75, 50)
            elif act == "quit":
                btn_text = "❌ QUIT"
                bg_c = (55, 30, 30) if not is_hovered else (85, 40, 40)

            cv2.rectangle(img, (bx1, by1), (bx2, by2), bg_c, cv2.FILLED)
            cv2.putText(img, btn_text, (bx1 + 8, by1 + 25), cv2.FONT_HERSHEY_DUPLEX, 0.44, (255, 255, 255), 1, lineType=cv2.LINE_AA)

            if is_hovered:
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (0, 255, 255), 2, lineType=cv2.LINE_AA)

    # ─────────────────────────────────────────────────────────
    # FLOATING TELEMETRY & STATUS DOCKS
    # ─────────────────────────────────────────────────────────
    # Top-Right Telemetry Badge (x: 1110 -> 1264, y: 12 -> 46)
    tel_bg = img[12:46, 1110:1264].copy()
    cv2.rectangle(tel_bg, (0, 0), (154, 34), (16, 20, 28), cv2.FILLED)
    cv2.addWeighted(tel_bg, 0.88, img[12:46, 1110:1264], 0.12, 0, img[12:46, 1110:1264])
    cv2.rectangle(img, (1110, 12), (1264, 46), (40, 50, 70), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, f"{fps} FPS", (1122, 35), cv2.FONT_HERSHEY_DUPLEX, 0.50, (0, 235, 140), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, "720p@60Hz", (1188, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (160, 175, 195), 1, lineType=cv2.LINE_AA)

    # Top-Right Active Mode Pill (x: 1110 -> 1264, y: 54 -> 88)
    mode_bg = img[54:88, 1110:1264].copy()
    cv2.rectangle(mode_bg, (0, 0), (154, 34), (16, 20, 28), cv2.FILLED)
    cv2.addWeighted(mode_bg, 0.88, img[54:88, 1110:1264], 0.12, 0, img[54:88, 1110:1264])
    cv2.rectangle(img, (1110, 54), (1264, 88), (40, 50, 70), 1, lineType=cv2.LINE_AA)

    m_color = (150, 150, 150)
    if mode == "SIGN / DRAW":
        m_color = current_pen_color
    elif mode == "PALM ERASER":
        m_color = (255, 140, 50)
    elif mode == "SELECTION":
        m_color = (0, 240, 255)

    cv2.circle(img, (1125, 71), 4, m_color, cv2.FILLED, lineType=cv2.LINE_AA)
    cv2.putText(img, mode, (1136, 75), cv2.FONT_HERSHEY_DUPLEX, 0.40, (240, 240, 240), 1, lineType=cv2.LINE_AA)

    # Bottom Floating Controls Pill (x: 340 -> 940, y: 676 -> 708)
    b_y1 = WEBCAM_HEIGHT - 38
    b_y2 = WEBCAM_HEIGHT - 10
    bot_bg = img[b_y1:b_y2, 340:940].copy()
    cv2.rectangle(bot_bg, (0, 0), (600, 28), (14, 18, 25), cv2.FILLED)
    cv2.addWeighted(bot_bg, 0.88, img[b_y1:b_y2, 340:940], 0.12, 0, img[b_y1:b_y2, 340:940])
    cv2.rectangle(img, (340, b_y1), (940, b_y2), (40, 50, 70), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, "[R] Record  |  [S] Snapshot  |  [C] Clear  |  [G] Glow Ink  |  [1-7] Colors  |  [Q] Quit",
                (355, b_y1 + 18), cv2.FONT_HERSHEY_DUPLEX, 0.40, (180, 195, 215), 1, lineType=cv2.LINE_AA)

    # ─────────────────────────────────────────────────────────
    # TOAST NOTIFICATION BANNER
    # ─────────────────────────────────────────────────────────
    if time.time() < toast_expiry:
        tw, th = 520, 36
        tx1 = (WEBCAM_WIDTH - tw) // 2
        ty1 = TOP_BAR_HEIGHT + 14
        tx2 = tx1 + tw
        ty2 = ty1 + th

        t_overlay = img[ty1:ty2, tx1:tx2].copy()
        cv2.rectangle(t_overlay, (0, 0), (tw, th), (20, 25, 35), cv2.FILLED)
        cv2.addWeighted(t_overlay, 0.90, img[ty1:ty2, tx1:tx2], 0.10, 0, img[ty1:ty2, tx1:tx2])
        cv2.rectangle(img, (tx1, ty1), (tx2, ty2), (0, 220, 255), 1, lineType=cv2.LINE_AA)
        cv2.putText(img, toast_msg, (tx1 + 18, ty1 + 23), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, lineType=cv2.LINE_AA)

    # ─────────────────────────────────────────────────────────
    # WHITE FLASH ANIMATION (Snapshot Shutter)
    # ─────────────────────────────────────────────────────────
    if flash_alpha > 0.05:
        white_screen = np.ones_like(img, dtype=np.uint8) * 255
        cv2.addWeighted(white_screen, flash_alpha, img, 1.0 - flash_alpha, 0, img)
        flash_alpha = max(0.0, flash_alpha - 0.20)

    # ─────────────────────────────────────────────────────────
    # VIDEO RECORDING FRAME WRITE
    # ─────────────────────────────────────────────────────────
    if is_recording and video_writer is not None:
        video_writer.write(img)

    # ─────────────────────────────────────────────────────────
    # DISPLAY & KEYBOARD SHORTCUTS
    # ─────────────────────────────────────────────────────────
    cv2.imshow("AI Virtual Painter", img)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break
    elif key == ord('r') or key == ord('R'):
        toggle_recording()
    elif key == ord('s') or key == ord('S'):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join(SNAPSHOT_DIR, f"painting_{ts}.png")
        canvas_m = (imgCanvas > 0)
        out_img = np.where(canvas_m, imgCanvas, img)
        cv2.imwrite(save_path, out_img)
        flash_alpha = 1.0
        toast_msg = f"Snapshot Saved: {ts}.png"
        toast_expiry = time.time() + 2.5
    elif key == ord('c') or key == ord('C'):
        imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)
        toast_msg = "Canvas Cleared!"
        toast_expiry = time.time() + 1.8
    elif key == ord('g') or key == ord('G'):
        glow_ink_mode = not glow_ink_mode
        toast_msg = f"Glow Ink: {'ON ✨' if glow_ink_mode else 'OFF'}"
        toast_expiry = time.time() + 1.8
    elif key in [ord(str(n)) for n in range(1, 8)]:
        active_color_idx = key - ord('1')
        active_color_name = COLOR_PALETTE[active_color_idx][0]
        active_color = COLOR_PALETTE[active_color_idx][1]
        toast_msg = f"Color: {active_color_name}"
        toast_expiry = time.time() + 1.8
    elif key == ord('+') or key == ord('='):
        active_brush_size = min(64, active_brush_size + 4)
        toast_msg = f"Brush Size: {active_brush_size}px"
        toast_expiry = time.time() + 1.5
    elif key == ord('-') or key == ord('_'):
        active_brush_size = max(2, active_brush_size - 4)
        toast_msg = f"Brush Size: {active_brush_size}px"
        toast_expiry = time.time() + 1.5

    # Exit cleanly if 'X' clicked
    if cv2.getWindowProperty("AI Virtual Painter", cv2.WND_PROP_VISIBLE) < 1:
        break

# Clean termination
if is_recording and video_writer is not None:
    video_writer.release()
detector.close()
cap.release()
cv2.destroyAllWindows()