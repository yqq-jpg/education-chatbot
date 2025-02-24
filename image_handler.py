from transformers import AutoImageProcessor, AutoModelForImageClassification, VisionEncoderDecoderModel, AutoTokenizer
import easyocr
from PIL import Image
import torch
import io
from typing import Dict, Any
import numpy as np

class HuggingFaceImageHandler:
    def __init__(self):
        # 图像处理
        self.classifier = AutoModelForImageClassification.from_pretrained("microsoft/resnet-50")
        self.classifier_processor = AutoImageProcessor.from_pretrained("microsoft/resnet-50")
        self.captioner = VisionEncoderDecoderModel.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
        self.feature_extractor = AutoImageProcessor.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
        self.tokenizer = AutoTokenizer.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
        self.reader = easyocr.Reader(['ch_sim', 'en'])
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.classifier.to(self.device)
        self.captioner.to(self.device)
        
        # 格式
        self.supported_formats = {'png', 'jpg', 'jpeg', 'bmp', 'webp'}

        self.max_length = 30
        self.num_beams = 4
        self.min_length = 10
        self.top_k = 50
        self.repetition_penalty = 1.5

    def process_image(self, image_data: bytes, file_format: str) -> Dict[str, Any]:
        try:
            if file_format.lower() not in self.supported_formats:
                return {'status': 'error', 'message': f'Unsupported image format: {file_format}'}

            image = Image.open(io.BytesIO(image_data)).convert('RGB')
            
            # 先进行文本检测
            ocr_result = self.reader.readtext(np.array(image))
            if len(ocr_result) > 5:
                text = "\n".join([text[1] for text in ocr_result])
                return {
                    'status': 'success',
                    'type': 'text',
                    'description': f"Detected Text:\n{text[:1000]}..."
                }
            
            # 分类
            classification = self.classify_image(image)
            # 描述
            caption = self.generate_caption(image)
            # 构建描述
            description = []
            description.append(f"Image Type: {classification['main_category']}")
            description.append(f"Scene Description: {caption}")
            description.append("Main Elements Detected:")
            for item in classification['results'][:3]:
                description.append(f"- {item['label']}: {item['confidence']}%")
            
            return {
                'status': 'success',
                'type': 'image',
                'description': "\n".join(description),
                'results': classification['results']
            }
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def generate_caption(self, image: Image.Image) -> str:
        try:
            inputs = self.feature_extractor(images=[image], return_tensors="pt")
            pixel_values = inputs.pixel_values.to(self.device)

            attention_mask = torch.ones(pixel_values.shape[0], pixel_values.shape[1], device=self.device)

            output_ids = self.captioner.generate(
                pixel_values,
                attention_mask=attention_mask,
                max_length=self.max_length,
                min_length=self.min_length,
                num_beams=self.num_beams,
                top_k=self.top_k,
                repetition_penalty=self.repetition_penalty,
                return_dict_in_generate=True
            ).sequences

            caption = self.tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]
            return caption

        except Exception as e:
            print(f"Caption generation error: {str(e)}")
            return "No description available"

    def classify_image(self, image: Image.Image) -> Dict[str, Any]:
        inputs = self.classifier_processor(images=image, return_tensors="pt").to(self.device)
        outputs = self.classifier(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        top_5_probs, top_5_indices = torch.topk(probs[0], 5)
        
        results = []
        for prob, idx in zip(top_5_probs, top_5_indices):
            label = self.classifier.config.id2label[idx.item()]
            confidence = prob.item() * 100
            results.append({
                'label': label,
                'confidence': round(confidence, 2)
            })
            
        return {
            'main_category': results[0]['label'],
            'results': results
        }