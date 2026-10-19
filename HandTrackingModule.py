import cv2
import mediapipe as mp
import os
import time

class HandDetector:
    def __init__(self, maxHands=1, detectionCon=0.48, trackCon=0.48):
        self.tipIds = [4, 8, 12, 16, 20]
        self.lmList = []
        self.results = None
        self.last_timestamp_ms = 0

        # Hand connections for drawing
        self.connections = [
            (0,1),(1,2),(2,3),(3,4),
            (0,5),(5,6),(6,7),(7,8),
            (9,10),(10,11),(11,12),
            (13,14),(14,15),(15,16),
            (17,18),(18,19),(19,20),
            (0,17),(5,9),(9,13),(13,17)
        ]

        # MediaPipe Tasks API in fast VIDEO mode
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hand_landmarker.task')
        if not os.path.exists(model_path):
            import urllib.request
            print("Downloading MediaPipe hand_landmarker.task model...")
            url = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
            urllib.request.urlretrieve(url, model_path)
            print("Downloaded hand_landmarker.task successfully.")

        base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=maxHands,
            min_hand_detection_confidence=detectionCon,
            min_tracking_confidence=trackCon
        )
        self.detector = mp.tasks.vision.HandLandmarker.create_from_options(options)

    def findHands(self, img, draw=True):
        imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=imgRGB)

        # Monotonic timestamp required for VIDEO mode
        current_time_ms = int(time.time() * 1000)
        if current_time_ms <= self.last_timestamp_ms:
            current_time_ms = self.last_timestamp_ms + 1
        self.last_timestamp_ms = current_time_ms

        self.results = self.detector.detect_for_video(mp_image, current_time_ms)

        if draw and self.results.hand_landmarks:
            for hand_landmarks in self.results.hand_landmarks:
                h, w, _ = img.shape
                points = []
                for lm in hand_landmarks:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    points.append((cx, cy))
                    cv2.circle(img, (cx, cy), 5, (255, 100, 255), cv2.FILLED)
                for start, end in self.connections:
                    cv2.line(img, points[start], points[end], (0, 220, 150), 2)
        return img

    def findPosition(self, img, handNo=0, draw=False):
        self.lmList = []
        if self.results and self.results.hand_landmarks:
            if handNo < len(self.results.hand_landmarks):
                hand_landmarks = self.results.hand_landmarks[handNo]
                h, w, _ = img.shape
                for id, lm in enumerate(hand_landmarks):
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    self.lmList.append([id, cx, cy])
                    if draw:
                        cv2.circle(img, (cx, cy), 5, (255, 0, 255), cv2.FILLED)
        return self.lmList

    def fingersUp(self):
        if not self.lmList or len(self.lmList) < 21:
            return [0, 0, 0, 0, 0]

        fingers = []

        # Thumb - check horizontal projection relative to IP joint with margin
        # Distinguish hand orientation roughly by comparing wrist (0) and pinky MCP (17)
        is_right_palm = self.lmList[17][1] > self.lmList[5][1]
        thumb_tip_x = self.lmList[self.tipIds[0]][1]
        thumb_ip_x = self.lmList[self.tipIds[0] - 1][1]

        if is_right_palm:
            fingers.append(1 if thumb_tip_x > thumb_ip_x + 5 else 0)
        else:
            fingers.append(1 if thumb_tip_x < thumb_ip_x - 5 else 0)

        # 4 Fingers: Index, Middle, Ring, Pinky
        # Add safety margin to prevent flickering when relaxed or angled
        for id in range(1, 5):
            tip_id = self.tipIds[id]
            tip_y = self.lmList[tip_id][2]
            pip_y = self.lmList[tip_id - 2][2]
            mcp_y = self.lmList[tip_id - 3][2]

            joint_len = abs(mcp_y - pip_y)
            # Threshold margin prevents jitter when middle finger is loosely held
            margin = max(10, int(joint_len * 0.22))

            if tip_y < (pip_y - margin):
                fingers.append(1)
            else:
                fingers.append(0)

        return fingers

    def getPalmCenter(self):
        if not self.lmList or len(self.lmList) < 21:
            return None, 60
        import math
        wx, wy = self.lmList[0][1], self.lmList[0][2]
        mx, my = self.lmList[9][1], self.lmList[9][2]
        center = ((wx + mx) // 2, (wy + my) // 2)
        dist = math.hypot(mx - wx, my - wy)
        radius = max(45, min(110, int(dist * 0.75)))
        return center, radius

    def close(self):
        try:
            if hasattr(self, 'detector') and self.detector:
                self.detector.close()
        except Exception:
            pass
