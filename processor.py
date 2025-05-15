# analytics/processor.py
from ultralytics import YOLO
import cv2

# YOLOv5 Tiny kullanılıyor
model = YOLO("yolov5n.pt")  # Daha hızlı: yolov5n veya yolov8n kullanabilirsin

def process_frame(frame):
    results = model(frame)
    for r in results:
        boxes = r.boxes.xyxy
        for box in boxes:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

    return frame
