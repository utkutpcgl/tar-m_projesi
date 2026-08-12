from scripts import build_controlled_spot_spray_poc_report_v1 as report


def _summary() -> dict:
    return report.build_summary(
        {
            "action": report.load(report.ACTION),
            "synthetic": report.load(report.SYNTHETIC),
            "external": report.load(report.EXTERNAL),
            "ab_receipt": report.load(report.AB_RECEIPT),
            "synthetic_receipt": report.load(report.SYNTHETIC_RECEIPT),
            "synthetic_release": report.load(report.SYNTHETIC_RELEASE),
            "compute": report.load(report.COMPUTE),
            "compute_halo": report.load(report.COMPUTE_HALO),
            "capture_v2": report.load(report.CAPTURE_V2),
            "pre_real_result": report.load(report.PRE_REAL_RESULT),
            "pre_real_diagnostics": report.load(report.PRE_REAL_DIAGNOSTICS),
            "pre_real_gallery": report.load(report.PRE_REAL_GALLERY_RECEIPT),
            "rig_acceptance": report.load_yaml(report.RIG_ACCEPTANCE),
            "capture_schema": report.load(report.CAPTURE_SCHEMA),
            "capture_policy": report.load_yaml(report.CAPTURE_POLICY),
            "finetune_contract": report.load_yaml(report.FINETUNE_CONTRACT),
            "action_eval_contract": report.load_yaml(report.ACTION_EVAL_CONTRACT),
        }
    )


def test_report_selects_directional_pre_real_model_without_field_go() -> None:
    summary = _summary()
    assert summary["schema_version"] == 5
    assert summary["decision"]["selected_development_model"] == report.SELECTED_MODEL
    assert summary["decision"]["field_fire_status"] == "NO-GO"
    assert summary["pre_real_ceiling"]["field_fire_go"] is False
    assert summary["phenobench"]["selected"]["f1"] == 0.7540106951871658
    assert summary["bonirob"]["selected"]["f1"] == 0.08964143426294822


def test_report_keeps_synthetic_out_of_real_selection_and_updates_start_text() -> None:
    summary = _summary()
    synthetic = summary["pre_real_ceiling"]["synthetic_fixed_pheno_threshold"]
    assert synthetic["real_model_selection_score_weight"] == 0.0
    assert summary["synthetic"]["selected_fixed_pheno_threshold"]["f1"] == 0.0
    text = report.package_readme(summary)
    assert "%75,4" in text
    assert "%9,0" in text
    assert "NO-GO" in text


def test_current_state_pages_use_selected_bonirob_metrics(monkeypatch) -> None:
    summary = _summary()
    rendered_text: list[str] = []
    rendered_rows: list[list[list[str]]] = []
    original_add_text = report.add_text
    original_draw_table = report.draw_table

    def capture_text(draw, xy, text, *args, **kwargs):
        rendered_text.append(text)
        return original_add_text(draw, xy, text, *args, **kwargs)

    def capture_table(canvas, box, headers, rows, *args, **kwargs):
        rendered_rows.append(rows)
        return original_draw_table(canvas, box, headers, rows, *args, **kwargs)

    monkeypatch.setattr(report, "add_text", capture_text)
    monkeypatch.setattr(report, "draw_table", capture_table)

    report.tracking_page(summary)
    report.diagnosis_page(summary)

    assert any("BoniRob recall %5,8" in text for text in rendered_text)
    assert rendered_rows[0][0][2] == "BoniRob F1 %9,0"
    assert not any("BoniRob recall %3,3" in text for text in rendered_text)
    assert rendered_rows[0][0][2] != "BoniRob F1 %5,4"


def test_report_binds_terminal_target_rig_contracts_without_ready_claim() -> None:
    summary = _summary()
    target = summary["target_rig_contracts"]

    assert target["overall_status"] == "PRE_REAL_NOT_READY"
    assert target["field_fire_status"] == "NO-GO"
    assert target["chemical_fire_status"] == "NO-GO_UNSUPPORTED"
    assert target["selected_foundation"]["checkpoint_sha256"] == (
        "3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100"
    )
    assert target["rig_acceptance"]["physical_result_exists"] is False
    assert target["rig_acceptance"]["current_controlled_data_collection_allowed"] is False
    assert target["rig_acceptance"]["current_dry_marker_allowed"] is False
    assert target["rig_acceptance"]["chemical_fire_allowed"] is False
    assert target["capture"]["real_manifest_exists"] is False
    assert target["capture"]["current_audit_status"] == "NOT_READY"
    assert target["capture"]["minimum_fields"] == 3
    assert target["capture"]["minimum_field_sessions"] == 4
    assert target["capture"]["split_target_fractions"] == {
        "train": 0.6,
        "validation": 0.2,
        "test": 0.2,
    }
    assert target["capture"]["synthetic_fixture_can_be_ready"] is False
    assert target["fine_tune"]["manager_acceptance_status"] == "pending_manager_acceptance"
    assert target["fine_tune"]["real_training_started"] is False
    assert target["fine_tune"]["final_checkpoint_rule"] == "fixed_epoch_30_last_checkpoint_only"
    assert target["track_action_evaluation"]["evaluated_checkpoint"] is None
    assert target["track_action_evaluation"]["current_evaluation_status"] == "NOT_READY"
    assert target["track_action_evaluation"]["synthetic_fixture_status"] == "FIXTURE_ONLY"


def test_start_text_and_markdown_explain_exact_next_physical_boundary() -> None:
    summary = _summary()
    start_text = report.package_readme(summary)
    markdown = report.markdown_report(summary)

    for text in (start_text, markdown):
        assert "3aba4b19" in text
        assert "physical A–E" in text or "Fiziksel A–E" in text
        assert "PRE_REAL_NOT_READY" in text or "NOT_READY" in text
        assert "chemical" in text.lower()
    assert "en az 3 tarla / 4 field-session" in start_text
    assert "evaluated_checkpoint" in markdown
    assert "60/20/20" in markdown
    assert "Wilson" in markdown


def test_target_rig_status_pages_keep_stage_boundaries_visible(monkeypatch) -> None:
    summary = _summary()
    rendered_text: list[str] = []
    rendered_rows: list[list[list[str]]] = []
    original_add_text = report.add_text
    original_draw_table = report.draw_table

    def capture_text(draw, xy, text, *args, **kwargs):
        rendered_text.append(text)
        return original_add_text(draw, xy, text, *args, **kwargs)

    def capture_table(canvas, box, headers, rows, *args, **kwargs):
        rendered_rows.append(rows)
        return original_draw_table(canvas, box, headers, rows, *args, **kwargs)

    monkeypatch.setattr(report, "add_text", capture_text)
    monkeypatch.setattr(report, "draw_table", capture_table)

    report.rig_acceptance_page(summary)
    report.target_rig_readiness_page(summary)
    report.proof_plan_page()

    flattened = " ".join(str(cell) for table in rendered_rows for row in table for cell in row)
    all_text = " ".join(rendered_text) + " " + flattened
    assert "A–E" in all_text
    assert "A–F" in all_text
    assert "evaluated_checkpoint = null" in all_text
    assert "≥3 tarla / ≥4 session" in all_text
    assert "Chemical" in all_text or "chemical" in all_text


def test_complete_offline_go_gate_stays_visible_and_frozen(monkeypatch) -> None:
    summary = _summary()
    gates = summary["target_rig_contracts"]["track_action_evaluation"][
        "offline_go_gates"
    ]
    assert gates["precision_minimum"] == 0.98
    assert gates["recall_minimum"] == 0.95
    assert gates["f1_minimum"] == 0.965
    assert gates["crop_hit_rate_maximum"] == 0.005
    assert gates["crop_hit_upper_confidence_bound_required"] is True
    assert gates["duplicate_shot_rate_maximum"] == 0.01
    assert gates["pooled_test_required"] is True
    assert gates["every_test_field_required"] is True

    rendered_text: list[str] = []
    rendered_rows: list[list[list[str]]] = []
    rendered_cards: list[tuple[str, str, str]] = []
    original_add_text = report.add_text
    original_draw_table = report.draw_table
    original_metric_card = report.metric_card

    def capture_text(draw, xy, text, *args, **kwargs):
        rendered_text.append(text)
        return original_add_text(draw, xy, text, *args, **kwargs)

    def capture_table(canvas, box, headers, rows, *args, **kwargs):
        rendered_rows.append(rows)
        return original_draw_table(canvas, box, headers, rows, *args, **kwargs)

    def capture_metric_card(canvas, box, value, label, note, *args, **kwargs):
        rendered_cards.append((value, label, note))
        return original_metric_card(canvas, box, value, label, note, *args, **kwargs)

    monkeypatch.setattr(report, "add_text", capture_text)
    monkeypatch.setattr(report, "draw_table", capture_table)
    monkeypatch.setattr(report, "metric_card", capture_metric_card)

    report.cover(summary, detailed=False)
    report.cover(summary, detailed=True)
    report.proof_plan_page()

    gate_text = " ".join(
        str(cell) for table in rendered_rows for row in table for cell in row
    )
    assert any(
        value == "%96,5" and "gerekli, tek başına GO değil" in label
        for value, label, _ in rendered_cards
    )
    assert any("güvenlik kapısı sayfa 6'da" in note for _, _, note in rendered_cards)
    assert any("güvenlik kapısı sayfa 17'de" in note for _, _, note in rendered_cards)
    for term in (
        "P≥%98",
        "R≥%95",
        "F1≥%96,5",
        "Crop-hit oranı",
        "zorunlu Wilson üst %95 ≤%0,5",
        "duplicate-shot ≤%1",
        "pooled PASS",
        "her-field PASS",
    ):
        assert term in gate_text

    markdown = report.markdown_report(summary)
    assert "zorunlu Wilson üst %95 sınırı `≤0.005`" in markdown
    assert "pooled test ve her test tarlası ayrı ayrı `PASS`" in markdown
    assert "yalnız bir gerekli koşuldur, tek başına GO değildir" in markdown


def test_generated_package_receipt_records_pre_real_status_and_pages(tmp_path) -> None:
    receipt = report.write_package(tmp_path / "report")

    assert receipt["schema_version"] == 2
    assert receipt["status"] == "report_package_complete_pre_real_target_rig_not_ready"
    assert receipt["decision"]["target_rig_status"] == "PRE_REAL_NOT_READY"
    assert receipt["decision"]["field_fire_status"] == "NO-GO"
    assert receipt["decision"]["chemical_fire_status"] == "NO-GO_UNSUPPORTED"
    assert receipt["pdf_pages"] == {
        "BASLA_BURADAN_KONTROLLU_SPOT_SPRAY_POC_V1.pdf": 6,
        "DETAYLI_KONTROLLU_SPOT_SPRAY_POC_V1.pdf": 20,
    }
    assert len(receipt["target_rig_source_sha256"]) == 9
    assert len(receipt["files"]) == 10
