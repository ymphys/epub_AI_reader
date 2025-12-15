"""
Shared configuration for default AI interactions.
"""

DEFAULT_AI_QUESTION = (
    "请用1-2句话总结当前页面的内容，请按每句话后换行的格式输出，请在最后对专业名词进行解释："
)

# Keep server, cache generator, and UI in sync on context trimming.
MAX_CONTEXT_LENGTH = 10000

# Stored in each processed book folder, next to book.pkl.
DEFAULT_CACHE_FILENAME = "default_ai_cache.json"
