"""全案件共通の設定読み込み。デバイスの実値はJSONだけで管理する。"""

import json
import math
from copy import deepcopy
from pathlib import Path


GLOBAL_CONFIG_PATH = Path(__file__).resolve().with_name('global_config.json')
DEVICE_OPTIONS = ('user_agent', 'viewport', 'screen', 'device_scale_factor', 'is_mobile', 'has_touch')


def load_global_config(path=None):
    config_path = Path(path) if path is not None else GLOBAL_CONFIG_PATH
    try:
        config = json.loads(config_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError(f'共通設定を読み込めません: {config_path}\n{error}') from error
    if not isinstance(config, dict):
        raise ValueError('global_config.jsonはJSONオブジェクトで指定してください。')
    devices = config.get('devices')
    if not isinstance(devices, dict) or not devices:
        raise ValueError('global_config.jsonのdevicesには1件以上のデバイスを登録してください。')
    default = config.get('default_device')
    if not isinstance(default, str) or default not in devices:
        raise ValueError('default_deviceにはdevicesに登録したIDを指定してください。')
    for device_id, device in devices.items():
        prefix = f'デバイス「{device_id}」'
        if not device_id.strip() or not isinstance(device, dict):
            raise ValueError(f'{prefix}の設定形式が不正です。')
        required = {'name', *DEVICE_OPTIONS}
        if set(device) != required:
            raise ValueError(f'{prefix}の設定項目を確認してください。必要な項目: {", ".join(sorted(required))}')
        if not isinstance(device['name'], str) or not device['name'].strip():
            raise ValueError(f'{prefix}のnameは空でない文字列にしてください。')
        ua = device['user_agent']
        if ua is not None and (not isinstance(ua, str) or not ua.strip() or '\n' in ua or '\r' in ua):
            raise ValueError(f'{prefix}のuser_agentは文字列またはnullにしてください。')
        for size_key in ('viewport', 'screen'):
            size = device[size_key]
            if (not isinstance(size, dict) or set(size) != {'width', 'height'} or
                    any(type(size[axis]) is not int or size[axis] <= 0 for axis in ('width', 'height'))):
                raise ValueError(f'{prefix}の{size_key}はwidth・heightを正の整数で指定してください。')
        scale = device['device_scale_factor']
        if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
            raise ValueError(f'{prefix}のdevice_scale_factorは正の有限数にしてください。')
        for flag in ('is_mobile', 'has_touch'):
            if type(device[flag]) is not bool:
                raise ValueError(f'{prefix}の{flag}はtrueまたはfalseにしてください。')
    return config


def resolve_device(device_id=None, path=None):
    config = load_global_config(path)
    selected = config['default_device'] if device_id is None else device_id
    if selected not in config['devices']:
        raise ValueError(f'デバイス「{selected}」はglobal_config.jsonに登録されていません。')
    return {'id': selected, **deepcopy(config['devices'][selected])}


def device_context_options(device):
    return {key: deepcopy(device[key]) for key in DEVICE_OPTIONS if device[key] is not None}


def load_recording_viewport(path=None):
    config = load_global_config(path)
    recording = config.get('recording', {'viewport': config['devices'][config['default_device']]['viewport']})
    if not isinstance(recording, dict):
        raise ValueError('recordingはviewportを含むオブジェクトにしてください。')
    return validate_recording_viewport(recording.get('viewport'))


def validate_recording_viewport(viewport):
    if (not isinstance(viewport, dict) or set(viewport) != {'width', 'height'} or
            any(type(viewport[axis]) is not int or not 1 <= viewport[axis] <= 16384
                for axis in ('width', 'height'))):
        raise ValueError('記録時のviewportはwidth・heightを1～16384の整数で指定してください。')
    return deepcopy(viewport)
