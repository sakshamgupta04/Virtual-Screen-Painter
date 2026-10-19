import cv2
import numpy as np
import os
import time
import math
from datetime import datetime
import HandTrackingModule as htm

# ─────────────────────────────────────────────────────────────
# CONFIGURATION & DIRECTORIES
# ─────────────────────────────────────────────────────────────
WEBCAM_WIDTH = 1280
WEBCAM_HEIGHT = 720
TOP_BAR_HEIGHT = 92

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")
RECORDING_DIR = os.path.join(BASE_DIR, "recordings")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# PALETTE & PRESETS
# ─────────────────────────────────────────────────────────────
COLORS = [
    ("Violet",  (235, 70, 215)),    # Neon Violet
    ("Cyan",    (255, 185, 0)),     # Electric Cyan
    ("Mint",    (45, 230, 110)),    # Neon Emerald Mint
    ("Amber",   (0, 190, 255)),     # Sunburst Amber
    ("Coral",   (75, 75, 255)),     # Sunset Coral
    ("White",   (255, 255, 255)),   # Pure White
    ("Rainbow", None)               # Dynamic Spectrum
]

SIZES = [
    ("S",  6),
    ("M",  14),
    ("L",  26)
]

PALM_ERASER_RADIUS = 65

# ─────────────────────────────────────────────────────────────
# CAMERA SETUP (Lean & High FPS)
# ─────────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WEBCAM_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, WEBCAM_HEIGHT)

if not cap.isOpened():
    print("Error: Could not access webcam.")
    exit(1)

# Hand tracking detector
detector = htm.HandDetector(detectionCon=0.48, trackCon=0.48, maxHands=1)

# Canvas & Undo History
imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)
history_stack = [imgCanvas.copy()]
MAX_HISTORY = 12

# ─────────────────────────────────────────────────────────────
# APPLICATION STATE
# ─────────────────────────────────────────────────────────────
active_tool = "PEN"  # "PEN", "LINE", "RECT", "CIRCLE"
active_color_idx = 1
active_color_name = COLORS[active_color_idx][0]
active_color = COLORS[active_color_idx][1]
rainbow_hue = 0.0

active_size_idx = 1
brush_size = SIZES[active_size_idx][1]
glow_mode = False
studio_mode = False

# Coordinate tracking & shape preview
xp, yp = 0, 0
smooth_x, smooth_y = 0, 0
prev_palm_x, prev_palm_y = 0, 0
shape_start = None
was_drawing_last_frame = False

# Dwell Hover Selection
dwell_target = None
dwell_start_time = 0.0
DWELL_THRESHOLD = 0.28  # 280ms hover to activate

# Recording state
is_recording = False
video_writer = None
rec_start_time = 0.0
rec_file_path = ""

# Animation / Toast
flash_alpha = 0.0
toast_msg = "NEO Studio Ready | ☝️ Draw | 🖐️ Open Palm Erases"
toast_timer = time.time() + 3.5
pulse_t = 0.0
prev_frame_t = time.time()
fps = 30

# ─────────────────────────────────────────────────────────────
# TOP BAR BUTTON LAYOUT (Adequate Spacing, Visual Hierarchy)
# ─────────────────────────────────────────────────────────────
def build_pro_header():
    buttons = []

    # 1. Tools: PEN, LINE, RECT, CIRCLE (x: 206 to 430)
    tx = 206
    tools_list = [
        ("tool_pen",    "PEN",  "PEN",  48),
        ("tool_line",   "LINE", "LINE", 50),
        ("tool_rect",   "RECT", "RECT", 50),
        ("tool_circle", "CIRC", "CIRC", 50)
    ]
    for bid, act_t, label, w in tools_list:
        buttons.append({
            "id": bid,
            "type": "tool",
            "tool": act_t,
            "rect": (tx, 28, tx + w, 74),
            "label": label
        })
        tx += w + 8

    # 2. Colors: 6 Swatches + Rainbow (x: 452 to 740)
    cx = 466
    for idx, (cname, bgr) in enumerate(COLORS):
        buttons.append({
            "id": f"color_{idx}",
            "type": "color",
            "idx": idx,
            "center": (cx, 51),
            "radius": 17,
            "color": bgr,
            "label": cname
        })
        cx += 40

    # 3. Sizes & Effects: S, M, L, GLOW, STUDIO (x: 755 to 950)
    sx = 755
    for s_idx, (sname, sz) in enumerate(SIZES):
        buttons.append({
            "id": f"size_{s_idx}",
            "type": "size",
            "idx": s_idx,
            "rect": (sx, 28, sx + 42, 74),
            "label": sname,
            "size": sz
        })
        sx += 48

    # Effects toggles
    buttons.append({
        "id": "toggle_glow",
        "type": "glow",
        "rect": (sx, 28, sx + 50, 74),
        "label": "GLOW"
    })
    sx += 56
    buttons.append({
        "id": "toggle_studio",
        "type": "studio",
        "rect": (sx, 28, sx + 58, 74),
        "label": "DARK"
    })

    # 4. Action Hub: UNDO, CLEAR, SNAP, REC, EXIT (x: 970 to 1264)
    ax = 970
    actions_list = [
        ("undo",     "UNDO", 52, (45, 45, 60)),
        ("clear",    "CLEAR", 56, (40, 40, 58)),
        ("snapshot", "SNAP",  56, (32, 60, 48)),
        ("record",   "REC",   68, (65, 28, 38)),
        ("quit",     "X",     42, (55, 28, 28))
    ]
    for act_id, label, w, bg_c in actions_list:
        buttons.append({
            "id": f"act_{act_id}",
            "type": "action",
            "action": act_id,
            "rect": (ax, 28, ax + w, 74),
            "label": label,
            "bg": bg_c
        })
        ax += w + 8

    return buttons

BUTTONS = build_pro_header()

def get_rainbow_color(hue):
    h = int(hue % 180)
    hsv = np.uint8([[[h, 255, 255]]])
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return (int(bgr[0,0,0]), int(bgr[0,0,1]), int(bgr[0,0,2]))

def commit_history():
    global history_stack
    history_stack.append(imgCanvas.copy())
    if len(history_stack) > MAX_HISTORY:
        history_stack.pop(0)

def undo_history():
    global imgCanvas, history_stack, toast_msg, toast_timer
    if len(history_stack) > 1:
        history_stack.pop()
        imgCanvas = history_stack[-1].copy()
        toast_msg = "Undo ↩️"
    else:
        imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)
        toast_msg = "Canvas Clean"
    toast_timer = time.time() + 1.5

def toggle_record():
    global is_recording, video_writer, rec_start_time, rec_file_path, toast_msg, toast_timer
    if not is_recording:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rec_file_path = os.path.join(RECORDING_DIR, f"painting_{ts}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(rec_file_path, fourcc, 30.0, (WEBCAM_WIDTH, WEBCAM_HEIGHT))
        if video_writer.isOpened():
            is_recording = True
            rec_start_time = time.time()
            toast_msg = "Recording Started 🔴"
            toast_timer = time.time() + 2.0
    else:
        is_recording = False
        if video_writer is not None:
            video_writer.release()
            video_writer = None
        toast_msg = f"Saved: recordings/{os.path.basename(rec_file_path)}"
        toast_timer = time.time() + 3.0

cv2.namedWindow("AI Virtual Painter", cv2.WINDOW_AUTOSIZE)

# ─────────────────────────────────────────────────────────────
# MAIN REAL-TIME LOOP
# ─────────────────────────────────────────────────────────────
while True:
    now = time.time()
    dt = now - prev_frame_t
    prev_frame_t = now
    if dt > 0:
        fps = int(0.92 * fps + 0.08 * (1.0 / dt))

    pulse_t += 0.12
    pulse_val = (math.sin(pulse_t) + 1.0) / 2.0

    rainbow_hue = (rainbow_hue + 1.8) % 180
    current_pen_color = get_rainbow_color(rainbow_hue) if active_color_name == "Rainbow" else active_color

    # 1. Read webcam frame
    success, img = cap.read()
    if not success or img is None:
        continue

    img = cv2.resize(img, (WEBCAM_WIDTH, WEBCAM_HEIGHT))
    img = cv2.flip(img, 1)

    # Dark Studio Mode effect
    if studio_mode:
        img = cv2.addWeighted(img, 0.35, np.zeros_like(img), 0.65, 0)

    # 2. Hand tracking
    img = detector.findHands(img, draw=False)
    lmList = detector.findPosition(img, draw=False)

    hovered_btn = None
    active_gesture = "READY"
    is_drawing_active = False

    if len(lmList) >= 21:
        fingers = detector.fingersUp()
        thumb_up = fingers[0]
        index_up = fingers[1]
        middle_up = fingers[2]
        ring_up = fingers[3]
        pinky_up = fingers[4]

        # Draw subtle futuristic neon joints on fingertips
        for id in [4, 8, 12, 16, 20]:
            cv2.circle(img, (lmList[id][1], lmList[id][2]), 4, (0, 240, 255), -1, lineType=cv2.LINE_AA)

        # Invariant gesture classification (works at shoulder level and any hand angle)
        is_palm = (sum(fingers) >= 4) or (index_up == 1 and middle_up == 1 and ring_up == 1 and pinky_up == 1)
        is_select = (index_up == 1 and middle_up == 1 and ring_up == 0 and pinky_up == 0) and not is_palm
        is_drawing = (index_up == 1) and not is_palm and not is_select

        # ─────────────────────────────────────────────────────
        # 🖐️ PALM ERASER (Instant, Full Screen)
        # ─────────────────────────────────────────────────────
        if is_palm:
            active_gesture = "PALM ERASER"
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
            shape_start = None

            palm_info = detector.getPalmCenter()
            palm_center = palm_info[0] if palm_info else None
            if palm_center:
                px, py = palm_center
                if prev_palm_x == 0 and prev_palm_y == 0:
                    prev_palm_x, prev_palm_y = px, py

                # Erase canvas smoothly
                cv2.circle(imgCanvas, (px, py), PALM_ERASER_RADIUS, (0, 0, 0), cv2.FILLED)
                cv2.line(imgCanvas, (prev_palm_x, prev_palm_y), (px, py), (0, 0, 0), PALM_ERASER_RADIUS * 2, lineType=cv2.LINE_AA)
                prev_palm_x, prev_palm_y = px, py

                # Futuristic holographic eraser shield
                cv2.circle(img, (px, py), PALM_ERASER_RADIUS, (255, 140, 40), 2, lineType=cv2.LINE_AA)
                cv2.circle(img, (px, py), PALM_ERASER_RADIUS + int(5 * pulse_val), (255, 200, 100), 1, lineType=cv2.LINE_AA)
                cv2.circle(img, (px, py), 4, (255, 255, 255), cv2.FILLED, lineType=cv2.LINE_AA)
                cv2.putText(img, "ERASING", (px - 34, py - PALM_ERASER_RADIUS - 8),
                            cv2.FONT_HERSHEY_DUPLEX, 0.44, (255, 200, 100), 1, lineType=cv2.LINE_AA)

        # ─────────────────────────────────────────────────────
        # ✌️ SELECTION & TOP BAR DWELL CONTROLS
        # ─────────────────────────────────────────────────────
        elif is_select:
            active_gesture = "SELECT"
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
            prev_palm_x, prev_palm_y = 0, 0
            shape_start = None

            x1, y1 = lmList[8][1], lmList[8][2]
            x2, y2 = lmList[12][1], lmList[12][2]
            mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2

            # Laser beam between fingertips with target crosshair
            cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 1, lineType=cv2.LINE_AA)
            cv2.circle(img, (mid_x, mid_y), 6, current_pen_color, cv2.FILLED, lineType=cv2.LINE_AA)
            cv2.circle(img, (mid_x, mid_y), 15 + int(pulse_val * 3), (0, 240, 255), 2, lineType=cv2.LINE_AA)

            # Check button collision
            for btn in BUTTONS:
                if btn["type"] == "color":
                    bx, by = btn["center"]
                    if math.hypot(mid_x - bx, mid_y - by) <= btn["radius"] + 8:
                        hovered_btn = btn
                        break
                elif btn["type"] in ["tool", "size", "glow", "studio", "action"]:
                    rx1, ry1, rx2, ry2 = btn["rect"]
                    if rx1 <= mid_x <= rx2 and ry1 <= mid_y <= ry2:
                        hovered_btn = btn
                        break

            # Dwell activation
            if hovered_btn is not None:
                if dwell_target == hovered_btn["id"]:
                    dwell_pct = min(1.0, (now - dwell_start_time) / DWELL_THRESHOLD)
                    # Neon progress ring
                    angle = int(dwell_pct * 360)
                    cv2.ellipse(img, (mid_x, mid_y), (18, 18), -90, 0, angle, (0, 255, 255), 2, lineType=cv2.LINE_AA)

                    if dwell_pct >= 1.0:
                        b_type = hovered_btn["type"]
                        if b_type == "tool":
                            active_tool = hovered_btn["tool"]
                            toast_msg = f"Tool: {active_tool}"
                        elif b_type == "color":
                            active_color_idx = hovered_btn["idx"]
                            active_color_name = hovered_btn["label"]
                            active_color = hovered_btn["color"]
                            toast_msg = f"Color: {active_color_name}"
                        elif b_type == "size":
                            active_size_idx = hovered_btn["idx"]
                            brush_size = hovered_btn["size"]
                            toast_msg = f"Size: {hovered_btn['label']} ({brush_size}px)"
                        elif b_type == "glow":
                            glow_mode = not glow_mode
                            toast_msg = f"Neon Glow: {'ON ✨' if glow_mode else 'OFF'}"
                        elif b_type == "studio":
                            studio_mode = not studio_mode
                            toast_msg = f"Dark Studio: {'ON 🌑' if studio_mode else 'OFF'}"
                        elif b_type == "action":
                            act = hovered_btn["action"]
                            if act == "undo":
                                undo_history()
                            elif act == "clear":
                                commit_history()
                                imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)
                                toast_msg = "Canvas Cleared"
                            elif act == "snapshot":
                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                save_path = os.path.join(SNAPSHOT_DIR, f"painting_{ts}.png")
                                m = (imgCanvas > 0)
                                out = np.where(m, imgCanvas, img)
                                cv2.imwrite(save_path, out)
                                flash_alpha = 1.0
                                toast_msg = f"Snapshot Saved: {ts}.png"
                            elif act == "record":
                                toggle_record()
                            elif act == "quit":
                                break

                        toast_timer = time.time() + 1.8
                        dwell_target = None
                else:
                    dwell_target = hovered_btn["id"]
                    dwell_start_time = now
            else:
                dwell_target = None

        # ─────────────────────────────────────────────────────
        # ☝️ DRAWING / SIGNATURE & SHAPES
        # ─────────────────────────────────────────────────────
        elif is_drawing:
            active_gesture = f"DRAW ({active_tool})"
            dwell_target = None
            prev_palm_x, prev_palm_y = 0, 0
            is_drawing_active = True

            x1, y1 = lmList[8][1], lmList[8][2]

            # Responsive smoothing
            if smooth_x == 0 and smooth_y == 0:
                smooth_x, smooth_y = x1, y1
                xp, yp = x1, y1
            else:
                smooth_x = int(smooth_x * 0.25 + x1 * 0.75)
                smooth_y = int(smooth_y * 0.25 + y1 * 0.75)

            # Avoid drawing inside the top header
            if smooth_y > TOP_BAR_HEIGHT + 5:
                # 1. Freehand PEN mode
                if active_tool == "PEN":
                    # Anti-jump safeguard (if hand relocated > 90px, start fresh stroke)
                    jump_dist = math.hypot(smooth_x - xp, smooth_y - yp)
                    if jump_dist > 90 or (xp == 0 and yp == 0):
                        xp, yp = smooth_x, smooth_y

                    # Optional Neon Glow aura
                    if glow_mode:
                        halo_c = tuple(int(c * 0.40) for c in current_pen_color)
                        cv2.line(imgCanvas, (xp, yp), (smooth_x, smooth_y), halo_c, brush_size + 16, lineType=cv2.LINE_AA)

                    # Core calligraphic vector stroke
                    cv2.line(imgCanvas, (xp, yp), (smooth_x, smooth_y), current_pen_color, brush_size, lineType=cv2.LINE_AA)
                    cv2.circle(imgCanvas, (smooth_x, smooth_y), brush_size // 2, current_pen_color, -1, lineType=cv2.LINE_AA)
                    xp, yp = smooth_x, smooth_y

                # 2. Geometric Shape Modes (LINE, RECT, CIRCLE)
                else:
                    if shape_start is None:
                        shape_start = (smooth_x, smooth_y)

            else:
                xp, yp = 0, 0

            # Reticle at index fingertip
            cv2.circle(img, (smooth_x, smooth_y), max(3, brush_size // 2) + 4, (255, 255, 255), 1, lineType=cv2.LINE_AA)
            cv2.circle(img, (smooth_x, smooth_y), max(2, brush_size // 2), current_pen_color, -1, lineType=cv2.LINE_AA)

        else:
            # Neutral / Standby gesture
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
            prev_palm_x, prev_palm_y = 0, 0
            dwell_target = None

    else:
        # Hand out of frame
        xp, yp = 0, 0
        smooth_x, smooth_y = 0, 0
        prev_palm_x, prev_palm_y = 0, 0
        dwell_target = None

    # Handle shape commit when finger is lifted / drawing ends
    if was_drawing_last_frame and not is_drawing_active:
        if active_tool != "PEN" and shape_start is not None and smooth_y > TOP_BAR_HEIGHT:
            sx, sy = shape_start
            ex, ey = smooth_x, smooth_y

            if glow_mode:
                halo_c = tuple(int(c * 0.40) for c in current_pen_color)
                if active_tool == "LINE":
                    cv2.line(imgCanvas, (sx, sy), (ex, ey), halo_c, brush_size + 16, lineType=cv2.LINE_AA)
                elif active_tool == "RECT":
                    cv2.rectangle(imgCanvas, (sx, sy), (ex, ey), halo_c, brush_size + 14, lineType=cv2.LINE_AA)
                elif active_tool == "CIRC":
                    r = int(math.hypot(ex - sx, ey - sy))
                    cv2.circle(imgCanvas, (sx, sy), r, halo_c, brush_size + 14, lineType=cv2.LINE_AA)

            if active_tool == "LINE":
                cv2.line(imgCanvas, (sx, sy), (ex, ey), current_pen_color, brush_size, lineType=cv2.LINE_AA)
            elif active_tool == "RECT":
                cv2.rectangle(imgCanvas, (sx, sy), (ex, ey), current_pen_color, brush_size, lineType=cv2.LINE_AA)
            elif active_tool == "CIRC":
                r = int(math.hypot(ex - sx, ey - sy))
                cv2.circle(imgCanvas, (sx, sy), r, current_pen_color, brush_size, lineType=cv2.LINE_AA)

            commit_history()
            shape_start = None

        elif active_tool == "PEN":
            commit_history()

    was_drawing_last_frame = is_drawing_active

    # ─────────────────────────────────────────────────────────
    # MERGE CANVAS ONTO WEBCAM (Ultra-Fast)
    # ─────────────────────────────────────────────────────────
    canvas_mask = (imgCanvas > 0)
    img = np.where(canvas_mask, imgCanvas, img)

    # Render interactive live preview for active geometric shape
    if is_drawing_active and active_tool != "PEN" and shape_start is not None and smooth_y > TOP_BAR_HEIGHT:
        sx, sy = shape_start
        ex, ey = smooth_x, smooth_y
        if active_tool == "LINE":
            cv2.line(img, (sx, sy), (ex, ey), current_pen_color, brush_size, lineType=cv2.LINE_AA)
        elif active_tool == "RECT":
            cv2.rectangle(img, (sx, sy), (ex, ey), current_pen_color, brush_size, lineType=cv2.LINE_AA)
        elif active_tool == "CIRC":
            r = int(math.hypot(ex - sx, ey - sy))
            cv2.circle(img, (sx, sy), r, current_pen_color, brush_size, lineType=cv2.LINE_AA)

    # ─────────────────────────────────────────────────────────
    # RENDER PRO STUDIO HEADER (Spacious, Elegant, Tactile)
    # ─────────────────────────────────────────────────────────
    # 1. Dark Glass Background
    bar_roi = img[0:TOP_BAR_HEIGHT, 0:WEBCAM_WIDTH]
    bar_bg = np.full_like(bar_roi, (18, 22, 30))
    cv2.addWeighted(bar_bg, 0.90, bar_roi, 0.10, 0, bar_roi)

    # Bottom border line with active color highlight
    cv2.line(img, (0, TOP_BAR_HEIGHT - 2), (WEBCAM_WIDTH, TOP_BAR_HEIGHT - 2), (40, 50, 70), 1)
    cv2.line(img, (0, TOP_BAR_HEIGHT - 1), (WEBCAM_WIDTH, TOP_BAR_HEIGHT - 1), current_pen_color, 2)

    # Brand Title & Dynamic Mode Pill (Left Side: x: 18 -> 190)
    cv2.putText(img, "NEO STUDIO", (20, 36), cv2.FONT_HERSHEY_DUPLEX, 0.68, (255, 255, 255), 2, lineType=cv2.LINE_AA)

    # Dynamic status pill
    mode_color = (150, 150, 150)
    if "DRAW" in active_gesture:
        mode_color = current_pen_color
    elif active_gesture == "PALM ERASER":
        mode_color = (255, 140, 40)
    elif active_gesture == "SELECT":
        mode_color = (0, 240, 255)

    pill_bg = img[48:78, 20:188]
    p_box = np.full_like(pill_bg, (28, 34, 46))
    cv2.addWeighted(p_box, 0.85, pill_bg, 0.15, 0, pill_bg)
    cv2.rectangle(img, (20, 48), (188, 78), (50, 60, 80), 1, lineType=cv2.LINE_AA)
    cv2.circle(img, (34, 63), 5, mode_color, -1, lineType=cv2.LINE_AA)
    cv2.putText(img, active_gesture, (46, 68), cv2.FONT_HERSHEY_DUPLEX, 0.40, (240, 240, 240), 1, lineType=cv2.LINE_AA)

    # Vertical Section Separators
    cv2.line(img, (196, 16), (196, TOP_BAR_HEIGHT - 16), (40, 50, 70), 1)
    cv2.line(img, (442, 16), (442, TOP_BAR_HEIGHT - 16), (40, 50, 70), 1)
    cv2.line(img, (745, 16), (745, TOP_BAR_HEIGHT - 16), (40, 50, 70), 1)
    cv2.line(img, (960, 16), (960, TOP_BAR_HEIGHT - 16), (40, 50, 70), 1)

    # Section Headers
    cv2.putText(img, "TOOL", (206, 20), cv2.FONT_HERSHEY_DUPLEX, 0.35, (140, 155, 175), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, "PALETTE", (452, 20), cv2.FONT_HERSHEY_DUPLEX, 0.35, (140, 155, 175), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, "STROKE & FX", (755, 20), cv2.FONT_HERSHEY_DUPLEX, 0.35, (140, 155, 175), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, "ACTIONS", (970, 20), cv2.FONT_HERSHEY_DUPLEX, 0.35, (140, 155, 175), 1, lineType=cv2.LINE_AA)

    # 2. Render Interactive Buttons
    for btn in BUTTONS:
        b_type = btn["type"]
        is_hovered = (hovered_btn is not None and hovered_btn["id"] == btn["id"])

        if b_type == "tool":
            rx1, ry1, rx2, ry2 = btn["rect"]
            is_active = (btn["tool"] == active_tool)

            bg_c = (32, 40, 54) if not is_hovered else (48, 65, 88)
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), bg_c, -1)

            border_c = current_pen_color if is_active else ((0, 240, 255) if is_hovered else (50, 60, 80))
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), border_c, 2 if is_active else 1, lineType=cv2.LINE_AA)

            (tw, th), _ = cv2.getTextSize(btn["label"], cv2.FONT_HERSHEY_DUPLEX, 0.40, 1)
            tx = rx1 + (rx2 - rx1 - tw) // 2
            ty = ry1 + (ry2 - ry1 + th) // 2
            txt_c = (255, 255, 255) if is_active else (200, 200, 200)
            cv2.putText(img, btn["label"], (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 0.40, txt_c, 1, lineType=cv2.LINE_AA)

        elif b_type == "color":
            cx, cy = btn["center"]
            r = btn["radius"]
            is_active = (btn["idx"] == active_color_idx)

            if btn["label"] == "Rainbow":
                cv2.circle(img, (cx, cy), r, current_pen_color, -1, lineType=cv2.LINE_AA)
                cv2.putText(img, "RGB", (cx - 11, cy + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (255, 255, 255), 1, lineType=cv2.LINE_AA)
            else:
                cv2.circle(img, (cx, cy), r, btn["color"], -1, lineType=cv2.LINE_AA)
                if btn["label"] == "White":
                    cv2.circle(img, (cx, cy), r, (140, 140, 140), 1, lineType=cv2.LINE_AA)

            if is_active:
                cv2.circle(img, (cx, cy), r + 4, (255, 255, 255), 2, lineType=cv2.LINE_AA)
                cv2.circle(img, (cx, cy), r + 6, current_pen_color, 1, lineType=cv2.LINE_AA)
            elif is_hovered:
                cv2.circle(img, (cx, cy), r + 4, (0, 240, 255), 2, lineType=cv2.LINE_AA)

        elif b_type == "size":
            rx1, ry1, rx2, ry2 = btn["rect"]
            is_active = (btn["idx"] == active_size_idx)

            bg_c = (32, 40, 54) if not is_hovered else (48, 65, 88)
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), bg_c, -1)

            border_c = current_pen_color if is_active else ((0, 240, 255) if is_hovered else (50, 60, 80))
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), border_c, 2 if is_active else 1, lineType=cv2.LINE_AA)

            (tw, th), _ = cv2.getTextSize(btn["label"], cv2.FONT_HERSHEY_DUPLEX, 0.38, 1)
            tx = rx1 + (rx2 - rx1 - tw) // 2
            cv2.putText(img, btn["label"], (tx, ry1 + 20), cv2.FONT_HERSHEY_DUPLEX, 0.38, (220, 220, 220), 1, lineType=cv2.LINE_AA)
            dot_r = max(2, btn["size"] // 3)
            cx = (rx1 + rx2) // 2
            cv2.circle(img, (cx, ry1 + 32), dot_r, (255, 255, 255), -1, lineType=cv2.LINE_AA)

        elif b_type in ["glow", "studio"]:
            rx1, ry1, rx2, ry2 = btn["rect"]
            is_active = glow_mode if b_type == "glow" else studio_mode

            bg_c = (20, 55, 75) if is_active else ((32, 40, 54) if not is_hovered else (48, 65, 88))
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), bg_c, -1)

            border_c = (0, 255, 255) if is_active else ((0, 240, 255) if is_hovered else (50, 60, 80))
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), border_c, 2 if is_active else 1, lineType=cv2.LINE_AA)

            (tw, th), _ = cv2.getTextSize(btn["label"], cv2.FONT_HERSHEY_DUPLEX, 0.36, 1)
            tx = rx1 + (rx2 - rx1 - tw) // 2
            txt_c = (0, 255, 255) if is_active else (200, 200, 200)
            cv2.putText(img, btn["label"], (tx, ry1 + 24), cv2.FONT_HERSHEY_DUPLEX, 0.36, txt_c, 1, lineType=cv2.LINE_AA)
            state_str = "ON" if is_active else "OFF"
            (sw, _), _ = cv2.getTextSize(state_str, cv2.FONT_HERSHEY_SIMPLEX, 0.30, 1)
            cv2.putText(img, state_str, (rx1 + (rx2 - rx1 - sw) // 2, ry1 + 38), cv2.FONT_HERSHEY_SIMPLEX, 0.30, txt_c, 1, lineType=cv2.LINE_AA)

        elif b_type == "action":
            rx1, ry1, rx2, ry2 = btn["rect"]
            act = btn["action"]
            bg_c = btn["bg"]

            if act == "record" and is_recording:
                bg_c = (35, 30, 200) if (int(pulse_t * 3) % 2 == 0) else (85, 20, 80)
            elif is_hovered:
                bg_c = tuple(min(255, c + 35) for c in bg_c)

            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), bg_c, -1)
            border_c = (0, 240, 255) if is_hovered else (55, 65, 85)
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), border_c, 1, lineType=cv2.LINE_AA)

            btn_label = btn["label"]
            if act == "record" and is_recording:
                dur = int(now - rec_start_time)
                btn_label = f"{dur//60:02d}:{dur%60:02d}"

            (tw, th), _ = cv2.getTextSize(btn_label, cv2.FONT_HERSHEY_DUPLEX, 0.38, 1)
            tx = rx1 + (rx2 - rx1 - tw) // 2
            ty = ry1 + (ry2 - ry1 + th) // 2
            cv2.putText(img, btn_label, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 0.38, (255, 255, 255), 1, lineType=cv2.LINE_AA)

    # ─────────────────────────────────────────────────────────
    # MINIMAL BOTTOM STATUS BAR & TOAST
    # ─────────────────────────────────────────────────────────
    cv2.putText(img, f"FPS: {fps}  |  🖐️ Open Palm = Erase  |  ✌️ 2 Fingers = Select  |  [Z] Undo  |  [S] Snap  |  [V] Rec",
                (24, WEBCAM_HEIGHT - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 170, 195), 1, lineType=cv2.LINE_AA)

    # Toast banner
    if time.time() < toast_timer:
        (tw, th), _ = cv2.getTextSize(toast_msg, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
        tx1 = (WEBCAM_WIDTH - tw - 36) // 2
        ty1 = TOP_BAR_HEIGHT + 14
        tx2 = tx1 + tw + 36
        ty2 = ty1 + 32

        toast_roi = img[ty1:ty2, tx1:tx2]
        toast_bg = np.full_like(toast_roi, (18, 22, 30))
        cv2.addWeighted(toast_bg, 0.90, toast_roi, 0.10, 0, toast_roi)
        cv2.rectangle(img, (tx1, ty1), (tx2, ty2), (0, 240, 255), 1, lineType=cv2.LINE_AA)
        cv2.putText(img, toast_msg, (tx1 + 18, ty1 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, lineType=cv2.LINE_AA)

    # White flash on snapshot
    if flash_alpha > 0.05:
        white = np.ones_like(img, dtype=np.uint8) * 255
        cv2.addWeighted(white, flash_alpha, img, 1.0 - flash_alpha, 0, img)
        flash_alpha = max(0.0, flash_alpha - 0.25)

    # Write video frame if recording
    if is_recording and video_writer is not None:
        video_writer.write(img)

    # ─────────────────────────────────────────────────────────
    # DISPLAY & KEYBOARD SHORTCUTS
    # ─────────────────────────────────────────────────────────
    cv2.imshow("AI Virtual Painter", img)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break
    elif key == ord('z') or key == ord('Z'):
        undo_history()
    elif key == ord('p') or key == ord('P'):
        active_tool = "PEN"
        toast_msg = "Tool: PEN"
        toast_timer = time.time() + 1.5
    elif key == ord('l') or key == ord('L'):
        active_tool = "LINE"
        toast_msg = "Tool: LINE"
        toast_timer = time.time() + 1.5
    elif key == ord('r') or key == ord('R'):
        active_tool = "RECT"
        toast_msg = "Tool: RECTANGLE"
        toast_timer = time.time() + 1.5
    elif key == ord('o') or key == ord('O'):
        active_tool = "CIRC"
        toast_msg = "Tool: CIRCLE"
        toast_timer = time.time() + 1.5
    elif key == ord('v') or key == ord('V'):
        toggle_record()
    elif key == ord('s') or key == ord('S'):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join(SNAPSHOT_DIR, f"painting_{ts}.png")
        m = (imgCanvas > 0)
        out = np.where(m, imgCanvas, img)
        cv2.imwrite(save_path, out)
        flash_alpha = 1.0
        toast_msg = f"Snapshot Saved: {ts}.png"
        toast_timer = time.time() + 2.0
    elif key == ord('c') or key == ord('C'):
        commit_history()
        imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)
        toast_msg = "Canvas Cleared"
        toast_timer = time.time() + 1.5
    elif key == ord('g') or key == ord('G'):
        glow_mode = not glow_mode
        toast_msg = f"Neon Glow: {'ON ✨' if glow_mode else 'OFF'}"
        toast_timer = time.time() + 1.5
    elif key == ord('b') or key == ord('B'):
        studio_mode = not studio_mode
        toast_msg = f"Dark Studio: {'ON 🌑' if studio_mode else 'OFF'}"
        toast_timer = time.time() + 1.5
    elif key in [ord(str(n)) for n in range(1, 8)]:
        active_color_idx = key - ord('1')
        active_color_name = COLORS[active_color_idx][0]
        active_color = COLORS[active_color_idx][1]
        toast_msg = f"Color: {active_color_name}"
        toast_timer = time.time() + 1.5
    elif key == ord('+') or key == ord('='):
        brush_size = min(60, brush_size + 4)
        toast_msg = f"Size: {brush_size}px"
        toast_timer = time.time() + 1.5
    elif key == ord('-') or key == ord('_'):
        brush_size = max(2, brush_size - 4)
        toast_msg = f"Size: {brush_size}px"
        toast_timer = time.time() + 1.5

    # Exit cleanly if 'X' clicked
    if cv2.getWindowProperty("AI Virtual Painter", cv2.WND_PROP_VISIBLE) < 1:
        break

# Clean termination
if is_recording and video_writer is not None:
    video_writer.release()
detector.close()
cap.release()
cv2.destroyAllWindows()