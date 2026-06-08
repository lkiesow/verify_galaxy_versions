#!/usr/bin/python3

# Copyright: (c) 2021, Lars Kiesow <lkiesow@uos.de>
# SPDX-License-Identifier: BSD-3-Clause

DOCUMENTATION = '''
---
module: verify_galaxy_versions
short_description: Verify installed Ansible Galaxy role versions
description:
  - Reads C(requirements.yml) from the current working directory and checks
    that every listed role is installed at the required version.
  - Fails if a role is missing or installed at a different version.
  - The roles search path is taken from C(roles_path) in C(ansible.cfg)
    (searched in the current directory, C(~/.ansible.cfg), and
    C(/etc/ansible/ansible.cfg) in that order). Falls back to
    C(~/.ansible/roles) when no config or no C(roles_path) is found.
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


def get_roles_paths():
    '''Return the list of Galaxy roles directories to search.

    Reads roles_path from the first ansible.cfg found in the standard
    locations. Relative paths in the config are resolved relative to the
    config file itself, not the current working directory. Falls back to
    ~/.ansible/roles when no config file or no roles_path setting is found.
    '''
    cfg = configparser.ConfigParser()
    for candidate in ('ansible.cfg', os.path.expanduser('~/.ansible.cfg'), '/etc/ansible/ansible.cfg'):
        if os.path.isfile(candidate):
            cfg.read(candidate)
            raw = cfg.get('defaults', 'roles_path', fallback=None)
            if raw:
                base = os.path.dirname(os.path.abspath(candidate))
                paths = []
                for p in raw.split(':'):
                    p = p.strip()
                    if p:
                        paths.append(p if os.path.isabs(p) else os.path.join(base, p))
                return paths
            break
    return [os.path.expanduser('~/.ansible/roles')]


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


def main():
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)

    try:
        with open('requirements.yml') as f:
            requirements = yaml.safe_load(f)
    except OSError:
        module.fail_json(msg='requirements.yml not found in current directory')

    installed = installed_roles()
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

    if errors:
        module.fail_json(msg='\n'.join(errors))

    module.exit_json(changed=False)


if __name__ == '__main__':
    main()
