from src.services.meltano import _extract_records_processed


def test_extract_records_processed_from_json_metrics() -> None:
    stdout = '{"metrics":{"records_processed":42}}\n'
    stderr = ""
    assert _extract_records_processed(stdout, stderr) == 42


def test_extract_records_processed_from_text_logs() -> None:
    stdout = "job completed, records processed: 128"
    stderr = ""
    assert _extract_records_processed(stdout, stderr) == 128
