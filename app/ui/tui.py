"""Rich-based TUI dashboard for AGVS4RTL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from pre_agent import Preprocessor
from ui.config_store import ConfigStore


STATUS_ICON = {
    "not_started": "🤓",
    "in_progress": "🤔",
    "success": "😋",
    "failed": "😅",
}

DEFAULT_AGENTS = [
    "pre_agent",
    "architecture_agent",
    "verify_agent",
    "manager_agent",
    "generate_agent",
    "test_agent",
    "analyzer_agent",
    "integrator_agent",
]


class TUIApp:
    """Terminal UI dashboard to manage preprocessing and project overview."""

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.console = Console()
        self.workspace_root = workspace_root or Path.cwd()
        
        # File paths
        self.tasks_file = self.workspace_root / "data" / "tasks.json"
        self.architecture_file = self.workspace_root / "data" / "architecture.txt"
        self.logs_dir = self.workspace_root / "data" / "log"
        
        self.intent_defaults: Dict[str, Any] = {
            "language": "zh",
            "target_language": "verilog",
            "clock": None,
            "reset": None,
            "interfaces": [],
        }
        self.config_store = ConfigStore(self.workspace_root)
        self.agent_config = self.config_store.load_config()

    def _read_multiline(self, title: str) -> str:
        """Read multiline input until an empty line is provided."""

        self.console.print(Panel.fit(title, title="输入说明"))
        lines: List[str] = []
        while True:
            line = self.console.input()
            if not line.strip():
                break
            lines.append(line)
        return "\n".join(lines).strip()

    def _read_constraints(self, kind: str) -> Dict[str, Any]:
        """Interactively read constraints into a dict."""

        constraints: Dict[str, Any] = {}
        self.console.print(Panel.fit(f"开始录入{kind}约束（可为空）", title="约束输入"))
        while True:
            add_more = Confirm.ask(f"添加一条{kind}约束？", default=False)
            if not add_more:
                break
            name = Prompt.ask("约束名称")
            value = Prompt.ask("约束值")
            constraints[name] = value
        return constraints

    def _read_interfaces(self) -> List[str]:
        """Read interface keywords as a list."""

        raw = Prompt.ask("接口/总线关键词（用逗号分隔，可空）", default="")
        if not raw.strip():
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _save_payload(self, payload: Dict[str, Any]) -> Path:
        """Save payload JSON to data/workspace/preprocess."""

        out_dir = self.workspace_root / "data" / "workspace" / "preprocess"
        out_dir.mkdir(parents=True, exist_ok=True)
        request_id = payload.get("metadata", {}).get("request_id", "request")
        out_path = out_dir / f"{request_id}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path

    def _load_tasks(self) -> List[Dict[str, Any]]:
        """Load task list from data/workspace/tasks.json if available."""

        task_file = self.workspace_root / "data" / "workspace" / "tasks.json"
        if task_file.exists():
            try:
                return json.loads(task_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
        return []

    def _load_architecture(self) -> str:
        """Load module architecture tree if exists, else show placeholder."""

        tree_file = self.workspace_root / "data" / "workspace" / "architecture.txt"
        if tree_file.exists():
            return tree_file.read_text(encoding="utf-8").strip()
        json_file = self.workspace_root / "data" / "workspace" / "architecture.json"
        if json_file.exists():
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "tree" in data:
                    return str(data["tree"]).strip()
            except json.JSONDecodeError:
                pass
        return "(尚未生成模块架构图)"

    def _load_logs(self) -> List[str]:
        """Load recent log files under data/log."""

        log_dir = self.workspace_root / "data" / "log"
        if not log_dir.exists():
            return []
        files = sorted(log_dir.glob("**/*"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [str(p.relative_to(self.workspace_root)) for p in files if p.is_file()][:5]

    def _render_tasks_table(self, tasks: List[Dict[str, Any]]) -> Table:
        """Render task table with status icons and duration/loops."""

        table = Table(title="任务列表", expand=True)
        table.add_column("状态", width=4, justify="center")
        table.add_column("任务", overflow="fold")
        table.add_column("耗时/循环", justify="right")
        if not tasks:
            table.add_row("🤓", "暂无任务", "-")
            return table
        for task in tasks:
            status = task.get("status", "not_started")
            icon = STATUS_ICON.get(status, "🤓")
            name = task.get("name", "未命名任务")
            duration = task.get("duration", "-")
            loops = task.get("loops", "-")
            table.add_row(icon, name, f"{duration}/{loops}")
        return table

    def _render_params_panel(self) -> Panel:
        """Render agent config panel."""

        agents = self.agent_config.get("agents", {})
        loop_cfg = self.agent_config.get("loop", {})
        lines = [
            f"global_loop_budget: {loop_cfg.get('global_loop_budget', '-')}",
            f"retry_count_max: {loop_cfg.get('retry_count_max', '-')}",
            "",
        ]
        for name in DEFAULT_AGENTS:
            cfg = agents.get(name, {})
            model = cfg.get("model", "-")
            top_k = cfg.get("top_k", "-")
            top_p = cfg.get("top_p", "-")
            temp = cfg.get("temperature", "-")
            api_set = "已设置" if cfg.get("api_key_enc") else "未设置"
            lines.append(
                f"{name}: model={model} top_k={top_k} top_p={top_p} temp={temp} api_key={api_set}"
            )
        return Panel("\n".join(lines), title="Agent配置", expand=True)

    def _render_logs_panel(self, logs: List[str]) -> Panel:
        """Render logs entry panel."""

        content = "\n".join(logs) if logs else "(暂无日志)"
        return Panel(content, title="日志入口（最近5条）", expand=True)

    def _render_arch_panel(self, arch_text: str) -> Panel:
        """Render architecture tree panel."""

        return Panel(arch_text, title="模块架构图", expand=True)

    def _render_input_panel(self) -> Panel:
        """Render input placeholder panel."""

        return Panel("请输入需求（选择菜单后输入）", title="输入框", expand=True)

    def _render_dashboard(self) -> None:
        """Render dashboard layout."""

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(Layout(name="left"), Layout(name="right"))
        layout["left"].split_column(
            Layout(name="tasks", ratio=2),
            Layout(name="logs", ratio=1),
            Layout(name="params", ratio=1),
        )
        layout["right"].split_column(
            Layout(name="input", ratio=1),
            Layout(name="arch", ratio=2),
        )

        tasks = self._load_tasks()
        logs = self._load_logs()
        arch_text = self._load_architecture()

        layout["header"].update(Panel("AGVS4RTL 项目仪表盘", title="AGVS4RTL"))
        layout["tasks"].update(self._render_tasks_table(tasks))
        layout["logs"].update(self._render_logs_panel(logs))
        layout["params"].update(self._render_params_panel())
        layout["input"].update(self._render_input_panel())
        layout["arch"].update(self._render_arch_panel(arch_text))
        layout["footer"].update(Panel("菜单: 1-输入 2-日志 3-参数 4-退出", title="操作"))

        self.console.print(layout)

    def _handle_input(self) -> None:
        """Handle input flow and preprocessing output."""

        summary = self._read_multiline("请输入需求描述（多行，空行结束）")
        if not summary:
            self.console.print("[red]需求描述不能为空。[/red]")
            return

        self.intent_defaults["language"] = Prompt.ask(
            "输入语言", default=self.intent_defaults["language"]
        )
        self.intent_defaults["target_language"] = Prompt.ask(
            "目标 HDL 语言", default=self.intent_defaults["target_language"]
        )
        self.intent_defaults["clock"] = Prompt.ask("时钟信息（可空）", default="") or None
        self.intent_defaults["reset"] = Prompt.ask("复位信息（可空）", default="") or None
        self.intent_defaults["interfaces"] = self._read_interfaces()

        hard_constraints = self._read_constraints("硬")
        soft_constraints = self._read_constraints("软")

        result = Preprocessor.from_text(
            text=summary,
            language=self.intent_defaults["language"],
            hard_constraints=hard_constraints,
            soft_constraints=soft_constraints,
            target_language=self.intent_defaults["target_language"],
            interfaces=self.intent_defaults["interfaces"],
            clock=self.intent_defaults["clock"],
            reset=self.intent_defaults["reset"],
            source="tui",
        )
        payload = result.to_state()

        self.console.print(Panel("预处理结果", title="完成"))
        self.console.print_json(json.dumps(payload, ensure_ascii=False, indent=2))

        if Confirm.ask("保存结果到 data/workspace/preprocess？", default=True):
            out_path = self._save_payload(payload)
            self.console.print(f"已保存：{out_path}")

    def _handle_logs(self) -> None:
        """Handle log entry view."""

        logs = self._load_logs()
        self.console.print(self._render_logs_panel(logs))
        if logs:
            open_log = Confirm.ask("显示最新日志内容？", default=False)
            if open_log:
                latest = self.workspace_root / logs[0]
                self.console.print(Panel(latest.read_text(encoding="utf-8"), title=str(logs[0])))

    def _prompt_api_key(self, agent_name: str) -> str:
        """Force prompt API key from TUI."""

        while True:
            api_key = Prompt.ask(f"{agent_name} API Key", password=True)
            if api_key.strip():
                return api_key.strip()
            self.console.print("[red]API Key 不能为空。[/red]")

    def _handle_params(self) -> None:
        """Handle agent configuration edits."""

        if not Confirm.ask("修改Agent配置？", default=False):
            return

        loop_cfg = self.agent_config.get("loop", {})
        loop_cfg["global_loop_budget"] = int(
            Prompt.ask(
                "global_loop_budget",
                default=str(loop_cfg.get("global_loop_budget", 3)),
            )
        )
        loop_cfg["retry_count_max"] = int(
            Prompt.ask(
                "retry_count_max",
                default=str(loop_cfg.get("retry_count_max", 2)),
            )
        )
        self.agent_config["loop"] = loop_cfg

        same_key = Confirm.ask("所有Agent使用同一个API Key？", default=True)
        shared_key = None
        if same_key:
            shared_key = self._prompt_api_key("ALL")

        agents_cfg = self.agent_config.get("agents", {})
        for name in DEFAULT_AGENTS:
            cfg = agents_cfg.get(name, {})
            cfg["model"] = Prompt.ask("model", default=str(cfg.get("model", "gpt-4o-mini")))
            cfg["top_k"] = int(Prompt.ask("top_k", default=str(cfg.get("top_k", 40))))
            cfg["top_p"] = float(Prompt.ask("top_p", default=str(cfg.get("top_p", 0.9))))
            cfg["temperature"] = float(
                Prompt.ask("temperature", default=str(cfg.get("temperature", 0.7)))
            )

            api_key = shared_key or self._prompt_api_key(name)
            cfg["api_key_enc"] = self.config_store.encrypt_api_key(api_key, self.agent_config)
            agents_cfg[name] = cfg

        self.agent_config["agents"] = agents_cfg
        self.config_store.save_config(self.agent_config)
        self.console.print("[green]Agent配置已保存。[/green]")

    def run(self) -> None:
        """Run the dashboard loop."""

        while True:
            self.console.clear()
            self._render_dashboard()
            choice = Prompt.ask("选择操作", default="4")
            if choice == "1":
                self._handle_input()
            elif choice == "2":
                self._handle_logs()
            elif choice == "3":
                self._handle_params()
            elif choice == "4":
                break
            else:
                self.console.print("[yellow]无效选项。[/yellow]")