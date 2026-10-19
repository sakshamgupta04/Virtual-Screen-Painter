# 🎨 NEO Virtual Painter — AI Hand Canvas

A high-performance, real-time AI Virtual Painter powered by Python, OpenCV, and MediaPipe Tasks.

### ✨ Features
- 🖐️ **Natural Palm Eraser**: Open your hand / palm to dynamically wipe and erase across the entire screen!
- ✍️ **Fast Signature & Calligraphy Engine**: Adaptive velocity smoothing + dense sub-step spline interpolation eliminates all lag, stutter, and on-and-off line drops during fast writing.
- ⚡ **60 FPS Hardware Acceleration**: DirectShow MJPG pipeline running at a rock-solid 60 FPS.
- 🎥 **Full Video Recording**: Record your drawing sessions with real-time HUD and save directly to [`recordings/`](file:///c:/Users/Saksham%20Gupta/OneDrive/Desktop/VirtualPainter-/recordings/).
- 📸 **Artwork Snapshot Export**: Instant high-res export to [`snapshots/`](file:///c:/Users/Saksham%20Gupta/OneDrive/Desktop/VirtualPainter-/snapshots/) with shutter flash animation.
- ✨ **Glow Ink & Rainbow Modes**: Toggle luminous neon bloom halo effects or cycle through rainbow spectrum hues.
- 🎨 **AAA Cyber Glassmorphic Studio Bar**:
  - **7 Color Swatches**: Violet, Cyan, Mint, Amber, Coral, White, RGB Rainbow.
  - **5 Brush Sizes**: XS (4px), S (8px), M (16px), L (28px), XL (44px).
  - **Hands-Free Dwell Selection**: Aim with two fingers; animated neon progress ring triggers actions.

---

### Installation & Setup
```bash
pip install -r requirements.txt
```

### How to Run
```bash
python VirtualPainter.py
```
*(Or double-click `run.bat`)*

---

### Gesture Controls
| Gesture | Action |
|---|---|
| ☝️ **Index finger pointing** | **Sign / Draw** with zero lag and anti-aliased calligraphy |
| 🖐️ **Open Palm (4-5 fingers)** | **Palm Eraser** (wipes away strokes anywhere the palm moves) |
| ✌️ **Two fingers (Index + Middle)** | **Selection mode** (aim at top bar to pick colors, sizes, record, snapshot) |

### Keyboard Shortcuts
| Key | Action |
|---|---|
| `R` | **Toggle Video Recording** (starts/stops recording to `./recordings/`) |
| `S` | **Save Snapshot** (saves PNG to `./snapshots/`) |
| `C` | **Clear Canvas** |
| `G` | **Toggle Glow Ink Mode** (luminous neon aura) |
| `1` – `7` | Select Color (Violet, Cyan, Mint, Amber, Coral, White, Rainbow) |
| `+` / `-` | Increase / Decrease brush size |
| `Q` / `Esc` | Exit application |
