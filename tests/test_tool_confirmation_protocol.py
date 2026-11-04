from backend.protocol import parse_event


def test_client_confirmation_response_is_a_versioned_protocol_event():
    event = parse_event(
        '{"type":"tool_confirmation_response","protocol_version":"1.0","session_id":"session-1","turn_id":"turn-1","confirmation_id":"confirmation-1","approved":true}',
        direction="client",
    )
    assert event.confirmation_id == "confirmation-1"
    assert event.approved is True
