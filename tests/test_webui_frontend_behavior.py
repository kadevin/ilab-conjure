from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.frontend_runner import compatibility_load_tests, run_frontend


class WebUIFrontendBehaviorTests(unittest.TestCase):


    def test_real_nano_defaults_survive_fixed_controls_and_resolve(self) -> None:
        from codex_image.webui.app import create_app
        from tests.test_provider_registry import command_fixture, resolver_fixture

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                api_settings_path=root / "api-settings.json",
                auth_settings_path=root / "auth-settings.json",
                webui_settings_path=root / "webui-settings.json",
                client_factory=lambda: object(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            with TestClient(app) as client:
                payload = client.get("/api/generation-catalog").json()
            fixture = root / "generation-catalog.json"
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            result = run_frontend(
                self, "catalog_default_parameters.ts", backend_fixture=True,
                node_test=False, env={"GENERATION_CATALOG_FIXTURE": str(fixture)},
            )
            parameters_by_model = json.loads(result.stdout)

        self.assertEqual(parameters_by_model["nano-banana-pro"]["canvas.resolution"], "1K")
        for model_id, parameters in parameters_by_model.items():
            with self.subTest(model=model_id):
                resolver = resolver_fixture(
                    canonical_model_id=model_id,
                    mapped_parameter_ids=frozenset(parameters),
                )
                plan = resolver.resolve(command_fixture(
                    canonical_model_id=model_id,
                    parameters=parameters,
                ))
                self.assertEqual(dict(plan.command.parameters), parameters)

    def test_real_generation_catalog_payload_matches_frontend_validator(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                api_settings_path=root / "api-settings.json",
                auth_settings_path=root / "auth-settings.json",
                webui_settings_path=root / "webui-settings.json",
                client_factory=lambda: object(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            with TestClient(app) as client:
                payload = client.get("/api/generation-catalog").json()
            fixture = root / "generation-catalog.json"
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            run_frontend(
                self, "catalog_payload_parity.test.ts", backend_fixture=True,
                env={"GENERATION_CATALOG_FIXTURE": str(fixture)},
            )


load_tests = compatibility_load_tests((
    'composer_navigation.test.ts',
    'upload_thumbnails.test.ts',
    'mobile_touch.test.ts',
    'ux_recovery.test.ts',
    'task_submission_behavior.test.ts',
    'user_config_backup.test.ts',
    'history_selection_shortcuts.test.ts',
    'history_action_panel.test.ts',
    'history_grid_resize.test.ts',
    'api_provider_sort.test.ts',
    'api_provider_credentials.test.ts',
    'history_task_reveal.test.ts',
    'history_active_filters.test.ts',
    'prompt_snippet_expansion.test.ts',
    'lightbox_zoom.test.ts',
    'task_card_swipe_logic.test.ts',
    'task_batch_selection.test.ts',
    'staged_references_session.test.ts',
    'queue_transition_render.test.ts',
    'history_realtime_refresh.test.ts',
    'task_snapshot_reconcile.test.ts',
    'task_sidebar_auto_load.test.ts',
    'segmented_indicator_behavior.test.ts',
    'task_model_summary.test.ts',
    'provider_binding_editor.test.ts',
    'network_request_policy.test.ts',
    'model_provider_behavior.test.ts',
))
