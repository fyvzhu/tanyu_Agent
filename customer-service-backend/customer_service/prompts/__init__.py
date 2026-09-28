"""
Prompt管理模块

使用Jinja2模板管理所有LLM提示词
"""
from __future__ import annotations

from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Prompt文件夹路径
PROMPTS_DIR = Path(__file__).parent

# 创建Jinja2环境
jinja_env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    autoescape=select_autoescape(),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_prompt(template_name: str, **kwargs) -> str:
    """
    渲染prompt模板
    
    Args:
        template_name: 模板文件名（如 "response_generation.jinja2"）
        **kwargs: 模板变量
    
    Returns:
        渲染后的prompt字符串
    """
    template = jinja_env.get_template(template_name)
    return template.render(**kwargs)


__all__ = ["render_prompt", "PROMPTS_DIR"]
