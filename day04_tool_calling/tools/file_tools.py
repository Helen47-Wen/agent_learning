import time
from pathlib import Path

from schemas.tool_result_schema import ToolResult


def _is_path_inside_root(path: Path, root: Path) -> bool:
    """
    防止工具越权访问项目根目录之外的文件。
    """
    try:
        # resolve() 会展开相对路径（转换成“真实绝对路径”）和 ..，relative_to() 用来确认最终路径仍在 root 内。
        #例如 Path("C:/project/a.txt").relative_to("C:/project")
        #就会得到 Path("a.txt")，否则就会报错
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def list_project_files(project_root: str, max_files: int = 50) -> ToolResult:
    """列出项目目录下的文件，返回相对路径，最多返回 max_files 个。"""
    start = time.time()
    tool_name = "list_project_files"

    try:
        root = Path(project_root)

        if not root.exists():
            return ToolResult(
                tool_name=tool_name,
                status="failed",
                message="项目根目录不存在。",
                error_type="file_not_found",
                elapsed_seconds=round(time.time() - start, 3),
            )

        files = []
        for path in root.rglob("*"):
            if path.is_file():
                # 返回相对路径，避免把调用方不需要的本机绝对路径暴露出去。
                files.append(str(path.relative_to(root)))

            if len(files) >= max_files:
                # 大项目文件很多，限制数量可以避免工具响应过长。
                break

        return ToolResult(
            tool_name=tool_name,
            status="success",
            message=f"已列出项目文件，共返回 {len(files)} 个。",
            data={
                "project_root": str(root),
                "files": files,
                "truncated": len(files) >= max_files, #在返回结果里加一个标记，表示“文件列表是不是被截断了”。
            },
            elapsed_seconds=round(time.time() - start, 3),
        )

    except Exception as e: #如果 try 里面发生错误，就把这个错误捕获下来，并命名为 e
        return ToolResult(
            tool_name=tool_name,
            status="failed",
            message=str(e),
            error_type="tool_exception",
            elapsed_seconds=round(time.time() - start, 3),
        )


def read_text_file(project_root: str, relative_path: str, max_chars: int = 4000) -> ToolResult:
    """读取项目内的文本文件，并按 max_chars 限制返回内容长度。"""
    start = time.time()
    tool_name = "read_text_file"

    try:
        root = Path(project_root)
        target = root / relative_path

        # relative_path 可能包含 ../，读取前必须确认最终路径仍属于项目目录。
        if not _is_path_inside_root(target, root):
            return ToolResult(
                tool_name=tool_name,
                status="blocked",
                message="禁止读取项目根目录之外的文件。",
                error_type="unsafe_operation",
                elapsed_seconds=round(time.time() - start, 3),
            )

        if not target.exists():
            return ToolResult(
                tool_name=tool_name,
                status="failed",
                message="目标文件不存在。",
                error_type="file_not_found",
                elapsed_seconds=round(time.time() - start, 3),
            )

        # errors="replace" 可以让少量非法字符不至于中断整个读取流程。
        text = target.read_text(encoding="utf-8", errors="replace")

        return ToolResult(
            tool_name=tool_name,
            status="success",
            message=f"已读取文件：{relative_path}",
            data={
                "relative_path": relative_path,
                # 只返回前 max_chars 个字符，完整性用 truncated 标记表达。
                "content": text[:max_chars],
                "truncated": len(text) > max_chars,
            },
            elapsed_seconds=round(time.time() - start, 3),
        )

    except Exception as e:
        return ToolResult(
            tool_name=tool_name,
            status="failed",
            message=str(e),
            error_type="tool_exception",
            elapsed_seconds=round(time.time() - start, 3),
        )


def search_text(project_root: str, keyword: str, max_matches: int = 20) -> ToolResult:
    """在常见文本文件中搜索关键字，返回匹配到的文件路径。"""
    start = time.time()
    tool_name = "search_text"

    try:
        root = Path(project_root)

        if not root.exists():
            return ToolResult(
                tool_name=tool_name,
                status="failed",
                message="项目根目录不存在。",
                error_type="file_not_found",
                elapsed_seconds=round(time.time() - start, 3),
            )

        matches = []

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            # 只扫描常见文本格式，避免误读二进制文件或无关文件。
            if path.suffix.lower() not in [".py", ".md", ".txt", ".json", ".yaml", ".yml"]:
                continue

            text = path.read_text(encoding="utf-8", errors="replace")

            # 大小写不敏感搜索，提升自然语言关键字匹配的容错性。
            if keyword.lower() in text.lower():
                matches.append(str(path.relative_to(root)))

            if len(matches) >= max_matches:
                # 命中数量达到上限后提前结束，控制工具输出规模。
                break

        return ToolResult(
            tool_name=tool_name,
            status="success",
            message=f"搜索完成，找到 {len(matches)} 个匹配文件。",
            data={
                "keyword": keyword,
                "matches": matches,
            },
            elapsed_seconds=round(time.time() - start, 3),
        )

    except Exception as e:
        return ToolResult(
            tool_name=tool_name,
            status="failed",
            message=str(e),
            error_type="tool_exception",
            elapsed_seconds=round(time.time() - start, 3),
        )


def read_recent_log(project_root: str, relative_path: str, n_lines: int = 80) -> ToolResult:
    """读取项目内日志文件的最后 n_lines 行，便于快速查看近期日志。"""
    start = time.time()
    tool_name = "read_recent_log"

    try:
        root = Path(project_root)
        target = root / relative_path

        # 日志路径同样来自外部参数，需要复用项目根目录边界检查。
        if not _is_path_inside_root(target, root):
            return ToolResult(
                tool_name=tool_name,
                status="blocked",
                message="禁止读取项目根目录之外的日志文件。",
                error_type="unsafe_operation",
                elapsed_seconds=round(time.time() - start, 3),
            )

        if not target.exists():
            return ToolResult(
                tool_name=tool_name,
                status="failed",
                message="日志文件不存在。",
                error_type="file_not_found",
                elapsed_seconds=round(time.time() - start, 3),
            )

        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()

        return ToolResult(
            tool_name=tool_name,
            status="success",
            message=f"已读取日志最后 {min(n_lines, len(lines))} 行。",
            data={
                "relative_path": relative_path,
                # Python 切片会自动处理 n_lines 大于总行数的情况。
                "recent_lines": lines[-n_lines:],
            },
            elapsed_seconds=round(time.time() - start, 3),
        )

    except Exception as e:
        return ToolResult(
            tool_name=tool_name,
            status="failed",
            message=str(e),
            error_type="tool_exception",
            elapsed_seconds=round(time.time() - start, 3),
        )
