# v1.7.3 same-seed determinism check

- Pair:
  `output/realism_v5_1_determinism_a_54121` and
  `output/realism_v5_1_determinism_b_54121`
- Seed/camera: `54121`, `camera_angled`
- Render: `640×360`, 16 spp, Blender 4.5.12 LTS, RTX 3090 OptiX
- Both validators: `PASS`

| Artefact | Result |
| --- | --- |
| Scenario metadata after removing elapsed time, output paths and file hashes | equal |
| YOLO label | byte-identical |
| RFID semantic mask | byte-identical |
| Three RFID instance masks | byte-identical |
| Concrete semantic mask | byte-identical |
| OptiX-denoised RGB PNG | different |

Annotation hashes:

```text
label      279ba84c5bb56cf279c66cd117adc4c3c43417f4668d02c71dc34ada673d0d7c
rfid union d7a488c56ed3236405095e0a175792bdd6b2608c579b475fab4e60456c7991db
rfid 00    6db2c85b060905fdbe16a6dabf72b606ec5ad9ad133f3c068dec66010cab96bc
rfid 01    a01aa9cfe53d70f091955ef666a76987a789332368432fb259e8cfe21f0f31e9
rfid 02    817efd776d4172cb7e802a4777e189657d037888afec117c5196514cc3c3f6b3
concrete   0b3879940a9b3eb125ea1b8ef26d7031c44369a7ebf5d81c33237a5cd573a32e
RGB A      4bbc30bfc58609cbb6b10d83d457435543263f280c4da5037ee62e7077cbed40
RGB B      e5bdec4cc95f3194f5b834e07cade854abc51f7550a94bcc2e3ee2b3760e6958
```

Doğru sözleşme senaryo ve annotation determinizmidir. GPU denoiser,
driver veya Blender build’i değiştiğinde RGB byte identity vaat edilmez.
