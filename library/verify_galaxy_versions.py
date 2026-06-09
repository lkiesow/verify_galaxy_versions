#!/usr/bin/python3

# Copyright: (c) 2021, Lars Kiesow <lkiesow@uos.de>
# SPDX-License-Identifier: BSD-3-Clause

DOCUMENTATION = '''
---
module: verify_galaxy_versions
short_description: Verify installed Ansible Galaxy role and collection versions
description:
  - Reads C(requirements.yml) from the current working directory and checks
    that every listed role and collection is installed at the required version.
  - Fails if a role or collection is missing or installed at a different version.
  - The roles search path is taken from C(roles_path) in C(ansible.cfg) and
    the collections search path from C(collections_path). Both are searched in
    the current directory, C(~/.ansible.cfg), and C(/etc/ansible/ansible.cfg)
    in that order, falling back to C(~/.ansible/roles) and
    C(~/.ansible/collections) respectively when not configured.
notes:
  - The module is always delegated to localhost and run once, so it is
    independent of the target host inventory.
author:
  - Lars Kiesow (@lkiesow)
'''

EXAMPLES = '''
- name: Verify Galaxy role versions
  verify_galaxy_versions:
  delegate_to: localhost
  run_once: true
'''

RETURN = '''# No return values beyond the standard failed/changed fields.'''

import configparser
import os
import sys
import yaml
from ansible.module_utils.basic import AnsibleModule


_CFG_CANDIDATES = ('ansible.cfg', os.path.expanduser('~/.ansible.cfg'), '/etc/ansible/ansible.cfg')


def _paths_from_config(key, subdir, default):
    '''Read a colon-separated path list from ansible.cfg, or return default.

    Pass 1: searches all three ansible.cfg locations for the specific key
    (roles_path or collections_path). Pass 2: searches all three locations
    for the home setting and returns <home>/<subdir>. Falls back to default
    if neither key is found anywhere.
    '''
    for candidate in _CFG_CANDIDATES:
        if os.path.isfile(candidate):
            cfg = configparser.ConfigParser()
            cfg.read(candidate)
            raw = cfg.get('defaults', key, fallback=None)
            if raw:
                base = os.path.dirname(os.path.abspath(candidate))
                paths = []
                for p in raw.split(':'):
                    p = p.strip()
                    if p:
                        paths.append(p if os.path.isabs(p) else os.path.join(base, p))
                return paths

    for candidate in _CFG_CANDIDATES:
        if os.path.isfile(candidate):
            cfg = configparser.ConfigParser()
            cfg.read(candidate)
            home = cfg.get('defaults', 'home', fallback=None)
            if home:
                base = os.path.dirname(os.path.abspath(candidate))
                home = home if os.path.isabs(home) else os.path.join(base, home)
                return [os.path.join(home, subdir)]

    return [default]


def get_roles_paths():
    '''Return the configured Galaxy roles directories, or ~/.ansible/roles.'''
    return _paths_from_config('roles_path', 'roles', os.path.expanduser('~/.ansible/roles'))


def get_collections_paths():
    '''Return the configured collections directories, or ~/.ansible/collections.

    Also includes any sys.path entry that contains an ansible_collections
    subdirectory, matching Ansible's own runtime collection discovery.
    '''
    paths = _paths_from_config('collections_path', 'collections', os.path.expanduser('~/.ansible/collections'))
    for p in sys.path:
        if p and p not in paths and os.path.isdir(os.path.join(p, 'ansible_collections')):
            paths.append(p)
    return paths


def installed_roles():
    '''Return a dict mapping installed role names to their version strings.

    Scans every directory returned by get_roles_paths() and reads the version
    from meta/.galaxy_install_info inside each role directory.
    '''
    roles = {}
    for path in get_roles_paths():
        if not os.path.isdir(path):
            continue
        for name in os.listdir(path):
            info_file = os.path.join(path, name, 'meta', '.galaxy_install_info')
            if os.path.isfile(info_file):
                with open(info_file) as f:
                    info = yaml.safe_load(f)
                roles[name] = str(info.get('version', '')) if info else ''
    return roles


def installed_collections():
    '''Return a dict mapping installed collection names to their version strings.

    Scans {path}/ansible_collections/{namespace}/{name}/MANIFEST.json for each
    path returned by get_collections_paths(). Collection names are in
    namespace.name format (e.g. middleware_automation.keycloak).
    '''
    collections = {}
    for base_path in get_collections_paths():
        collections_dir = os.path.join(base_path, 'ansible_collections')
        if not os.path.isdir(collections_dir):
            continue
        for namespace in os.listdir(collections_dir):
            ns_path = os.path.join(collections_dir, namespace)
            if not os.path.isdir(ns_path):
                continue
            for name in os.listdir(ns_path):
                manifest = os.path.join(ns_path, name, 'MANIFEST.json')
                if os.path.isfile(manifest):
                    with open(manifest) as f:
                        info = yaml.safe_load(f)
                    version = info.get('collection_info', {}).get('version', '')
                    collections[f'{namespace}.{name}'] = str(version)
    return collections


def main():
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)

    try:
        with open('requirements.yml') as f:
            requirements = yaml.safe_load(f)
    except OSError:
        module.fail_json(msg='requirements.yml not found in current directory')

    installed = installed_roles()
    installed_col = installed_collections()
    errors = []

    for role in requirements.get('roles', []):
        if isinstance(role, str):
            name = role
            required_version = None
        else:
            name = role.get('name')
            if not name and role.get('src'):
                # Derive name from URL last path component, stripping optional .git
                last = role['src'].rstrip('/').rsplit('/', 1)[-1]
                name = last[:-4] if last.endswith('.git') else last
            required_version = role.get('version')
        if not name or not required_version:
            continue

        if name not in installed:
            errors.append(f'role {name} is not installed')
            continue

        if installed[name] != str(required_version):
            errors.append(
                f'role {name} has incorrect version '
                f'(required: {required_version}, present: {installed[name]})'
            )

    for collection in requirements.get('collections', []):
        if isinstance(collection, str):
            name = collection
            required_version = None
        else:
            name = collection.get('name')
            required_version = collection.get('version')
        if not name or not required_version:
            continue

        if name not in installed_col:
            errors.append(f'collection {name} is not installed')
            continue

        if installed_col[name] != str(required_version):
            errors.append(
                f'collection {name} has incorrect version '
                f'(required: {required_version}, present: {installed_col[name]})'
            )

    if errors:
        module.fail_json(msg='\n'.join(errors))

    module.exit_json(changed=False)


if __name__ == '__main__':
    main()
