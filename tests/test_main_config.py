#!/usr/bin/env python3
import inspect
from pathlib import Path
from unittest import mock

import pytest

import yo.main as main
from yo.util import YoExc


@pytest.fixture
def patch_main_config_paths(fake_home, monkeypatch):
    yo_config = fake_home / ".oci" / "yo.ini"
    oci_config = fake_home / ".oci" / "config"
    monkeypatch.setattr(main, "CONFIG_FILE", str(yo_config))
    monkeypatch.setattr(main, "OCI_CONFIG_FILE", str(oci_config))
    return yo_config, oci_config


def _base_config(
    yo_extra: str = "",
    instance_sections: str = "",
    aliases_section: str = "",
) -> str:
    parts = [
        inspect.cleandoc(
            f"""
            [yo]
            instance_compartment_id = ocid1.compartment.oc1..test
            region = us-ashburn-1
            my_email = USER@EXAMPLE.COM
            my_username = testuser
            {yo_extra}
            """
        ).strip(),
        inspect.cleandoc(
            """
            [regions.us-ashburn-1]
            vcn_id = ocid1.vcn.oc1..test
            subnet_id = ocid1.subnet.oc1..test
            """
        ).strip(),
    ]
    if instance_sections:
        parts.append(instance_sections.strip())
    if aliases_section:
        parts.append(aliases_section.strip())
    return "\n\n".join(parts) + "\n"


def test_yo_config_unmodified_true_then_false(patch_main_config_paths):
    yo_config, _ = patch_main_config_paths
    sample = Path(main.SAMPLE_CONFIG_FILE).read_text()
    yo_config.write_text(sample)
    assert main.yo_config_unmodified()

    yo_config.write_text(sample + "\n# local change\n")
    assert not main.yo_config_unmodified()


def test_check_configs_missing_creates_sample_and_raises(
    patch_main_config_paths,
):
    yo_config, _ = patch_main_config_paths
    with mock.patch("rich.console.Console", autospec=True) as console_cls:
        with pytest.raises(YoExc, match="Configuration incomplete"):
            main.check_configs()

    assert yo_config.exists()
    assert yo_config.read_text() == Path(main.SAMPLE_CONFIG_FILE).read_text()
    assert console_cls.return_value.print.call_count > 0


def test_check_configs_complete_and_modified_returns(patch_main_config_paths):
    yo_config, oci_config = patch_main_config_paths
    oci_config.write_text("[DEFAULT]\nregion=us-ashburn-1\n")
    yo_config.write_text(
        _base_config(
            instance_sections="[instances.DEFAULT]\navailability_domain=1\nshape=VM.Standard.E2.1.Micro\nos=Oracle Linux:9"
        )
    )

    with mock.patch("rich.console.Console", autospec=True) as console_cls:
        main.check_configs()
    console_cls.assert_not_called()


def test_check_configs_unmodified_sample_raises(patch_main_config_paths):
    yo_config, oci_config = patch_main_config_paths
    oci_config.write_text("[DEFAULT]\nregion=us-ashburn-1\n")
    yo_config.write_text(Path(main.SAMPLE_CONFIG_FILE).read_text())

    with pytest.raises(YoExc, match="Configuration incomplete"):
        main.check_configs()


def test_load_config_parses_inheritance_and_aliases(patch_main_config_paths):
    yo_config, _ = patch_main_config_paths
    contents = _base_config(
        instance_sections=inspect.cleandoc(
            """
            [instances.base]
            availability_domain = 3
            shape = VM.Standard.E2.1.Micro
            os = Oracle Linux:9
            tasks = prep, bootstrap

            [instances.DEFAULT]
            inherit = base
            shape = VM.Standard.A1.Flex
            cpu = 2
            mem = 12
            name = web
            """
        ),
        aliases_section=inspect.cleandoc(
            """
            [aliases]
            ll = list --all
            """
        ),
    )
    yo_config.write_text(contents)

    full = main.load_config(str(yo_config))
    default = full.profiles["DEFAULT"]
    assert full.config.my_email == "user@example.com"
    assert default.shape == "VM.Standard.A1.Flex"
    assert default.os == "Oracle Linux:9"
    assert default.tasks == ["prep", "bootstrap"]
    assert default.cpu == 2.0
    assert default.mem == 12.0
    assert full.aliases["ll"] == "list --all"


def test_load_config_rejects_hash_in_alias_by_default(
    patch_main_config_paths,
):
    yo_config, _ = patch_main_config_paths
    yo_config.write_text(
        _base_config(
            instance_sections=inspect.cleandoc(
                """
                [instances.DEFAULT]
                availability_domain = 1
                shape = VM.Standard.E2.1.Micro
                os = Oracle Linux:9
                """
            ),
            aliases_section=inspect.cleandoc(
                """
                [aliases]
                bad = list # inline hash should fail
                """
            ),
        )
    )
    with pytest.raises(YoExc, match="aliases"):
        main.load_config(str(yo_config))


def test_load_config_allows_hash_in_alias_when_enabled(
    patch_main_config_paths,
):
    yo_config, _ = patch_main_config_paths
    yo_config.write_text(
        _base_config(
            yo_extra="allow_hash_in_config_value = true",
            instance_sections=inspect.cleandoc(
                """
                [instances.DEFAULT]
                availability_domain = 1
                shape = VM.Standard.E2.1.Micro
                os = Oracle Linux:9
                """
            ),
            aliases_section=inspect.cleandoc(
                """
                [aliases]
                c = list # trailing hash is allowed
                """
            ),
        )
    )

    full = main.load_config(str(yo_config))
    assert full.aliases["c"] == "list # trailing hash is allowed"


def test_load_config_rejects_circular_inheritance(patch_main_config_paths):
    yo_config, _ = patch_main_config_paths
    yo_config.write_text(
        _base_config(
            instance_sections=inspect.cleandoc(
                """
                [instances.a]
                inherit = b

                [instances.b]
                inherit = a
                """
            )
        )
    )
    with pytest.raises(YoExc, match="Circular dependency"):
        main.load_config(str(yo_config))
