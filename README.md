Ansible: Verify Galaxy Role
===========================

This Ansible role lets you ensure that the correct Galaxy role versions specified in your `requirements.yml` are actually installed, and you are not accidentally deploying with different/unwanted versions of your dependencies. If an installed dependency does not match the required version, the executed play fails.



The role in action:

[<img src="https://github.com/lkiesow/verify_galaxy_versions/assets/1008395/6614693b-47de-49a5-877b-e7bf5dc12b1e" width="400" />](https://go.uos.de/verify_galaxy_versions)

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
