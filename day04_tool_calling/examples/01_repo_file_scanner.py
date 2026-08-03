import sys
import json
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(str(DAY_DIR))

from tools.file_tools import list_project_files, read_text_file, search_text


if __name__ == "__main__":
    project_root = ROOT_DIR / "projects" / "agentic_repoops_assistant"

    result_1 = list_project_files(str(project_root))
    print("\n工具 1：list_project_files")
    print(json.dumps(result_1.model_dump(), ensure_ascii=False, indent=2))

    result_2 = read_text_file(str(project_root), "README.md")
    print("\n工具 2：read_text_file")
    print(json.dumps(result_2.model_dump(), ensure_ascii=False, indent=2))

    result_3 = search_text(str(project_root), "Agent")
    print("\n工具 3：search_text")
    print(json.dumps(result_3.model_dump(), ensure_ascii=False, indent=2))