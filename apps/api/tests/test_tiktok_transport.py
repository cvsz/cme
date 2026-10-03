import pytest

from cme_api.integrations.tiktok import TikTokClient, TikTokTransportError


def test_upload_host_accepts_official_https():
    TikTokClient.validate_upload_url(
        "https://open-upload.tiktokapis.com/video/?upload_id=x"
    )


def test_upload_host_rejects_untrusted_host():
    with pytest.raises(TikTokTransportError):
        TikTokClient.validate_upload_url("https://example.com/video/?upload_id=x")
