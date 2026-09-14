from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import asyncio
from io import BytesIO

from fastapi.testclient import TestClient

from PIL import Image

from codex_image.client import ImageResult
from codex_image.generation.catalog import get_model_manifest
from codex_image.generation.snapshot import generation_snapshot, execution_plan_from_snapshot
from codex_image.generation.types import GenerationCommand, ImageInput
from codex_image.providers.codex import CodexImagesAdapter, CodexResponsesAdapter
from codex_image.providers.contracts import ExecutionPlan, ProviderConnection, ProviderModelBinding
from codex_image.providers.registry import default_registry
from codex_image.webui.execution_plan_client import ExecutionPlanImageClient
from codex_image.webui.generation_request import codex_provider_connection
from codex_image.webui.provider_validation import _validate_binding
from codex_image.webui.storage import TaskStorage
from codex_image.webui.task_outputs import _output_thumbnail_fields
from codex_image.webui.thumbnails import inspect_image_transparency


class TransparentBackgroundTests(unittest.TestCase):
    def test_codex_queue_preserves_user_prompt_and_reports_real_pixels_in_every_fidelity_mode(self):
        from codex_image.webui.app import create_app
        for profile in ('images', 'responses'):
            for fidelity in ('original', 'strict', 'off'):
                with self.subTest(profile=profile, fidelity=fidelity), TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    transparent = fidelity == 'original'
                    image = Image.new('RGBA', (16, 16), (10, 20, 30, 0 if transparent else 255))
                    data = BytesIO()
                    image.save(data, format='PNG')
                    fake = Mock()
                    fake.generate_image.return_value = ImageResult(data.getvalue(), '', 'png', '1024x1024', 'transparent', 'auto', {})
                    app = create_app(
                        output_root=root / 'outputs', input_root=root / 'inputs',
                        source_data_root=root / 'source-data', gallery_root=root / 'gallery',
                        auth_settings_path=root / 'auth.json', api_settings_path=root / 'api.json',
                        webui_settings_path=root / 'settings.json', network_egress_settings_path=root / 'network.json',
                        client_factory=lambda: fake, auth_checker=lambda: True,
                        batch_delay_seconds=0, auto_start_queue=False, auto_retry=False,
                    )
                    with TestClient(app) as client:
                        response = client.post('/api/generate', data={
                            'prompt': 'A glass rabbit.', 'background': 'transparent',
                            'output_format': 'png', 'size': '1024x1024', 'quality': 'auto',
                            'prompt_fidelity': fidelity, 'codex_mode': profile,
                        })
                        self.assertEqual(response.status_code, 200, response.text)
                        task_id = response.json()['task']['task_id']
                        preview = response.json()['request']
                        asyncio.run(app.state.queue_manager.run_available_once())
                        task = client.get(f'/api/tasks/{task_id}').json()['task']
                        thumbnail = client.get(f'/api/tasks/{task_id}/outputs/1/thumbnail')
                        self.assertEqual(thumbnail.status_code, 200)
                        self.assertEqual(thumbnail.headers['content-type'], 'image/webp' if transparent else 'image/jpeg')
                    self.assertEqual(task['status'], 'completed')
                    self.assertEqual(task['prompt'], 'A glass rabbit.')
                    self.assertEqual(task['generation_snapshot']['transparency_mode'], 'prompt')
                    self.assertIs(task['outputs'][0]['has_transparency'], transparent)
                    kwargs = fake.generate_image.call_args.kwargs
                    self.assertIsNone(kwargs['background'])
                    self.assertIn('real alpha', kwargs['prompt'])
                    self.assertEqual(fake.generate_image.call_count, 1)
                    if profile == 'images':
                        self.assertEqual(preview['prompt'], kwargs['prompt'])
                    else:
                        self.assertEqual(preview['instructions'], kwargs['instructions'])

    def plan(self, profile='openai_images', mode='native', operation='generate', model='gpt-image-2', background='transparent', output_format='png'):
        binding = ProviderModelBinding('binding', 'relay', model, 'remote-image', profile, 'gpt_' + profile,
                                       frozenset({'generate', 'edit'}), transparency_mode=mode)
        provider = ProviderConnection('relay', 'Relay', 'https://example.invalid/v1', '', 1, (binding,))
        command = GenerationCommand(operation, model, 'relay', 'Draw a glass rabbit.',
                                    {'gpt.background': background, 'output.format': output_format},
                                    image_inputs=(ImageInput('data:image/png;base64,aW1hZ2U='),) if operation == 'edit' else (),
                                    instructions='Keep the prompt verbatim.', main_model='gpt-5.6-luna')
        manifest = get_model_manifest(model)
        request = default_registry().codec(binding.parameter_codec).encode(command, manifest, binding)
        return ExecutionPlan(command, manifest, provider, binding, request)

    def image_tool(self, plan):
        payload = plan.protocol_request.json_body
        return next(t for t in payload['tools'] if t['type'] == 'image_generation') if plan.binding.protocol_profile.endswith('responses') else payload

    def test_native_and_prompt_modes_all_gpt_models_operations_and_protocols(self):
        for model in ('gpt-image-2', 'gpt-image-2.5-flare', 'gpt-image-2.5-sunburst'):
            for profile in ('openai_images', 'openai_responses', 'codex_images', 'codex_responses'):
                for operation in ('generate', 'edit'):
                    for mode in ('native', 'prompt'):
                        with self.subTest(model=model, profile=profile, operation=operation, mode=mode):
                            plan = self.plan(profile, mode, operation, model)
                            tool = self.image_tool(plan)
                            if mode == 'native':
                                self.assertEqual(tool['background'], 'transparent')
                            else:
                                self.assertNotIn('background', tool)
                                self.assertIn('real alpha', str(plan.protocol_request.json_body))
                                if profile.endswith('responses'):
                                    self.assertIn('even in original or strict', plan.protocol_request.json_body['instructions'])
                            self.assertEqual(plan.command.prompt, 'Draw a glass rabbit.')
                            self.assertEqual(plan.command.parameters['gpt.background'], 'transparent')

    def test_nontransparent_requests_do_not_add_instructions(self):
        for background in ('auto', 'opaque', None):
            for profile in ('openai_images', 'openai_responses', 'codex_images', 'codex_responses'):
                native = self.plan(profile, 'native', background=background)
                prompt = self.plan(profile, 'prompt', background=background)
                self.assertEqual(native.protocol_request, prompt.protocol_request)

    def test_jpeg_is_rejected_before_transport_and_webp_allowed(self):
        for mode in ('native', 'prompt'):
            with self.assertRaisesRegex(ValueError, 'transparent_background_requires_png_or_webp'):
                self.plan(mode=mode, output_format='jpeg')
            self.assertEqual(self.image_tool(self.plan(mode=mode, output_format='webp'))['output_format'], 'webp')

    def test_new_codex_bindings_use_prompt_and_still_only_support_image2(self):
        bindings = codex_provider_connection('images').bindings
        self.assertEqual({b.transparency_mode for b in bindings}, {'prompt'})
        self.assertEqual({b.canonical_model_id for b in bindings}, {'gpt-image-2'})
        self.assertEqual({b.id for b in bindings}, {'codex-gpt-image-2-images', 'codex-gpt-image-2-responses'})

    def test_snapshot_freezes_strategy_and_legacy_snapshot_keeps_native(self):
        for profile in ('codex_images', 'codex_responses', 'openai_images', 'openai_responses'):
            plan = self.plan(profile, 'prompt')
            snapshot = generation_snapshot(plan)
            restored = execution_plan_from_snapshot(snapshot=snapshot, command=plan.command, api_key='', registry=default_registry())
            self.assertEqual(restored.protocol_request, plan.protocol_request)
            self.assertEqual(restored.binding.transparency_prompt_version, 1)
            del snapshot['transparency_mode']
            del snapshot['transparency_prompt_version']
            restored = execution_plan_from_snapshot(snapshot=snapshot, command=plan.command, api_key='', registry=default_registry())
            self.assertEqual(self.image_tool(restored)['background'], 'transparent')

    def test_webui_legacy_adapter_applies_same_prompt_and_omits_native_background(self):
        for profile in ('codex_images', 'codex_responses', 'openai_images', 'openai_responses'):
            for operation in ('generate', 'edit'):
                plan = self.plan(profile, 'prompt', operation)
                client = Mock()
                result = ImageResult(b'image', '', 'png', '1024x1024', 'auto', 'auto', {})
                client.generate_image.return_value = result
                client.edit_image.return_value = result
                adapter = ExecutionPlanImageClient(plan, client)
                getattr(adapter, operation + '_image')(background='transparent')
                kwargs = getattr(client, operation + '_image').call_args.kwargs
                self.assertIsNone(kwargs['background'])
                self.assertEqual(kwargs['prompt'].count('Output requirement selected by the user:'), 1)
                if profile.endswith('responses'):
                    self.assertEqual(kwargs['instructions'], plan.protocol_request.json_body['instructions'])
                else:
                    self.assertEqual(kwargs['prompt'], plan.protocol_request.json_body['prompt'])

    def test_codex_adapters_apply_prompt_compatibility(self):
        for profile, adapter, client_name, method in (
            ('codex_images', CodexImagesAdapter, 'CodexImagesImageClient', 'generate_images'),
            ('codex_responses', CodexResponsesAdapter, 'CodexImageClient', 'generate_image'),
        ):
            with patch('codex_image.providers.codex.' + client_name) as factory:
                getattr(factory.return_value, method).return_value = [] if profile.endswith('images') else ImageResult(b'image', '', 'png', '', '', '', {})
                adapter().execute(self.plan(profile, 'prompt'))
                kwargs = getattr(factory.return_value, method).call_args.kwargs
                self.assertIsNone(kwargs['background'])
                self.assertIn('real alpha', kwargs['prompt'])

    def test_binding_validation_preserves_prompt_and_rejects_unknown_modes(self):
        plan = self.plan()
        raw = {key: getattr(plan.binding, key) for key in ('id', 'canonical_model_id', 'remote_model_id', 'protocol_profile', 'parameter_codec', 'operations')}
        raw['transparency_mode'] = 'prompt'
        self.assertEqual(_validate_binding(raw, fallback_id='binding')['transparency_mode'], 'prompt')
        raw['transparency_mode'] = 'probe-and-retry'
        with self.assertRaisesRegex(ValueError, 'invalid_transparency_mode'):
            _validate_binding(raw, fallback_id='binding')

    def test_pixel_detection_and_alpha_preserving_output_thumbnails(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root / 'output', input_root=root / 'input')
            cases = [
                ('rgba.png', Image.new('RGBA', (16, 16), (20, 30, 40, 0)), True),
                ('solid-alpha.png', Image.new('RGBA', (16, 16), (20, 30, 40, 255)), False),
                ('rgb.png', Image.new('RGB', (16, 16), 'white'), False),
                ('rgb.jpg', Image.new('RGB', (16, 16), 'white'), False),
                ('alpha.webp', Image.new('RGBA', (16, 16), (20, 30, 40, 128)), True),
            ]
            palette = Image.new('P', (16, 16), 0)
            palette.info['transparency'] = 0
            cases.append(('palette.png', palette, True))
            for index, (filename, image, expected) in enumerate(cases, 1):
                with self.subTest(filename=filename):
                    source = root / filename
                    image.save(source)
                    original = source.read_bytes()
                    self.assertIs(inspect_image_transparency(source), expected)
                    fields = _output_thumbnail_fields(storage, '20260911-010203-test', index, source)
                    self.assertIs(fields['has_transparency'], expected)
                    self.assertEqual(Path(fields['thumbnail_file']).suffix, '.webp' if expected else '.jpg')
                    for field in ('thumbnail_file', 'sidebar_thumbnail_file'):
                        self.assertIs(inspect_image_transparency(storage.output_path(fields[field])), expected)
                    self.assertEqual(source.read_bytes(), original)
            broken = root / 'bad.png'
            broken.write_bytes(b'not an image')
            self.assertIsNone(inspect_image_transparency(broken))


if __name__ == '__main__':
    unittest.main()
