#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量为语音识别文本添加标点符号的脚本
"""
import re
import os
import sys

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def punctuate_text(text):
    """
    为语音识别文本添加标点符号
    """
    # 按句子分段（按自然的停顿）
    sentences = []

    # 常见的连接词和语气词，这些地方可能需要加逗号
    connectors = [
        '是吧', '对不对', '对吧', '吧', '呢', '啊', '呀', '哎', '诶',
        '然后', '那么', '其实', '可能', '其实', '因为', '所以', '但是',
        '不过', '然后', '接着', '最后', '当然', '当然了', '当然就是',
        '比如说', '比方说', '例如', '比如', '例如'
    ]

    # 分割文本为句子
    lines = text.strip().split('\n')
    current_speaker = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 检查是否是新的讲话人标记
        if line.startswith('1号讲话人') or line.startswith('2号讲话人'):
            current_speaker = line.split()[0]
            continue

        if line.startswith('00:'):
            continue

        # 处理普通文本行
        if line and not line.startswith('1号') and not line.startswith('2号'):
            # 已经有标点的句子直接保留
            if '，' in line or '。' in line or '？' in line or '！' in line:
                sentences.append((current_speaker, line))
            else:
                # 为没有标点的句子添加标点
                punctuated = add_punctuation(line)
                sentences.append((current_speaker, punctuated))

    return format_output(sentences, lines)


def add_punctuation(text):
    """
    添加标点符号到文本
    """
    # 常见的句子结束标记
    text = re.sub(r'([吗啦吧呀])\s*$', r'\1。', text)
    text = re.sub(r'([！])\s*$', r'\1', text)

    # 在连接词前后加逗号
    for conn in ['是吧', '对不对', '对吧', '呢', '呀', '啊']:
        text = re.sub(rf'({conn})', r'，\1', text)

    # 在常见的语气停顿处加逗号
    # 语气词之后或之前加逗号
    text = re.sub(r'(，)([你我他客户它])', r'\2，', text)
    text = re.sub(r'(，)([的得地])', r'\2，', text)

    # 多个空格变成逗号
    text = re.sub(r'\s{2,}', r'，', text)

    # 句子分割：在这些词后面加句号
    split_words = ['明白', '知道', '了解', '了解了', '懂了', 'ok', 'OK', '好吧', '说完']
    for word in split_words:
        text = re.sub(rf'{word}(\s+)', r'\1。', text)

    # 确保结尾有句号
    if not text.endswith('。') and not text.endswith('？') and not text.endswith('！'):
        text = text + '。'

    return text


def format_output(sentences, original_lines):
    """
    格式化输出，保持原有的格式结构
    """
    output = []
    for line in original_lines:
        line = line.strip()
        if not line:
            continue
        elif line.startswith('1号讲话人') or line.startswith('2号讲话人') or line.startswith('3号讲话人'):
            output.append(line)
        elif line.startswith('00:'):
            output.append(line)
        else:
            # 查找对应的句子
            punctuated = add_punctuation(line)
            output.append(punctuated)
    return '\n'.join(output)


def process_file(filepath):
    """
    处理单个文件
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 如果文件已经有标点，跳过
    if '，' in content and '。' in content:
        # 检查标点密度
        comma_count = content.count('，') + content.count('。') + content.count('？') + content.count('！')
        text_length = len(content)
        if comma_count / text_length > 0.01:  # 标点密度超过1%认为已处理
            print(f"Skipping (already punctuated)")
            return

    punctuated = format_output([], content.split('\n'))

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(punctuated)

    print(f"Processed file")


if __name__ == '__main__':
    import glob

    _root = os.path.join(os.path.dirname(__file__), "..")
    doc_dir = os.path.join(_root, "docs", "other-book", "doc")
    md_files = glob.glob(os.path.join(doc_dir, "*.md"))

    for filepath in md_files:
        process_file(filepath)