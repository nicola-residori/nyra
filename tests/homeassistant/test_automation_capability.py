import inspect

import pytest


def test_adapter_owns_nyra_specific_authenticated_automation_paths():
    from homeassistant.custom_components.nyra.automation_capability import (
        AUTOMATION_COLLECTION_PATH,
        AUTOMATION_ITEM_PATH,
        COMPLETE_ONE_SHOT_SERVICE,
    )
    assert AUTOMATION_COLLECTION_PATH == "/api/nyra/automations"
    assert AUTOMATION_ITEM_PATH == "/api/nyra/automations/{automation_id}"
    assert COMPLETE_ONE_SHOT_SERVICE == "complete_one_shot"


def test_managed_marker_is_explicit_and_manual_automation_is_not_owned():
    from homeassistant.custom_components.nyra.automation_capability import (
        is_nyra_managed,
    )
    assert is_nyra_managed(
        {"description": "[NYRA managed_by=NYRA behavior_b64=abc]"}
    )
    assert not is_nyra_managed(
        {"description": "Created manually in Home Assistant"}
    )


def test_adapter_validates_before_write_and_never_interprets_natural_language():
    import homeassistant.custom_components.nyra.automation_capability as module

    source = inspect.getsource(module)
    assert "async_validate_config_item" in source
    assert "parse_command" not in source
    assert "Skill" not in source
    assert "LLM" not in source


@pytest.mark.asyncio
async def test_one_shot_completion_physically_deletes_only_nyra_managed_automation():
    from homeassistant.custom_components.nyra.automation_capability import (
        complete_one_shot,
    )

    class Backend:
        def __init__(self, current):
            self.current = current
            self.deleted = []

        async def read(self, automation_id):
            return self.current

        async def delete(self, automation_id):
            self.deleted.append(automation_id)
            self.current = None
            return True

    managed = Backend(
        {"description": "[NYRA managed_by=NYRA behavior_b64=abc]"}
    )
    manual = Backend({"description": "manual"})

    assert await complete_one_shot(managed, "nyra_one") is True
    assert managed.deleted == ["nyra_one"]

    assert await complete_one_shot(manual, "manual_one") is False
    assert manual.deleted == []
