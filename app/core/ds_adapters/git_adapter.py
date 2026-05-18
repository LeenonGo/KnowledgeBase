"""Git 仓库数据源适配器"""

import os
import hashlib
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# 支持的文件扩展名
DEFAULT_EXTENSIONS = [".md", ".txt", ".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".json", ".rst"]

# Git 临时目录
GIT_TMP_DIR = Path(tempfile.gettempdir()) / "kg_git_sync"


class GitAdapter:
    """Git 仓库适配器"""

    def test_connection(self, config: dict) -> dict:
        """测试 Git 仓库连接"""
        repo_url = config.get("repo_url", "").strip()
        if not repo_url:
            return {"success": False, "message": "仓库地址不能为空"}

        branch = config.get("branch", "main")
        auth_token = config.get("auth_token", "").strip()

        # 构造带 token 的 URL
        clone_url = self._inject_token(repo_url, auth_token)

        # 用 git ls-remote 测试连接（不下载内容）
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--heads", clone_url, branch],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return {"success": True, "message": f"连接成功，分支 {branch} 存在"}
            else:
                # 尝试 master 分支
                if branch == "main":
                    result2 = subprocess.run(
                        ["git", "ls-remote", "--heads", clone_url, "master"],
                        capture_output=True, text=True, timeout=15,
                    )
                    if result2.returncode == 0:
                        return {"success": True, "message": "连接成功，建议使用 master 分支"}
                return {"success": False, "message": f"连接失败: {result.stderr.strip()[:200]}"}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "连接超时（15s）"}
        except FileNotFoundError:
            return {"success": False, "message": "服务器未安装 git 命令"}
        except Exception as e:
            return {"success": False, "message": f"连接异常: {str(e)[:200]}"}

    def list_files(self, config: dict) -> list[dict]:
        """克隆仓库并列出文件"""
        repo_url = config.get("repo_url", "").strip()
        branch = config.get("branch", "main")
        path_prefix = config.get("path", "").strip().strip("/")
        auth_token = config.get("auth_token", "").strip()
        extensions = config.get("file_extensions", DEFAULT_EXTENSIONS)
        source_id = config.get("source_id", "unknown")

        clone_url = self._inject_token(repo_url, auth_token)
        clone_dir = GIT_TMP_DIR / source_id

        # 清理旧目录
        if clone_dir.exists():
            shutil.rmtree(clone_dir, ignore_errors=True)
        GIT_TMP_DIR.mkdir(parents=True, exist_ok=True)

        # 浅克隆
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, "--single-branch",
                 clone_url, str(clone_dir)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone 失败: {result.stderr.strip()[:200]}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("git clone 超时（60s）")

        # 遍历文件
        files = []
        base = clone_dir / path_prefix if path_prefix else clone_dir
        if not base.exists():
            raise RuntimeError(f"目录不存在: {path_prefix}")

        for f in base.rglob("*"):
            if not f.is_file():
                continue
            if extensions and f.suffix.lower() not in extensions:
                continue
            # 跳过隐藏目录（.git 等）
            parts = f.relative_to(clone_dir).parts
            if any(p.startswith(".") for p in parts):
                continue

            stat = f.stat()
            file_hash = self._file_hash(str(f))
            rel_path = str(f.relative_to(clone_dir))

            files.append({
                "path": rel_path,
                "name": f.name,
                "hash": file_hash,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        return files

    def download_file(self, config: dict, file_info: dict, source_id: str = "unknown") -> str:
        """返回已克隆文件的本地路径"""
        clone_dir = GIT_TMP_DIR / source_id
        file_path = clone_dir / file_info["path"]
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_info['path']}")
        return str(file_path)

    def cleanup(self, source_id: str):
        """清理克隆目录"""
        clone_dir = GIT_TMP_DIR / source_id
        if clone_dir.exists():
            shutil.rmtree(clone_dir, ignore_errors=True)

    def get_supported_extensions(self) -> list[str]:
        return DEFAULT_EXTENSIONS

    def _inject_token(self, repo_url: str, auth_token: str) -> str:
        """将 token 注入 HTTPS URL"""
        if not auth_token or not repo_url.startswith("https://"):
            return repo_url
        # https://github.com/org/repo → https://token@github.com/org/repo
        return repo_url.replace("https://", f"https://{auth_token}@", 1)

    def _file_hash(self, file_path: str) -> str:
        """计算文件 SHA-256"""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
