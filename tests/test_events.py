import copy
from custom_components.ajaxsecurflow.events import apply_event
from custom_components.ajaxsecurflow.models import HubData


def _data():
    return {
        "HUB1": HubData(
            hub={"id": "HUB1", "name": "Casa", "state": "DISARMED", "online": True},
            groups={"G1": {"id": "G1", "name": "Planta baja", "state": "DISARMED"}},
            devices={
                "D1": {"id": "D1", "name": "Puerta", "deviceType": "DoorProtect", "reed_closed": True,
                       "extra_contact_aware": True, "extra_contact_closed": True, "online": True, "malfunctions": []},
                "D2": {"id": "D2", "name": "Salón", "deviceType": "MotionProtect", "motion_detected": False, "online": True},
            },
        )
    }


def _env(hub_id="HUB1", event_type="SECURITY", tag="", transition="TRIGGERED", source_id="", source_type="DEVICE", ts="2026-09-18T10:00:00+00:00"):
    return {
        "id": "1", "hub_id": hub_id, "event_type": event_type, "title": "t", "description": "d",
        "severity": "info", "timestamp": ts, "media_urls": [], "source": "sqs",
        "data": {"event": {"eventTag": tag, "transition": transition, "sourceObjectId": source_id,
                           "sourceObjectType": source_type, "hubId": hub_id}},
    }


def test_unknown_hub_returns_false_and_leaves_data():
    data = _data()
    before = copy.deepcopy(data["HUB1"].hub)
    assert apply_event(data, _env(hub_id="NOPE")) is False
    assert data["HUB1"].hub == before


def test_arm_updates_hub_state():
    data = _data()
    assert apply_event(data, _env(tag="Arm")) is True
    assert data["HUB1"].hub["state"] == "ARMED"


def test_disarm_clears_triggered():
    data = _data()
    data["HUB1"].triggered = True
    apply_event(data, _env(tag="Disarm"))
    assert data["HUB1"].hub["state"] == "DISARMED"
    assert data["HUB1"].triggered is False


def test_night_mode_on():
    data = _data()
    apply_event(data, _env(tag="NightModeOn"))
    assert data["HUB1"].hub["state"] == "NIGHT_MODE"


def test_group_arm_updates_group_not_hub():
    data = _data()
    apply_event(data, _env(tag="Arm", source_id="G1", source_type="GROUP"))
    assert data["HUB1"].groups["G1"]["state"] == "ARMED"
    assert data["HUB1"].hub["state"] == "DISARMED"


def test_alarm_sets_triggered():
    data = _data()
    apply_event(data, _env(event_type="ALARM", tag="MotionDetected", source_id="D2"))
    assert data["HUB1"].triggered is True
    assert data["HUB1"].devices["D2"]["motion_detected"] is True


def test_motion_recovered_clears_flag():
    data = _data()
    data["HUB1"].devices["D2"]["motion_detected"] = True
    apply_event(data, _env(tag="MotionDetected", transition="RECOVERED", source_id="D2"))
    assert data["HUB1"].devices["D2"]["motion_detected"] is False


def test_ext_contact_opened_and_recovered():
    data = _data()
    apply_event(data, _env(tag="ExtContactOpened", source_id="D1"))
    assert data["HUB1"].devices["D1"]["extra_contact_closed"] is False
    apply_event(data, _env(tag="ExtContactOpened", transition="RECOVERED", source_id="D1"))
    assert data["HUB1"].devices["D1"]["extra_contact_closed"] is True


def test_reed_opened_updates_reed_closed():
    data = _data()
    apply_event(data, _env(tag="Opened", source_id="D1"))
    assert data["HUB1"].devices["D1"]["reed_closed"] is False


def test_tamper_and_offline():
    data = _data()
    apply_event(data, _env(tag="TamperOpened", source_id="D1"))
    assert data["HUB1"].devices["D1"]["tampered"] is True
    apply_event(data, _env(tag="Offline", source_id="D1"))
    assert data["HUB1"].devices["D1"]["online"] is False
    apply_event(data, _env(tag="Offline", transition="RECOVERED", source_id="D1"))
    assert data["HUB1"].devices["D1"]["online"] is True


def test_malfunction_added_and_recovered():
    data = _data()
    apply_event(data, _env(event_type="MALFUNCTION", tag="BatteryLow", source_id="D1"))
    assert data["HUB1"].devices["D1"]["malfunctions"] == ["BatteryLow"]
    apply_event(data, _env(event_type="FUNCTION_RECOVERED", tag="BatteryLow", transition="RECOVERED", source_id="D1"))
    assert data["HUB1"].devices["D1"]["malfunctions"] == []


def test_unknown_device_only_records_last_event():
    data = _data()
    assert apply_event(data, _env(tag="MotionDetected", source_id="NOPE")) is True
    assert data["HUB1"].last_event["tag"] == "MotionDetected"


def test_idempotent_on_duplicate():
    data = _data()
    env = _env(event_type="ALARM", tag="MotionDetected", source_id="D2")
    apply_event(data, env)
    snapshot = copy.deepcopy(data["HUB1"])
    apply_event(data, env)
    assert data["HUB1"] == snapshot
