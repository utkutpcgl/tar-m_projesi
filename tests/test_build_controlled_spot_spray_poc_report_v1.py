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
        }
    )


def test_report_selects_directional_pre_real_model_without_field_go() -> None:
    summary = _summary()
    assert summary["schema_version"] == 4
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
