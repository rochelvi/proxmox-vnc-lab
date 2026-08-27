import pytest
from pydantic import ValidationError

from app.config import Settings


def test_templates_parse_with_whitespace():
    settings = Settings(templates="9000:Ubuntu 22.04, 9001: Debian 12 ")
    assert [(item.vmid, item.label) for item in settings.templates_list()] == [
        (9000, "Ubuntu 22.04"),
        (9001, "Debian 12"),
    ]


def test_templates_fall_back_to_template_vmid():
    settings = Settings(template_vmid=9010, templates="")
    assert [(item.vmid, item.label) for item in settings.templates_list()] == [(9010, "template-9010")]


@pytest.mark.parametrize("value", ["missing-label", "not-a-number:Ubuntu", "9000:", "9000:One,9000:Two"])
def test_malformed_templates_raise_validation_error(value):
    with pytest.raises(ValidationError, match="TEMPLATES"):
        Settings(templates=value)
