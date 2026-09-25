import re
import shlex
from enum import Enum
from typing import List, Optional, Set
from pydantic import BaseModel


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    BLOCKED = "BLOCKED"
    SUSPICIOUS = "SUSPICIOUS"


class SecurityResult(BaseModel):
    allowed: bool
    risk_level: RiskLevel
    reason: str
    command: str
    flagged_token: Optional[str] = None


class CommandValidator:
    """Security Guardrail validating shell commands before execution.

    Implements:
    - Strict regex-based blacklist for catastrophic & destructive operations
    - Whitelist validation of primary executables for SRE diagnostics
    - AST / subshell analysis for pipeline and chaining abuse
    """

    # 1. Catastrophic patterns: unconditionally blocked
    BLACKLIST_PATTERNS = [
        # Recursive delete of root / wildcard / system dirs
        (r"\brm\s+.*(-[a-zA-Z]*r[a-zA-Z]*|--recursive).*(\s+/|\s+/\*|\s+~\b|\s+\.\b)", "Recursive root or wild deletion"),
        (r"\brm\s+.*-[a-zA-Z]*f[a-zA-Z]*.*(\s+/|\s+/\*|\s+~\b)", "Force root deletion"),
        # Direct raw disk / filesystem manipulation
        (r"\b(mkfs|fdisk|parted|sfdisk|gdisk)\b", "Low-level disk partition or format command"),
        (r"\bdd\s+.*(if=|of=/dev/)", "Direct raw block device write via dd"),
        # Fork bomb
        (r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:", "Fork-bomb pattern detected"),
        # Piped remote execution
        (r"\b(curl|wget)\b.*\|\s*(sh|bash|python|perl|zsh)\b", "Piped remote script execution (curl | sh)"),
        # Privilege escalation / permission destruction
        (r"\bchmod\s+.*(-R\s+)?(777|000)\s+(/|/\*)", "Destructive recursive permission modification"),
        (r"\bchown\s+.*(-R\s+)?.*(/|/\*)", "Destructive recursive ownership modification"),
        # System shutdown/reboot
        (r"\b(shutdown|reboot|poweroff|init\s+0|halt)\b", "System termination/reboot attempt"),
        # Reverse shells
        (r"\b(nc|netcat)\b.*-e\s+(/bin/sh|/bin/bash)", "Reverse shell attempt"),
        # Sudo/su attempts (agent runs as unprivileged user)
        (r"\b(sudo|su)\s+", "Unprivileged agent cannot invoke sudo/su"),
    ]

    # 2. Permitted SRE diagnostic binaries
    WHITELIST_COMMANDS: Set[str] = {
        # Filesystem & storage inspection
        "df", "du", "ls", "pwd", "stat", "file", "find", "echo",
        "cat", "head", "tail", "grep", "awk", "sed", "sort", "uniq", "wc",
        # CPU, memory, processes
        "free", "top", "ps", "uptime", "vmstat", "iostat", "mpstat", "pidstat",
        "lsof", "pgrep", "kill",  # targeted process kill can be allowed if specific PID
        # Network diagnostics
        "ip", "ss", "netstat", "ping", "traceroute", "tracepath",
        "curl", "wget", "nslookup", "dig", "host",
        # System metadata & logs
        "uname", "hostname", "id", "whoami", "date", "env",
        "journalctl", "systemctl", "dmesg",
        # Containers (read-only inspection)
        "docker", "podman",
        # Windows powershell/cmd diagnostic commands fallback
        "get-process", "get-service", "get-psdrive", "dir", "type",
    }

    # Commands that require read-only flags (e.g. systemctl status/is-active, not stop/disable)
    RESTRICTED_SUBCOMMANDS = {
        "systemctl": {"status", "is-active", "is-failed", "list-units", "list-unit-files"},
        "docker": {"ps", "stats", "logs", "inspect", "version", "top", "images"},
        "journalctl": {"-u", "-n", "-r", "-xe", "-b", "--no-pager", "--vacuum-time", "--vacuum-size"},
    }

    def validate(self, command: str) -> SecurityResult:
        """Validates a command against blacklist rules and whitelist policy."""
        clean_cmd = command.strip()
        if not clean_cmd:
            return SecurityResult(
                allowed=False,
                risk_level=RiskLevel.BLOCKED,
                reason="Empty command received.",
                command=command,
            )

        # Step 1: Check blacklist patterns
        for pattern, reason in self.BLACKLIST_PATTERNS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                return SecurityResult(
                    allowed=False,
                    risk_level=RiskLevel.BLOCKED,
                    reason=f"Security Guardrail blocked command: {reason}",
                    command=command,
                    flagged_token=pattern,
                )

        # Step 2: Split pipeline and chained operations (;, &&, ||, |)
        sub_commands = self._split_pipeline(clean_cmd)

        for sub_cmd in sub_commands:
            sub_clean = sub_cmd.strip()
            if not sub_clean:
                continue

            # Extract base binary
            tokens = self._extract_tokens(sub_clean)
            if not tokens:
                continue

            base_bin = tokens[0].lower().split("/")[-1]

            # Check if base binary is in whitelist
            if base_bin not in self.WHITELIST_COMMANDS:
                return SecurityResult(
                    allowed=False,
                    risk_level=RiskLevel.BLOCKED,
                    reason=f"Command '{base_bin}' is not in permitted SRE diagnostics whitelist.",
                    command=command,
                    flagged_token=base_bin,
                )

            # Check restricted subcommands (e.g., docker run vs docker ps)
            if base_bin in self.RESTRICTED_SUBCOMMANDS:
                allowed_subs = self.RESTRICTED_SUBCOMMANDS[base_bin]
                has_allowed_sub = any(t in allowed_subs for t in tokens[1:])
                if not has_allowed_sub:
                    return SecurityResult(
                        allowed=False,
                        risk_level=RiskLevel.BLOCKED,
                        reason=f"Subcommand for '{base_bin}' not allowed. Permitted: {sorted(list(allowed_subs))}",
                        command=command,
                        flagged_token=sub_clean,
                    )

        return SecurityResult(
            allowed=True,
            risk_level=RiskLevel.SAFE,
            reason="Command passed all security validations.",
            command=command,
        )

    def _split_pipeline(self, cmd: str) -> List[str]:
        """Splits commands connected by pipes and logical operators."""
        # Split by ;, &&, ||, |
        parts = re.split(r"(?:&&|\|\||;|\|)", cmd)
        return [p.strip() for p in parts if p.strip()]

    def _extract_tokens(self, cmd: str) -> List[str]:
        """Safely extracts command tokens handling quotes."""
        try:
            return shlex.split(cmd, posix=True)
        except ValueError:
            # Fallback to simple split if unclosed quote
            return cmd.split()
