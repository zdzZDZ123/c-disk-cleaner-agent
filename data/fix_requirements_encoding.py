with open('requirements.txt', 'rb') as f:
    content = f.read()
try:
    content_utf8 = content.decode('utf-8')
except UnicodeDecodeError:
    content_utf8 = content.decode('gbk', errors='replace')
with open('requirements.txt', 'w', encoding='utf-8') as f:
    f.write(content_utf8)
print("requirements.txt 已转换为 UTF-8 编码。") 