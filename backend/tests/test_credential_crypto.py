from app.core.credential_crypto import decrypt_secret, encrypt_secret, normalize_jira_domain


def test_encrypt_secret_roundtrip_does_not_store_plaintext() -> None:
    plaintext = "jira-api-token-example"
    ciphertext = encrypt_secret(plaintext)
    assert plaintext not in ciphertext
    assert decrypt_secret(ciphertext) == plaintext


def test_normalize_jira_domain_strips_scheme_and_path() -> None:
    assert normalize_jira_domain("https://team.atlassian.net/jira") == "team.atlassian.net"
    assert normalize_jira_domain("team.atlassian.net") == "team.atlassian.net"
