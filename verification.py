import os
import json
import re
import docker
from pathlib import Path

TASKS_DIR = Path(r"google__pytype-1353")
IMAGE_NAME_TEMPLATE = "swebench/sweb.eval.x86_64.marimo_1776_marimo-7160"


class DockerImageManager:
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
            print("✅ 成功连接到 Docker 服务。")
        except Exception as e:
            print(f"❌ 错误: 无法连接到 Docker 服务。请确保 Docker 正在运行。")
            print(f"   详细信息: {e}")
            exit(1)

    def parse_instance_id(self, instance_id: str) -> dict | None:
        try:
            # 1. 先从【最右边】切一刀，以 '-' 分隔。
            # rsplit('-', 1) 表示从右往左切，只切 1 次。
            # 这样无论 Repo 名字里有多少个 '-'，我们都能精准拿到最后的 PR ID
            repo_part, pr_id = instance_id.rsplit('-', 1)
            
            # 验证切出来的 PR ID 是不是纯数字
            if not pr_id.isdigit():
                raise ValueError("PR ID 不是数字")

            # 2. 再从【最左边】切一刀，以 '__' 分隔。
            # split('__', 1) 表示从左往右切，只切 1 次。
            # 这样无论 Repo 名字里有没有 '__'，我们都认为第一个 '__' 之前的是 Owner
            owner, repo_name = repo_part.split('__', 1)

            return {
                "repo_owner": owner,
                "repo_name": repo_name,
                "pr_id": pr_id,
            }
        except ValueError:
            # 如果分割失败（找不到 '-' 或 '__'），或者解包数量不对，会抛出 ValueError
            print(f"⚠️ 警告: 无法解析 instance_id '{instance_id}'。格式严重不匹配。")
            return None

    def validate_task_data(self, data: dict, filename: str) -> bool:
        """
        校验 JSON 数据字段是否符合要求
        """
        # 1. 定义必须存在的字段
        required_fields = [
            "instance_id",
            "patch",
            "repo",
            "base_commit",
            "hints_text",
            "created_at",
            "test_patch",
            "problem_statement",
            "environment_setup_commit",
            "FAIL_TO_PASS",
            "PASS_TO_PASS",
            "language",
            "content_category",
        ]

        # 2. 定义允许为空的字段 (hints_text, PASS_TO_PASS)
        #    注意：FAIL_TO_PASS 不在这里，说明它不能为空
        allowed_empty_fields = {"hints_text", "PASS_TO_PASS"}

        # --- 基础字段存在性与非空校验 ---
        for field in required_fields:
            if field not in data:
                print(f"   ❌ [校验失败] {filename}: 缺少必须字段 '{field}'")
                return False

            value = data[field]

            # 如果不在允许为空的列表中，则进行非空检查
            if field not in allowed_empty_fields:
                if value is None:
                    print(
                        f"   ❌ [校验失败] {filename}: 字段 '{field}' 不能为空 (None)"
                    )
                    return False
                if isinstance(value, (str, list, dict)) and len(value) == 0:
                    print(
                        f"   ❌ [校验失败] {filename}: 字段 '{field}' 不能为空 (长度为0)"
                    )
                    return False

        # --- Language 校验 ---
        # 允许的值 (全部小写)
        valid_languages = {
            "python",
            "java",
            "typescript",
            "javascript",
            "go",
            "rust",
            "c",
            "c++",
        }

        lang_val = data["language"]
        # 统一转为列表处理 (支持 str 或 list)
        langs_to_check = (
            [lang_val]
            if isinstance(lang_val, str)
            else (lang_val if isinstance(lang_val, list) else [])
        )

        # 再次确认是否有值 (虽然前面非空校验过，但防一手 list 中包含空字符串等情况)
        if not langs_to_check:
            print(f"   ❌ [校验失败] {filename}: language 字段格式无效")
            return False

        for l in langs_to_check:
            if not isinstance(l, str):
                print(f"   ❌ [校验失败] {filename}: language 包含非字符串类型")
                return False
            if l.lower() not in valid_languages:
                print(
                    f"   ❌ [校验失败] {filename}: language '{l}' 无效。允许值: {valid_languages}"
                )
                return False

        # --- Content Category 校验 ---
        # 允许的值
        valid_categories = {
            "计算",
            "通用工具",
            "可视化",
            "系统",
            "时间",
            "网络",
            "加密",
            "其他"
        }

        cat_val = data["content_category"]
        # 统一转为列表处理 (支持 str 或 list)
        cats_to_check = (
            [cat_val]
            if isinstance(cat_val, str)
            else (cat_val if isinstance(cat_val, list) else [])
        )

        if not cats_to_check:
            print(f"   ❌ [校验失败] {filename}: content_category 字段格式无效")
            return False

        for c in cats_to_check:
            if not isinstance(c, str):
                print(f"   ❌ [校验失败] {filename}: content_category 包含非字符串类型")
                return False
            if c not in valid_categories:
                print(
                    f"   ❌ [校验失败] {filename}: content_category '{c}' 无效。允许值: {valid_categories}"
                )
                return False

        return True

    def check_image_exists(self, image_name: str) -> bool:
        try:
            self.client.images.get(image_name)
            return True
        except docker.errors.ImageNotFound:
            return False

    def run_validation(self, json_file_path: Path, image_name: str, instance_id: str):
        """运行验证容器,分别挂载每个文件到容器的 /testbed"""
        print(f"   -> 🚀 开始运行验证: {instance_id}")
        source_dir = json_file_path.parent.absolute()

        print(f"   -> 源目录: {source_dir}")
        print(f"   -> 目录中的文件:")
        for item in source_dir.iterdir():
            print(f"      - {item.name}")

        # 准备要挂载的文件
        files_to_mount = {
            "run_verification.py": source_dir / "run_verification.py",
            "test.patch": source_dir / "test.patch",
            "code.patch": source_dir / "code.patch",
        }

        # 构建 volumes 字典 - 分别挂载每个文件
        volumes = {}
        for target_name, source_path in files_to_mount.items():
            if source_path.exists():
                volumes[str(source_path)] = {
                    "bind": f"/testbed/{target_name}",
                    "mode": "rw",
                }
                print(f"   -> 将挂载: {source_path.name} -> /testbed/{target_name}")
            else:
                print(f"   -> ⚠️ 文件不存在,跳过: {target_name}")

        # 挂载输出目录 - 改为当前任务目录
        output_dir = source_dir
        volumes[str(output_dir)] = {"bind": "/testbed_output", "mode": "rw"}
        print(f"   -> 输出目录挂载: {output_dir} -> /testbed_output")

        result_file_path = output_dir / "result.json"
        if result_file_path.exists():
            try:
                os.remove(result_file_path)
                print(f"   -> 🗑️ 已清理旧的结果文件: {result_file_path.name}")
            except OSError as e:
                print(f"   -> ⚠️ 警告: 无法删除旧结果文件: {e}")
        try:
            print(f"   -> 启动容器 (镜像: {image_name})...")

            container = self.client.containers.run(
                image_name,
                # 关键点：在 -c 前面加上 -i
                command="/bin/bash -i -c 'cd /testbed && python run_verification.py && cp -f results.json /testbed_output/result.json 2>/dev/null || true'",
                volumes=volumes,
                network_mode="none",
                environment={"INSTANCE_ID": instance_id},
                remove=True,
                detach=True,
                # 建议加上 tty=True，防止 bash 抱怨没有终端
                tty=True,
                working_dir="/testbed",
            )
            # 流式日志
            for chunk in container.logs(stream=True, follow=True):
                print(chunk.decode("utf-8", "replace"), end="")

            ret = container.wait()
            exit_code = ret.get("StatusCode", 1)
            print(f"\n[容器退出码] {exit_code}")
            # logs = container.decode("utf-8")
            # print("   --- 容器日志 START ---")
            # print(logs)
            # print("   --- 容器日志 END ---")

            # 检查结果文件
            result_file = output_dir / "result.json"
            if result_file.exists():
                print(f"   -> ✅ 验证完成,结果文件已生成: {result_file}")
            else:
                print(f"   -> ❌ 错误: 容器运行完毕,但未生成结果文件")
                print(f"   -> 目录内容:")
                for item in output_dir.iterdir():
                    print(f"      - {item.name}")

        except docker.errors.ContainerError as e:
            print(f"   -> ❌ 错误: 容器运行异常退出")
            print(f"   -> 退出码: {e.exit_status}")
            print(f"   -> 错误详情: {str(e)}")

        except Exception as e:
            print(f"   -> ❌ 运行容器时发生未知错误: {e}")
            import traceback

            traceback.print_exc()

    def process_tasks(self, tasks_dir: Path):
        if not tasks_dir.is_dir():
            print(f"❌ 错误: 任务目录 '{tasks_dir}' 不存在。")
            return

        print(f"\n🔍 开始扫描目录: {tasks_dir}")
        processed_images = set()

        for json_file in tasks_dir.rglob("*.json"):
            # 1. 读取 JSON
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                print(f"   -> ⚠️ 跳过无效 JSON 文件: {json_file.name}")
                continue
            except Exception as e:
                print(f"🚨 读取文件 '{json_file}' 时发生错误: {e}")
                continue

            # 2. 检查 instance_id 并验证文件名
            instance_id = data.get("instance_id")
            
            # 如果 JSON 中没有 instance_id，或者文件名不等于 "{instance_id}.json"，则跳过
            if not instance_id:
                continue
            
            expected_filename = f"{instance_id}.json"
            if json_file.name != expected_filename:
                continue

            # 3. 文件名匹配成功后，再进行严格的字段格式校验
            if not self.validate_task_data(data, json_file.name):
                # 校验失败，跳过此文件
                continue

            parsed_info = self.parse_instance_id(instance_id)
            if not parsed_info:
                continue
            parsed_info_lower = {
                    "repo_owner": parsed_info["repo_owner"].lower(),
                    "repo_name": parsed_info["repo_name"].lower(),
                    "pr_id": parsed_info["pr_id"]
            }
            image_name = IMAGE_NAME_TEMPLATE.format(**parsed_info_lower)

            if image_name not in processed_images:
                processed_images.add(image_name)
                print(f"\n{'='*60}")
                print(f"镜像: {image_name}")
                print(f"任务: {instance_id}")
                print(f"文件: {json_file.name}")
                print(f"{'='*60}")

                if not self.check_image_exists(image_name):
                    print(f"   ❌ 镜像不存在，跳过此任务")
                    continue

                print(f"   ✅ 镜像已存在")

            # 运行验证
            if self.check_image_exists(image_name):
                self.run_validation(json_file, image_name, instance_id)
            else:
                print(f"   -> ⚠️ 跳过验证: 镜像不存在")

        print(f"\n{'='*60}")
        print(f"✅ 扫描完成,共处理 {len(processed_images)} 个镜像")
        print(f"{'='*60}")


def verify():
    manager = DockerImageManager()
    manager.process_tasks(TASKS_DIR)


if __name__ == "__main__":
    verify()
