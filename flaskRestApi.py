from flask import Flask, Response, request, jsonify, render_template, redirect, url_for
import cv2
from streamer import stream_from_camera
from processor import process_frame

app = Flask(__name__)

# GLOBAL DEĞERLER
is_streaming = False
resolution = [640, 480]
fps = 30

# KAMERA GERÇEK AYARLARI
actual_resolution = [640, 480]
actual_fps = 30

def generate():
    global resolution, fps, actual_resolution, actual_fps
    cap = cv2.VideoCapture(0)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
    cap.set(cv2.CAP_PROP_FPS, fps)

    # GERÇEK DEĞERLERİ AL
    actual_resolution = [
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ]
    actual_fps = int(cap.get(cv2.CAP_PROP_FPS))

    while is_streaming:
        ret, frame = cap.read()
        if not ret:
            break

        # GÖRÜNTÜYÜ ZORLA BOYUTLANDIR
        frame = cv2.resize(frame, tuple(resolution))

        processed = process_frame(frame)
        _, buffer = cv2.imencode('.jpg', processed)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()

@app.route('/video_feed')
def video_feed():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

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
        <h2>Streaming Started</h2>
        <img src="/video_feed" /><br><br>

        <form action="/stop" method="get">
            <button type="submit">🛑 Stop Stream</button>
        </form>
    </body>
    </html>
    """

@app.route('/set_params', methods=['GET', 'POST'])
def set_params():
    global resolution, fps, is_streaming, actual_resolution, actual_fps
    if request.method == 'POST':
        try:
            width = int(request.form.get('width'))
            height = int(request.form.get('height'))
            fps_value = int(request.form.get('fps'))

            resolution = [width, height]
            fps = fps_value
            is_streaming = True

            # Kamera test: gerçek değerleri hemen al
            cap = cv2.VideoCapture(0)
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
        "actual_fps": actual_fps
    })

if __name__ == '__main__':
    app.run(debug=True)
