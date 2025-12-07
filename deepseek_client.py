import os
import requests
import json
from typing import Dict, List, Optional

class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def chat(self, messages: List[Dict], model: str = "deepseek-chat", temperature: float = 0.7) -> str:
        """
        与 DeepSeek API 进行对话
        """
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API 请求错误: {str(e)}")
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"API 响应解析错误: {str(e)}")
    
    def chat_with_context(self, user_message: str, book_context: str = "", chapter_title: str = "") -> str:
        """
        基于书籍上下文与 DeepSeek 对话
        """
        system_prompt = """你是一个专业的阅读助手，帮助用户理解和分析书籍内容。请基于提供的书籍上下文，以专业、有帮助的方式回答用户的问题。"""
        
        context_part = ""
        if book_context:
            context_part = f"\n\n当前阅读内容（{chapter_title}）：\n{book_context}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{user_message}{context_part}"}
        ]
        
        return self.chat(messages)