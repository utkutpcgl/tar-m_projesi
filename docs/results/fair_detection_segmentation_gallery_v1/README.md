# Fair detection vs segmentation gallery

Each image uses a publisher-labelled PhenoBench test plot. Green is crop, purple is ground-truth weed, orange is predicted weed. A green action point touches the exact ground-truth weed tissue; a red point does not. Detection acts at the weed box centre; segmentation acts at the deepest interior point of its predicted weed mask. Confidence thresholds were locked on validation before test inference.
