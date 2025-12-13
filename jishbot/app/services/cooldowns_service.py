import time
from collections import defaultdict
from typing import Dict, Tuple


class CooldownService:
    def __init__(self) -> None:
        # (channel, command) -> timestamp
        self.global_cooldowns: Dict[Tuple[str, str], float] = {}
        # (channel, command, user) -> timestamp
        self.user_cooldowns: Dict[Tuple[str, str, str], float] = {}

    def check_and_set(
        self,
        channel_id: str,
        command_name: str,
        user_id: str,
        cooldown_global: int,
        cooldown_user: int,
    ) -> bool:
        """Return True if command is allowed; sets cooldowns when allowed."""
        now = time.time()
        global_key = (channel_id, command_name)
        user_key = (channel_id, command_name, user_id)

        if cooldown_global > 0:
            next_ready = self.global_cooldowns.get(global_key, 0)
            if now < next_ready:
                return False
        if cooldown_user > 0:
            next_ready_user = self.user_cooldowns.get(user_key, 0)
            if now < next_ready_user:
                return False

        if cooldown_global > 0:
            self.global_cooldowns[global_key] = now + cooldown_global
        if cooldown_user > 0:
            self.user_cooldowns[user_key] = now + cooldown_user
        return True


cooldowns = CooldownService()
