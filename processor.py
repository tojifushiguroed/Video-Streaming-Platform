from ultralytics import YOLO
import cv2
import numpy as np
from datetime import datetime

model = YOLO("yolov5n.pt")

FRAME_SKIP = 2
frame_count = 0

algilanan_nesneler = []

def get_detected_objects(frame):
    orig_h, orig_w = frame.shape[:2]
    input_size = 320
    small_frame = cv2.resize(frame, (input_size, input_size))
    results = model(small_frame, verbose=False)
    detected_objects = []
    for r in results:
        if r.boxes is not None and len(r.boxes.xyxy) > 0:  # Boxes nesnesi ve algılama var mı kontrolü
            for *xyxy_tensor, conf, cls in r.boxes.xyxy.cpu().numpy():
                xyxy = [int(x) for x in xyxy_tensor]
                detected_objects.append({
                    'sinif': model.names[int(cls)],
                    'guven': float(conf),
                    'bounding_box': xyxy,  # Bounding box koordinatlarını da ekleyelim
                    'timestamp': datetime.now().isoformat()
                })
    return detected_objects

def set_frame_skip(n):
    global FRAME_SKIP
    FRAME_SKIP = n

def process_frame(frame):
    global frame_count
    frame_count += 1

    if frame_count % FRAME_SKIP != 0:
        return frame

    orig_h, orig_w = frame.shape[:2]
    input_size = 320
    small_frame = cv2.resize(frame, (input_size, input_size))

    results = model(small_frame)

    for r in results:
        boxes = r.boxes.xyxy.cpu().numpy()
        scores = r.boxes.conf.cpu().numpy()
        classes = r.boxes.cls.cpu().numpy()

        for box, score, cls in zip(boxes, scores, classes):
            x1, y1, x2, y2 = box
            x1 = int(x1 * orig_w / input_size)
            y1 = int(y1 * orig_h / input_size)
            x2 = int(x2 * orig_w / input_size)
            y2 = int(y2 * orig_h / input_size)

            label = f"{model.names[int(cls)]} {score:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    return frame
