import torch

from agri_seg.engine import predict_logits
from agri_seg.models import CropConditionedFPN, FPNDecoder


class TinyBackbone(torch.nn.Module):
    def forward(self, images: torch.Tensor) -> list[torch.Tensor]:
        base = images.mean(dim=1, keepdim=True)
        return [
            torch.nn.functional.avg_pool2d(base, 2).repeat(1, 4, 1, 1),
            torch.nn.functional.avg_pool2d(base, 4).repeat(1, 8, 1, 1),
            torch.nn.functional.avg_pool2d(base, 8).repeat(1, 16, 1, 1),
            torch.nn.functional.avg_pool2d(base, 16).repeat(1, 32, 1, 1),
        ]


def test_factorized_head_is_a_probability_distribution() -> None:
    model = CropConditionedFPN(
        TinyBackbone(),
        channels=(4, 8, 16, 32),
        num_crop_ids=3,
        decoder_width=16,
        head="factorized",
    )
    logits = model(torch.randn(2, 3, 64, 64), torch.tensor([0, 1]))
    probabilities = logits.exp()
    torch.testing.assert_close(
        probabilities.sum(dim=1),
        torch.ones(2, 64, 64),
        rtol=1e-5,
        atol=1e-5,
    )


def test_fpn_rejects_wrong_feature_count() -> None:
    decoder = FPNDecoder((4, 8), width=16)
    try:
        decoder([torch.randn(1, 4, 8, 8)])
    except ValueError as error:
        assert "Expected 2" in str(error)
    else:
        raise AssertionError("wrong feature count was accepted")


def test_backbone_input_is_padded_then_output_is_cropped() -> None:
    class RecordingBackbone(TinyBackbone):
        input_multiple = 14

        def __init__(self) -> None:
            super().__init__()
            self.seen_size: tuple[int, int] | None = None

        def forward(self, images: torch.Tensor) -> list[torch.Tensor]:
            self.seen_size = tuple(images.shape[-2:])
            return super().forward(images)

    backbone = RecordingBackbone()
    model = CropConditionedFPN(
        backbone,
        channels=(4, 8, 16, 32),
        num_crop_ids=3,
        decoder_width=16,
        head="factorized",
    )
    output = model(torch.randn(1, 3, 65, 79), torch.tensor([0]))
    assert backbone.seen_size == (70, 84)
    assert output.shape == (1, 3, 65, 79)
    torch.testing.assert_close(
        output.exp().sum(dim=1),
        torch.ones(1, 65, 79),
        rtol=1e-5,
        atol=1e-5,
    )


def test_tiled_prediction_matches_full_for_pointwise_model() -> None:
    class Pointwise(torch.nn.Module):
        def forward(
            self, images: torch.Tensor, crop_ids: torch.Tensor
        ) -> torch.Tensor:
            return torch.stack(
                (images[:, 0], images[:, 1], images[:, 2]), dim=1
            )

    model = Pointwise()
    images = torch.randn(1, 3, 100, 130)
    crop_ids = torch.tensor([0])
    expected = model(images, crop_ids)
    actual = predict_logits(
        model,
        images,
        crop_ids,
        use_amp=False,
        tile_size=64,
        tile_overlap=16,
        tile_trigger_pixels=0,
    )
    torch.testing.assert_close(actual, expected, rtol=1e-5, atol=1e-5)
