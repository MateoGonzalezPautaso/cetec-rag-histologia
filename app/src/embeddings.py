"""
Image embedding models: PlipWrapper (CLIP-based) and UniWrapper (ViT pathology).
Includes image preprocessing shared by both models and the extraction pipeline.
"""

import numpy as np
import torch
from PIL import Image
from typing import Optional

from .config import DIM_IMG_PLIP, DIM_IMG_UNI


# ── Preprocessing ─────────────────────────────────────────────────────────────

def preprocess_image_for_embedding(image_path: str) -> Image.Image:
    """
    Enhance contrast and brightness of a user-uploaded image before embedding.

    User images are NOT magnified because indexed images were already magnified
    during PDF extraction — magnifying the query image would distort similarity scores.
    """
    try:
        from PIL import ImageEnhance
        img = Image.open(image_path).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Brightness(img).enhance(1.1)
        return img
    except Exception as e:
        print(f"⚠️ Error preprocessing image: {e}, using original")
        return Image.open(image_path).convert("RGB")


# ── PLIP (pathology CLIP) ─────────────────────────────────────────────────────

class PlipWrapper:
    def __init__(self, device: str):
        self.device = device
        self.model = None
        self.processor = None

    def load(self):
        from transformers import CLIPModel, CLIPProcessor
        print("🔄 Cargando PLIP (vinid/plip)...")
        try:
            self.model = CLIPModel.from_pretrained("vinid/plip").to(self.device).eval()
            self.processor = CLIPProcessor.from_pretrained("vinid/plip")
            print("✅ PLIP cargado")
        except Exception as e:
            print(f"❌ Error cargando PLIP: {e}")

    def embed_image(self, image_path: str, preprocess: bool = True) -> np.ndarray:
        # No devolvemos un vector de ceros: bajo distancia COSINE es degenerado
        # (norma 0) y, si se indexa, contamina la colección con puntos que nunca
        # matchean y sin error visible. Preferimos fallar para que el llamador
        # lo maneje (saltar el ítem al indexar, fallback a texto en consulta).
        if not self.model:
            raise RuntimeError("PLIP no está cargado; no se puede generar el embedding de imagen.")
        try:
            image = (
                preprocess_image_for_embedding(image_path)
                if preprocess
                else Image.open(image_path).convert("RGB")
            )
            inputs = self.processor(images=image, return_tensors="pt")
            pixel_values = inputs["pixel_values"].to(self.device)
            with torch.inference_mode():
                vision_out = self.model.vision_model(pixel_values=pixel_values)
                image_features = self.model.visual_projection(vision_out.pooler_output)
            return image_features.cpu().numpy().flatten()
        except Exception as e:
            raise RuntimeError(f"Error generando embedding PLIP: {e}") from e


# ── UNI (pathology ViT-L) ─────────────────────────────────────────────────────

class UniWrapper:
    def __init__(self, device: str):
        self.device = device
        self.model = None
        self.transform = None

    def load(self):
        import timm
        from timm.data import resolve_data_config
        from timm.data.transforms_factory import create_transform
        print("🔄 Cargando UNI (MahmoodLab)...")
        try:
            self.model = timm.create_model(
                "hf_hub:MahmoodLab/UNI",
                pretrained=True,
                init_values=1e-5,
                dynamic_img_size=True,
            ).to(self.device).eval()
            config = resolve_data_config(self.model.pretrained_cfg, model=self.model)
            self.transform = create_transform(**config)
            print("✅ UNI cargado")
        except Exception as e:
            print(f"❌ Error cargando UNI: {e}")

    def embed_image(self, image_path: str, preprocess: bool = True) -> np.ndarray:
        # Ver nota en PlipWrapper.embed_image: fallamos en vez de devolver ceros.
        if not self.model:
            raise RuntimeError("UNI no está cargado; no se puede generar el embedding de imagen.")
        try:
            image = (
                preprocess_image_for_embedding(image_path)
                if preprocess
                else Image.open(image_path).convert("RGB")
            )
            tensor = self.transform(image).unsqueeze(0).to(self.device)
            with torch.inference_mode():
                emb = self.model(tensor)
            return emb.cpu().numpy().flatten()
        except Exception as e:
            raise RuntimeError(f"Error generando embedding UNI: {e}") from e


# ── Image extraction config ───────────────────────────────────────────────────

class ImageExtractionConfig:
    MIN_WIDTH: int = 150
    MIN_HEIGHT: int = 150
    TARGET_MAGNIFICATION_SIZE: int = 868
    ENHANCE_CONTRAST: bool = True
    ENHANCE_BRIGHTNESS: bool = True
    CONTRAST_FACTOR: float = 1.2
    BRIGHTNESS_FACTOR: float = 1.1
    FALLBACK_DPI: int = 150
    RESAMPLING_ALGORITHM = Image.Resampling.LANCZOS
