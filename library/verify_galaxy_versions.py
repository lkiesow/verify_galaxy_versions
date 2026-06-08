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
import re
import yaml
from ansible.module_utils.basic import AnsibleModule


def _paths_from_config(key, default):
    '''Read a colon-separated path list from ansible.cfg, or return default.

    Searches ansible.cfg in the current directory, ~/.ansible.cfg, and
    /etc/ansible/ansible.cfg. Relative paths are resolved relative to the
    config file's own directory.
    '''
    cfg = configparser.ConfigParser()
    for candidate in ('ansible.cfg', os.path.expanduser('~/.ansible.cfg'), '/etc/ansible/ansible.cfg'):
        if os.path.isfile(candidate):
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
            break
    return [default]


def get_roles_paths():
    '''Return the configured Galaxy roles directories, or ~/.ansible/roles.'''
    return _paths_from_config('roles_path', os.path.expanduser('~/.ansible/roles'))


def get_collections_paths():
    '''Return the configured collections directories, or ~/.ansible/collections.'''
    return _paths_from_config('collections_path', os.path.expanduser('~/.ansible/collections'))


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
        name = role.get('name')
        if not name:
            # Derive name from git URL (e.g. https://example.com/foo/bar.git -> bar)
            if role.get('scm') == 'git' and role.get('src'):
                m = re.search(r'/([^/]*)\.git', role['src'])
                if m:
                    name = m.group(1)
        if not name:
            continue

        if name not in installed:
            errors.append(f'role {name} is not installed')
            continue

        required = role.get('version')
        if required and installed[name] != str(required):
            errors.append(
                f'role {name} has incorrect version '
                f'(required: {required}, present: {installed[name]})'
            )

    for collection in requirements.get('collections', []):
        name = collection.get('name')
        if not name:
            continue

        if name not in installed_col:
            errors.append(f'collection {name} is not installed')
            continue

        required = collection.get('version')
        if required and installed_col[name] != str(required):
            errors.append(
                f'collection {name} has incorrect version '
                f'(required: {required}, present: {installed_col[name]})'
            )

    if errors:
        module.fail_json(msg='\n'.join(errors))

    module.exit_json(changed=False)


if __name__ == '__main__':
    main()
