from flask import Flask, Response, request, jsonify, render_template, redirect, url_for
import cv2
from processor import process_frame  # Frame işleme fonksiyonu

app = Flask(__name__)

# 🔧 GLOBAL AYARLAR
is_streaming = False
resolution = [640, 480]
fps = 30

actual_resolution = [640, 480]
actual_fps = 30

# 🔍 Kamera kaynaklarını otomatik tara
def detect_cameras(max_sources=10):
    available_sources = []
    for i in range(max_sources):
        cap = cv2.VideoCapture(i)
        if cap is not None and cap.isOpened():
            available_sources.append(i)
            cap.release()
    return available_sources

# 📷 OTO ALGILANAN KAMERA KAYNAKLARI
camera_sources = detect_cameras()
print(f"[INFO] Algılanan kameralar: {camera_sources}")


def generate_combined_stream(sources):
    caps = [cv2.VideoCapture(src) for src in sources]
    for cap in caps:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        cap.set(cv2.CAP_PROP_FPS, fps)

    while is_streaming:
        frames = []
        for cap in caps:
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.resize(frame, tuple(resolution))
            processed = process_frame(frame)
            frames.append(processed)

        if not frames:
            break

        try:
            if len(frames) == 1:
                combined = frames[0]
            elif len(frames) == 2:
                combined = cv2.hconcat(frames)
            elif len(frames) <= 4:
                row1 = cv2.hconcat(frames[:2])
                row2 = cv2.hconcat(frames[2:]) if len(frames) > 2 else row1
                combined = cv2.vconcat([row1, row2])
            else:
                # Çok fazla kamera varsa hepsini yatay hizala
                combined = cv2.hconcat(frames)
        except Exception as e:
            print(f"[ERROR] Frame birleştirme hatası: {e}")
            continue

        _, buffer = cv2.imencode('.jpg', combined)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    for cap in caps:
        cap.release()


@app.route('/video_feed')
def video_feed():
    return Response(generate_combined_stream(camera_sources),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/start')
def start():
    global is_streaming
    is_streaming = True
    return "Stream started"


@app.route('/stop')
def stop():
    global is_streaming
    is_streaming = False
    return "Stream stopped"


@app.route('/video_page')
def video_page():
    return """
    <html>
    <body>
        <h2>Streaming Multiple Cameras (Merged View)</h2>
        <img src="/video_feed" /><br><br>

        <form action="/stop" method="get">
            <button type="submit">🛑 Stop Stream</button>
        </form>
    </body>
    </html>
    """


@app.route('/set_params', methods=['GET', 'POST'])
def set_params():
    global resolution, fps, actual_resolution, actual_fps, is_streaming

    if request.method == 'POST':
        try:
            width = int(request.form.get('width'))
            height = int(request.form.get('height'))
            fps_value = int(request.form.get('fps'))

            resolution = [width, height]
            fps = fps_value
            is_streaming = True

            # İlk kameradan gerçek değerleri test et
            if camera_sources:
                cap = cv2.VideoCapture(camera_sources[0])
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
                cap.set(cv2.CAP_PROP_FPS, fps)

                actual_resolution = [
                    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                ]
                actual_fps = int(cap.get(cv2.CAP_PROP_FPS))
                cap.release()

            print(f"[INFO] Yeni parametreler: İstenen={resolution}@{fps}, Gerçek={actual_resolution}@{actual_fps}")
            return redirect(url_for('video_page'))

        except Exception as e:
            print(f"[ERROR] Formdan değer alınamadı: {e}")
            return "Invalid input!", 400

    return render_template('setParams.html', resolution=resolution, fps=fps)


@app.route('/status')
def status():
    return jsonify({
        "is_streaming": is_streaming,
        "requested_resolution": resolution,
        "requested_fps": fps,
        "actual_resolution": actual_resolution,
        "actual_fps": actual_fps,
        "camera_sources": camera_sources
    })


if __name__ == '__main__':
    app.run(debug=True)
