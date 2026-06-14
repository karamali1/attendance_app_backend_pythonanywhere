import cv2
import numpy as np
from insightface.app import FaceAnalysis


class InsightFaceService:
    def __init__(self):
        # 🔹 Default model (fast)
        self.app = FaceAnalysis(name="buffalo_l")
        self.app.prepare(ctx_id=-1, det_size=(640, 640))

        # 🔹 High-resolution model (for classroom counting)
        # self.app_high_res = FaceAnalysis(name="buffalo_l")
        # self.app_high_res.prepare(ctx_id=-1, det_size=(1280, 1280))

    def get_face_embedding(self, image_path: str):
        image = cv2.imread(image_path)

        if image is None:
            raise ValueError("Could not read image")

        faces = self.app.get(image)

        if len(faces) == 0:
            raise ValueError("No face detected in image")

        if len(faces) > 1:
            raise ValueError("Multiple faces detected in image")

        face = faces[0]
        return face.embedding

    @staticmethod
    def embedding_to_bytes(embedding):
        return np.asarray(embedding, dtype=np.float32).tobytes()

    @staticmethod
    def bytes_to_embedding(embedding_bytes: bytes):
        return np.frombuffer(embedding_bytes, dtype=np.float32)

    @staticmethod
    def cosine_similarity(embedding1, embedding2):
        embedding1 = np.asarray(embedding1, dtype=np.float32)
        embedding2 = np.asarray(embedding2, dtype=np.float32)

        denominator = np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
        if denominator == 0:
            return 0.0

        return float(np.dot(embedding1, embedding2) / denominator)

    def compare_image_with_stored_embedding(self, image_path: str, stored_embedding_bytes: bytes):
        new_embedding = self.get_face_embedding(image_path)
        stored_embedding = self.bytes_to_embedding(stored_embedding_bytes)
        return self.cosine_similarity(new_embedding, stored_embedding)


    def compare_embedding_with_stored_embedding(self, new_embedding, stored_embedding_bytes):
        stored_embedding = self.bytes_to_embedding(stored_embedding_bytes)

        new_norm = np.linalg.norm(new_embedding)
        stored_norm = np.linalg.norm(stored_embedding)

        if new_norm == 0 or stored_norm == 0:
            raise ValueError("Invalid embedding for comparison")

        similarity = float(np.dot(new_embedding, stored_embedding) / (new_norm * stored_norm))
        return similarity

    def count_faces_in_image(self, image_path: str) -> int:
        image = cv2.imread(image_path)

        if image is None:
            raise ValueError("Failed to read the image")

        faces = self.app.get(image)

        return len(faces)



