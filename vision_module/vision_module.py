
import torch
import torch.nn as nn
from PIL import Image
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights


class VisionDetector:

    def __init__(self, checkpoint_path, device=None):

        # Device
        if device is None:
            self.device = torch.device(
                "cuda" if torch.cuda.is_available() else "cpu"
            )
        else:
            self.device = torch.device(device)

        # Load checkpoint
        self.checkpoint = torch.load(
            checkpoint_path,
            map_location=self.device,
            weights_only=False
        )

        # Load labels and thresholds saved inside V3 checkpoint
        self.labels = self.checkpoint["labels"]
        self.thresholds = self.checkpoint["thresholds"]

        # Create exact MobileNetV3-Small architecture
        weights = MobileNet_V3_Small_Weights.DEFAULT

        self.model = mobilenet_v3_small(weights=None)

        self.model.classifier[3] = nn.Linear(
            in_features=1024,
            out_features=len(self.labels)
        )

        # Load trained V3 weights
        self.model.load_state_dict(
            self.checkpoint["model_state_dict"]
        )

        self.model.to(self.device)
        self.model.eval()

        # Exact preprocessing expected by MobileNetV3
        self.transform = weights.transforms()

    def predict(self, image_path):

        # Load image
        image = Image.open(image_path).convert("RGB")

        # Preprocess
        image_tensor = self.transform(image)
        image_tensor = image_tensor.unsqueeze(0).to(self.device)

        # Inference
        with torch.no_grad():
            logits = self.model(image_tensor)
            probabilities = torch.sigmoid(logits)[0]

        probabilities = probabilities.cpu().numpy()

        # Build fusion-friendly result
        predictions = {}

        for i, label in enumerate(self.labels):

            probability = float(probabilities[i])
            threshold = float(self.thresholds[label])

            predictions[label] = {
                "probability": probability,
                "confidence_percent": probability * 100,
                "threshold": threshold,
                "detected": probability >= threshold
            }

        return {
            "module": "vision",
            "model": self.checkpoint["model_name"],
            "version": self.checkpoint["version"],
            "predictions": predictions
        }
