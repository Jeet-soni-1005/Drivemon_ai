import cv2
import numpy as np
from picamera2 import Picamera2
import time
import socketio
import requests

sio = socketio.Client()
sio.connect("http://0.0.0.0:5000")

# Initialize the camera
picam2 = Picamera2()
camera_config = picam2.create_preview_configuration(
    main={"size": (640, 480), "format": "RGB888"}
)
picam2.configure(camera_config)
picam2.start()
time.sleep(2)  # Allow the camera to stabilize
# Load YOLOv4-Tiny model files
config_path = "yolov4-tiny.cfg"  # Path to YOLOv4-Tiny configuration file
weights_path = "yolov4-tiny.weights"  # Path to YOLOv4-Tiny weights file
names_path = "coco.names"  # Path to the file containing COCO class labels

# Load YOLO network
net = cv2.dnn.readNetFromDarknet(config_path, weights_path)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
# Load class labels
with open(names_path, 'r') as f:
    classes = f.read().strip().split("\n")

# Define the YOLO parameters
input_width, input_height = 416, 416  # Input size for YOLO
conf_threshold = 0.5  # Confidence threshold
nms_threshold = 0.4  # Non-maximum suppression threshold
# Known values for distance calculation
real_object_widths = {
    "bottle": 7.0,  # Approximate object widths in cm
    "person": 49.0,
    "car": 180.0
}
focal_length = 700.0  # Calibrated focal length (pixels)

while True:
    # Capture a frame
    frame = picam2.capture_array()

    # Ensure the frame has 3 channels (RGB)
    if frame.shape[2] == 4:  # If 4-channel, drop the alpha channel
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    # Get the frame's dimensions
    height, width = frame.shape[:2]
    # Prepare the frame for YOLO
    blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (input_width, input_height), swapRB=True, crop=False)
    net.setInput(blob)
    # Get the names of the YOLO output layers
    layer_names = net.getUnconnectedOutLayersNames()
    outputs = net.forward(layer_names)
    # Initialize lists to store detection results
    class_ids, confidences, boxes = [], [], []
    for output in outputs:
        for detection in output:
            scores = detection[5:]  # Class probabilities
            class_id = np.argmax(scores)
            confidence = scores[class_id]

            if confidence > conf_threshold:
                # Scale the bounding box coordinates back to the frame size
                box = detection[:4] * np.array([width, height, width, height])
                center_x, center_y, box_width, box_height = box.astype("int")

                x = int(center_x - (box_width / 2))
                y = int(center_y - (box_height / 2))
                boxes.append([x, y, int(box_width), int(box_height)])
                confidences.append(float(confidence))
                class_ids.append(class_id)

    # Apply non-maximum suppression to reduce overlapping boxes
    if len(boxes) > 0:
        indices = cv2.dnn.NMSBoxes(boxes, confidences, conf_threshold, nms_threshold)
        for i in indices.flatten():
            x, y, w, h = boxes[i]
            label = f"{classes[class_ids[i]]}: {confidences[i]:.2f}"

            # Calculate the distance if the class has a known width
            detected_class = classes[class_ids[i]]
            if detected_class in real_object_widths:
                real_width = real_object_widths[detected_class]
                distance = (real_width * focal_length) / w  # Calculate distance in cm
                label += f", {distance:.1f} cm"
                print(f"{detected_class} detected at {distance:.1f} cm")

                    # Send Distance to GPS Server
                sio.emit("distance_update", {"distance": distance})

            # Draw the bounding box and label on the frame
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Display the real-time video feed
    cv2.imshow("Real-Time Object Detection with Distance", frame)
    # Exit when 'q' is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
# Stop the camera and close OpenCV windows
picam2.stop()
cv2.destroyAllWindows()
sio.disconnect()
