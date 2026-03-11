from src.schemas.jira import JiraExtractionConfig


def test_jira_extraction_config_accepts_legacy_basic_alias() -> None:
    config = JiraExtractionConfig.model_validate({"auth_type": "basic", "streams": ["issues"]})

    assert config.auth_type == "basic_token"
