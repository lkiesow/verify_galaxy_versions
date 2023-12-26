Ansible: Verify Galaxy Role
===========================

Verify thatthe correct Galaxy role versions are installed.


Example Playbook
----------------

Example of how to configure and use the role:

```yaml
- name: Verify Galaxy Roles
  hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - lkiesow.verify_galaxy_versions
```
