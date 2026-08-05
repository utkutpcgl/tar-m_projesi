"""Deployable segmentation candidates with a shared three-class contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

import torch
from torch import nn
from torch.nn import functional as F


class FeatureBackbone(Protocol):
    channels: Sequence[int]

    def __call__(self, images: torch.Tensor) -> list[torch.Tensor]: ...


def _set_trainable(module: nn.Module, trainable: bool) -> None:
    for parameter in module.parameters():
        parameter.requires_grad = trainable


class TorchvisionConvNeXtTiny(nn.Module):
    channels = (96, 192, 384, 768)

    def __init__(self, pretrained: bool = True, trainable: str = "frozen") -> None:
        super().__init__()
        from torchvision.models import ConvNeXt_Tiny_Weights, convnext_tiny

        weights = ConvNeXt_Tiny_Weights.IMAGENET1K_V1 if pretrained else None
        model = convnext_tiny(weights=weights)
        self.features = model.features
        _set_trainable(self.features, trainable == "all")
        if trainable == "stage4":
            _set_trainable(self.features[6], True)
            _set_trainable(self.features[7], True)
        elif trainable not in {"frozen", "all"}:
            raise ValueError(f"Unsupported ConvNeXt trainable mode: {trainable}")

    def forward(self, images: torch.Tensor) -> list[torch.Tensor]:
        outputs: list[torch.Tensor] = []
        features = images
        for index, layer in enumerate(self.features):
            features = layer(features)
            if index in {1, 3, 5, 7}:
                outputs.append(features)
        return outputs


class Dinov3ConvNeXtTiny(nn.Module):
    """Hugging Face DINOv3 backbone; model terms and authentication are required."""

    model_name = "facebook/dinov3-convnext-tiny-pretrain-lvd1689m"

    def __init__(self, trainable: str = "frozen") -> None:
        super().__init__()
        try:
            from transformers import AutoModel

            self.backbone = AutoModel.from_pretrained(
                self.model_name,
                output_hidden_states=True,
            )
        except Exception as error:
            raise RuntimeError(
                "DINOv3 weights are gated. Accept the DINOv3 terms at "
                f"https://huggingface.co/{self.model_name}, authenticate with "
                "`huggingface-cli login` or HF_TOKEN, then retry."
            ) from error
        self.channels = tuple(
            int(value) for value in self.backbone.config.hidden_sizes
        )
        _set_trainable(self.backbone, trainable == "all")
        if trainable == "stage4":
            stage = getattr(
                getattr(self.backbone, "encoder", self.backbone), "stages", None
            )
            if stage is None:
                raise RuntimeError(
                    "Could not locate DINOv3 stage4; use trainable=frozen or all"
                )
            _set_trainable(stage[-1], True)
        elif trainable not in {"frozen", "all"}:
            raise ValueError(f"Unsupported DINOv3 trainable mode: {trainable}")

    def forward(self, images: torch.Tensor) -> list[torch.Tensor]:
        output = self.backbone(images, output_hidden_states=True)
        # hidden_states[0] is the stem; stages 1..4 are strides 4/8/16/32.
        return list(output.hidden_states[1:])


class Dinov2Small(nn.Module):
    """Ungated Apache-2.0 foundation-model control (single-scale ViT features)."""

    model_name = "facebook/dinov2-small"
    channels = (384, 384, 384, 384)
    input_multiple = 14

    def __init__(
        self, trainable: str = "frozen", pretrained: bool = True
    ) -> None:
        super().__init__()
        if pretrained:
            from transformers import AutoModel

            self.backbone = AutoModel.from_pretrained(
                self.model_name, output_hidden_states=True
            )
        else:
            from transformers import Dinov2Config, Dinov2Model

            self.backbone = Dinov2Model(
                Dinov2Config(
                    image_size=518,
                    hidden_size=384,
                    num_hidden_layers=12,
                    num_attention_heads=6,
                    output_hidden_states=True,
                )
            )
        _set_trainable(self.backbone, trainable == "all")
        if trainable == "stage4":
            _set_trainable(self.backbone.encoder.layer[-3:], True)
        elif trainable not in {"frozen", "all"}:
            raise ValueError(f"Unsupported DINOv2 trainable mode: {trainable}")

    def forward(self, images: torch.Tensor) -> list[torch.Tensor]:
        output = self.backbone(images, output_hidden_states=True)
        height = images.shape[-2] // self.backbone.config.patch_size
        width = images.shape[-1] // self.backbone.config.patch_size
        selected = [3, 6, 9, 12]
        features: list[torch.Tensor] = []
        for index in selected:
            # Remove CLS token and reshape patch tokens to a dense feature map.
            tokens = output.hidden_states[index][:, 1 : 1 + height * width]
            features.append(
                tokens.transpose(1, 2).reshape(
                    images.shape[0], -1, height, width
                )
            )
        return features


class FPNDecoder(nn.Module):
    def __init__(
        self,
        channels: Sequence[int],
        width: int = 128,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.lateral = nn.ModuleList(
            [nn.Conv2d(channel, width, kernel_size=1) for channel in channels]
        )
        self.smooth = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Conv2d(width, width, kernel_size=3, padding=1, bias=False),
                    nn.GroupNorm(16, width),
                    nn.GELU(),
                )
                for _ in channels
            ]
        )
        self.fuse = nn.Sequential(
            nn.Conv2d(
                width * len(channels), width, kernel_size=3, padding=1, bias=False
            ),
            nn.GroupNorm(16, width),
            nn.GELU(),
            nn.Dropout2d(dropout),
        )
        self.width = width

    def forward(self, features: Sequence[torch.Tensor]) -> torch.Tensor:
        if len(features) != len(self.lateral):
            raise ValueError(
                f"Expected {len(self.lateral)} features, received {len(features)}"
            )
        pyramid = [
            layer(feature) for layer, feature in zip(self.lateral, features)
        ]
        for index in range(len(pyramid) - 2, -1, -1):
            pyramid[index] = pyramid[index] + F.interpolate(
                pyramid[index + 1],
                size=pyramid[index].shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
        pyramid = [
            layer(feature) for layer, feature in zip(self.smooth, pyramid)
        ]
        spatial_size = pyramid[0].shape[-2:]
        return self.fuse(
            torch.cat(
                [
                    F.interpolate(
                        feature,
                        size=spatial_size,
                        mode="bilinear",
                        align_corners=False,
                    )
                    for feature in pyramid
                ],
                dim=1,
            )
        )


class CropConditionedFPN(nn.Module):
    """Hierarchical vegetation + target-crop head with exact 3-class probabilities."""

    def __init__(
        self,
        backbone: nn.Module,
        channels: Sequence[int],
        num_crop_ids: int = 32,
        decoder_width: int = 128,
        head: Literal["factorized", "flat"] = "factorized",
        known_crop_ids: Sequence[int] = (0,),
        conditioning_dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.backbone = backbone
        self.decoder = FPNDecoder(channels, width=decoder_width)
        self.unknown_crop_id = num_crop_ids
        self.head_type = head
        self.conditioning_dropout = conditioning_dropout
        known = torch.zeros(num_crop_ids + 1, dtype=torch.bool)
        for crop_id in known_crop_ids:
            if 0 <= int(crop_id) < num_crop_ids:
                known[int(crop_id)] = True
        known[self.unknown_crop_id] = True
        self.register_buffer("known_crop_ids", known)
        if head == "factorized":
            self.crop_embedding: nn.Embedding | None = nn.Embedding(
                num_crop_ids + 1, decoder_width
            )
            nn.init.zeros_(self.crop_embedding.weight)
        else:
            self.crop_embedding = None
        output_channels = 2 if head == "factorized" else 3
        self.head = nn.Sequential(
            nn.Conv2d(decoder_width, decoder_width, 3, padding=1, bias=False),
            nn.GroupNorm(16, decoder_width),
            nn.GELU(),
            nn.Conv2d(decoder_width, output_channels, 1),
        )

    def forward(
        self, images: torch.Tensor, target_crop_id: torch.Tensor | None = None
    ) -> torch.Tensor:
        original_size = images.shape[-2:]
        input_multiple = getattr(self.backbone, "input_multiple", None)
        if input_multiple:
            pad_height = (-images.shape[-2]) % int(input_multiple)
            pad_width = (-images.shape[-1]) % int(input_multiple)
            backbone_images = F.pad(images, (0, pad_width, 0, pad_height))
        else:
            backbone_images = images
        features = self.backbone(backbone_images)
        decoded = self.decoder(features)
        if self.crop_embedding is not None:
            if target_crop_id is None:
                target_crop_id = torch.full(
                    (images.shape[0],),
                    self.unknown_crop_id,
                    device=images.device,
                    dtype=torch.long,
                )
            crop_ids = target_crop_id.clamp(0, self.unknown_crop_id)
            known = self.known_crop_ids[crop_ids]
            crop_ids = torch.where(
                known,
                crop_ids,
                torch.full_like(crop_ids, self.unknown_crop_id),
            )
            if self.training and self.conditioning_dropout > 0:
                dropped = torch.rand(
                    crop_ids.shape, device=crop_ids.device
                ) < self.conditioning_dropout
                crop_ids = torch.where(
                    dropped,
                    torch.full_like(crop_ids, self.unknown_crop_id),
                    crop_ids,
                )
            conditioning = self.crop_embedding(crop_ids)[:, :, None, None]
            decoded = decoded + conditioning
        logits = F.interpolate(
            self.head(decoded),
            size=backbone_images.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )
        if self.head_type == "factorized":
            vegetation = logits[:, 0]
            crop_given_vegetation = logits[:, 1]
            semantic = torch.stack(
                (
                    F.logsigmoid(-vegetation),
                    F.logsigmoid(vegetation)
                    + F.logsigmoid(crop_given_vegetation),
                    F.logsigmoid(vegetation)
                    + F.logsigmoid(-crop_given_vegetation),
                ),
                dim=1,
            )
        else:
            semantic = logits
        return semantic[:, :, : original_size[0], : original_size[1]]


class SegFormerModel(nn.Module):
    def __init__(
        self,
        model_name: str = "nvidia/mit-b2",
        trainable: str = "all",
        pretrained: bool = True,
    ) -> None:
        super().__init__()
        from transformers import SegformerConfig, SegformerForSemanticSegmentation

        labels = {
            "num_labels": 3,
            "id2label": {
                0: "background",
                1: "target_crop",
                2: "other_vegetation",
            },
            "label2id": {
                "background": 0,
                "target_crop": 1,
                "other_vegetation": 2,
            },
        }
        if pretrained:
            self.model = SegformerForSemanticSegmentation.from_pretrained(
                model_name,
                **labels,
                ignore_mismatched_sizes=True,
            )
        else:
            size = model_name.rsplit("-", 1)[-1]
            variants = {
                "b0": ([32, 64, 160, 256], [2, 2, 2, 2], 256),
                "b1": ([64, 128, 320, 512], [2, 2, 2, 2], 256),
                "b2": ([64, 128, 320, 512], [3, 4, 6, 3], 768),
                "b3": ([64, 128, 320, 512], [3, 4, 18, 3], 768),
                "b4": ([64, 128, 320, 512], [3, 8, 27, 3], 768),
                "b5": ([64, 128, 320, 512], [3, 6, 40, 3], 768),
            }
            if size not in variants:
                raise ValueError(f"Unsupported offline SegFormer variant: {size}")
            hidden_sizes, depths, decoder_width = variants[size]
            offline_config = SegformerConfig(
                hidden_sizes=hidden_sizes,
                depths=depths,
                decoder_hidden_size=decoder_width,
                **labels,
            )
            self.model = SegformerForSemanticSegmentation(offline_config)
        if trainable == "frozen":
            _set_trainable(self.model.segformer, False)
        elif trainable == "stage4":
            _set_trainable(self.model.segformer, False)
            _set_trainable(self.model.segformer.encoder.block[-1], True)
        elif trainable != "all":
            raise ValueError(f"Unsupported SegFormer trainable mode: {trainable}")

    def forward(
        self, images: torch.Tensor, target_crop_id: torch.Tensor | None = None
    ) -> torch.Tensor:
        logits = self.model(pixel_values=images).logits
        return F.interpolate(
            logits,
            size=images.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )


class DeepLabV3Model(nn.Module):
    def __init__(
        self, trainable: str = "all", pretrained: bool = True
    ) -> None:
        super().__init__()
        from torchvision.models import ResNet50_Weights
        from torchvision.models.segmentation import deeplabv3_resnet50

        self.model = deeplabv3_resnet50(
            weights=None,
            weights_backbone=(
                ResNet50_Weights.IMAGENET1K_V2 if pretrained else None
            ),
            num_classes=3,
            aux_loss=False,
        )
        if trainable == "frozen":
            _set_trainable(self.model.backbone, False)
        elif trainable == "stage4":
            _set_trainable(self.model.backbone, False)
            _set_trainable(self.model.backbone.layer4, True)
        elif trainable != "all":
            raise ValueError(f"Unsupported DeepLab trainable mode: {trainable}")

    def forward(
        self, images: torch.Tensor, target_crop_id: torch.Tensor | None = None
    ) -> torch.Tensor:
        return self.model(images)["out"]


@dataclass(frozen=True)
class ModelConfig:
    architecture: str
    pretrained: bool = True
    trainable: str = "frozen"
    decoder_width: int = 128
    head: Literal["factorized", "flat"] = "factorized"
    num_crop_ids: int = 32
    known_crop_ids: Sequence[int] = (0,)
    conditioning_dropout: float = 0.2


def build_model(config: ModelConfig) -> nn.Module:
    if config.architecture == "convnext_tiny_fpn":
        backbone = TorchvisionConvNeXtTiny(
            pretrained=config.pretrained, trainable=config.trainable
        )
        return CropConditionedFPN(
            backbone,
            backbone.channels,
            num_crop_ids=config.num_crop_ids,
            decoder_width=config.decoder_width,
            head=config.head,
            known_crop_ids=config.known_crop_ids,
            conditioning_dropout=config.conditioning_dropout,
        )
    if config.architecture == "dinov3_convnext_tiny_fpn":
        backbone = Dinov3ConvNeXtTiny(trainable=config.trainable)
        return CropConditionedFPN(
            backbone,
            backbone.channels,
            num_crop_ids=config.num_crop_ids,
            decoder_width=config.decoder_width,
            head=config.head,
            known_crop_ids=config.known_crop_ids,
            conditioning_dropout=config.conditioning_dropout,
        )
    if config.architecture == "dinov2_small_fpn":
        backbone = Dinov2Small(
            trainable=config.trainable, pretrained=config.pretrained
        )
        return CropConditionedFPN(
            backbone,
            backbone.channels,
            num_crop_ids=config.num_crop_ids,
            decoder_width=config.decoder_width,
            head=config.head,
            known_crop_ids=config.known_crop_ids,
            conditioning_dropout=config.conditioning_dropout,
        )
    if config.architecture.startswith("segformer_"):
        size = config.architecture.removeprefix("segformer_")
        return SegFormerModel(
            f"nvidia/mit-{size}",
            trainable=config.trainable,
            pretrained=config.pretrained,
        )
    if config.architecture == "deeplabv3_resnet50":
        return DeepLabV3Model(
            trainable=config.trainable, pretrained=config.pretrained
        )
    raise KeyError(f"Unknown architecture: {config.architecture}")


def trainable_parameter_count(model: nn.Module) -> tuple[int, int]:
    total = sum(parameter.numel() for parameter in model.parameters())
    trainable = sum(
        parameter.numel()
        for parameter in model.parameters()
        if parameter.requires_grad
    )
    return total, trainable
