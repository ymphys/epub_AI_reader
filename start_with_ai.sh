#!/bin/bash

# DeepSeek AI 增强版 EPUB 阅读器启动脚本

echo "=== DeepSeek AI 增强版 EPUB 阅读器 ==="
echo ""

# 检查是否设置了 API 密钥
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ 警告: DEEPSEEK_API_KEY 环境变量未设置"
    echo ""
    echo "请先设置您的 DeepSeek API 密钥:"
    echo "export DEEPSEEK_API_KEY=\"your_api_key_here\""
    echo ""
    echo "或者直接在运行前设置:"
    echo "DEEPSEEK_API_KEY=\"your_key\" python server.py"
    echo ""
else
    echo "✅ DeepSeek API 密钥已设置"
fi

echo ""
echo "启动服务器..."
echo "访问地址: http://127.0.0.1:8123"
echo ""

# 检查是否有已处理的书籍
if [ -d "*_data" ]; then
    echo "📚 发现已处理的书籍:"
    for dir in *_data; do
        if [ -d "$dir" ]; then
            echo "  - $dir"
        fi
    done
    echo ""
else
    echo "📖 没有找到已处理的书籍"
    echo "要处理新的 EPUB 文件，请运行:"
    echo "python reader3.py your_book.epub"
    echo ""
fi

# 启动服务器
uv run server.py