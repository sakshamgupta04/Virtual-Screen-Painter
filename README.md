# 🎨 NEO Virtual Painter — AI Hand Canvas

A high-performance, real-time AI Virtual Painter powered by Python, OpenCV, and MediaPipe Tasks.

### ✨ Features
- 🖐️ **Natural Palm Eraser**: Open your hand / palm to dynamically wipe and erase across the entire screen!
- ✍️ **Fast Signature & Calligraphy Pen**: Responsive adaptive tracking eliminates lag and dropped strokes.
- 📐 **Geometric Shape Drawer**: Draw crisp **Straight Lines**, **Rectangles**, and **Circles** with live dynamic previews.
- ↩️ **Undo / History Stack**: One-click undo to step backwards through your strokes.
- ✨ **Neon Glow Ink Effect**: Add a luminous bloom halo to strokes for high-tech neon artwork.
- 🌑 **Dark Studio Backdrop Mode**: Dims the webcam background into a sleek dark canvas so your art pops with maximum contrast.
- 🎥 **Full Video Recording**: Record your drawing sessions with timer HUD and save directly to [`recordings/`](file:///c:/Users/Saksham%20Gupta/OneDrive/Desktop/VirtualPainter-/recordings/).
- 📸 **Snapshot Export**: Instant high-res export to [`snapshots/`](file:///c:/Users/Saksham%20Gupta/OneDrive/Desktop/VirtualPainter-/snapshots/) with shutter flash animation.
- 🎨 **AAA Cyber Glassmorphic Studio Bar**:
  - **4 Tools**: Freehand Pen, Straight Line, Rectangle, Circle.
  - **7 Color Swatches**: Violet, Cyan, Mint, Amber, Coral, White, RGB Rainbow.
  - **Stroke Sizing**: Small, Medium, Large.
  - **Hands-Free Dwell Selection**: Aim with two fingers; animated neon progress ring activates any tool.

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
| ☝️ **Index finger pointing** | **Draw / Sketch** with active tool (Pen, Line, Rect, Circle) |
| 🖐️ **Open Palm (4-5 fingers)** | **Palm Eraser** (wipes away strokes anywhere the palm moves) |
| ✌️ **Two fingers (Index + Middle)** | **Selection mode** (aim at top bar to pick tools, colors, undo, save) |

### Keyboard Shortcuts
| Key | Action |
|---|---|
| `P` / `L` / `R` / `O` | Select Tool: **P**en, **L**ine, **R**ectangle, Circle (**O**) |
| `Z` | **Undo** last stroke |
| `G` | Toggle **Neon Glow Mode** |
| `B` | Toggle **Dark Studio Backdrop** |
| `V` | **Toggle Video Recording** (`./recordings/`) |
| `S` | **Save Snapshot** (`./snapshots/`) |
| `C` | **Clear Canvas** |
| `1` – `7` | Select Color (Violet, Cyan, Mint, Amber, Coral, White, Rainbow) |
| `+` / `-` | Adjust brush size |
| `Q` / `Esc` | Exit application |
