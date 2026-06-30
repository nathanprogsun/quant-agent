"""Skill storage backends."""

from app.skills.storage.local_skill_storage import LocalSkillStorage
from app.skills.storage.skill_storage import SkillStorage

__all__ = ["LocalSkillStorage", "SkillStorage"]
