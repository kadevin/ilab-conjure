from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.frontend_runner import run_frontend


class WebUIFrontendBehaviorTests(unittest.TestCase):
    def test_composer_history_navigation(self) -> None:
        run_frontend(self, "composer_navigation.test.ts")

    def test_upload_thumbnail_behavior(self) -> None:
        run_frontend(self, "upload_thumbnails.test.ts")

    def test_mobile_touch_behavior(self) -> None:
        run_frontend(self, "mobile_touch.test.ts")

    def test_ux_recovery_behavior(self) -> None:
        run_frontend(self, "ux_recovery.test.ts")

    def test_task_submission_behavior(self) -> None:
        run_frontend(self, "task_submission_behavior.test.ts")

    def test_user_config_backup_behavior(self) -> None:
        run_frontend(self, "user_config_backup.test.ts")

    def test_history_selection_shortcuts_behavior(self) -> None:
        run_frontend(self, "history_selection_shortcuts.test.ts")

    def test_history_action_panel_behavior(self) -> None:
        run_frontend(self, "history_action_panel.test.ts")

    def test_history_grid_resize_behavior(self) -> None:
        run_frontend(self, "history_grid_resize.test.ts")

    def test_api_provider_sort_behavior(self) -> None:
        run_frontend(self, "api_provider_sort.test.ts")

    def test_api_provider_credentials_behavior(self) -> None:
        run_frontend(self, "api_provider_credentials.test.ts")

    def test_history_task_reveal_behavior(self) -> None:
        run_frontend(self, "history_task_reveal.test.ts")

    def test_history_active_filter_behavior(self) -> None:
        run_frontend(self, "history_active_filters.test.ts")

    def test_adjacent_prompt_snippet_chips_expand_before_submission(self) -> None:
        run_frontend(self, "prompt_snippet_expansion.test.ts")

    def test_lightbox_zoom_behavior(self) -> None:
        run_frontend(self, "lightbox_zoom.test.ts")

    def test_task_card_swipe_logic(self) -> None:
        run_frontend(self, "task_card_swipe_logic.test.ts")

    def test_task_batch_selection_behavior(self) -> None:
        run_frontend(self, "task_batch_selection.test.ts")

    def test_staged_references_survive_history_round_trip(self) -> None:
        run_frontend(self, "staged_references_session.test.ts")

    def test_queue_transition_render_behavior(self) -> None:
        run_frontend(self, "queue_transition_render.test.ts")

    def test_history_realtime_refresh_behavior(self) -> None:
        run_frontend(self, "history_realtime_refresh.test.ts")

    def test_task_snapshot_reconcile_behavior(self) -> None:
        run_frontend(self, "task_snapshot_reconcile.test.ts")

    def test_task_sidebar_auto_load_behavior(self) -> None:
        run_frontend(self, "task_sidebar_auto_load.test.ts")

    def test_segmented_indicator_initial_position_behavior(self) -> None:
        run_frontend(self, "segmented_indicator_behavior.test.ts")

    def test_task_model_summary_behavior(self) -> None:
        run_frontend(self, "task_model_summary.test.ts")

    def test_provider_binding_editor_behavior(self) -> None:
        run_frontend(self, "provider_binding_editor.test.ts")

    def test_network_request_policy_behavior(self) -> None:
        run_frontend(self, "network_request_policy.test.ts")

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

    def test_model_provider_selection_behavior(self) -> None:
        run_frontend(self, "model_provider_behavior.test.ts")
