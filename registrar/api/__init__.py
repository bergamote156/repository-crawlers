"""
Onedata API Clients

This module provides client classes for interacting with Onedata REST APIs:
- OnepanelClient: Admin operations (storages, space support)
- OnezoneClient: Space creation, tokens, handles
- OneproviderClient: File registration, shares
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from registrar.api.onepanel import OnepanelClient
from registrar.api.oneprovider import OneproviderClient
from registrar.api.onezone import OnezoneClient

__all__ = ["OnepanelClient", "OnezoneClient", "OneproviderClient"]
