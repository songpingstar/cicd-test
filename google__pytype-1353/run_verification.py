#!/usr/bin/env python3
import subprocess
import sys
import os
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Union, List

# --- 配置 ---
# 请在这里设置你的代码仓库的绝对路径
REPO_PATH = 'pytype'
# 要进行测试的基础 commit 哈希
BASE_COMMIT = '0b797cc8f8127419b0758bef409a9046d54a39bb'
# 实例ID，用于结果文件的顶级键
INSTANCE_ID = 'google__pytype-1353'


# --- 路径配置 (自动计算) ---
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = Path(REPO_PATH)

class Colors:
    """用于在终端中彩色打印的辅助类。"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

# 初始化结果字典
results = {
    INSTANCE_ID: {
        "patch_is_None": False,
        "patch_exists": True,
        "patch_successfully_applied": False,
        "resolved": False,
        "tests_status": {
            "FAIL_TO_PASS": {"success": [], "failure": []},
            "PASS_TO_PASS": {"success": [], "failure": []},
            "FAIL_TO_FAIL": {"success": [], "failure": []},
            "PASS_TO_FAIL": {"success": [], "failure": []}
        }
    }
}

# --- 辅助函数 ---

def print_header(message):
    """打印格式化的标题。"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BLUE}=== {message}{Colors.ENDC}")
    print(f"{Colors.BLUE}{'='*60}{Colors.ENDC}")

def run_command(command, cwd, check=True):
    """运行一个子进程命令并返回结果。
    
    适配 Python 3.6: 使用 stdout=PIPE, stderr=PIPE 替代 capture_output=True,
    使用 universal_newlines=True 替代 text=True。
    """
    try:
        process = subprocess.run(
            command, 
            check=check, 
            stdout=subprocess.PIPE, # 替代 capture_output=True
            stderr=subprocess.PIPE, # 替代 capture_output=True
            universal_newlines=True, # 替代 text=True
            cwd=str(cwd)
        )
        return True, process.stdout, process.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr
    except FileNotFoundError:
        return False, "", f"Command '{command[0]}' not found."

def reset_repo(commit_hash):
    """重置仓库到指定的 commit，并强制清理所有未跟踪的文件。"""
    print_header(f"RESETTING REPO TO COMMIT: {commit_hash[:7]}")
    success, _, stderr = run_command(["git", "reset", "--hard", commit_hash], cwd=REPO_DIR)
    if not success:
        print(f"{Colors.RED}[ERROR] 'git reset --hard' failed.{Colors.ENDC}\n{stderr}")
        return False
    success_clean, _, stderr_clean = run_command(["git", "clean", "-df"], cwd=REPO_DIR)
    if not success_clean:
        print(f"{Colors.RED}[ERROR] 'git clean -df' failed.{Colors.ENDC}\n{stderr}")
        return False
    print(f"{Colors.GREEN}[SUCCESS] Repo has been forcefully reset and cleaned.{Colors.ENDC}")
    return True

def apply_patch(patch_path):
    """直接应用一个补丁文件。"""
    if not patch_path.exists():
        # 替换 ℹ️
        print(f"{Colors.YELLOW}[INFO] Patch file {patch_path.name} not found, skipping.{Colors.ENDC}")
        return True
    print(f"{Colors.YELLOW}   -> Applying patch: {patch_path.name}{Colors.ENDC}")
    success, _, stderr = run_command(["git", "apply", str(patch_path)], cwd=REPO_DIR)
    if not success:
        # 替换 ❌
        print(f"{Colors.RED}[ERROR] Applying patch {patch_path.name} failed.{Colors.ENDC}\n{stderr}")
        return False
    # 替换 ✅
    print(f"{Colors.GREEN}[SUCCESS] Applied patch {patch_path.name} successfully.{Colors.ENDC}")
    return True
    
def get_modified_test_files_from_patch(patch_path: Path) -> List[str]:
    """
    从指定的补丁文件中解析出所有被修改的 .py 文件路径。
    如果文件不存在、读取失败或没有找到 .py 文件，则返回原始的默认测试文件列表。
    """
    # 原始的默认测试文件列表
    DEFAULT_TEST_FILES = ["tests/reference.py", "tests/test_kerns.py", "tests/test_likelihoods.py"]

    if not patch_path.is_file():
        print(f"{Colors.YELLOW}[INFO] Patch file {patch_path.name} not found. Running default tests.{Colors.ENDC}")
        return DEFAULT_TEST_FILES

    modified_files = set()
    try:
        with open(patch_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # 补丁文件头行格式通常是 '--- a/path/to/file' 或 '+++ b/path/to/file'
                if line.startswith('--- a/') or line.startswith('+++ b/'):
                    # 提取路径并去除 'a/' 或 'b/' 前缀
                    path = line.split(' ', 2)[1].strip()
                    if path.startswith('a/') or path.startswith('b/'):
                        path = path[2:]
                    
                    # 仅添加 Python 文件
                    if path.endswith('.py'):
                        modified_files.add(path)
                        
    except Exception as e:
        print(f"{Colors.RED}[ERROR] Failed to read or parse patch file {patch_path}: {e}. Running default tests.{Colors.ENDC}")
        return DEFAULT_TEST_FILES

    file_list = sorted(list(modified_files))
    
    if not file_list:
         print(f"{Colors.YELLOW}[INFO] No Python files found in {patch_path}. Running default tests.{Colors.ENDC}")
         return DEFAULT_TEST_FILES
    
    # 打印运行的文件列表（仅展示前几个）
    print(f"{Colors.BLUE}[INFO] Dynamic test file list generated from {patch_path.name}: {', '.join(file_list[:3])}{'...' if len(file_list) > 3 else ''}{Colors.ENDC}")
    return file_list

def parse_junit_xml_report(report_path: Path) -> Union[dict, None]:
    """解析 JUnit XML 报告并返回一个包含测试结果的字典。"""
    if not report_path.is_file():
        # 保持无 emoji 状态
        print(f"{Colors.RED}   -> FAILED: Pytest did not generate a report file at {report_path}.{Colors.ENDC}")
        return None
        
    test_results = {}
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
        for testcase in root.iter("testcase"):
            class_name = testcase.get("classname", "")
            test_name = testcase.get("name", "")
            
            nodeid = ""
            if class_name:

                if any(c.isupper() for c in class_name):

                    parts = class_name.split('.')
                    module_path_parts = parts[:-1]
                    class_name_only = parts[-1]   
                    
                    # 将模块路径转换为文件路径
                    if module_path_parts:
                        file_path = "/".join(module_path_parts) + ".py"
                    else:
                        file_path = f"{class_name_only}.py"
                        
                    nodeid = f"{file_path}::{class_name_only}::{test_name}"
                else:
                    parts = class_name.split('.')
                    file_path = "/".join(parts) + ".py"
                    nodeid = f"{file_path}::{test_name}"
            else:
                nodeid = test_name

            failure_node = testcase.find("failure")
            error_node = testcase.find("error")
            skipped_node = testcase.find("skipped")

            if failure_node is not None:
                test_results[nodeid] = "failed"
            elif error_node is not None:
                test_results[nodeid] = "error"
            elif skipped_node is None:
                test_results[nodeid] = "passed"
                
    except ET.ParseError as e:
        print(f"{Colors.RED}   -> FAILED: Could not parse the JUnit XML report: {e}{Colors.ENDC}")
        return None
    finally:
        if report_path.exists():
            try:
                report_path.unlink() # 使用 pathlib 的 unlink 方法更现代
            except OSError as e:
                # 替换 ⚠️
                print(f"{Colors.YELLOW}   -> WARNING: Could not delete report file {report_path}: {e}{Colors.ENDC}")

    return test_results

def run_all_tests_and_get_results(test_files: List[str]) -> Union[dict, None]:
    """使用 pytest 运行指定的测试文件列表，并从 JUnit XML 报告中解析结果。"""
    report_file=SCRIPT_DIR/f"report_{os.getpid()}.xml"

    existing_test_files = []
    for file_path_str in test_files:
        repo_file_path = REPO_DIR / file_path_str
        if repo_file_path.is_file():
            existing_test_files.append(file_path_str)

    # 将动态获取的测试文件列表添加到 command 中
    command=["pytest"] + existing_test_files + [f"--junitxml={str(report_file)}"]

    # 打印执行的命令
    print(f"{Colors.BLUE}   -> Executing: pytest {' '.join(test_files)}{Colors.ENDC}")

    run_command(command,cwd=REPO_DIR,check=False)

    results=parse_junit_xml_report(report_file)
    if results is not None:
        print(f"{Colors.GREEN} -> COMPLETED: Parsed {len(results)} test results.{Colors.ENDC}")
    return results

def write_results_and_exit(success=True):
    """将最终结果写入json文件并退出程序。"""
    output_path = SCRIPT_DIR / "results.json"
    print_header("FINAL STEP: WRITING results.json")
    try:
        with open(output_path, "w") as f: json.dump(results, f, indent=4)
        # 替换 ✅
        print(f"{Colors.GREEN}[SUCCESS] Successfully wrote results to {output_path}{Colors.ENDC}")
    except Exception as e:
        # 替换 ❌
        print(f"{Colors.RED}[ERROR] Could not write to {output_path}: {e}{Colors.ENDC}")
    sys.exit(0 if success else 1)

def main():
    global results
    
    # 1. 确定要运行的测试文件列表
    test_patch_path = SCRIPT_DIR / "test.patch"
    test_files_to_run = get_modified_test_files_from_patch(test_patch_path)

    # --- 补丁前运行 ---
    if not reset_repo(BASE_COMMIT): write_results_and_exit(False)
    if not apply_patch(test_patch_path): write_results_and_exit(False)
    
    print_header("STEP 1: PRE-PATCH - Running tests with only test patch")
    # 传递动态生成的测试文件列表
    pre_patch_results = run_all_tests_and_get_results(test_files_to_run)
    if pre_patch_results is None: write_results_and_exit(False)

    # --- 补丁后运行 ---
    if not reset_repo(BASE_COMMIT): write_results_and_exit(False)
    if not apply_patch(test_patch_path): write_results_and_exit(False)
    if not apply_patch(SCRIPT_DIR / "code.patch"): write_results_and_exit(False)
    results[INSTANCE_ID]["patch_successfully_applied"] = True

    print_header("STEP 2: POST-PATCH - Running tests with both patches")
    # 传递动态生成的测试文件列表
    post_patch_results = run_all_tests_and_get_results(test_files_to_run)
    if post_patch_results is None: write_results_and_exit(False)

    # --- 结果分类 ---
    print_header("STEP 3: CATEGORIZING RESULTS")
    all_tests_run = set(pre_patch_results.keys()) | set(post_patch_results.keys())
    
    for test in sorted(list(all_tests_run)):
        pre_status = pre_patch_results.get(test, "passed")
        post_status = post_patch_results.get(test, "failed")

        if pre_status == "failed" and post_status == "passed":
            results[INSTANCE_ID]["tests_status"]["FAIL_TO_PASS"]["success"].append(test)
        elif pre_status == "passed" and post_status == "passed":
            results[INSTANCE_ID]["tests_status"]["PASS_TO_PASS"]["success"].append(test)
        elif pre_status == "failed" and post_status == "failed":
            results[INSTANCE_ID]["tests_status"]["FAIL_TO_FAIL"]["failure"].append(test)
        elif pre_status == "passed" and post_status == "failed":
            results[INSTANCE_ID]["tests_status"]["PASS_TO_FAIL"]["failure"].append(test)
    
    for category, result in results[INSTANCE_ID]["tests_status"].items():
        if result["success"]: print(f"{Colors.GREEN}  [{category}]: {len(result['success'])} tests{Colors.ENDC}")
        if result["failure"]: print(f"{Colors.RED}  [{category}]: {len(result['failure'])} tests{Colors.ENDC}")

    fail_to_fail = results[INSTANCE_ID]["tests_status"]["FAIL_TO_FAIL"]["failure"]
    pass_to_fail = results[INSTANCE_ID]["tests_status"]["PASS_TO_FAIL"]["failure"]
    fail_to_pass = results[INSTANCE_ID]["tests_status"]["FAIL_TO_PASS"]["success"]

    if fail_to_pass and not fail_to_fail and not pass_to_fail:
        results[INSTANCE_ID]["resolved"] = True
        # 替换 🎉🎉🎉
        print(f"\n{Colors.GREEN}=== VERIFICATION SUCCESSFUL! ==={Colors.ENDC}")
        write_results_and_exit(True)
    else:
        # 替换 ❌❌❌
        print(f"\n{Colors.RED}=== VERIFICATION FAILED! ==={Colors.ENDC}")
        # 保持无 emoji 状态
        if not fail_to_pass: print(f"{Colors.YELLOW}  - No tests were fixed.{Colors.ENDC}")
        if fail_to_fail: print(f"{Colors.YELLOW}  - {len(fail_to_fail)} test(s) continued to fail (first 5): {fail_to_fail[:5]}{Colors.ENDC}")
        if pass_to_fail: print(f"{Colors.YELLOW}  - {len(pass_to_fail)} regression(s) detected (first 5): {pass_to_fail[:5]}{Colors.ENDC}")
        write_results_and_exit(False)

if __name__ == "__main__":
    if not REPO_PATH or not REPO_DIR.is_dir() or not (REPO_DIR / '.git').is_dir():
        # Fix UnicodeEncodeError: replacing Chinese characters with ASCII-safe English
        print(f"{Colors.RED}ERROR: Invalid repository path configured!{Colors.ENDC}")
        print(f"{Colors.YELLOW}Please modify the `REPO_PATH` variable at the top of the script.{Colors.ENDC}")
        print(f"{Colors.YELLOW}Current configured path: '{REPO_PATH}'{Colors.ENDC}")
        sys.exit(1)
    
    main()
