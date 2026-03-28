"""Config reader for uconsole — reads uconsole.conf (INI) and config.json (user prefs)."""

import configparser
import json
import os

_CONF_FILE = '/etc/uconsole/uconsole.conf'
_CONF_DEFAULT = '/etc/uconsole/uconsole.conf.default'
_USER_CONF = os.path.join(os.path.expanduser('~'), '.config', 'uconsole', 'config.json')
_USER_DEFAULT = os.path.join(os.path.expanduser('~'), '.config', 'uconsole', 'config.json.default')


def _load_ini():
    cp = configparser.ConfigParser()
    cp.read([_CONF_DEFAULT, _CONF_FILE])
    return cp


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get(section, key, default=None):
    """Read a value from uconsole.conf with fallback to defaults."""
    cp = _load_ini()
    try:
        return cp.get(section, key)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default


def get_user(key, default=None):
    """Read a value from user config.json with fallback to defaults."""
    data = _load_json(_USER_CONF)
    if key in data:
        return data[key]
    data = _load_json(_USER_DEFAULT)
    return data.get(key, default)


def set_user(key, value):
    """Write a value to user config.json."""
    data = _load_json(_USER_CONF)
    data[key] = value
    os.makedirs(os.path.dirname(_USER_CONF), exist_ok=True)
    with open(_USER_CONF, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
