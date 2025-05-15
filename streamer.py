# ingestion/stream_ingest.py
import cv2

def stream_from_camera(source=0):
    cap = cv2.VideoCapture(source)  # 0 = default webcam, ya da IP: "rtsp://..."
    if not cap.isOpened():
        raise Exception("Cannot open video source")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        yield frame  # frame'i işlemeye gönder

    cap.release()
