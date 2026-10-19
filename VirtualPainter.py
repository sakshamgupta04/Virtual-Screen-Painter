import cv2
import numpy as np
import os
import time
import math
from datetime import datetime
import HandTrackingModule as htm

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────
WEBCAM_WIDTH = 1280
WEBCAM_HEIGHT = 720

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")
RECORDING_DIR = os.path.join(BASE_DIR, "recordings")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# PALETTE & SIZES
# ─────────────────────────────────────────────────────────────
COLORS = [
    ("Violet", (235, 70, 215)),    # #D946EF
    ("Cyan",   (255, 185, 0)),     # #06B6D4
    ("Green",  (45, 230, 110)),    # #10B981
    ("Amber",  (0, 190, 255)),     # #F59E0B
    ("Coral",  (75, 75, 255)),     # #F43F5E
    ("White",  (255, 255, 255)),   # #FFFFFF
]

SIZES = [
    ("Thin", 6),
    ("Med",  14),
    ("Bold", 26)
]

PALM_ERASER_RADIUS = 60
TOOL_ERASER_RADIUS = 50

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

# Canvas (BGR, 0 = black/transparent)
imgCanvas = np.zeros((WEBCAM_HEIGHT, WEBCAM_WIDTH, 3), np.uint8)

# ─────────────────────────────────────────────────────────────
# APPLICATION STATE
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
DWELL_THRESHOLD = 0.28  # Snappy 280ms hover to activate

# Recording state
is_recording = False
video_writer = None
rec_start_time = 0.0
rec_file_path = ""

# Animation / Toast
flash_alpha = 0.0
toast_msg = "Virtual Painter Ready | ☝️ Draw | 🖐️ Open Palm Erases"
toast_timer = time.time() + 3.0
pulse_t = 0.0
prev_frame_t = time.time()
fps = 30

# ─────────────────────────────────────────────────────────────
# FLOATING ISLAND TOOLBAR LAYOUT (Clean, Unified, Apple-like)
# ─────────────────────────────────────────────────────────────
BAR_X1, BAR_Y1 = 180, 14
BAR_X2, BAR_Y2 = 1100, 74

def build_toolbar():
    buttons = []
    # 1. Colors (Circles)
    cx = 220
    for idx, (cname, bgr) in enumerate(COLORS):
        buttons.append({
            "id": f"color_{idx}",
            "type": "color",
            "idx": idx,
            "center": (cx, 44),
            "radius": 16,
            "color": bgr,
            "label": cname
        })
        cx += 44

    # 2. Brush Sizes
    sx = 530
    for s_idx, (sname, sz) in enumerate(SIZES):
        buttons.append({
            "id": f"size_{s_idx}",
            "type": "size",
            "idx": s_idx,
            "center": (sx, 44),
            "radius": 16,
            "size": sz,
            "label": sname
        })
        sx += 42

    # 3. Action Buttons (Pill rects)
    actions = [
        ("eraser",   "ERASER", 740, 810, (40, 48, 60)),
        ("clear",    "CLEAR",  820, 890, (40, 40, 55)),
        ("snapshot", "SNAP",   900, 960, (35, 60, 50)),
        ("record",   "REC",    970, 1030, (60, 30, 40)),
        ("quit",     "X",      1040, 1076, (55, 30, 30))
    ]
    for act_id, label, x1, x2, bg_c in actions:
        buttons.append({
            "id": f"act_{act_id}",
            "type": "action",
            "action": act_id,
            "rect": (x1, 26, x2, 62),
            "label": label,
            "bg": bg_c
        })

    return buttons

TOOLBAR_BUTTONS = build_toolbar()

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
# MAIN LOOP
# ─────────────────────────────────────────────────────────────
while True:
    now = time.time()
    dt = now - prev_frame_t
    prev_frame_t = now
    if dt > 0:
        fps = int(0.9 * fps + 0.1 * (1.0 / dt))

    pulse_t += 0.12
    pulse_val = (math.sin(pulse_t) + 1.0) / 2.0

    # 1. Capture webcam frame
    success, img = cap.read()
    if not success or img is None:
        continue

    img = cv2.resize(img, (WEBCAM_WIDTH, WEBCAM_HEIGHT))
    img = cv2.flip(img, 1)

    # 2. Hand tracking
    img = detector.findHands(img, draw=False)
    lmList = detector.findPosition(img, draw=False)

    hovered_btn = None
    selection_point = None
    active_gesture = "STANDBY"

    if len(lmList) >= 21:
        fingers = detector.fingersUp()
        thumb_up = fingers[0]
        index_up = fingers[1]
        middle_up = fingers[2]
        ring_up = fingers[3]
        pinky_up = fingers[4]

        # Gesture classification
        is_palm = (sum(fingers) >= 4) or (index_up == 1 and middle_up == 1 and ring_up == 1 and pinky_up == 1)
        is_select = (index_up == 1 and middle_up == 1 and ring_up == 0 and pinky_up == 0) and not is_palm
        is_drawing = (index_up == 1) and not is_palm and not is_select

        # ── 🖐️ PALM ERASER (Instant & Full Screen) ──
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

                # Erase canvas
                cv2.circle(imgCanvas, (px, py), PALM_ERASER_RADIUS, (0, 0, 0), cv2.FILLED)
                cv2.line(imgCanvas, (prev_palm_x, prev_palm_y), (px, py), (0, 0, 0), PALM_ERASER_RADIUS * 2, lineType=cv2.LINE_AA)
                prev_palm_x, prev_palm_y = px, py

                # Clean holographic eraser ring
                cv2.circle(img, (px, py), PALM_ERASER_RADIUS, (255, 140, 50), 2, lineType=cv2.LINE_AA)
                cv2.circle(img, (px, py), PALM_ERASER_RADIUS + int(4 * pulse_val), (255, 200, 100), 1, lineType=cv2.LINE_AA)
                cv2.circle(img, (px, py), 4, (255, 255, 255), cv2.FILLED, lineType=cv2.LINE_AA)

        # ── ✌️ SELECTION & TOOLBAR DWELL HOVER ──
        elif is_select:
            active_gesture = "SELECT"
            xp, yp = 0, 0
            smooth_x, smooth_y = 0, 0
            prev_palm_x, prev_palm_y = 0, 0
            grace_frames = 0

            x1, y1 = lmList[8][1], lmList[8][2]
            x2, y2 = lmList[12][1], lmList[12][2]
            mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2
            selection_point = (mid_x, mid_y)

            # Sleek dual-finger reticle
            cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 1, lineType=cv2.LINE_AA)
            cv2.circle(img, (mid_x, mid_y), 6, active_color if not is_eraser_tool else (200, 200, 200), cv2.FILLED, lineType=cv2.LINE_AA)
            cv2.circle(img, (mid_x, mid_y), 14, (0, 240, 255), 1, lineType=cv2.LINE_AA)

            # Check button collision
            for btn in TOOLBAR_BUTTONS:
                if btn["type"] in ["color", "size"]:
                    bx, by = btn["center"]
                    if math.hypot(mid_x - bx, mid_y - by) <= btn["radius"] + 8:
                        hovered_btn = btn
                        break
                elif btn["type"] == "action":
                    rx1, ry1, rx2, ry2 = btn["rect"]
                    if rx1 <= mid_x <= rx2 and ry1 <= mid_y <= ry2:
                        hovered_btn = btn
                        break

            # Dwell activation
            if hovered_btn is not None:
                if dwell_target == hovered_btn["id"]:
                    dwell_pct = min(1.0, (now - dwell_start_time) / DWELL_THRESHOLD)
                    # Neon progress arc around cursor
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
                                toast_msg = f"Pen Mode: {'ERASER' if is_eraser_tool else active_color_name}"
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

        # ── ☝️ DRAWING / SIGNATURE (Zero-Lag Smooth Line) ──
        elif is_drawing:
            active_gesture = "DRAW"
            dwell_target = None
            prev_palm_x, prev_palm_y = 0, 0
            grace_frames = 0

            x1, y1 = lmList[8][1], lmList[8][2]

            # Responsive EMA: 70% current position for zero-lag signatures
            if smooth_x == 0 and smooth_y == 0:
                smooth_x, smooth_y = x1, y1
                xp, yp = x1, y1
            else:
                smooth_x = int(smooth_x * 0.30 + x1 * 0.70)
                smooth_y = int(smooth_y * 0.30 + y1 * 0.70)

            # Draw onto canvas if outside toolbar
            if smooth_y > BAR_Y2 + 5:
                curr_color = (0, 0, 0) if is_eraser_tool else active_color
                curr_thickness = TOOL_ERASER_RADIUS if is_eraser_tool else brush_size

                # Fast anti-aliased stroke + round cap
                cv2.line(imgCanvas, (xp, yp), (smooth_x, smooth_y), curr_color, curr_thickness, lineType=cv2.LINE_AA)
                cv2.circle(imgCanvas, (smooth_x, smooth_y), curr_thickness // 2, curr_color, -1, lineType=cv2.LINE_AA)
                xp, yp = smooth_x, smooth_y
            else:
                xp, yp = 0, 0

            # Minimalist reticle at index fingertip
            cur_r = (TOOL_ERASER_RADIUS // 2) if is_eraser_tool else max(3, brush_size // 2)
            cv2.circle(img, (smooth_x, smooth_y), cur_r + 4, (255, 255, 255), 1, lineType=cv2.LINE_AA)
            cv2.circle(img, (smooth_x, smooth_y), cur_r, (0, 0, 0) if is_eraser_tool else active_color, -1, lineType=cv2.LINE_AA)

        else:
            # Standby gesture: allow 3 grace frames before breaking stroke
            grace_frames += 1
            if grace_frames > 3:
                xp, yp = 0, 0
                smooth_x, smooth_y = 0, 0
            prev_palm_x, prev_palm_y = 0, 0
            dwell_target = None

    else:
        # Hand out of frame: grace period avoids broken strokes on quick flicks
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
    # RENDER FLOATING ISLAND TOOLBAR (ROI Blend: 0.2ms)
    # ─────────────────────────────────────────────────────────
    # 1. Island Backdrop
    roi = img[BAR_Y1:BAR_Y2, BAR_X1:BAR_X2]
    island_bg = np.full_like(roi, (18, 22, 30))
    cv2.addWeighted(island_bg, 0.90, roi, 0.10, 0, roi)

    # Outer border
    cv2.rectangle(img, (BAR_X1, BAR_Y1), (BAR_X2, BAR_Y2), (45, 55, 75), 1, lineType=cv2.LINE_AA)

    # Dividers
    cv2.line(img, (495, BAR_Y1 + 10), (495, BAR_Y2 - 10), (40, 50, 70), 1)
    cv2.line(img, (670, BAR_Y1 + 10), (670, BAR_Y2 - 10), (40, 50, 70), 1)

    # 2. Render Buttons
    for btn in TOOLBAR_BUTTONS:
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
            cx, cy = btn["center"]
            r = btn["radius"]
            is_active = (btn["idx"] == active_size_idx)

            bg_c = (35, 42, 55) if not is_hovered else (55, 70, 95)
            cv2.circle(img, (cx, cy), r, bg_c, -1, lineType=cv2.LINE_AA)
            dot_r = max(2, btn["size"] // 3)
            cv2.circle(img, (cx, cy), dot_r, (255, 255, 255), -1, lineType=cv2.LINE_AA)

            if is_active:
                cv2.circle(img, (cx, cy), r, active_color if not is_eraser_tool else (200, 200, 200), 2, lineType=cv2.LINE_AA)
            elif is_hovered:
                cv2.circle(img, (cx, cy), r, (0, 240, 255), 1, lineType=cv2.LINE_AA)

        elif b_type == "action":
            rx1, ry1, rx2, ry2 = btn["rect"]
            act = btn["action"]
            bg_c = btn["bg"]

            if act == "eraser" and is_eraser_tool:
                bg_c = (200, 100, 40)
            elif act == "record" and is_recording:
                bg_c = (30, 30, 200) if (int(pulse_t * 3) % 2 == 0) else (80, 20, 80)
            elif is_hovered:
                bg_c = tuple(min(255, c + 35) for c in bg_c)

            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), bg_c, -1)
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), (0, 240, 255) if is_hovered else (50, 60, 80), 1, lineType=cv2.LINE_AA)

            btn_label = btn["label"]
            if act == "record" and is_recording:
                dur = int(now - rec_start_time)
                btn_label = f"{dur//60:02d}:{dur%60:02d}"

            # Centered text
            (tw, th), _ = cv2.getTextSize(btn_label, cv2.FONT_HERSHEY_DUPLEX, 0.40, 1)
            tx = rx1 + (rx2 - rx1 - tw) // 2
            ty = ry1 + (ry2 - ry1 + th) // 2
            cv2.putText(img, btn_label, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 0.40, (255, 255, 255), 1, lineType=cv2.LINE_AA)

    # ─────────────────────────────────────────────────────────
    # MINIMAL STATUS BADGE & TOAST (Clean, Uncluttered)
    # ─────────────────────────────────────────────────────────
    # Status indicator in bottom-left corner
    cv2.putText(img, f"FPS: {fps}  |  {active_gesture}  |  🖐️ Palm = Erase", (24, WEBCAM_HEIGHT - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 200), 1, lineType=cv2.LINE_AA)

    # Toast banner
    if time.time() < toast_timer:
        (tw, th), _ = cv2.getTextSize(toast_msg, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
        tx1 = (WEBCAM_WIDTH - tw - 36) // 2
        ty1 = BAR_Y2 + 14
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

    # Write frame if recording
    if is_recording and video_writer is not None:
        video_writer.write(img)

    # ─────────────────────────────────────────────────────────
    # SHOW WINDOW & HANDLE KEYS
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
        toast_msg = f"Pen Mode: {'ERASER' if is_eraser_tool else active_color_name}"
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

    # Exit cleanly if 'X' button clicked
    if cv2.getWindowProperty("AI Virtual Painter", cv2.WND_PROP_VISIBLE) < 1:
        break

# Clean exit
if is_recording and video_writer is not None:
    video_writer.release()
detector.close()
cap.release()
cv2.destroyAllWindows()