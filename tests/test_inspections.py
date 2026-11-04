"""GoCanvas risk inspections: form import, parsing, revisions, and linking.

Fixtures are real submissions of the Chipotle RiskGate form with names, addresses, store
numbers, and notes replaced. `submission_pdf_sample` is the one behind
docs/risk-submissions/Chipotle_Riskgate_Inspection_Form.pdf, so its expectations are the PDF's.
"""

import copy
import json
import logging
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app import load_inspections, relink_inspections
from app.db.session import SessionLocal
from app.models import InspectionKind, InspectionSubmission, Location, ServiceOrder
from app.services.inspections import (
    InspectionError,
    import_form,
    split_options,
    store_submission,
)

FIXTURES = Path(__file__).parent / "fixtures" / "gocanvas"
FORM = json.loads((FIXTURES / "risk_form.json").read_text())
SERVICE_LINE_AREAS = [
    "Point of Sale (Smart Safe)",
    "Front Make Line (FML Wall Cavity & FML Internals)",
    "Digital Make Line / Second Make Line (Wall Junction, IT Cabinet, & Internals)",
    "Grill",
    "Fryer",
]


def submission(name: str) -> dict:
    return json.loads((FIXTURES / f"submission_{name}.json").read_text())


def load(db, operator_id, *names: str) -> list[InspectionSubmission]:
    import_form(db, operator_id, FORM, InspectionKind.risk)
    stored = [store_submission(db, operator_id, submission(n)).submission for n in names]
    db.commit()
    return stored


def zones_by_key(stored: InspectionSubmission) -> dict:
    return {zone.zone_key: zone for zone in stored.risk_zones}


def issues(stored: InspectionSubmission) -> list[tuple[str | None, str]]:
    return [(w["field_key"], w["issue"]) for w in stored.parse_warnings]


def test_form_import_derives_zones_and_maps_every_entry(world):
    with SessionLocal() as db:
        form = import_form(db, world.op_a, FORM, InspectionKind.risk)
        db.commit()
        assert [zone.name for zone in form.zones] == [
            "Front of House",
            "Restrooms",
            "Service Line / Food Preparation",
            "Kitchen Support Areas",
            "Office & Administrative Areas",
            "Rear Entry & Trash Room",
            "Basement (if applicable)",
            "Shared Structures /Adjacent Tenancies",
            "Ceiling Voids, Exterior Perimeter, Paneling, Dumbwaiter/Elevator, Mall location",
        ]
        assert len(form.fields) == 190
        assert [f.label for f in form.fields if f.field_key is None] == []
        by_entry = {f.entry_id: f for f in form.fields}
        # Front of House: areas are multi-select, pest type single; options trimmed.
        assert (by_entry[753278043].field_key, by_entry[753278043].multi_select) == ("areas", True)
        assert (by_entry[753278051].field_key, by_entry[753278051].multi_select) == (
            "pest_types",
            False,
        )
        assert by_entry[753278044].options == ["Metal", "Wood"]
        # RAMP and the summary sit in the last zone's section but belong to the submission.
        assert (by_entry[753278214].field_key, by_entry[753278214].zone_key) == (
            "ramp_recommendation",
            None,
        )
        assert by_entry[753278217].field_key == "material.chicken_fence"

        # Re-importing replaces the map rather than adding to it.
        form = import_form(db, world.op_a, FORM, InspectionKind.risk)
        db.commit()
        assert (len(form.zones), len(form.fields)) == (9, 190)


def test_pdf_sample_matches_the_pdf_report(world):
    with SessionLocal() as db:
        [stored] = load(db, world.op_a, "pdf_sample")
        assert stored.inspector_name == "Test Inspector"
        assert stored.inspected_at.isoformat() == "2026-10-28T05:07:00"
        assert (stored.store_label, stored.store_number) == ("Chipotle - Store #9001", "9001")
        assert stored.risk_summary.ramp_recommendation == 3
        assert stored.parse_warnings == [] and stored.unmapped_entry_ids == []

        # The PDF's station details, zone by zone.
        rows = [
            (
                z.inspected,
                z.areas,
                z.all_areas_inspected,
                z.doors_are,
                z.door_sweeps_ok,
                z.doors_aligned,
                z.rodent_activity,
                z.pest_activity,
                z.pest_types,
                (z.sanitation_risk, z.structural_risk, z.overall_risk),
            )
            for z in stored.risk_zones
        ]
        assert rows == [
            (
                "yes",
                ["Beverage Station", "Booths/Seating", "Guest Ordering Line"],
                None,
                ["Metal"],
                False,
                True,
                False,
                True,
                ["Flies"],
                (3, 2, 3),
            ),
            ("yes", ["Mens", "Womans"], None, ["Metal"], False, True, False, False, [], (1, 2, 2)),
            ("yes", SERVICE_LINE_AREAS, True, [], None, None, False, False, [], (3, 4, 4)),
            ("yes", rows[3][1], True, ["Metal"], True, True, False, False, [], (3, 3, 3)),
            ("yes", ["Managers Office"], True, ["Metal"], False, True, False, False, [], (1, 3, 2)),
            ("yes", [], None, ["Metal"], True, True, False, False, [], (2, 1, 1)),
            ("n/a", [], None, [], None, None, None, None, [], (None, None, None)),
            ("n/a", [], None, [], None, None, None, None, [], (None, None, None)),
            ("yes", [], None, [], None, None, False, False, [], (1, 1, 1)),
        ]
        assert len(rows[3][1]) == 12 and rows[3][1][0] == "Chefs table (Behind FML)"
        zones = zones_by_key(stored)
        assert zones["rear_entry_trash_room"].attributes == {
            "dumpster": ["Shared"],
            "trash_room": ["Separated / Off Premise"],
        }
        assert zones[stored.risk_zones[8].zone_key].attributes == {
            "ceiling": ["Drop Ceiling"],
            "exterior_perimeter": ["Patio", "Parking Lot"],
            "paneling": ["Corrugated Tin and Trim"],
            "in_mall": False,
            "dumbwaiter_operational": False,
        }
        # The zone summary: only Front of House had activity.
        assert [z.has_activity for z in stored.risk_zones] == [True] + [False] * 8
        assert {m.material_key: m.used for m in stored.risk_materials} == {
            "door_sweeps": False,
            "chicken_fence": False,
            "copper_mesh": False,
            "excluder_pad": False,
            "tin_cats": False,
            "snap_traps": False,
            "metal_flashing": False,
            "caulking_sealant": False,
        }


def test_every_response_is_kept_as_received(world):
    with SessionLocal() as db:
        [stored] = load(db, world.op_a, "pdf_sample")
        source = submission("pdf_sample")["responses"]
        assert [
            (r.gocanvas_response_id, r.entry_id, r.label, r.displayed) for r in stored.responses
        ] == [(r["id"], r["entry_id"], r["label"], r["displayed"]) for r in source]
        assert [r.value if r.value is not None else r.value_json for r in stored.responses] == [
            r["value"] for r in source
        ]
        assert stored.raw_payload == submission("pdf_sample")


@pytest.mark.parametrize("name", ["newline_separated", "comma_separated"])
def test_multi_selects_split_on_any_separator(world, name):
    with SessionLocal() as db:
        [stored] = load(db, world.op_a, name)
        zones = zones_by_key(stored)
        assert set(zones["front_of_house"].areas) == {
            "Beverage Station",
            "Booths/Seating",
            "Guest Ordering Line",
        }
        assert set(zones["restrooms"].areas) == {"Mens", "Womans"}
        assert not [w for w in stored.parse_warnings if "options" in w["issue"]]


def test_split_options_keeps_options_that_contain_commas():
    options = ["Grill", SERVICE_LINE_AREAS[2], "Fryer"]
    assert split_options(f"Grill,{SERVICE_LINE_AREAS[2]},Fryer ", options) == (
        ["Grill", SERVICE_LINE_AREAS[2], "Fryer"],
        [],
    )
    assert split_options("grill\r\nWok", options) == (["Grill", "Wok"], ["Wok"])
    assert split_options("", options) == ([], [])


def test_retired_options_are_kept_with_a_warning(world):
    with SessionLocal() as db:
        [stored] = load(db, world.op_a, "retired_option")
        assert zones_by_key(stored)["front_of_house"].pest_types == ["Rats"]
        assert ("pest_types", "'Rats' is not one of the form's options") in issues(stored)


def test_pest_types_get_one_spelling_across_zones(world):
    payload = submission("pdf_sample")
    for response in payload["responses"]:
        if response["export_label"] == "TypeOfPest":
            response["value"] = "Occasional Invader"
    with SessionLocal() as db:
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        stored = store_submission(db, world.op_a, payload).submission
        assert zones_by_key(stored)["front_of_house"].pest_types == ["Occasional Invaders"]
        assert stored.parse_warnings == []


def test_ramp_digits_and_blanks(world):
    with SessionLocal() as db:
        digit, blank = load(db, world.op_a, "ramp_digit", "newline_separated")
        assert digit.risk_summary.ramp_recommendation == 3
        assert blank.risk_summary.ramp_recommendation is None
        assert "ramp_recommendation" not in [key for key, _ in issues(blank)]


def test_material_quantities_from_older_submissions(world):
    with SessionLocal() as db:
        [stored] = load(db, world.op_a, "material_quantities")
        materials = {m.material_key: (m.used, m.quantity) for m in stored.risk_materials}
        assert materials["copper_mesh"] == (True, Decimal("24"))
        assert materials["snap_traps"] == (True, Decimal("50"))
        assert not [w for w in stored.parse_warnings if w["field_key"].startswith("material.")]


def test_text_in_a_score_is_left_null_and_warned(world):
    with SessionLocal() as db:
        [stored] = load(db, world.op_a, "text_in_score")
        zone = zones_by_key(stored)["service_line_food_preparation"]
        assert zone.structural_risk is None
        assert ("structural_risk", "expected a risk score from 1 to 5") in issues(stored)
        [raw] = [r for r in stored.responses if r.export_label == "Structural2"]
        assert raw.value.startswith("Nothing observed")


def test_unpadded_time_and_blank_store(world):
    with SessionLocal() as db:
        short, blank = load(db, world.op_a, "short_time", "blank_store")
        assert short.inspected_at.strftime("%H:%M") == "20:45"
        assert (blank.store_label, blank.store_number, blank.location_id) == (None, None, None)


def test_revisions_replace_the_parsed_rows_and_stale_ones_are_ignored(world):
    original = submission("pdf_sample")
    revised = copy.deepcopy(original)
    revised.update(revision=True, revised_at="2026-10-30T12:00:00Z")
    for response in revised["responses"]:
        if response["export_label"] == "Sanitation":
            response["value"] = "5"
    with SessionLocal() as db:
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        assert store_submission(db, world.op_a, original).outcome == "created"
        db.commit()
        assert store_submission(db, world.op_a, original).outcome == "unchanged"
        result = store_submission(db, world.op_a, revised)
        db.commit()
        assert result.outcome == "updated"
        stored = result.submission
        assert (len(stored.responses), len(stored.risk_zones)) == (190, 9)
        assert zones_by_key(stored)["front_of_house"].sanitation_risk == 5
        # The original arriving late doesn't undo the revision.
        assert store_submission(db, world.op_a, original).outcome == "stale"
        db.commit()
        db.refresh(stored)
        assert zones_by_key(stored)["front_of_house"].sanitation_risk == 5
        same_id = InspectionSubmission.gocanvas_submission_id == original["id"]
        assert db.scalars(select(InspectionSubmission).where(same_id)).all() == [stored]


def test_links_the_order_by_work_order_number_else_the_store(world):
    payload = submission("pdf_sample")
    for response in payload["responses"]:
        if response["export_label"] == "WorkOrderI":
            response["value"] = "5550001"
        if response["export_label"] == "StoreNumbe":
            response["value"] = "Chipotle - Store #1"
    with SessionLocal() as db:
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        # The store number alone finds the location ("ACME TACOS - STORE #1").
        stored = store_submission(db, world.op_a, payload).submission
        assert (stored.location_id, stored.service_order_id) == (world.location_a, None)

        db.get(ServiceOrder, world.service_order_a).order_number = "5550001"
        payload["revised_at"] = "2026-10-30T12:00:00Z"
        stored = store_submission(db, world.op_a, payload).submission
        assert (stored.location_id, stored.service_order_id) == (
            world.location_a,
            world.service_order_a,
        )
        # Another operator's copy of the submission never links operator A's order or store.
        import_form(db, world.op_b, FORM, InspectionKind.risk)
        other = store_submission(db, world.op_b, payload).submission
        assert (other.location_id, other.service_order_id) == (None, None)


def test_submission_needs_its_form_and_operator_scope(world):
    with SessionLocal() as db:
        with pytest.raises(InspectionError, match="hasn't been imported"):
            store_submission(db, world.op_a, submission("pdf_sample"))
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        with pytest.raises(InspectionError, match="hasn't been imported"):
            store_submission(db, world.op_b, submission("pdf_sample"))
        with pytest.raises(InspectionError, match="Not a GoCanvas submission"):
            store_submission(db, world.op_a, FORM)


def test_loader_command(world, tmp_path, caplog):
    form_file = tmp_path / "form.json"
    form_file.write_text(json.dumps(FORM))
    files = [str(FIXTURES / f"submission_{n}.json") for n in ("pdf_sample", "ramp_digit")]
    args = ["--operator-id", str(world.op_a), "--form", str(form_file), "--kind", "risk"]
    args.append("--no-photos")  # photo fetching is covered in test_inspection_photos.py
    caplog.set_level("INFO")
    assert load_inspections.main([*args, *files]) == 0
    assert "Submissions: 2 created" in caplog.text
    assert load_inspections.main([*args, *files]) == 0
    assert "Submissions: 2 unchanged" in caplog.text
    assert load_inspections.main([*args, "--reparse", *files]) == 0
    assert "Submissions: 2 updated" in caplog.text


REPEAT_OFFSET = 10_000_000_000  # above every real entry id


def _two_summary_sections() -> tuple[dict, dict]:
    """The form with a second section asking for the summary too, like National Accounts', and a
    submission answering both."""
    form = copy.deepcopy(FORM)
    form["id"] = 5962102
    payload = submission("pdf_sample")
    payload["form_id"] = 5962102
    index = next(
        i
        for i, section in enumerate(form["sections"])
        if section["description"].startswith("Ceiling Voids")
    )
    second = copy.deepcopy(form["sections"][index])
    second["id"] += REPEAT_OFFSET
    second["description"] = "Receiving & Refuse Areas"
    new_ids = {}
    for sheet in second["sheets"]:
        for entry in sheet["entries"]:
            new_ids[entry["id"]] = entry["id"] + REPEAT_OFFSET
            entry["id"] = new_ids[entry["id"]]
    form["sections"].insert(index + 1, second)
    payload["responses"].extend(
        {
            **response,
            "id": response["id"] + REPEAT_OFFSET,
            "entry_id": new_ids[response["entry_id"]],
        }
        for response in list(payload["responses"])
        if response["entry_id"] in new_ids
    )
    return form, payload


def _answer_summary(payload: dict, form: dict, *, section: int, **values: str) -> None:
    """Set the RAMP recommendation and manager summary in the first (1) or second (2) section."""
    entries = [
        entry
        for s in form["sections"]
        for sheet in s.get("sheets") or []
        for entry in sheet["entries"]
    ]
    labels = {"ramp": "ramp recommendation", "manager": "service manager"}
    for name, value in values.items():
        wanted = [e["id"] for e in entries if e["label"].lower().startswith(labels[name])]
        for response in payload["responses"]:
            if response["entry_id"] in wanted and (response["entry_id"] >= REPEAT_OFFSET) == (
                section == 2
            ):
                response["value"] = value


def test_a_blank_second_summary_doesnt_replace_the_first(world):
    form, payload = _two_summary_sections()
    _answer_summary(payload, form, section=1, ramp="RAMP 3", manager="Found it.")
    _answer_summary(payload, form, section=2, ramp="", manager="")
    with SessionLocal() as db:
        import_form(db, world.op_a, form, InspectionKind.risk)
        stored = store_submission(db, world.op_a, payload).submission
        assert stored.risk_summary.ramp_recommendation == 3
        assert stored.risk_summary.manager_summary == "Found it."
        assert len(stored.risk_zones) == len(zones_by_key(stored))
        # Every response is still stored as sent.
        assert len(stored.responses) == len(payload["responses"])
        db.rollback()


def test_a_second_summary_fills_a_blank_first_and_different_notes_are_joined(world):
    form, payload = _two_summary_sections()
    _answer_summary(payload, form, section=1, ramp="", manager="First.")
    _answer_summary(payload, form, section=2, ramp="RAMP 1", manager="Second.")
    with SessionLocal() as db:
        import_form(db, world.op_a, form, InspectionKind.risk)
        stored = store_submission(db, world.op_a, payload).submission
        assert stored.risk_summary.ramp_recommendation == 1
        assert stored.risk_summary.manager_summary == "First.\n\nSecond."
        db.rollback()


def test_two_different_recommendations_keep_the_first_with_a_warning(world):
    form, payload = _two_summary_sections()
    _answer_summary(payload, form, section=1, ramp="RAMP 2")
    _answer_summary(payload, form, section=2, ramp="RAMP 3")
    with SessionLocal() as db:
        import_form(db, world.op_a, form, InspectionKind.risk)
        stored = store_submission(db, world.op_a, payload).submission
        assert stored.risk_summary.ramp_recommendation == 2
        assert (
            "ramp_recommendation",
            "asked twice with different answers; kept the first",
        ) in issues(stored)
        db.rollback()


def _at_address(payload: dict, address: str, city: str) -> dict:
    for response in payload["responses"]:
        label = response["export_label"]
        if label == "WorkOrderI":
            response["value"] = "Reeves"
        elif label == "StoreNumbe":
            response["value"] = "SWEETGREEN - SOMEWHERE"
        elif label == "Address":
            response["value"] = address
        elif label == "City":
            response["value"] = city
    return payload


def _with_work_order(payload: dict, ref: str, store: str = "") -> dict:
    for response in payload["responses"]:
        if response["export_label"] == "WorkOrderI":
            response["value"] = ref
        elif response["export_label"] == "StoreNumbe":
            response["value"] = store
    return payload


@pytest.mark.parametrize(
    "ref",
    [
        "1",
        "Inspection 1",
        "Inspection  1",
        "Inspect 1",
        "1 inspection",
        "Risk assessment #1",
        "#1 risk assessment",
        "Chipotle #1\n116 Andrew Dr, Pittsburgh, PA",
        "Inspection of #1. 89 Wagner Rd, Monaca, PA 15061",
    ],
)
def test_links_by_a_store_number_typed_in_the_work_order(world, ref):
    with SessionLocal() as db:
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        stored = store_submission(
            db, world.op_a, _with_work_order(submission("pdf_sample"), ref)
        ).submission
        assert stored.location_id == world.location_a
        db.rollback()


@pytest.mark.parametrize(
    "ref",
    [
        "Risk assessment",
        "assessment",
        "#999 risk assessment",
        "1 Andrew Dr",
        "Inspection 1 Main St",
    ],
)
def test_other_work_order_text_finds_no_store(world, ref):
    with SessionLocal() as db:
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        stored = store_submission(
            db, world.op_a, _with_work_order(submission("pdf_sample"), ref)
        ).submission
        assert stored.location_id is None
        db.rollback()


def test_a_store_number_that_matches_nothing_never_follows_the_address(world):
    """An inspector picks another customer's store on the form: its address must not link it."""
    with SessionLocal() as db:
        location = db.get(Location, world.location_a)
        location.address, location.city = "1500 3RD AVE", "NEW YORK"
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        payload = _at_address(submission("pdf_sample"), "1500 3rd Ave", "New York")
        _with_work_order(payload, "Risk assessment", "SWEETGREEN - Loc #304851")
        stored = store_submission(db, world.op_a, payload).submission
        assert (stored.store_number, stored.location_id) == ("304851", None)
        db.rollback()


def test_the_work_order_beats_a_wrong_pick_on_the_form(world):
    with SessionLocal() as db:
        location = db.get(Location, world.location_a)
        location.pestpac_company = "CHIPOTLE - STORE #5221"
        other = Location(
            operator_id=world.op_a,
            bill_to_id=world.bill_to_a,
            pestpac_location_id=800998,
            pestpac_fetched_at=location.pestpac_fetched_at,
            pestpac_company="SWEETGREEN",
            address="1500 3RD AVE",
            city="NEW YORK",
        )
        db.add(other)
        db.flush()
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        payload = _at_address(submission("pdf_sample"), "1500 3rd Ave", "New York")
        _with_work_order(
            payload, "Chipotle #5221\n116 Andrew Dr, Pittsburgh, PA", "SWEETGREEN - Loc #304851"
        )
        stored = store_submission(db, world.op_a, payload).submission
        assert stored.location_id == world.location_a
        db.rollback()


def test_relink_applies_the_rules_to_stored_submissions(world, caplog):
    with SessionLocal() as db:
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        stored = store_submission(
            db, world.op_a, _with_work_order(submission("pdf_sample"), "Inspection 1")
        ).submission
        stored.location_id = None
        db.commit()
        submission_id = stored.id

    args = ["--operator-id", str(world.op_a)]
    assert relink_inspections.main([*args, "--dry-run"]) == 0
    with SessionLocal() as db:
        assert db.get(InspectionSubmission, submission_id).location_id is None

    assert relink_inspections.main(args) == 0
    with SessionLocal() as db:
        assert db.get(InspectionSubmission, submission_id).location_id == world.location_a

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.relink_inspections"):
        assert relink_inspections.main(args) == 0
    assert "0 submissions changed: 0 to another store" in caplog.text
    assert relink_inspections.main(["--operator-id", str(world.op_b)]) == 0
    with SessionLocal() as db:
        assert db.get(InspectionSubmission, submission_id).location_id == world.location_a


def test_links_by_address_only_when_one_location_is_there(world):
    with SessionLocal() as db:
        location = db.get(Location, world.location_a)
        location.address, location.city = "10 HUDSON YARDS", "NEW YORK"
        import_form(db, world.op_a, FORM, InspectionKind.risk)
        payload = _at_address(submission("pdf_sample"), "10 Hudson Yards ", "New York")
        stored = store_submission(db, world.op_a, payload).submission
        assert (stored.store_number, stored.location_id) == (None, world.location_a)

        other = db.scalar(
            select(Location).where(
                Location.id != world.location_a, Location.operator_id == world.op_a
            )
        )
        if other is None:
            other = Location(
                operator_id=world.op_a,
                bill_to_id=world.bill_to_a,
                pestpac_location_id=800999,
                pestpac_fetched_at=location.pestpac_fetched_at,
            )
            db.add(other)
        other.address, other.city = "10 HUDSON YARDS", "NEW YORK"
        other.removed_at = None
        db.flush()
        payload["revised_at"] = "2026-10-30T12:00:00Z"
        stored = store_submission(db, world.op_a, payload).submission
        assert stored.location_id is None  # two locations there: not a guess
        db.rollback()
