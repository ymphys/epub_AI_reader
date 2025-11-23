"""
Shared configuration for default AI interactions.
"""

DEFAULT_AI_QUESTION = (
    "请用1-3句话总结当前页面的内容，并对其中专业名词进行解释，请按每句话后换行的格式输出："
)

# Keep server, cache generator, and UI in sync on context trimming.
MAX_CONTEXT_LENGTH = 2000

# Stored in each processed book folder, next to book.pkl.
DEFAULT_CACHE_FILENAME = "default_ai_cache.json"
