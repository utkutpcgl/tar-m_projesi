from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml
from PIL import Image

from scripts.audit_spot_spray_capture_v1 import (
    audit_capture,
    load_json_object,
    load_yaml_mapping as load_capture_policy,
    sha256,
)
from scripts.evaluate_spot_spray_rig_acceptance_v1 import (
    evaluate as evaluate_rig,
    load_yaml_mapping as load_rig_yaml,
)


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_POLICY = ROOT / "configs/data/spot_spray_capture_audit_v1.yaml"
CAPTURE_SCHEMA = ROOT / "configs/data/spot_spray_capture_manifest_v1.schema.json"
CAPTURE_AUDITOR = ROOT / "scripts/audit_spot_spray_capture_v1.py"
RIG_CONTRACT = ROOT / "configs/deploy/spot_spray_rig_acceptance_v1.yaml"
RIG_EVALUATOR = ROOT / "scripts/evaluate_spot_spray_rig_acceptance_v1.py"
RIG_RECEIPT = ROOT / "tests/fixtures/spot_spray_rig_acceptance_v1/synthetic_pass.yaml"
ACTION_CONFIG = ROOT / "configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml"
FINETUNE_CONFIG = ROOT / "configs/benchmark/spot_spray_target_rig_finetune_v1.yaml"
PRE_REAL_SELECTION = ROOT / "docs/results/pre_real_data_ceiling_result_v1.json"
CAPTURE_FIXTURES = ROOT / "tests/fixtures/spot_spray_capture_v1"


def test_terminal_identity_chain_is_current_and_forged_rig_results_fail_closed(
    tmp_path: Path,
) -> None:
    capture = load_capture_policy(CAPTURE_POLICY)
    rig_policy = capture["rig_acceptance"]
    assert ROOT / rig_policy["contract_path"] == RIG_CONTRACT
    assert ROOT / rig_policy["evaluator_path"] == RIG_EVALUATOR
    assert rig_policy["contract_exact_byte_sha256"] == sha256(RIG_CONTRACT)
    assert rig_policy["evaluator_sha256"] == sha256(RIG_EVALUATOR)

    evaluated = evaluate_rig(
        load_rig_yaml(RIG_CONTRACT),
        load_rig_yaml(RIG_RECEIPT),
        ROOT,
        RIG_RECEIPT,
        RIG_CONTRACT,
    )
    assert evaluated["contract_identity"] == {
        "identity_id": rig_policy["contract_identity_id"],
        "algorithm": rig_policy["contract_identity_algorithm"],
        "default_contract_path": rig_policy["contract_path"],
        "expected_exact_byte_sha256": rig_policy["contract_exact_byte_sha256"],
        "observed_exact_byte_sha256": rig_policy["contract_exact_byte_sha256"],
        "exact_bytes_verified": True,
        "expected_canonical_policy_sha256": rig_policy[
            "contract_canonical_policy_sha256"
        ],
        "observed_canonical_policy_sha256": rig_policy[
            "contract_canonical_policy_sha256"
        ],
        "canonical_policy_verified": True,
    }
    assert evaluated["implementation"] == {
        "script": rig_policy["evaluator_path"],
        "script_sha256": rig_policy["evaluator_sha256"],
    }

    finetune = yaml.safe_load(FINETUNE_CONFIG.read_text(encoding="utf-8"))
    expected_capture_sources = {
        "schema": CAPTURE_SCHEMA,
        "policy": CAPTURE_POLICY,
        "audit_implementation": CAPTURE_AUDITOR,
    }
    for name, path in expected_capture_sources.items():
        source = finetune["capture_interface"]["sources"][name]
        assert ROOT / source["path"] == path
        assert source["sha256"] == sha256(path)

    foundation = Path(finetune["foundation"]["checkpoint"])
    pre_real = json.loads(PRE_REAL_SELECTION.read_text(encoding="utf-8"))
    foundation_sha256 = finetune["foundation"]["checkpoint_sha256"]
    assert foundation.is_file()
    assert sha256(foundation) == foundation_sha256
    assert pre_real["fairness"]["challenger_checkpoint_sha256"] == foundation_sha256
    assert pre_real["result"]["field_fire_go"] is False
    assert pre_real["result"]["synthetic_score_used_in_real_decision"] is False

    action = yaml.safe_load(ACTION_CONFIG.read_text(encoding="utf-8"))
    assert action["capture_audit"]["trusted_sources"] == {
        "schema": str(CAPTURE_SCHEMA.relative_to(ROOT)),
        "policy": str(CAPTURE_POLICY.relative_to(ROOT)),
        "implementation": str(CAPTURE_AUDITOR.relative_to(ROOT)),
    }
    assert action["offline_go_gates"]["synthetic_score_weight_in_real_go_decision"] == 0.0
    assert action["model"]["foundation"]["checkpoint_sha256"] == foundation_sha256
    assert action["model"]["evaluated_checkpoint"]["checkpoint"] is None

    capture_report = audit_capture(
        CAPTURE_FIXTURES / "valid_complete_synthetic.json",
        CAPTURE_POLICY,
        data_root=CAPTURE_FIXTURES,
        repo_root=ROOT,
    )
    protected = {Path(path) for path in capture_report["inputs"]["protected_paths"]}
    assert {CAPTURE_AUDITOR, RIG_CONTRACT, RIG_EVALUATOR} <= protected

    forged = copy.deepcopy(evaluated)
    forged["evidence_kind"] = "physical_bench"
    forged["decision"].update(
        code="GO_CONTROLLED_DATA_COLLECTION",
        controlled_data_collection_allowed=True,
        deployment_evidence_eligible=True,
    )
    manifest = load_json_object(CAPTURE_FIXTURES / "valid_complete_synthetic.json")
    manifest["evidence_scope"] = "real_target_rig"
    for index, frame in enumerate(manifest["frames"]):
        relative_image = Path("images") / f"{frame['frame_id']}.png"
        image_path = tmp_path / relative_image
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 6), (index * 20, 100, 40)).save(image_path)
        profile_id = (
            f"profile_{frame['exposure_us']}_{frame['gain_db']}_"
            f"{frame['working_distance_mm']}"
        )
        frame.update(
            image_path=relative_image.as_posix(),
            image_sha256=sha256(image_path),
            camera_frame_counter=1000 + int(frame["frame_index"]),
            camera_timestamp_ns=int(frame["timestamp_ns"]) + 10,
            white_balance={
                "mode": "manual",
                "red_gain": 1.25,
                "green_gain": 1.0,
                "blue_gain": 1.4,
            },
            native_width_px=8,
            native_height_px=6,
            pixel_format="RGB8",
            camera_id="SYNTHETIC-CAMERA-SERIAL",
            rig_id="SYNTHETIC-RIG-NOT-HARDWARE",
            capture_profile_id=profile_id,
            strobe_settings={
                "profile_id": frame["strobe_profile_id"],
                "pulse_width_us": 150.0,
                "peak_current_a": 5.0,
            },
        )
    attacks = (
        ("missing_identity", lambda payload: payload.pop("contract_identity")),
        (
            "stale_evaluator",
            lambda payload: payload["implementation"].update(
                script_sha256="0" * 64
            ),
        ),
    )
    for name, mutate in attacks:
        candidate = copy.deepcopy(forged)
        mutate(candidate)
        result_path = tmp_path / f"{name}.json"
        result_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
        manifest["rig_acceptance"] = {
            "result_path": result_path.name,
            "result_sha256": sha256(result_path),
        }
        manifest_path = tmp_path / f"{name}_manifest.json"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        report = audit_capture(
            manifest_path,
            CAPTURE_POLICY,
            data_root=tmp_path,
            repo_root=ROOT,
        )
        summary = report["integrity"]["rig_acceptance"]
        assert report["status"] == "INVALID"
        assert report["valid"] is False
        assert report["ready"] is False
        assert report["evidence"]["counts_as_real_target_rig_evidence"] is False
        assert summary["physical_collection_allowed"] is False
        assert summary["contract_identity_bound"] is (name != "missing_identity")
        assert summary["implementation_identity_bound"] is (
            name != "stale_evaluator"
        )
        assert {entry["code"] for entry in report["errors"]} & {
            "rig_acceptance.content_invalid",
            "rig_acceptance.provenance_mismatch",
        }
