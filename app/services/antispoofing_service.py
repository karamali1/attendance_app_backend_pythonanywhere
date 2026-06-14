import os
import sys
import warnings

import cv2
import numpy as np
import torch
from uniface import RetinaFace

warnings.filterwarnings("ignore")


ANTI_SPOOFING_DIR = os.path.join(
    os.path.dirname(__file__),
    "face-anti-spoofing"
)

if ANTI_SPOOFING_DIR not in sys.path:
    sys.path.append(ANTI_SPOOFING_DIR)

from models import MiniFASNetV2  # noqa: E402
from utils import crop_face, to_tensor, xyxy2xywh  # noqa: E402


class AntiSpoofingService:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.weight_path = os.path.join(
            ANTI_SPOOFING_DIR,
            "weights",
            "MiniFASNetV2.pth"
        )

        self.input_size = (80, 80)
        self.scale = 2.7

        self.model = MiniFASNetV2()
        self.model.load_state_dict(
            torch.load(
                self.weight_path,
                map_location=self.device,
                weights_only=True
            )
        )
        self.model.to(self.device)
        self.model.eval()

        self.detector = RetinaFace()

        print(f"MiniFASNetV2 anti-spoofing loaded on {self.device}")

    def predict_image(self, image_path: str, confidence: float = 0.5) -> dict:
        image = cv2.imread(image_path)

        if image is None:
            raise ValueError(f"Failed to load image: {image_path}")

        faces = self.detector.detect(image)
        faces = [face for face in faces if face.confidence >= confidence]

        if not faces:
            return {
                "success": False,
                "is_real": False,
                "label": "NoFace",
                "score": 0.0,
                "message": "No face detected for anti-spoofing"
            }

        if len(faces) > 1:
            return {
                "success": False,
                "is_real": False,
                "label": "MultipleFaces",
                "score": 0.0,
                "message": "Multiple faces detected for anti-spoofing"
            }

        face = faces[0]
        bbox_xywh = xyxy2xywh(face.bbox).astype(int).tolist()

        h, w = self.input_size

        face_crop = crop_face(
            image=image,
            bbox=bbox_xywh,
            scale=self.scale,
            out_w=w,
            out_h=h
        )

        tensor = to_tensor(face_crop).unsqueeze(0).to(self.device)

        with torch.no_grad():
            output = self.model(tensor)
            probs = torch.softmax(output, dim=1).cpu().numpy()

        label_idx = int(np.argmax(probs))
        score = float(probs[0, label_idx])

        label = "Real" if label_idx == 1 else "Fake"
        is_real = label == "Real"

        return {
            "success": True,
            "is_real": is_real,
            "label": label,
            "score": score,
            "bbox": bbox_xywh,
            "message": f"{label} face detected with score {score:.2f}"
        }