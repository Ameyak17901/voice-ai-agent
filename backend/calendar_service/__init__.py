"""
Calendar integrations and scheduling services for the Voice AI Agent.
Includes Cal.com API v2 client and local persistence bridges.
"""
from .calcom_client import CalComClient, calcom_client

__all__ = ["CalComClient", "calcom_client"]
