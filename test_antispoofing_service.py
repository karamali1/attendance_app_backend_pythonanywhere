from app.services.antispoofing_instance import anti_spoofing_service

image_path = "app/services/face-anti-spoofing/assets/karam.jpg"

result = anti_spoofing_service.predict_image(image_path)

print(result)
