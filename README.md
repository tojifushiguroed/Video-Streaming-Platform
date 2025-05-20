# Video-Streaming-Platform / Multi-Webcam Streamer with YOLO
Intelligent Multi-Source Video Analytics &amp; Streaming Platform

# Project Owners: Elif Deniz Gölboyu 2202756 & Alihan Güler 2105173

## 1. Introduction
This project is a Flask-based web application designed to stream video from multiple webcams, perform real-time object detection using the YOLOv5 model, and publish the detection results to an MQTT broker. This system is ideal for applications requiring live video analysis, such as security monitoring, industrial automation, and traffic management. 
## 2. System Architecture
The architecture of the multi-webcam streamer system comprises the following key components:
Webcams/IP Cameras: Multiple video sources, each providing a live video stream.
GStreamer: A multimedia framework responsible for capturing and processing video streams from the webcams.
Flask Web Server: A Python web framework that handles HTTP requests, manages video streaming, and provides API endpoints.
YOLOv5: A deep learning model used for real-time object detection within the video frames.
MQTT Broker: A messaging server that receives and distributes object detection data to subscribed clients.

### 2.1. Architecture Diagram
https://claude.ai/public/artifacts/32f4de6d-b2cc-46ba-ba4d-3da10448000d


## 3. Data Flow
The data flow within the system can be described as follows:
Video Capture: GStreamer captures video streams from multiple webcams. Each webcam's video feed is processed by a separate GStreamer pipeline.
Frame Processing: The Flask application receives raw video frames from the GStreamer pipelines.
Object Detection: The YOLOv5 model processes each frame to identify and locate objects of interest.
Data Publication: Detection data, including object class, location, and confidence score, is published to the MQTT broker.
Video Streaming: The Flask application encodes the video frames into MJPEG format and streams them to a web browser for display.


## 4. Setup and Installation
The following steps outline the installation and configuration process:

### 4.1. GStreamer Installation
GStreamer is used to manage the video input from the webcams. Installation steps vary depending on the operating system.
Linux:
sudo apt-get install libgstreamer1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
macOS:
brew install gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly
Windows:
Download the GStreamer installer from the official website.
Ensure that the "Complete" installation option is selected.
Verify the installation by running gst-inspect-1.0.

### 4.2. Python Dependencies
The application requires the following Python packages:
pip install Flask numpy opencv-python ultralytics paho-mqtt
Flask: A web framework for building the application.
NumPy: A library for numerical computations.
OpenCV: A library for computer vision tasks.
Ultralytics: The Python interface for the YOLOv5 model.
Paho-MQTT: A library for communicating with the MQTT broker.
PyGObject: Python bindings for GStreamer. Installation may vary; on Linux, use sudo apt-get install python3-gi python3-gst-1.0. For Windows/macOS, use pip install PyGObject after GStreamer is set up.

### 4.3. MQTT Broker Installation
An MQTT broker is required to receive and distribute object detection data. Mosquitto is a popular open-source MQTT broker.
Linux:
sudo apt-get install mosquitto mosquitto-clients
macOS:
brew install mosquitto
Windows:
Download the Mosquitto installer from the official website.
Ensure the MQTT broker is running after installation.


## 5. Code Explanation
The core functionality of the application is implemented in flaskRestApi.py. Here's a breakdown of the key code sections:

Imports: The script begins by importing necessary libraries, including Flask, GStreamer, YOLOv5, and Paho-MQTT [cite: flaskRestApi.py].
Global Variables: Global variables define default stream settings, the YOLOv5 model, and MQTT connection parameters [cite: flaskRestApi.py].
GStreamer Initialization: GStreamer is initialized using Gst.init(None) [cite: flaskRestApi.py].

MQTT Connection: The connect_mqtt() function establishes a connection to the MQTT broker [cite: flaskRestApi.py].
GStreamer Pipeline Creation: The create_pipelines() function dynamically constructs GStreamer pipelines for each webcam. The pipeline includes a source plugin (v4l2src, avfvideosrc, or dshowvideosrc depending on the OS), videoconvert, and appsink [cite: flaskRestApi.py].

Frame Processing:
The on_new_sample() function retrieves video frames from the GStreamer pipelines [cite: flaskRestApi.py].
The process_frame() function performs object detection using the YOLOv5 model. It then draws bounding boxes and labels on the frame and publishes the detection data to the MQTT broker using mqtt_client.publish() [cite: flaskRestApi.py].
Video Streaming: The /video_feed route uses a generator function (generate_stream()) to continuously capture frames from the webcams, combine them, encode them as MJPEG, and stream them to the client [cite: flaskRestApi.py].

Flask Routes:
/: Redirects to the parameter setting page [cite: flaskRestApi.py].
/set_params: Handles setting the video stream resolution and FPS [cite: flaskRestApi.py].
/video_page: Displays the video stream in a web page [cite: flaskRestApi.py].
/start and /stop: Control the starting and stopping of the GStreamer pipelines [cite: flaskRestApi.py].
/last_detections: Returns the latest object detection data in JSON format [cite: flaskRestApi.py].
/status: Returns the current status of the application [cite: flaskRestApi.py]

## 6. Key Features
Multi-Camera Support: Simultaneously streams video from multiple webcams.
Real-time Object Detection: Utilizes YOLOv5 for accurate and efficient object detection.
Configurable Parameters: Allows users to adjust stream resolution and frames per second (FPS).
MQTT Integration: Publishes detection data to an MQTT broker for external processing.
Web-based Interface: Provides a user-friendly web interface for viewing the video stream and controlling the application.

## 7. Operating Instructions
Install GStreamer: Install the appropriate GStreamer packages for your operating system (see section 4.1).
Install Python dependencies: Install the required Python packages using pip: pip install Flask numpy opencv-python ultralytics paho-mqtt

Install an MQTT broker: Install and run an MQTT broker such as Mosquitto (see section 4.3). By default the application is configured to connect to a public broker at broker.hivemq.com.

Run the Flask app: navigate to the directory where the flaskRestApi.py file is located. Run python flaskRestApi.py in the terminal to start the Flask application.
Access the application: Open a web browser and navigate to http://127.0.0.1:5000/ (or the address where the Flask app is running).
You will be redirected to the /set_params page to set streaming parameters such as resolution and FPS. 
After setting the parameters, you will be redirected to /video_page to view the video stream.

View the video stream: On the /video_page page, you will see the live video stream from the webcams.
Check the stream:
Click the "Start" button to start the stream.
Click the "Stop" button to stop the stream. When stopped you will return to the parameter settings.
Get detection data: You can access /last_detections to get the latest detection data in JSON format.
Check the application status: You can access /status to get the current status of the app (e.g. streaming status, camera resources, FPS) in JSON format.

## 8. References
Redmon, J., Divvala, S., Girshick, R., & Farhadi, A. (2016). You Only Look Once: Unified, Real-Time Object Detection. arXiv preprint arXiv:1506.02640.
Bradski, G. (2000). The OpenCV Library. Dr. Dobb's Journal of Software Tools.
GStreamer. (n.d.). GStreamer Documentation. Retrieved from https://gstreamer.freedesktop.org/documentation/
Flask. (n.d.). Flask Documentation. Retrieved from https://flask.palletsprojects.com/
Mosquitto. (n.d.). Eclipse Mosquitto. Retrieved from https://mosquitto.org/
Ultralytics. (n.d.). Ultralytics YOLOv5. Retrieved from https://github.com/ultralytics/yolov5

