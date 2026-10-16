import pytest
import responses

from apps.notifications import sms


def test_mock_records_and_never_calls_out(settings):
    settings.SMS_PROVIDER = "mock"
    sms.MockSms.outbox.clear()
    assert sms.send_sms("+2348012345678", "hello").startswith("mock-")
    assert sms.MockSms.outbox == [("+2348012345678", "hello")]


@responses.activate
def test_termii_failure_raises(settings):
    settings.SMS_PROVIDER = "termii"
    responses.post("https://termii.test/api/sms/send", status=500)
    settings.TERMII_BASE_URL = "https://termii.test"
    with pytest.raises(sms.SmsError):
        sms.send_sms("+2348012345678", "hello")
    assert responses.calls[0].request.body and b'"to": "2348012345678"' in responses.calls[0].request.body
