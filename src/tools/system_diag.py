import os
import shutil
import sys
import time
from typing import Any, Dict, List
from .base import BaseTool, ToolResult
from ..security.sandbox import SafeCommandExecutor

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class SystemDiagTool(BaseTool):
    """Specialized SRE Diagnostic Tool for CPU, disk, memory, process and network metrics."""

    name = "system_diagnostic"
    description = (
        "Inspects system health metrics: CPU utilization ('cpu'), disk space ('disk'), "
        "memory usage ('memory'), top running processes ('process'), or network interfaces ('network')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["cpu", "disk", "memory", "process", "network"],
                "description": "Subsystem to diagnose: 'cpu', 'disk', 'memory', 'process', or 'network'",
            },
            "path": {
                "type": "string",
                "description": "Optional path for disk diagnosis (default: '/')",
                "default": "/",
            },
        },
        "required": ["target"],
    }

    def __init__(self, executor: SafeCommandExecutor):
        self.executor = executor

    async def execute(self, **kwargs) -> ToolResult:
        target = kwargs.get("target", "cpu").lower()
        path = kwargs.get("path", "/")
        start = time.perf_counter()

        try:
            if target == "cpu":
                return await self._diag_cpu(start)
            elif target == "disk":
                return await self._diag_disk(path, start)
            elif target == "memory":
                return await self._diag_memory(start)
            elif target == "process":
                return await self._diag_process(start)
            elif target == "network":
                return await self._diag_network(start)
            else:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    output="",
                    error=f"Unsupported diagnostic target: '{target}'. Valid targets: cpu, disk, memory, process, network",
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Exception during {target} diagnostic: {str(exc)}",
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )

    async def _diag_cpu(self, start: float) -> ToolResult:
        if HAS_PSUTIL:
            cpu_pct = psutil.cpu_percent(interval=0.4)
            per_cpu = psutil.cpu_percent(interval=None, percpu=True)
            phys_cores = psutil.cpu_count(logical=False) or 1
            log_cores = psutil.cpu_count(logical=True) or 1

            load_avg_str = ""
            if hasattr(os, "getloadavg"):
                lavg = os.getloadavg()
                load_avg_str = f"  Load Average (1m, 5m, 15m): {lavg[0]:.2f}, {lavg[1]:.2f}, {lavg[2]:.2f}\n"

            # Top CPU consuming processes
            top_procs: List[Dict[str, Any]] = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    top_procs.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            top_procs.sort(key=lambda x: x.get("cpu_percent") or 0.0, reverse=True)

            procs_text = "\n".join(
                f"  PID {p['pid']:>5} | CPU: {p.get('cpu_percent', 0.0):>5.1f}% | MEM: {p.get('memory_percent', 0.0):>4.1f}% | {p.get('name', 'unknown')}"
                for p in top_procs[:5]
            )

            per_cpu_str = ", ".join(f"{c}%" for c in per_cpu)
            output = (
                f"CPU Utilization Report:\n"
                f"  Total CPU Load: {cpu_pct}%\n"
                f"  Cores: {phys_cores} physical, {log_cores} logical threads\n"
                f"  Per-core load: [{per_cpu_str}]\n"
                f"{load_avg_str}\n"
                f"Top 5 CPU-consuming processes:\n{procs_text}"
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=output,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
                metadata={"target": "cpu", "cpu_percent": cpu_pct},
            )

        # Fallback to shell command
        cmd = "top -b -n 1 | head -n 15" if sys.platform != "win32" else "powershell -Command Get-WmiObject Win32_Processor | Select LoadPercentage"
        exec_res = await self.executor.execute(cmd)
        return ToolResult(
            tool_name=self.name,
            success=exec_res.exit_code == 0,
            output=exec_res.stdout or "CPU metrics retrieved.",
            error=exec_res.stderr if exec_res.exit_code != 0 else None,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "cpu"},
        )

    async def _diag_disk(self, path: str, start: float) -> ToolResult:
        try:
            total, used, free = shutil.disk_usage(path)
            pct_used = round((used / total) * 100, 1)
            py_summary = (
                f"Disk Usage Summary for '{path}':\n"
                f"  Total: {round(total / (1024**3), 2)} GB\n"
                f"  Used:  {round(used / (1024**3), 2)} GB ({pct_used}%)\n"
                f"  Free:  {round(free / (1024**3), 2)} GB"
            )
        except Exception:
            py_summary = f"Could not inspect path {path} directly."

        output = py_summary

        if HAS_PSUTIL:
            try:
                parts = psutil.disk_partitions(all=False)
                parts_info = []
                for p in parts:
                    try:
                        u = psutil.disk_usage(p.mountpoint)
                        parts_info.append(
                            f"  {p.device} ({p.mountpoint}) [{p.fstype}]: {u.percent}% used ({round(u.free/(1024**3), 1)} GB free)"
                        )
                    except (PermissionError, OSError):
                        continue
                if parts_info:
                    output += "\n\nMounted Partitions:\n" + "\n".join(parts_info)
            except Exception:
                pass

        return ToolResult(
            tool_name=self.name,
            success=True,
            output=output,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "disk", "path": path},
        )

    async def _diag_memory(self, start: float) -> ToolResult:
        if HAS_PSUTIL:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            output = (
                f"Memory (RAM) Diagnostics:\n"
                f"  Total:     {mem.total / (1024**3):.2f} GB\n"
                f"  Used:      {mem.used / (1024**3):.2f} GB ({mem.percent}%)\n"
                f"  Available: {mem.available / (1024**3):.2f} GB\n"
                f"  Free:      {mem.free / (1024**3):.2f} GB\n\n"
                f"Swap:\n"
                f"  Total: {swap.total / (1024**3):.2f} GB, Used: {swap.used / (1024**3):.2f} GB ({swap.percent}%)"
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=output,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
                metadata={"target": "memory", "percent": mem.percent},
            )

        cmd = "free -m" if sys.platform != "win32" else "powershell -Command Get-CimInstance Win32_OperatingSystem | Select TotalVisibleMemorySize,FreePhysicalMemory"
        exec_res = await self.executor.execute(cmd)
        return ToolResult(
            tool_name=self.name,
            success=exec_res.exit_code == 0,
            output=exec_res.stdout or "Memory metrics retrieved.",
            error=exec_res.stderr if exec_res.exit_code != 0 else None,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "memory"},
        )

    async def _diag_process(self, start: float) -> ToolResult:
        if HAS_PSUTIL:
            procs: List[Dict[str, Any]] = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
                try:
                    procs.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Sort by CPU and memory
            procs.sort(key=lambda x: ((x.get("cpu_percent") or 0.0) + (x.get("memory_percent") or 0.0)), reverse=True)

            lines = [
                f"  PID {p['pid']:>5} | CPU: {p.get('cpu_percent', 0.0):>5.1f}% | MEM: {p.get('memory_percent', 0.0):>4.1f}% | Status: {p.get('status','?')} | {p.get('name', 'unknown')}"
                for p in procs[:10]
            ]
            output = "Top Resource-Consuming Processes (by CPU + RAM):\n" + "\n".join(lines)
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=output,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
                metadata={"target": "process"},
            )

        cmd = "ps aux --sort=-%cpu | head -n 11" if sys.platform != "win32" else "powershell -Command Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 Id,ProcessName,WorkingSet64"
        exec_res = await self.executor.execute(cmd)
        return ToolResult(
            tool_name=self.name,
            success=exec_res.exit_code == 0,
            output=exec_res.stdout or "Process list retrieved.",
            error=exec_res.stderr if exec_res.exit_code != 0 else None,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "process"},
        )

    async def _diag_network(self, start: float) -> ToolResult:
        if HAS_PSUTIL:
            net_io = psutil.net_io_counters()
            if_addrs = psutil.net_if_addrs()
            if_lines = []
            for if_name, addrs in list(if_addrs.items())[:4]:
                ips = [a.address for a in addrs if ":" not in a.address and not a.address.startswith("127.")]
                if ips:
                    if_lines.append(f"  Interface '{if_name}': {', '.join(ips)}")

            output = (
                f"Network Diagnostics:\n"
                f"  Traffic: Sent {net_io.bytes_sent / (1024**2):.1f} MB, Recv {net_io.bytes_recv / (1024**2):.1f} MB\n"
                f"  Packets: Sent {net_io.packets_sent}, Recv {net_io.packets_recv}\n"
                f"  Errors:  In {net_io.errin}, Out {net_io.errout} | Drops: In {net_io.dropin}, Out {net_io.dropout}\n"
                f"Active Interfaces:\n" + ("\n".join(if_lines) if if_lines else "  No external IPv4 interfaces found.")
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=output,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
                metadata={"target": "network"},
            )

        cmd = "ss -tulwn" if sys.platform != "win32" else "netstat -an"
        exec_res = await self.executor.execute(cmd)
        return ToolResult(
            tool_name=self.name,
            success=exec_res.exit_code == 0,
            output=exec_res.stdout[:1500] if exec_res.stdout else "Network metrics retrieved.",
            error=exec_res.stderr if exec_res.exit_code != 0 else None,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "network"},
        )
