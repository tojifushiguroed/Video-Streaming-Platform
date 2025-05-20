from flask import Flask, Response, jsonify, redirect, request, render_template, url_for
import platform
import logging
import threading
import time
import numpy as np
import cv2
import gi
from ultralytics import YOLO
from datetime import datetime
import paho.mqtt.client as mqtt
import json
import os

# --- GStreamer Init ---
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# --- YOLO & Global Config ---
model = YOLO("yolov5n.pt")
FRAME_SKIP = 1
frame_count = {}

# Default values for stream settings
stream_resolution = (640, 480)
stream_fps = 30

is_streaming = False
pipelines = []
main_loop = None
loop_thread = None
camera_sources = []
current_os = platform.system().lower()
latest_detections = []

# --- Flask Setup ---
app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("MultiCamStreamer")
Gst.init(None)

# --- MQTT Setup ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "yolo/detections"
mqtt_client = mqtt.Client()

def connect_mqtt():
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        print(f"[MQTT ERROR] {e}")

# --- YOLO Frame Processor ---
def process_frame(frame, source_id):
    if source_id not in frame_count:
        frame_count[source_id] = 0

    frame_count[source_id] += 1
    if frame_count[source_id] % FRAME_SKIP != 0:
        return frame

    try:
        results = model(frame)
        if not frame.flags.writeable:
            frame = frame.copy()

        for r in results:
            boxes = r.boxes.xyxy.cpu().numpy()
            scores = r.boxes.conf.cpu().numpy()
            classes = r.boxes.cls.cpu().numpy()

            for box, score, cls in zip(boxes, scores, classes):
                if float(score) < 0.2:
                    continue
                x1, y1, x2, y2 = map(int, box)
                if (x2 - x1) < 10 or (y2 - y1) < 10:
                    continue

                label = f"{model.names[int(cls)]}"
                confidence = float(score)

                # MQTT Publish
                mqtt_data = {
                    "camera": source_id,
                    "label": label,
                    "confidence": confidence,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Store in latest detections
                latest_detections.append({
                    "camera": source_id,
                    "label": label,
                    "confidence": confidence,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Limit the number of stored detections
                if len(latest_detections) > 50:
                    latest_detections.pop(0)
                
                try:
                    mqtt_client.publish(MQTT_TOPIC, json.dumps(mqtt_data))
                except Exception as e:
                    print(f"[MQTT Publish Error] {e}")

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    except Exception as e:
        print(f"[YOLO error @ camera {source_id}]: {e}")

    return frame

# --- GStreamer Helpers ---
def get_video_source(index):
    if current_os == "darwin":  # macOS
        return f"avfvideosrc device-index={index}"
    elif current_os == "windows":
        return f"dshowvideosrc device-index={index}"
    elif current_os == "linux":
        return f"v4l2src device=/dev/video{index}"
    raise RuntimeError(f"Unsupported OS: {current_os}")

def detect_cameras(max_sources=5):
    sources = []
    
    # Linux'ta kamera cihazlarını özel olarak kontrol et
    if current_os == "linux":
        for i in range(max_sources):
            if os.path.exists(f"/dev/video{i}"):
                sources.append(i)
        return sources
    
    # Diğer işletim sistemleri için
    for i in range(max_sources):
        try:
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cap.release()
                sources.append(i)
        except Exception:
            continue
    
    logger.info(f"Detected cameras: {sources}")
    return sources

def on_new_sample(sink, source_id):
    sample = sink.emit("pull-sample")
    if not sample:
        return Gst.FlowReturn.ERROR

    buffer = sample.get_buffer()
    caps = sample.get_caps()
    success, map_info = buffer.map(Gst.MapFlags.READ)
    if not success:
        buffer.unmap(map_info)
        return Gst.FlowReturn.ERROR

    try:
        width = caps.get_structure(0).get_value("width")
        height = caps.get_structure(0).get_value("height")
        
        # Create frame from buffer
        frame = np.ndarray((height, width, 3), np.uint8, map_info.data)
        
        # Process frame
        processed = process_frame(frame, source_id)
        
        # Store the processed frame
        for p in pipelines:
            if p["source_id"] == source_id:
                p["last_frame"] = processed.copy()
                break
    except Exception as e:
        logger.error(f"Error processing frame from source {source_id}: {e}")
    finally:
        buffer.unmap(map_info)
    
    return Gst.FlowReturn.OK

def create_pipelines():
    global pipelines
    stop_pipelines()
    pipelines.clear()
    
    width, height = stream_resolution
    fps = stream_fps
    
    # Oluşturulan pipeline sayısı
    created = 0
    
    for src in camera_sources:
        try:
            # GStreamer pipeline string'ini oluştur
            pipe_str = None
            
            if current_os == "linux":
                pipe_str = (
                    f"v4l2src device=/dev/video{src} ! "
                    f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
                    f"videoconvert ! video/x-raw,format=BGR ! "
                    f"appsink name=sink{src} emit-signals=true max-buffers=1 drop=true"
                )
            elif current_os == "darwin":  # macOS
                pipe_str = (
                    f"avfvideosrc device-index={src} ! "
                    f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
                    f"videoconvert ! video/x-raw,format=BGR ! "
                    f"appsink name=sink{src} emit-signals=true max-buffers=1 drop=true"
                )
            elif current_os == "windows":
                pipe_str = (
                    f"dshowvideosrc device-index={src} ! "
                    f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
                    f"videoconvert ! video/x-raw,format=BGR ! "
                    f"appsink name=sink{src} emit-signals=true max-buffers=1 drop=true"
                )
            
            # Create pipeline
            if pipe_str:
                pipeline = Gst.parse_launch(pipe_str)
                sink = pipeline.get_by_name(f"sink{src}")
                
                if sink is None:
                    raise ValueError(f"sink{src} not found in pipeline")
                
                # Set up event handler for new frames
                sink.connect("new-sample", on_new_sample, src)
                
                # Add to pipelines list
                pipelines.append({
                    "pipeline": pipeline, 
                    "sink": sink, 
                    "source_id": src, 
                    "last_frame": None
                })
                
                created += 1
                logger.info(f"Created pipeline for source {src} with resolution {width}x{height} @ {fps} FPS")
            
        except Exception as e:
            logger.error(f"Pipeline error for source {src}: {e}")
    
    logger.info(f"Created {created} pipelines out of {len(camera_sources)} camera sources")
    return bool(pipelines)

def start_loop():
    global main_loop, loop_thread
    if main_loop is None:
        main_loop = GLib.MainLoop()
        loop_thread = threading.Thread(target=main_loop.run, daemon=True)
        loop_thread.start()

def stop_pipelines():
    global main_loop, loop_thread, is_streaming
    
    # Set streaming flag to False
    is_streaming = False
    
    # Stop all pipelines
    for p in pipelines:
        try:
            p["pipeline"].set_state(Gst.State.NULL)
        except Exception as e:
            logger.error(f"Error stopping pipeline: {e}")
    
    # Stop the GLib main loop
    if main_loop and main_loop.is_running():
        main_loop.quit()
        if loop_thread:
            loop_thread.join(timeout=1.0)
    
    # Clear references
    main_loop = None
    loop_thread = None
    pipelines.clear()

def start_pipelines():
    for p in pipelines:
        p["pipeline"].set_state(Gst.State.PLAYING)

def restart_streaming():
    """Restart the streaming with current settings"""
    global is_streaming
    
    # Stop current pipelines
    stop_pipelines()
    
    # Wait a moment
    time.sleep(1)
    
    # Create new pipelines
    if create_pipelines():
        start_loop()
        start_pipelines()
        is_streaming = True
        return True
    return False

# --- Stream Generator ---
def generate_stream():
    global is_streaming
    
    # Try to create pipelines if not already created
    if not pipelines:
        if not create_pipelines():
            yield b''
            return
        start_loop()
        start_pipelines()
    
    is_streaming = True
    
    # Stream frames as long as streaming is active
    while is_streaming:
        # Get frames from all pipelines
        frames = [p["last_frame"] for p in pipelines if p["last_frame"] is not None]
        
        if not frames:
            time.sleep(0.01)
            continue
        
        try:
            # Ensure all frames have the correct size
            resized_frames = []
            width, height = stream_resolution
            
            for frame in frames:
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(frame, (width, height))
                resized_frames.append(frame)
            
            # Combine frames based on how many we have
            if len(resized_frames) == 1:
                combined = resized_frames[0]
            elif len(resized_frames) == 2:
                combined = cv2.hconcat(resized_frames)
            else:
                # For more than 2 frames, create a grid layout
                grid_size = int(np.ceil(np.sqrt(len(resized_frames))))
                rows = []
                
                for i in range(0, len(resized_frames), grid_size):
                    row_frames = resized_frames[i:i+grid_size]
                    # Pad the last row if needed
                    while len(row_frames) < grid_size:
                        empty_frame = np.zeros((height, width, 3), dtype=np.uint8)
                        row_frames.append(empty_frame)
                    rows.append(cv2.hconcat(row_frames))
                
                combined = cv2.vconcat(rows)
            
            # Convert to JPEG and yield
            _, buffer = cv2.imencode('.jpg', combined)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        except Exception as e:
            logger.error(f"Frame combine error: {e}")
            time.sleep(0.1)
    
    stop_pipelines()

# --- Flask Routes ---
@app.route('/')
def index():
    # Redirect to set_params page first as requested
    return redirect(url_for('set_params'))

@app.route('/video_feed')
def video_feed():
    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/set_params', methods=['GET', 'POST'])
def set_params():
    global stream_resolution, stream_fps
    
    if request.method == 'POST':
        try:
            width = int(request.form.get('width'))
            height = int(request.form.get('height'))
            fps_value = int(request.form.get('fps'))
            
            # Validate input ranges
            if width < 160 or width > 1920 or height < 120 or height > 1080 or fps_value < 1 or fps_value > 60:
                return render_template('setParams.html', 
                                      resolution=stream_resolution, 
                                      fps=stream_fps, 
                                      error="Geçersiz değerler! Çözünürlük: 160x120 - 1920x1080, FPS: 1-60 arasında olmalıdır.")
            
            # Update settings
            stream_resolution = (width, height)
            stream_fps = fps_value
            logger.info(f"[SET_PARAMS] Updated to {stream_resolution} @ {stream_fps} FPS")
            
            # Detect cameras if not already detected
            if not camera_sources:
                camera_sources.extend(detect_cameras())
            
            # Redirect to video page to start streaming with new settings
            return redirect(url_for('video_page'))
        
        except Exception as e:
            logger.error(f"[SET_PARAMS ERROR] {e}")
            return render_template('setParams.html', 
                                  resolution=stream_resolution, 
                                  fps=stream_fps, 
                                  error="Geçersiz giriş!")
    
    # GET request - show settings form
    width, height = stream_resolution
    return render_template('setParams.html', resolution=(width, height), fps=stream_fps)


@app.route('/video_page')
def video_page():
    width, height = stream_resolution
    return render_template('video_page.html', 
                          width=width, 
                          height=height, 
                          fps=stream_fps)

@app.route('/start', methods=['POST'])
def start():
    global is_streaming, camera_sources
    
    # Detect cameras if not already done
    if not camera_sources:
        camera_sources = detect_cameras()
    
    # Start streaming
    is_streaming = True
    restart_streaming()
    
    # Return to video page
    return redirect(url_for('video_page'))

@app.route('/stop', methods=['POST'])
def stop():
    global is_streaming
    
    # Stop streaming
    is_streaming = False
    stop_pipelines()
    
    # Redirect to set_params page as requested in the workflow
    return redirect(url_for('set_params'))

@app.route('/last_detections', methods=['GET'])
def last_detections():
    return jsonify(latest_detections[-10:])

@app.route('/status')
def status():
    return jsonify({
        "is_streaming": is_streaming,
        "camera_sources": camera_sources,
        "resolution": stream_resolution,
        "fps": stream_fps,
        "active_pipelines": len(pipelines),
        "detection_count": len(latest_detections)
    })

# Create templates directory if it doesn't exist
if not os.path.exists('templates'):
    os.makedirs('templates')

# Create template files
with open('templates/setParams.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Kamera Ayarları</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input[type="number"] {
            width: 100px;
            padding: 5px;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 10px;
        }
        .error {
            color: red;
            margin-bottom: 15px;
        }
    </style>
</head>
<body>
    <h1>Kamera Ayarları</h1>
    
    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}
    
    <form action="/set_params" method="post">
        <div class="form-group">
            <label for="width">Genişlik:</label>
            <input type="number" id="width" name="width" min="160" max="1920" value="{{ resolution[0] }}" required>
        </div>
        
        <div class="form-group">
            <label for="height">Yükseklik:</label>
            <input type="number" id="height" name="height" min="120" max="1080" value="{{ resolution[1] }}" required>
        </div>
        
        <div class="form-group">
            <label for="fps">FPS:</label>
            <input type="number" id="fps" name="fps" min="1" max="60" value="{{ fps }}" required>
        </div>
        
        <button type="submit">Kaydet ve Başlat</button>
    </form>
</body>
</html>
''')

with open('templates/video_page.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Multi Webcam Stream with YOLO</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            text-align: center;
        }
        h2 {
            color: #333;
        }
        .stream-container {
            margin: 20px 0;
        }
        .controls {
            margin: 20px 0;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin: 0 10px;
        }
        button.stop {
            background-color: #f44336;
        }
        a {
            display: inline-block;
            margin-top: 15px;
            color: #2196F3;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        .info {
            background-color: #f1f1f1;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <h2>Multi Webcam Stream with YOLO</h2>
    
    <div class="info">
        <p>Çözünürlük: {{ width }}x{{ height }} @ {{ fps }} FPS</p>
    </div>
    
    <div class="stream-container">
        <img src="/video_feed" alt="Video Stream" />
    </div>
    
    <div class="controls">
        <form action="/start" method="post">
            <button type="submit">Start</button>
        </form>
        
        <form action="/stop" method="post">
            <button type="submit" class="stop">Stop</button>
        </form>
    </div>
    
    <a href="/set_params">Ayarları Değiştir</a>
</body>
</html>
''')

# --- App Entry ---
if __name__ == '__main__':
    connect_mqtt()
    app.run(host='0.0.0.0', port=5000, debug=True)