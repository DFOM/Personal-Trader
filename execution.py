"""Compatibility module for execution service.

SECURITY REMINDER FOR LIVE ALPACA USE:
- Issue broker API keys with Trade-Only scope (least privilege).
- Enforce broker-side IP whitelisting so order traffic is only accepted from trusted Render egress IPs.
"""

from execution.service import ExecutionService

__all__ = ["ExecutionService"]
