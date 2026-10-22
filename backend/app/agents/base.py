"""
Base Agent Abstract Interface for Hospital Intelligence Agents.

Provides common abstractions, database session persistence, and standard
telemetry bindings across all specialized operational and clinical agents.
"""

from abc import ABC
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract Base Class for all specialized hospital intelligence agents.
    
    Guarantees:
    - Uniform asynchronous database session injection.
    - Consistent agent metadata attributes (agent_id, name).
    - Preserves exact constructor signatures and non-destructive evaluation contracts.
    """

    def __init__(self, db: AsyncSession, agent_id: str, name: str):
        self.db: AsyncSession = db
        self.agent_id: str = agent_id
        self.name: str = name
        logger.debug(f"Initialized agent [{self.agent_id}]: {self.name}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(agent_id='{self.agent_id}', name='{self.name}')>"
