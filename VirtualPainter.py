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
TOP_BAR_HEIGHT = 92

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")
RECORDING_DIR = os.path.join(BASE_DIR, "recordings")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# PALETTE & BRUSH PRESETS
# ─────────────────────────────────────────────────────────────
COLORS = [
    ("Violet", (235, 70, 215)),    # #D946EF
    ("Cyan",   (255, 185, 0)),     # #06B6D4
    ("Mint",   (45, 230, 110)),    # #10B981
    ("Amber",  (0, 190, 255)),     # #F59E0B
    ("Coral",  (75, 75, 255)),     # #F43F5E
    ("White",  (255, 255, 255)),   # #FFFFFF
]

SIZES = [
    ("Thin", 6),
    ("Med",  14),
    ("Bold", 26)
]

PALM_ERASER_RADIUS = 65
TOOL_ERASER_RADIUS = 50

# ─────────────────────────────────────────────────────────────
# CAMERA SETUP (Lean, Robust, High FPS)
# ─────────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WEBCAM_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, WEBCAM_HEIGHT)

if not cap.isOpened():
    print("Error: Could not access webcam.")
    exit(1)

# Hand tracking detector (rotation & shoulder-level invariant)
detector = htm.HandDetector(detectionCon=0.48, trackCon=0.48, maxHands=1)

# Persistent Drawing Canvas (BGR)
imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)

# ─────────────────────────────────────────────────────────────
# STATE VARIABLES
# ─────────────────────────────────────────────────────────────
active_color_idx = 1
active_color = COLORS[active_color_idx][1]
active_color_name = COLORS[active_color_idx][0]

active_size_idx = 1
brush_size = SIZES[active_size_idx][1]
is_eraser_tool = False

# Coordinate tracking
xp, yp = 0, 0
smooth_x, smooth_y = 0, 0
prev_palm_x, prev_palm_y = 0, 0
grace_frames = 0

# Dwell Hover Selection
dwell_target = None
dwell_start_time = 0.0
DWELL_THRESHOLD = 0.30  # 300ms hover to activate

# Recording state
is_recording = False
video_writer = None
rec_start_time = 0.0
rec_file_path = ""

# Animation / Toast
flash_alpha = 0.0
toast_msg = "Studio Painter Ready | ☝️ Point to Draw | 🖐️ Open Palm Erases"
toast_timer = time.time() + 3.5
pulse_t = 0.0
prev_frame_t = time.time()
fps = 30

# ─────────────────────────────────────────────────────────────
# PROFESSIONAL STUDIO HEADER LAYOUT (Adequate Space & Clear Visuals)
# ─────────────────────────────────────────────────────────────
def build_studio_header():
    buttons = []

    # 1. Color Swatches (x: 220 to 520, y: 38)
    cx = 240
    for idx, (cname, bgr) in enumerate(COLORS):
        buttons.append({
            "id": f"color_{idx}",
            "type": "color",
            "idx": idx,
            "center": (cx, 48),
            "radius": 18,
            "color": bgr,
            "label": cname
        })
        cx += 48

    # 2. Brush Sizes (Pill cards: x: 550 to 760)
    sx = 555
    size_w = 62
    for s_idx, (sname, sz) in enumerate(SIZES):
        buttons.append({
            "id": f"size_{s_idx}",
            "type": "size",
            "idx": s_idx,
            "rect": (sx, 26, sx + size_w, 72),
            "label": sname,
            "size": sz
        })
        sx += size_w + 10

    # 3. Action Hub Buttons (x: 790 to 1250)
    ax = 785
    actions = [
        ("eraser",   "ERASER", 82,  (40, 48, 62)),
        ("clear",    "CLEAR",  76,  (40, 40, 58)),
        ("snapshot", "SNAP",   76,  (32, 60, 48)),
        ("record",   "REC",    86,  (65, 28, 38)),
        ("quit",     "EXIT",   64,  (55, 28, 28))
    ]
    for act_id, label, w, bg_c in actions:
        buttons.append({
            "id": f"act_{act_id}",
            "type": "action",
            "action": act_id,
            "rect": (ax, 26, ax + w, 72),
            "label": label,
            "bg": bg_c
        })
        ax += w + 10

    return buttons

BUTTONS = build_studio_header()

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

    # 1. Read webcam frame
    success, img = cap.read()
    if not success or img is None:
        continue

    img = cv2.resize(img, (WEBCAM_WIDTH, WEBCAM_HEIGHT))
    img = cv2.flip(img, 1)

    # 2. Hand tracking
    img = detector.findHands(img, draw=False)
    lmList = detector.findPosition(img, draw=False)

    hovered_btn = None
    active_gesture = "STANDBY"

    if len(lmList) >= 21:
        fingers = detector.fingersUp()
        thumb_up = fingers[0]
        index_up = fingers[1]
        middle_up = fingers[2]
        ring_up = fingers[3]
        pinky_up = fingers[4]

        # Draw subtle, high-tech neon joints on hand for visual feedback
        for id in [4, 8, 12, 16, 20]:
            cv2.circle(img, (lmList[id][1], lmList[id][2]), 4, (0, 240, 255), -1, lineType=cv2.LINE_AA)

        # Robust gesture classification (shoulder-level friendly)
        is_palm = (sum(fingers) >= 4) or (index_up == 1 and middle_up == 1 and ring_up == 1 and pinky_up == 1)
        is_select = (index_up == 1 and middle_up == 1 and ring_up == 0 and pinky_up == 0) and not is_palm
        is_drawing = (index_up == 1) and not is_palm and not is_select

        # ─────────────────────────────────────────────────────
        # 🖐️ PALM ERASER (Works anywhere including bottom)
        # ─────────────────────────────────────────────────────
        if is_palm:
            active_gesture = "PALM ERASER"
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
            grace_frames = 0

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

                # Clean holographic eraser shield
                cv2.circle(img, (px, py), PALM_ERASER_RADIUS, (255, 140, 40), 2, lineType=cv2.LINE_AA)
                cv2.circle(img, (px, py), PALM_ERASER_RADIUS + int(4 * pulse_val), (255, 200, 100), 1, lineType=cv2.LINE_AA)
                cv2.circle(img, (px, py), 4, (255, 255, 255), cv2.FILLED, lineType=cv2.LINE_AA)
                cv2.putText(img, "ERASING", (px - 34, py - PALM_ERASER_RADIUS - 8),
                            cv2.FONT_HERSHEY_DUPLEX, 0.44, (255, 200, 100), 1, lineType=cv2.LINE_AA)

        # ─────────────────────────────────────────────────────
        # ✌️ SELECTION & TOP BAR DWELL HOVER
        # ─────────────────────────────────────────────────────
        elif is_select:
            active_gesture = "SELECT"
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
            prev_palm_x, prev_palm_y = 0, 0
            grace_frames = 0

            x1, y1 = lmList[8][1], lmList[8][2]
            x2, y2 = lmList[12][1], lmList[12][2]
            mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2

            # Laser beam between fingertips with target crosshair
            cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 1, lineType=cv2.LINE_AA)
            cv2.circle(img, (mid_x, mid_y), 6, active_color if not is_eraser_tool else (200, 200, 200), cv2.FILLED, lineType=cv2.LINE_AA)
            cv2.circle(img, (mid_x, mid_y), 15 + int(pulse_val * 3), (0, 240, 255), 2, lineType=cv2.LINE_AA)

            # Check button collision
            for btn in BUTTONS:
                if btn["type"] == "color":
                    bx, by = btn["center"]
                    if math.hypot(mid_x - bx, mid_y - by) <= btn["radius"] + 8:
                        hovered_btn = btn
                        break
                elif btn["type"] in ["size", "action"]:
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
                        if b_type == "color":
                            active_color_idx = hovered_btn["idx"]
                            active_color = hovered_btn["color"]
                            active_color_name = hovered_btn["label"]
                            is_eraser_tool = False
                            toast_msg = f"Color: {active_color_name}"
                        elif b_type == "size":
                            active_size_idx = hovered_btn["idx"]
                            brush_size = hovered_btn["size"]
                            toast_msg = f"Size: {hovered_btn['label']} ({brush_size}px)"
                        elif b_type == "action":
                            act = hovered_btn["action"]
                            if act == "eraser":
                                is_eraser_tool = not is_eraser_tool
                                toast_msg = f"Tool: {'ERASER' if is_eraser_tool else active_color_name}"
                            elif act == "clear":
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
        # ☝️ DRAWING / SIGNATURE (Zero-Lag Smooth Line)
        # ─────────────────────────────────────────────────────
        elif is_drawing:
            active_gesture = "DRAW"
            dwell_target = None
            prev_palm_x, prev_palm_y = 0, 0
            grace_frames = 0

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
                # Anti-jump safeguard: if distance > 90px (hand relocated), start fresh stroke
                jump_dist = math.hypot(smooth_x - xp, smooth_y - yp)
                if jump_dist > 90 or (xp == 0 and yp == 0):
                    xp, yp = smooth_x, smooth_y

                curr_color = (0, 0, 0) if is_eraser_tool else active_color
                curr_thickness = TOOL_ERASER_RADIUS if is_eraser_tool else brush_size

                # Fast anti-aliased vector stroke with round cap
                cv2.line(imgCanvas, (xp, yp), (smooth_x, smooth_y), curr_color, curr_thickness, lineType=cv2.LINE_AA)
                cv2.circle(imgCanvas, (smooth_x, smooth_y), curr_thickness // 2, curr_color, -1, lineType=cv2.LINE_AA)
                xp, yp = smooth_x, smooth_y
            else:
                xp, yp = 0, 0

            # Reticle at fingertip
            cur_r = (TOOL_ERASER_RADIUS // 2) if is_eraser_tool else max(3, brush_size // 2)
            cv2.circle(img, (smooth_x, smooth_y), cur_r + 4, (255, 255, 255), 1, lineType=cv2.LINE_AA)
            cv2.circle(img, (smooth_x, smooth_y), cur_r, (0, 0, 0) if is_eraser_tool else active_color, -1, lineType=cv2.LINE_AA)

        else:
            # Standby gesture: allow 3 grace frames before terminating stroke
            grace_frames += 1
            if grace_frames > 3:
                xp, yp = 0, 0
                smooth_x, smooth_y = 0, 0
            prev_palm_x, prev_palm_y = 0, 0
            dwell_target = None

    else:
        # Hand out of frame: grace period avoids breaks
        grace_frames += 1
        if grace_frames > 3:
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
        prev_palm_x, prev_palm_y = 0, 0
        dwell_target = None

    # ─────────────────────────────────────────────────────────
    # MERGE CANVAS ONTO WEBCAM (Ultra-Fast)
    # ─────────────────────────────────────────────────────────
    canvas_mask = (imgCanvas > 0)
    img = np.where(canvas_mask, imgCanvas, img)

    # ─────────────────────────────────────────────────────────
    # RENDER STUDIO HEADER (Full-Width, Spacious & Attractive)
    # ─────────────────────────────────────────────────────────
    # 1. Dark Glass Background
    bar_roi = img[0:TOP_BAR_HEIGHT, 0:WEBCAM_WIDTH]
    bar_bg = np.full_like(bar_roi, (18, 22, 30))
    cv2.addWeighted(bar_bg, 0.90, bar_roi, 0.10, 0, bar_roi)

    # Bottom border line with active color highlight
    cv2.line(img, (0, TOP_BAR_HEIGHT - 2), (WEBCAM_WIDTH, TOP_BAR_HEIGHT - 2), (40, 50, 70), 1)
    cv2.line(img, (0, TOP_BAR_HEIGHT - 1), (WEBCAM_WIDTH, TOP_BAR_HEIGHT - 1), active_color if not is_eraser_tool else (200, 200, 200), 2)

    # Brand Title & Dynamic Mode Pill (Left Side: x: 20 -> 210)
    cv2.putText(img, "STUDIO PAINTER", (22, 36), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 2, lineType=cv2.LINE_AA)

    # Dynamic status pill
    mode_color = (150, 150, 150)
    if active_gesture == "DRAW":
        mode_color = active_color if not is_eraser_tool else (200, 200, 200)
    elif active_gesture == "PALM ERASER":
        mode_color = (255, 140, 40)
    elif active_gesture == "SELECT":
        mode_color = (0, 240, 255)

    pill_bg = img[48:78, 22:190]
    p_box = np.full_like(pill_bg, (28, 34, 46))
    cv2.addWeighted(p_box, 0.85, pill_bg, 0.15, 0, pill_bg)
    cv2.rectangle(img, (22, 48), (190, 78), (50, 60, 80), 1, lineType=cv2.LINE_AA)
    cv2.circle(img, (36, 63), 5, mode_color, -1, lineType=cv2.LINE_AA)
    cv2.putText(img, active_gesture, (48, 68), cv2.FONT_HERSHEY_DUPLEX, 0.44, (240, 240, 240), 1, lineType=cv2.LINE_AA)

    # Vertical Section Separators
    cv2.line(img, (210, 16), (210, TOP_BAR_HEIGHT - 16), (40, 50, 70), 1)
    cv2.line(img, (535, 16), (535, TOP_BAR_HEIGHT - 16), (40, 50, 70), 1)
    cv2.line(img, (765, 16), (765, TOP_BAR_HEIGHT - 16), (40, 50, 70), 1)

    # Section Headers
    cv2.putText(img, "PALETTE", (240, 22), cv2.FONT_HERSHEY_DUPLEX, 0.36, (140, 155, 175), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, "STROKE", (555, 22), cv2.FONT_HERSHEY_DUPLEX, 0.36, (140, 155, 175), 1, lineType=cv2.LINE_AA)
    cv2.putText(img, "ACTIONS", (785, 22), cv2.FONT_HERSHEY_DUPLEX, 0.36, (140, 155, 175), 1, lineType=cv2.LINE_AA)

    # 2. Render Interactive Buttons
    for btn in BUTTONS:
        b_type = btn["type"]
        is_hovered = (hovered_btn is not None and hovered_btn["id"] == btn["id"])

        if b_type == "color":
            cx, cy = btn["center"]
            r = btn["radius"]
            is_active = (btn["idx"] == active_color_idx and not is_eraser_tool)

            cv2.circle(img, (cx, cy), r, btn["color"], -1, lineType=cv2.LINE_AA)
            if btn["label"] == "White":
                cv2.circle(img, (cx, cy), r, (140, 140, 140), 1, lineType=cv2.LINE_AA)

            if is_active:
                cv2.circle(img, (cx, cy), r + 4, (255, 255, 255), 2, lineType=cv2.LINE_AA)
                cv2.circle(img, (cx, cy), r + 6, btn["color"], 1, lineType=cv2.LINE_AA)
            elif is_hovered:
                cv2.circle(img, (cx, cy), r + 4, (0, 240, 255), 2, lineType=cv2.LINE_AA)

        elif b_type == "size":
            rx1, ry1, rx2, ry2 = btn["rect"]
            is_active = (btn["idx"] == active_size_idx)

            bg_c = (32, 40, 54) if not is_hovered else (48, 65, 88)
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), bg_c, -1)

            # Active glowing border
            border_c = active_color if is_active else ((0, 240, 255) if is_hovered else (50, 60, 80))
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), border_c, 2 if is_active else 1, lineType=cv2.LINE_AA)

            # Label & preview circle
            cx = (rx1 + rx2) // 2
            cv2.putText(img, btn["label"], (rx1 + 10, ry1 + 20), cv2.FONT_HERSHEY_DUPLEX, 0.38, (220, 220, 220), 1, lineType=cv2.LINE_AA)
            dot_r = max(2, btn["size"] // 3)
            cv2.circle(img, (cx, ry1 + 32), dot_r, (255, 255, 255), -1, lineType=cv2.LINE_AA)

        elif b_type == "action":
            rx1, ry1, rx2, ry2 = btn["rect"]
            act = btn["action"]
            bg_c = btn["bg"]

            if act == "eraser" and is_eraser_tool:
                bg_c = (200, 100, 40)
            elif act == "record" and is_recording:
                bg_c = (35, 30, 200) if (int(pulse_t * 3) % 2 == 0) else (85, 20, 80)
            elif is_hovered:
                bg_c = tuple(min(255, c + 35) for c in bg_c)

            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), bg_c, -1)
            border_c = (0, 240, 255) if is_hovered else (55, 65, 85)
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), border_c, 1, lineType=cv2.LINE_AA)

            btn_label = btn["label"]
            if act == "record" and is_recording:
                dur = int(now - rec_start_time)
                btn_label = f"REC {dur//60:02d}:{dur%60:02d}"

            (tw, th), _ = cv2.getTextSize(btn_label, cv2.FONT_HERSHEY_DUPLEX, 0.42, 1)
            tx = rx1 + (rx2 - rx1 - tw) // 2
            ty = ry1 + (ry2 - ry1 + th) // 2
            cv2.putText(img, btn_label, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 0.42, (255, 255, 255), 1, lineType=cv2.LINE_AA)

    # ─────────────────────────────────────────────────────────
    # MINIMAL BOTTOM STATUS BAR & TOAST
    # ─────────────────────────────────────────────────────────
    # Clean bottom hint
    cv2.putText(img, f"FPS: {fps}  |  🖐️ Open Palm = Erase  |  ✌️ 2 Fingers = Select  |  [S] Snap  |  [R] Record",
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
    elif key == ord('r') or key == ord('R'):
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
        imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)
        toast_msg = "Canvas Cleared"
        toast_timer = time.time() + 1.5
    elif key == ord('e') or key == ord('E'):
        is_eraser_tool = not is_eraser_tool
        toast_msg = f"Tool: {'ERASER' if is_eraser_tool else active_color_name}"
        toast_timer = time.time() + 1.5
    elif key in [ord(str(n)) for n in range(1, 7)]:
        active_color_idx = key - ord('1')
        active_color_name = COLORS[active_color_idx][0]
        active_color = COLORS[active_color_idx][1]
        is_eraser_tool = False
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