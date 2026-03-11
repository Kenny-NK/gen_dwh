from src.schemas.jira import JiraExtractionConfig


def test_jira_extraction_config_accepts_legacy_basic_alias() -> None:
    config = JiraExtractionConfig.model_validate({"auth_type": "basic", "streams": ["issues"]})

    assert config.auth_type == "basic_token"


def test_jira_extraction_config_infers_jql_mode_for_legacy_jql_payload() -> None:
    config = JiraExtractionConfig.model_validate(
        {
            "streams": ["issues"],
            "jql": 'project = DWHTOT ORDER BY created DESC',
        }
    )

    assert config.query_mode == "jql"
    assert config.jql == 'project = DWHTOT ORDER BY created DESC'


def test_jira_extraction_config_normalizes_blank_jql_to_none() -> None:
    config = JiraExtractionConfig.model_validate(
        {
            "streams": ["issues"],
            "query_mode": "jql",
            "jql": "   ",
        }
    )

    assert config.query_mode == "jql"
    assert config.jql is None
