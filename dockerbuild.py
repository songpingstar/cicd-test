import os
import json
import re
import docker
import sys
from pathlib import Path

# ==================== 配置区域 ====================
TASKS_DIR = Path(r"疑难杂症\fsspec__filesystem_spec-1141")
IMAGE_NAME_TEMPLATE = "swebench/sweb.eval.x_86_64.{repo_owner}_1776_{repo_name}-{pr_id}"

# 构建选项
FORCE_REBUILD = False  # 是否强制重新构建已存在的镜像
SKIP_EXISTING = True   # 是否跳过已存在的镜像
EXIT_ON_FAILURE = True # 如果为 True，构建失败时立即终止程序


class DockerImageBuilder:
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

    def check_image_exists(self, image_name: str) -> bool:
        """检查 Docker 镜像是否已存在"""
        try:
            self.client.images.get(image_name)
            return True
        except docker.errors.ImageNotFound:
            return False

    def build_image(self, json_file_path: Path, image_name: str, force_rebuild: bool = False):
        """构建 Docker 镜像 (实时输出日志)"""
        
        # 检查镜像是否已存在
        if not force_rebuild and self.check_image_exists(image_name):
            print(f"   ✅ 镜像已存在，跳过构建")
            return True

        if force_rebuild and self.check_image_exists(image_name):
            print(f"   🔄 强制重新构建镜像...")
        else:
            print(f"   🔨 开始构建镜像...")

        source_dir = json_file_path.parent.absolute()

        # 检查必要文件是否存在
        dockerfile_path = source_dir / "Dockerfile"
        if not dockerfile_path.exists():
            print(f"   ❌ 错误: Dockerfile 不存在于 {source_dir}")
            return False

        try:
            print(f"   -> 构建上下文: {source_dir}")
            print(f"   -> Dockerfile: {dockerfile_path}")
            print(f"   -> 镜像名称: {image_name}")
            print("   --- 构建日志 START ---")

            # 使用底层 API (client.api.build) 来获取流式响应
            response = self.client.api.build(
                path=str(source_dir),
                tag=image_name,
                rm=True,
                forcerm=True,
                nocache=force_rebuild,
                decode=True  # 关键：将流解码为 JSON 对象
            )

            build_success = True
            
            # 迭代生成器，实时打印
            for chunk in response:
                if 'stream' in chunk:
                    # stream 中通常自带换行符，所以 end=''，flush=True 确保立即显示
                    print(chunk['stream'], end='', flush=True)
                elif 'error' in chunk:
                    print(f"\n❌ 构建错误: {chunk['error']}")
                    build_success = False
                elif 'errorDetail' in chunk:
                    print(f"\n❌ 错误详情: {chunk['errorDetail']}")
                    build_success = False
                elif 'status' in chunk:
                    # 打印如 Pulling fs layer 等状态信息，可选
                    # print(f"\n>> {chunk['status']}", end='', flush=True)
                    pass

            print("\n   --- 构建日志 END ---")

            if build_success:
                print(f"   ✅ 镜像构建成功: {image_name}")
                return True
            else:
                error_msg = f"❌❌❌ Docker 构建失败: {image_name} ❌❌❌"
                print(f"\n{error_msg}")
                # 如果你想在这里直接抛出异常给上层处理：
                # raise RuntimeError(error_msg) 
                return False

        except docker.errors.APIError as e:
            print(f"   ❌ Docker API 错误: {e}")
            return False
        except Exception as e:
            print(f"   ❌ 构建时发生未知错误: {e}")
            import traceback
            traceback.print_exc()
            return False

    def process_tasks(self, tasks_dir: Path, force_rebuild: bool = False, skip_existing: bool = True):
        """处理任务目录中的所有任务"""
        if not tasks_dir.is_dir():
            print(f"❌ 错误: 任务目录 '{tasks_dir}' 不存在。")
            return

        print(f"\n🔍 开始扫描目录: {tasks_dir}")
        print(f"   强制重建: {'是' if force_rebuild else '否'}")
        print(f"   跳过已存在: {'是' if skip_existing else '否'}")
        
        processed_images = set()
        success_count = 0
        skip_count = 0
        fail_count = 0

        for json_file in tasks_dir.rglob("*.json"):
            # 跳过结果文件
            if json_file.name == "result.json":
                continue
            
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # 检查是否包含 instance_id
                instance_id = data.get("instance_id")
                if not instance_id:
                    continue

                parsed_info = self.parse_instance_id(instance_id)
                if not parsed_info:
                    continue

                # 将 parsed_info 中的 repo_owner 和 repo_name 转换为小写
                parsed_info_lower = {
                    "repo_owner": parsed_info["repo_owner"].lower(),
                    "repo_name": parsed_info["repo_name"].lower(),
                    "pr_id": parsed_info["pr_id"]
                }
                image_name = IMAGE_NAME_TEMPLATE.format(**parsed_info_lower)

                # 避免重复处理同一个镜像
                if image_name in processed_images:
                    continue

                processed_images.add(image_name)
                print(f"\n{'='*60}")
                print(f"镜像: {image_name}")
                print(f"任务: {instance_id}")
                print(f"{'='*60}")

                # 检查镜像是否已存在
                if skip_existing and not force_rebuild and self.check_image_exists(image_name):
                    print(f"   ✅ 镜像已存在，跳过构建")
                    skip_count += 1
                    continue

                # 构建镜像
                if self.build_image(json_file, image_name, force_rebuild):
                    success_count += 1
                else:
                    fail_count += 1
                    if EXIT_ON_FAILURE:
                        print(f"\n🚨 检测到构建失败，且配置为立即终止 (EXIT_ON_FAILURE=True)。")
                        print(f"   失败镜像: {image_name}")
                        print(f"   相关文件: {json_file}")
                        sys.exit(1) # 退出程序

            except json.JSONDecodeError:
                print(f"   -> ⚠️ 跳过无效 JSON 文件: {json_file.name}")
                continue
            except Exception as e:
                print(f"🚨 处理文件 '{json_file}' 时发生错误: {e}")
                import traceback
                traceback.print_exc()
                fail_count += 1

        # 打印统计信息
        print(f"\n{'='*60}")
        print(f"📊 构建统计:")
        print(f"   总计镜像: {len(processed_images)}")
        print(f"   ✅ 成功构建: {success_count}")
        print(f"   ⏭️  跳过: {skip_count}")
        print(f"   ❌ 失败: {fail_count}")
        print(f"{'='*60}")


def build():
    """主函数"""
    print("🐳 Docker 镜像构建工具 (实时输出版)")
    print("="*60)
    
    builder = DockerImageBuilder()
    builder.process_tasks(TASKS_DIR, FORCE_REBUILD, SKIP_EXISTING)


if __name__ == "__main__":
    build()