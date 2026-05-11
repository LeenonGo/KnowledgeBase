"""联网搜索 — 封装 SerpAPI 搜索，未配置时返回空结果"""

import os

import requests


def web_search(query: str, num_results: int = 5) -> str:
    """
    使用 SerpAPI 进行互联网搜索。

    Args:
        query: 搜索查询
        num_results: 返回结果数量

    Returns:
        格式化的搜索结果文本，未配置 API Key 时返回提示信息
    """
    api_key = os.getenv("SERP_API_KEY", "")
    if not api_key:
        return "联网搜索未配置（缺少 SERP_API_KEY 环境变量），无法执行搜索。"

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": num_results,
                "hl": "zh-CN",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []

        # 有机搜索结果
        organic = data.get("organic_results", [])
        for item in organic[:num_results]:
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            results.append(f"**{title}**\n{snippet}\n链接: {link}")

        # 知识图谱 / Answer Box
        answer_box = data.get("answer_box", {})
        if answer_box:
            ab_text = answer_box.get("answer", "") or answer_box.get("snippet", "")
            if ab_text:
                results.insert(0, f"**直接答案:** {ab_text}")

        if not results:
            return f"未找到与「{query}」相关的搜索结果。"

        return f"搜索「{query}」的结果：\n\n" + "\n\n".join(results)

    except requests.exceptions.Timeout:
        return "搜索请求超时，请稍后重试。"
    except requests.exceptions.RequestException as e:
        return f"搜索请求失败: {e}"
    except Exception as e:
        return f"搜索处理异常: {e}"
