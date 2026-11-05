"""Typed tool execution entry point used by the HTTP and agent layers."""

from app.ai.workflow import execute_tool

__all__ = ["execute_tool"]
