"""Shared ontology and defaults."""

BACKGROUND = 0
CROP = 1
WEED = 2
IGNORE = 255

CLASS_NAMES = ("background", "target_crop", "other_vegetation")
NUM_CLASSES = len(CLASS_NAMES)

MANIFEST_COLUMNS = (
    "sample_id",
    "image_path",
    "mask_path",
    "split",
    "dataset_id",
    "field_id",
    "session_id",
    "capture_date",
    "platform",
    "sensor",
    "target_crop_id",
    "crop_species",
    "weed_species_optional",
    "growth_stage",
    "annotation_exhaustive",
    "license_status",
    "commercial_allowed",
)

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

