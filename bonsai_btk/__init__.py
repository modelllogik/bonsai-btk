# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BTK Tools for Bonsai.

Scaffold only. The tools are added module by module, starting with release 0.1.0
(intersection snap and dimension chain). Bonsai must be installed and enabled.
"""

_MODULES = ()


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
