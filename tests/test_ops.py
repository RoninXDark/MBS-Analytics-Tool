from pathlib import Path

from bond_story_reporting.ops import bundle_output_artifacts, run_doctor


def test_doctor_generates_report(tmp_path: Path):
    report = run_doctor(output_dir=tmp_path)
    assert "python" in report
    assert "dependencies" in report
    assert (tmp_path / "doctor_report.json").exists()


def test_bundle_output_artifacts(tmp_path: Path):
    source = tmp_path / "output"
    source.mkdir(parents=True, exist_ok=True)
    (source / "a.txt").write_text("hello", encoding="utf-8")
    (source / "nested").mkdir(parents=True, exist_ok=True)
    (source / "nested" / "b.txt").write_text("world", encoding="utf-8")

    bundle = bundle_output_artifacts(source)
    assert bundle.exists()
    assert bundle.suffix == ".zip"

