import sys
import platform
import logging
from flask import Flask, Response, request, jsonify, render_template, redirect, url_for
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import threading
import time
import numpy as np
import cv2
from processor import process_frame  # Kullanıcının frame işleme fonksiyonu

# Logger ayarla
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("flaskRestApi")

# GStreamer başlat
Gst.init(None)

app = Flask(__name__)

# GLOBAL SETTINGS
is_streaming = False
resolution = [640, 480]
fps = 30

actual_resolution = [640, 480]
actual_fps = 30

pipelines = []
main_loop = None
loop_thread = None

# Platform tespiti
current_os = platform.system().lower()
logger.debug(f"Current OS detected: {current_os}")

def get_video_source_element(index):
    if current_os == 'linux':
        return f"v4l2src device=/dev/video{index}"
    elif current_os == 'darwin':
        return f"avfvideosrc device-index={index}"
    elif current_os == 'windows':
        # Windows'da genellikle device-name ile seçmek daha stabil, ama index deneyelim
        # dshow source isimleri çekmek isterseniz daha karmaşık API gerekir
        return f'dshow device-index={index}'
    else:
        raise RuntimeError(f"Unsupported OS: {current_os}")

def detect_cameras(max_sources=10):
    available_sources = []
    for i in range(max_sources):
        try:
            source_element = get_video_source_element(i)
            pipeline_str = f"{source_element} ! video/x-raw,width=640,height=480 ! fakesink"
            test_pipe = Gst.parse_launch(pipeline_str)
            ret = test_pipe.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.SUCCESS or ret == Gst.StateChangeReturn.ASYNC:
                available_sources.append(i)
                logger.debug(f"Camera {i} available")
            test_pipe.set_state(Gst.State.NULL)
        except GLib.Error as e:
            logger.debug(f"[DEBUG] Camera index {i} not available: {e}")
        except RuntimeError as e:
            logger.error(str(e))
            break
    return available_sources

camera_sources = detect_cameras()
logger.info(f"Detected cameras: {camera_sources}")

def on_new_sample(sink, source_id):
    sample = sink.emit("pull-sample")
    if sample:
        buffer = sample.get_buffer()
        caps = sample.get_caps()
        
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            return Gst.FlowReturn.ERROR
        
        structure = caps.get_structure(0)
        width = structure.get_value("width")
        height = structure.get_value("height")
        
        frame = np.ndarray(
            shape=(height, width, 3),
            dtype=np.uint8,
            buffer=map_info.data
        )
        
        for p in pipelines:
            if p["source_id"] == source_id:
                p["last_frame"] = frame.copy()
                break
        
        buffer.unmap(map_info)
        
        return Gst.FlowReturn.OK
    return Gst.FlowReturn.ERROR

def create_gstreamer_pipelines():
    global pipelines
    stop_gstreamer_pipelines()
    pipelines = []
    
    for src in camera_sources:
        try:
            source_element = get_video_source_element(src)
            pipeline_str = (
                f"{source_element} ! "
                f"video/x-raw,width={resolution[0]},height={resolution[1]},framerate={fps}/1 ! "
                f"videoconvert ! video/x-raw,format=BGR ! "
                f"appsink name=sink{src} emit-signals=true max-buffers=1 drop=true"
            )
            pipeline = Gst.parse_launch(pipeline_str)
            sink = pipeline.get_by_name(f"sink{src}")
            
            pipelines.append({
                "pipeline": pipeline,
                "sink": sink,
                "source_id": src,
                "last_frame": None
            })
            
            sink.connect("new-sample", on_new_sample, src)
            logger.debug(f"Pipeline created for camera {src}")
            
        except GLib.Error as e:
            logger.error(f"Could not create pipeline for camera {src}: {e}")
    
    if not pipelines:
        logger.error("No pipelines created. No cameras or failed to create pipelines.")
        return False
    return True

def start_gstreamer_loop():
    global main_loop, loop_thread
    if main_loop is not None:
        return
    
    main_loop = GLib.MainLoop()
    loop_thread = threading.Thread(target=main_loop.run)
    loop_thread.daemon = True
    loop_thread.start()
    logger.debug("GStreamer main loop started")

def stop_gstreamer_pipelines():
    global main_loop, loop_thread, pipelines
    logger.debug("Stopping GStreamer pipelines and main loop.")
    
    for p in pipelines:
        if p["pipeline"]:
            p["pipeline"].set_state(Gst.State.NULL)
    
    if main_loop and main_loop.is_running():
        main_loop.quit()
        if loop_thread:
            loop_thread.join(timeout=1.0)
    
    main_loop = None
    loop_thread = None
    pipelines = []
    logger.debug("GStreamer pipelines and loop stopped.")

def start_pipelines():
    for p in pipelines:
        p["pipeline"].set_state(Gst.State.PLAYING)
    logger.debug("GStreamer pipelines set to PLAYING")

def generate_combined_stream():
    global is_streaming
    
    if not create_gstreamer_pipelines():
        yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
        return
    
    start_gstreamer_loop()
    start_pipelines()
    
    while is_streaming:
        frames = []
        for p in pipelines:
            if p["last_frame"] is not None:
                frame = p["last_frame"].copy()
                processed = process_frame(frame)  # Kullanıcının işlemi
                frames.append(processed)
        
        if not frames:
            time.sleep(0.01)
            continue
        
        try:
            if len(frames) == 1:
                combined = frames[0]
            elif len(frames) == 2:
                combined = cv2.hconcat(frames)
            elif len(frames) <= 4:
                row1 = cv2.hconcat(frames[:2])
                if len(frames) > 2:
                    if len(frames) == 3:
                        blank = np.zeros_like(frames[0])
                        row2 = cv2.hconcat([frames[2], blank])
                    else:
                        row2 = cv2.hconcat(frames[2:4])
                    combined = cv2.vconcat([row1, row2])
                else:
                    combined = row1
            else:
                combined = cv2.hconcat(frames[:4])
            
            _, buffer = cv2.imencode('.jpg', combined)
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            logger.error(f"Frame combining error: {e}")
            time.sleep(0.1)
    
    stop_gstreamer_pipelines()

@app.route('/video_feed')
def video_feed():
    return Response(generate_combined_stream(),
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
    stop_gstreamer_pipelines()
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
            
            actual_resolution = resolution.copy()
            actual_fps = fps
            
            is_streaming = True
            logger.info(f"Parameters updated: resolution={resolution}, fps={fps}")
            return redirect(url_for('video_page'))
        except Exception as e:
            logger.error(f"Could not get values from form: {e}")
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

@app.route('/')
def index():
    return redirect(url_for('set_params'))

if __name__ == '__main__':
    try:
        app.run(debug=True, threaded=True)
    finally:
        stop_gstreamer_pipelines()
